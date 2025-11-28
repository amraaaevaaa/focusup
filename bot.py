import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import BOT_TOKEN
from database import init_db
from handlers import tasks_router, pomodoro_router, stats_router, help_router, kalendar_router, ai_router
from voice_recognition import VoiceRecognizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.include_router(tasks_router)
dp.include_router(pomodoro_router)
dp.include_router(kalendar_router)
dp.include_router(ai_router)
dp.include_router(stats_router)
dp.include_router(help_router)

pending_voice_texts = {}
@dp.message(Command("start"))
async def cmd_start(message):
    from database import add_user
    
    user_internal_id = add_user(
        message.from_user.id, 
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    print(f"🔍 DEBUG: Пользователь {message.from_user.id} -> внутренний ID: {user_internal_id}")
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Задачи"), KeyboardButton(text="🍅 Pomodoro")],
            [KeyboardButton(text="📅 Календарь"), KeyboardButton(text="🤖 AI-помощник")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Помощь")]
        ],
        resize_keyboard=True
    )
    
    start_text = """**FocusUp — система управления задачами**

Управляйте задачами эффективно с помощью AI-анализа.

Выберите раздел:"""

    await message.answer(start_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.message(F.text == "🤖 AI-помощник")
async def ai_main_menu(message):
    from handlers.ai import ai_main_menu as ai_menu
    await ai_menu(message)

@dp.message(F.voice)
async def handle_voice_message(message: Message):
    try:
        await bot.send_chat_action(message.chat.id, "typing")
        
        processing_msg = await message.answer("🎤 Обрабатываю голосовое сообщение...")

        voice_file = await bot.get_file(message.voice.file_id)
        voice_bytes = await bot.download_file(voice_file.file_path)

        voice_recognizer = VoiceRecognizer()
        text = await voice_recognizer.recognize_voice(voice_bytes.read())
        
        if text:
            await processing_msg.delete()

            pending_voice_texts[message.from_user.id] = text

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать задачу", callback_data="voice_create")],
                [InlineKeyboardButton(text="🤖 Отправить в GPT", callback_data="voice_gpt")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="voice_cancel")]
            ])

            await message.answer(f"\n{text}\n\nЧто сделать с этим текстом?", reply_markup=kb)
            
        else:
            await processing_msg.edit_text("❌ Не удалось распознать голосовое сообщение. Попробуйте еще раз.")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}")
        await message.answer("❌ Произошла ошибка при обработке голосового сообщения.")

async def send_to_ai_helper(message: Message, text: str):
    """Отправляет текст в AI без использования FSMContext"""
    try:
        from database import get_user_id, get_user_tasks, get_user_stats
        from ai_helper import ai_assistant
        from handlers.ai import _normalize_ai_response, _plain_ai_text
        
        await message.answer("🤖 Думаю...")
        
        user_internal_id = get_user_id(message.from_user.id)
        user_context = None
        
        if user_internal_id:
            tasks = get_user_tasks(user_internal_id)
            stats = get_user_stats(user_internal_id)
            user_context = f"Задач всего: {len(tasks)}, активных: {stats['active_tasks']}, выполнено: {stats['completed_tasks']}"

        response = await ai_assistant.generate_response(text, user_context)
        
        formatted_response = _normalize_ai_response(response)
        formatted_response = _plain_ai_text(formatted_response)
        
        if not formatted_response or formatted_response.strip() == "":
            formatted_response = "Извините, не удалось получить ответ от AI. Попробуйте ещё раз."
        
        await message.answer(formatted_response)
        
    except Exception as e:
        logger.error(f"Ошибка при отправке в AI: {e}")
        await message.answer("Извините, произошла ошибка при обработке вашего сообщения. Попробуйте ещё раз.")

async def process_text_command(message: Message, text: str):
    task_created = await try_create_task_from_text(message, text)
        
    if not task_created:
        await send_to_ai_helper(message, text)


@dp.callback_query(F.data == "voice_create")
async def voice_create_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    text = pending_voice_texts.pop(user_id, None)
    await callback.answer()

    if not text:
        await callback.message.answer("ℹ️ Нет распознанного текста для обработки.")
        return

    class MockMessage:
        def __init__(self, user, chat):
            self.from_user = user
            self.chat = chat
            
        async def answer(self, text, **kwargs):
            await callback.message.answer(text, **kwargs)
    
    mock_message = MockMessage(callback.from_user, callback.message.chat)
    created = await try_create_task_from_text(mock_message, text)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if not created:
        await send_to_ai_helper(mock_message, text)


@dp.callback_query(F.data == "voice_gpt")
async def voice_gpt_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    text = pending_voice_texts.pop(user_id, None)
    await callback.answer()

    if not text:
        await callback.message.answer("ℹ️ Нет распознанного текста для отправки в GPT.")
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    class MockMessage:
        def __init__(self, user, chat):
            self.from_user = user
            self.chat = chat
            
        async def answer(self, text, **kwargs):
            await callback.message.answer(text, **kwargs)
    
    mock_message = MockMessage(callback.from_user, callback.message.chat)
    await send_to_ai_helper(mock_message, text)


@dp.callback_query(F.data == "voice_cancel")
async def voice_cancel_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    _ = pending_voice_texts.pop(user_id, None)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ Отменено.")

async def try_create_task_from_text(message: Message, text: str) -> bool:
    import re
    from datetime import datetime, timedelta
    from database import add_user, get_user_id, add_task, get_user_tasks
    
    try:
        add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name
        )
        
        user_internal_id = get_user_id(message.from_user.id)
        if not user_internal_id:
            return False
            
        clean_text = re.sub(r'^🎤\s*Распознанный текст:\s*', '', text, flags=re.IGNORECASE).strip()
        text_lower = clean_text.lower()
        
        time_patterns = [
            r'(\d{1,2})\s*час[аов]*\s*(вечера|утра|дня|ночи)',  # "5 часов вечера"
            r'в\s*(\d{1,2})\s*час[аов]*\s*(вечера|утра|дня|ночи)',  # "в 5 часов вечера"
            r'в (\d{1,2})[:\.](\d{2})',  # "в 17:00"
            r'в (\d{1,2})',              # "в 17"
            r'(\d{1,2})[:\.](\d{2})',    # "17:00"
        ]
        
        date_patterns = [
            r'сегодня',
            r'завтра',
            r'послезавтра',
            r'(\d{1,2})\.(\d{1,2})',   
            r'(\d{1,2}) (января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        ]
        
        target_date = datetime.now().date()
        deadline_time = None
        
        if 'завтра' in text_lower:
            target_date = (datetime.now() + timedelta(days=1)).date()
        elif 'послезавтра' in text_lower:
            target_date = (datetime.now() + timedelta(days=2)).date()
            
        # Ищем время с улучшенной логикой
        for pattern in time_patterns:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                
                # Обработка времени с "вечера/утра/дня/ночи"
                if len(groups) == 2 and groups[1] in ['вечера', 'утра', 'дня', 'ночи']:
                    hour = int(groups[0])
                    time_period = groups[1]
                    
                    # Конвертируем в 24-часовой формат
                    if time_period == 'утра':
                        if hour == 12:
                            hour = 0
                        elif hour > 12:
                            continue  # Некорректное время
                    elif time_period == 'дня':
                        if hour < 12:
                            hour += 12
                        elif hour == 12:
                            pass  # 12 дня = 12:00
                        else:
                            continue  # Некорректное время
                    elif time_period == 'вечера':
                        if hour < 12:
                            hour += 12
                        elif hour == 12:
                            pass  # 12 вечера = 12:00 (но это странно, обычно говорят "12 ночи")
                        else:
                            continue  # Некорректное время
                    elif time_period == 'ночи':
                        if hour == 12:
                            hour = 0  # 12 ночи = 00:00
                        elif hour > 12:
                            continue  # Некорректное время
                    
                    if 0 <= hour <= 23:
                        deadline_time = f"{hour:02d}:00"
                        break
                        
                # Обработка обычного формата времени
                elif len(groups) >= 2 and groups[1].isdigit():
                    hour, minute = int(groups[0]), int(groups[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        deadline_time = f"{hour:02d}:{minute:02d}"
                        break
                elif len(groups) == 1:
                    hour = int(groups[0])
                    if 0 <= hour <= 23:
                        deadline_time = f"{hour:02d}:00"
                        break
        

        deadline_str = None
        if deadline_time:
            deadline_str = f"{target_date.strftime('%d.%m.%y')} {deadline_time}"
        elif 'сегодня' in text_lower or 'завтра' in text_lower or 'послезавтра' in text_lower:
            deadline_str = target_date.strftime('%d.%m.%y')
            
        task_title = clean_text

        phrases_to_remove = [
            r'\bсегодня\s*в\s*\d{1,2}\s*час[аов]*\s*(вечера|утра|дня|ночи)\b',  # "сегодня в 5 часов вечера"
            r'\bзавтра\s*в\s*\d{1,2}\s*час[аов]*\s*(вечера|утра|дня|ночи)\b',   # "завтра в 5 часов вечера"
            r'\bв\s*\d{1,2}\s*час[аов]*\s*(вечера|утра|дня|ночи)\b',            # "в 5 часов вечера"
            r'\b\d{1,2}\s*час[аов]*\s*(вечера|утра|дня|ночи)\b',                # "5 часов вечера"
            r'\bсегодня\s*в\s*\d{1,2}[:\.]?\d{0,2}\b',  
            r'\bзавтра\s*в\s*\d{1,2}[:\.]?\d{0,2}\b', 
            r'\bв\s*\d{1,2}[:\.]?\d{0,2}\b',          
            r'\b\d{1,2}[:\.]?\d{0,2}\s*часов?\b',     
            r'\bсегодня\b', r'\bзавтра\b', r'\bпослезавтра\b'
        ]
        
        try:
            from ai_helper import ai_assistant
            logger.info(f"🔍 DEBUG: Генерируем название через GPT для текста: '{clean_text}'")
            gpt_title = await ai_assistant.generate_task_title(clean_text)
            
            if gpt_title and len(gpt_title.strip()) >= 3:
                task_title = gpt_title.strip()
                logger.info(f"✅ GPT создал название: '{task_title}'")
            else:
                logger.info("⚠️ GPT не смог создать название, используем fallback логику")
                
                for phrase in phrases_to_remove:
                    task_title = re.sub(phrase, '', task_title, flags=re.IGNORECASE).strip()
                
                task_title = re.sub(r'\s+', ' ', task_title).strip()
                task_title = re.sub(r'^[,\.\-\s]+|[,\.\-\s]+$', '', task_title).strip()
                
                if len(task_title) < 3:
                    if 'встреча' in text_lower:
                        task_title = "Встреча"
                    elif 'собрание' in text_lower:
                        task_title = "Собрание" 
                    elif 'звонок' in text_lower:
                        task_title = "Звонок"
                    elif 'дело' in text_lower:
                        task_title = "Важное дело"
                    else:
                        task_title = "Новая задача"
                
                if len(task_title) > 30:
                    task_title = task_title[:27] + "..."
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации названия через GPT: {e}")
            for phrase in phrases_to_remove:
                task_title = re.sub(phrase, '', task_title, flags=re.IGNORECASE).strip()
            
            task_title = re.sub(r'\s+', ' ', task_title).strip()
            task_title = re.sub(r'^[,\.\-\s]+|[,\.\-\s]+$', '', task_title).strip()
            
            if len(task_title) < 3:
                task_title = "Новая задача"
            
            if len(task_title) > 30:
                task_title = task_title[:27] + "..."
            
        category = "Общие"
        if any(word in text_lower for word in ["встреча", "собрание", "звонок", "разговор"]):
            category = "Встречи"
        elif any(word in text_lower for word in ["работа", "проект", "задача", "дело"]):
            category = "Работа"
        elif any(word in text_lower for word in ["учеба", "экзамен", "лекция", "урок"]):
            category = "Учеба"
        elif any(word in text_lower for word in ["покупки", "магазин", "купить"]):
            category = "Покупки"
        elif any(word in text_lower for word in ["спорт", "тренировка", "зал"]):
            category = "Спорт"
            
        logger.info(f"🔍 DEBUG: Пытаемся создать задачу - title='{task_title}', category='{category}', deadline='{deadline_str}'")
        
        task_id = add_task(
            user_id=user_internal_id,
            title=task_title,
            category=category,
            deadline=deadline_str,
            tags="голосовая"
        )
        
        logger.info(f"🔍 DEBUG: Результат создания задачи - task_id={task_id}")
        
        if task_id:
            success_msg = f"✅ **Задача создана!**\n\n"
            success_msg += f"📝 **Название:** {task_title}\n"
            success_msg += f"📁 **Категория:** {category}\n"
            
            if deadline_str:
                success_msg += f"📅 **Дедлайн:** {deadline_str}\n"
            
            success_msg += f"🏷️ **Теги:** голосовая\n"

            
            await message.answer(success_msg, parse_mode="Markdown")
            
            tasks_after = get_user_tasks(user_internal_id)
            logger.info(f"🔍 DEBUG: Задач у пользователя после создания: {len(tasks_after)}")
            
            return True
        else:
            logger.error("❌ add_task вернула None или 0")
            await message.answer("❌ Не удалось создать задачу. Проверьте логи.")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при создании задачи из текста: {e}")
        
    return False
async def main():
    init_db()
    logger.info("🚀 FocusUp Bot запускается...")
    
    try:
        await dp.start_polling(bot)
        logger.info("✅ Бот успешно запущен!")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")