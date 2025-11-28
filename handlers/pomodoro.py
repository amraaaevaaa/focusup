from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime, timedelta
import asyncio
import random
import tempfile
import os
from database import add_pomodoro_session
from gif_creator import gif_creator
router = Router()
active_timers = {}
POMODORO_GIFs = {
    'work': 'https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif',
    'break': 'https://media.giphy.com/media/3o7aD2saQhR4kbbQDu/giphy.gif',
    'long_break': 'https://media.giphy.com/media/26AHPxxnSw1L9T1rW/giphy.gif'
}
async def create_and_send_timer_gif(duration, session_type):

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gif') as tmp_file:
            gif_path = tmp_file.name
       
        preview_seconds = min(30, duration)
        gif_creator.create_timer_gif(preview_seconds, session_type, gif_path)
       
        with open(gif_path, 'rb') as gif_file:
            gif_data = gif_file.read()
       
        os.unlink(gif_path)
       
        return types.BufferedInputFile(gif_data, filename="pomodoro_timer.gif")
       
    except Exception as e:
        print(f"Ошибка создания GIF: {e}")
        return None
def create_initial_caption(session_type, duration):

    session_names = {
        'work': 'Работа',
        'break': 'Короткий перерыв',
        'long_break': 'Длинный отдых'
    }
   
    return (f"🍅 **{session_names[session_type]} сессия началась!**\n\n"
           f"⏰ Длительность: {duration // 60} минут\n"
           f"🎬 Запускаем таймер...")
@router.message(F.text == "🍅 Pomodoro")
async def pomodoro_menu(message: types.Message):
    # Получаем статистику пользователя
    from database import get_user_id, get_user_stats
    user_internal_id = get_user_id(message.from_user.id)
    stats_text = ""
    
    if user_internal_id:
        stats = get_user_stats(user_internal_id)
        pomodoro_count = stats.get('pomodoro_sessions', 0)
        if pomodoro_count > 0:
            stats_text = f"\n📊 Сегодня завершено: {pomodoro_count} сессий"

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏱️ 25 мин Работа", callback_data="pomo_start_work"),
                types.InlineKeyboardButton(text="☕ 5 мин Отдых", callback_data="pomo_start_break")
            ],
            [
                types.InlineKeyboardButton(text="🌴 15 мин Длинный отдых", callback_data="pomo_start_long_break"),
                types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="pomo_settings")
            ],
            [
                types.InlineKeyboardButton(text="📊 Моя статистика", callback_data="pomo_stats"),
                types.InlineKeyboardButton(text="🔄 Автопоследовательность", callback_data="pomo_auto")
            ]
        ]
    )
   
    await message.answer(
        f"🍅 **Pomodoro Таймер**\n\n"
        f"Выберите тип сессии:\n"
        f"• ⏱️ 25 мин - Фокусировка на работе\n"
        f"• ☕ 5 мин - Короткий перерыв\n"
        f"• 🌴 15 мин - Длинный перерыв{stats_text}\n\n"
        f"💡 Классический Pomodoro: 25 мин работы → 5 мин отдыха",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
@router.callback_query(F.data.startswith("pomo_start_"))
async def start_pomodoro(callback: types.CallbackQuery):

    user_id = callback.from_user.id
   
    if user_id in active_timers:
        await stop_pomodoro(user_id)
   
    session_type = callback.data.replace("pomo_start_", "")
   
    if session_type == "work":
        duration = 25 * 60
        session_name = "Работа"
    elif session_type == "break":
        duration = 5 * 60
        session_name = "Короткий перерыв"
    else:
        duration = 15 * 60
        session_name = "Длинный перерыв"
   
    gif_file = await create_and_send_timer_gif(duration, session_type)
   
    if gif_file:
        initial_message = await callback.message.answer_animation(
            animation=gif_file,
            caption=create_initial_caption(session_type, duration),
            reply_markup=create_active_timer_buttons(session_type)
        )
    else:
        initial_message = await callback.message.answer(
            create_initial_caption(session_type, duration),
            reply_markup=create_active_timer_buttons(session_type)
        )
   
    active_timers[user_id] = {
        'task': asyncio.create_task(pomodoro_timer_seconds(user_id, duration, session_type, initial_message)),
        'start_time': datetime.now(),
        'duration': duration,
        'message_id': initial_message.message_id,
        'chat_id': initial_message.chat.id,
        'session_type': session_type,
        'paused': False,
        'remaining_seconds': duration
    }
   
    await callback.answer(f"🍅 {session_name} сессия запущена!")
async def pomodoro_timer_seconds(user_id, duration, session_type, message):

    try:
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration)
       
        while datetime.now() < end_time:
            await asyncio.sleep(1)
           
            if user_id not in active_timers:
                break
               
            if active_timers[user_id]['paused']:
                continue
               
            current_time = datetime.now()
            elapsed = current_time - start_time
            remaining = end_time - current_time
           
            active_timers[user_id]['remaining_seconds'] = int(remaining.total_seconds())
           
            elapsed_str = format_time_with_seconds(elapsed.seconds)
            remaining_str = format_time_with_seconds(remaining.seconds)
           
            progress = create_progress_bar(elapsed.seconds, duration)
           
            caption = create_timer_caption(session_type, elapsed_str, remaining_str, progress)
           
            try:
                await message.edit_caption(
                    caption=caption,
                    reply_markup=create_active_timer_buttons(session_type)
                )
            except Exception as e:
                continue
       
        if user_id in active_timers and not active_timers[user_id]['paused']:
            await pomodoro_finished(user_id, session_type, message)
           
    except asyncio.CancelledError:
        print("Таймер отменен")
    except Exception as e:
        print(f"Ошибка в таймере: {e}")
def create_active_timer_buttons(session_type):

    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏸️ Пауза", callback_data="pomo_pause"),
                types.InlineKeyboardButton(text="⏹️ Остановить", callback_data="pomo_stop")
            ],
            [
                types.InlineKeyboardButton(text="🔄 Главное меню", callback_data="pomo_menu")
            ]
        ]
    )
def create_paused_timer_buttons(session_type):

    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="▶️ Возобновить", callback_data="pomo_resume"),
                types.InlineKeyboardButton(text="⏹️ Завершить", callback_data="pomo_stop")
            ],
            [
                types.InlineKeyboardButton(text="☕ Быстрый отдых", callback_data="pomo_start_break"),
                types.InlineKeyboardButton(text="🌴 Длинный отдых", callback_data="pomo_start_long_break")
            ],
            [
                types.InlineKeyboardButton(text="🔄 Главное меню", callback_data="pomo_menu")
            ]
        ]
    )
def create_stopped_timer_buttons():

    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏱️ Новая работа", callback_data="pomo_start_work"),
                types.InlineKeyboardButton(text="☕ Отдых", callback_data="pomo_start_break")
            ],
            [
                types.InlineKeyboardButton(text="🌴 Длинный отдых", callback_data="pomo_start_long_break"),
                types.InlineKeyboardButton(text="🔄 Главное меню", callback_data="pomo_menu")
            ]
        ]
    )
@router.callback_query(F.data == "pomo_pause")
async def pause_pomodoro(callback: types.CallbackQuery):

    user_id = callback.from_user.id
   
    if user_id in active_timers and not active_timers[user_id]['paused']:
        active_timers[user_id]['paused'] = True
       
        remaining = active_timers[user_id]['remaining_seconds']
        minutes = remaining // 60
        seconds = remaining % 60
       
        session_names = {
            'work': 'Работа',
            'break': 'Короткий перерыв',
            'long_break': 'Длинный перерыв'
        }
       
        await callback.message.edit_caption(
            caption=f"⏸️ **{session_names[active_timers[user_id]['session_type']]} сессия на паузе**\n\n"
                   f"⏰ Осталось: {minutes:02d}:{seconds:02d}\n\n"
                   f"Выберите действие:",
            reply_markup=create_paused_timer_buttons(active_timers[user_id]['session_type'])
        )
       
        await callback.answer("⏸️ Сессия поставлена на паузу")
@router.callback_query(F.data == "pomo_resume")
async def resume_pomodoro(callback: types.CallbackQuery):

    user_id = callback.from_user.id
   
    if user_id in active_timers and active_timers[user_id]['paused']:
        active_timers[user_id]['paused'] = False
       
        remaining = active_timers[user_id]['remaining_seconds']
        minutes = remaining // 60
        seconds = remaining % 60
       
        session_names = {
            'work': 'Работа',
            'break': 'Короткий перерыв',
            'long_break': 'Длинный перерыв'
        }
       
        await callback.message.edit_caption(
            caption=f"▶️ **{session_names[active_timers[user_id]['session_type']]} сессия возобновлена!**\n\n"
                   f"⏰ Осталось: {minutes:02d}:{seconds:02d}\n\n"
                   f"Продолжаем работу! 💪",
            reply_markup=create_active_timer_buttons(active_timers[user_id]['session_type'])
        )
       
        await callback.answer("▶️ Сессия возобновлена")
@router.callback_query(F.data == "pomo_stop")
async def stop_pomodoro_handler(callback: types.CallbackQuery):

    user_id = callback.from_user.id
   
    if user_id in active_timers:
        session_type = active_timers[user_id]['session_type']
        remaining = active_timers[user_id]['remaining_seconds']
        minutes_used = (active_timers[user_id]['duration'] - remaining) // 60
       
        await stop_pomodoro(user_id)
       
        session_names = {
            'work': 'Работа',
            'break': 'Короткий перерыв',
            'long_break': 'Длинный перерыв'
        }
       
        await callback.message.edit_caption(
            caption=f"⏹️ **{session_names[session_type]} сессия остановлена**\n\n"
                   f"⏱️ Вы поработали: {minutes_used} минут\n"
                   f"💪 Хорошая попытка!\n\n"
                   f"Выберите следующее действие:",
            reply_markup=create_stopped_timer_buttons()
        )
       
        await callback.answer("⏹️ Сессия остановлена")
# Удалена старая функция back_to_menu - заменена на show_pomodoro_menu
async def stop_pomodoro(user_id):

    if user_id in active_timers:
        if not active_timers[user_id]['task'].done():
            active_timers[user_id]['task'].cancel()
        del active_timers[user_id]
def format_time_with_seconds(total_seconds):

    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"
def create_progress_bar(elapsed, total):

    width = 15
    progress = min(1.0, elapsed / total)
    filled = int(width * progress)
    bar = "█" * filled + "▒" * (width - filled)
    percentage = int(progress * 100)
    return f"[{bar}] {percentage}%"
def create_timer_caption(session_type, elapsed, remaining, progress):

    session_names = {
        'work': 'Работа 🎯',
        'break': 'Короткий перерыв ☕',
        'long_break': 'Длинный перерыв 🌴'
    }
   
    time_emoji = "⏰"
    remaining_seconds = int(remaining.split(':')[0]) * 60 + int(remaining.split(':')[1])
    if remaining_seconds < 60:
        time_emoji = "⚡"
    elif remaining_seconds < 300:
        time_emoji = "🔜"
   
    return (f"🍅 **{session_names[session_type]}**\n\n"
            f"🕐 Прошло: {elapsed}\n"
            f"{time_emoji} Осталось: {remaining}\n"
            f"{progress}\n\n"
            f"{get_motivational_quote(remaining_seconds)}")
def get_motivational_quote(remaining_seconds):
    """Улучшенные мотивационные сообщения"""
    if remaining_seconds < 60:
        quotes = [
            "Почти готово! 🏁", 
            "Последние секунды! ⚡", 
            "Ты у цели! 🎯",
            "Финишная прямая! 🚀",
            "Ещё чуть-чуть! 💪"
        ]
    elif remaining_seconds < 300:
        quotes = [
            "Осталось совсем немного! 🔜", 
            "Продолжай в том же духе! 🔥",
            "Ты на правильном пути! ⭐",
            "Концентрация на максимуме! 🎯",
            "Отличная работа! 👏"
        ]
    else:
        quotes = [
            "Ты справишься! 💪", 
            "Сосредоточься на цели! 🎯", 
            "Держи темп! 🚀",
            "Твоё время - твоя сила! ⚡",
            "Каждая минута важна! ⏰",
            "Фокус - ключ к успеху! 🗝️",
            "Ты можешь больше! 🌟",
            "Продуктивность в действии! 🔥"
        ]
    return random.choice(quotes)
async def pomodoro_finished(user_id, session_type, message):
    """Обработчик завершения Pomodoro сессии с поддержкой автоцикла"""
    try:
        timer_info = active_timers[user_id]
        duration = timer_info['duration']
        from database import get_user_id
        user_internal_id = get_user_id(user_id)
        if user_internal_id:
            add_pomodoro_session(user_internal_id, duration)
       
        session_names = {
            'work': 'Работа',
            'break': 'Короткий перерыв',
            'long_break': 'Длинный перерыв'
        }
        
        # Проверяем, это автоцикл или обычная сессия
        is_auto_cycle = timer_info.get('auto_cycle', False)
        
        if is_auto_cycle:
            # Логика автоцикла
            current_step = timer_info.get('cycle_step', 1)
            total_steps = timer_info.get('total_steps', 8)
            
            if current_step < total_steps:
                # Переходим к следующему шагу
                await start_next_auto_step(user_id, current_step + 1, message)
            else:
                # Автоцикл завершён
                await message.edit_caption(
                    caption=f"� **Автоцикл Pomodoro завершён!**\n\n"
                           f"�🎉 Поздравляем! Вы прошли полный цикл:\n"
                           f"• 4 рабочих сессии (100 минут)\n"
                           f"• 3 коротких перерыва (15 минут)\n"
                           f"• 1 длинный отдых (15 минут)\n\n"
                           f"⏰ Общее время: 2 часа 10 минут\n"
                           f"💪 Отличная работа!",
                    reply_markup=create_stopped_timer_buttons()
                )
                if user_id in active_timers:
                    del active_timers[user_id]
        else:
            # Обычная сессия
            await message.edit_caption(
                caption=f"🎉 **{session_names[session_type]} сессия завершена!**\n\n"
                       f"✅ Отличная работа!\n"
                       f"⏱️ Время: {duration // 60} минут\n\n"
                       f"Выберите следующее действие:",
                reply_markup=create_stopped_timer_buttons()
            )
            if user_id in active_timers:
                del active_timers[user_id]
       
    except Exception as e:
        print(f"Ошибка при завершении: {e}")
        if user_id in active_timers:
            del active_timers[user_id]

async def start_next_auto_step(user_id, step, message):
    """Запуск следующего шага в автоцикле"""
    try:
        # Определяем параметры для следующего шага
        if step in [1, 3, 5, 7]:  # Рабочие сессии
            session_type = "work"
            duration = 25 * 60
            session_name = "Работа"
        elif step in [2, 4, 6]:   # Короткие перерывы
            session_type = "break"
            duration = 5 * 60
            session_name = "Короткий перерыв"
        else:  # step == 8, длинный перерыв
            session_type = "long_break"
            duration = 15 * 60
            session_name = "Длинный перерыв"
        
        # Показываем промежуточное сообщение
        await message.edit_caption(
            caption=f"✅ Сессия {step-1}/8 завершена!\n\n"
                   f"🔄 Переходим к следующему этапу:\n"
                   f"📍 Сессия {step}/8: {session_name}\n"
                   f"⏰ Длительность: {duration // 60} минут\n\n"
                   f"Готовы продолжить?",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text="▶️ Продолжить", callback_data=f"auto_continue_{step}"),
                        types.InlineKeyboardButton(text="⏹️ Остановить", callback_data="pomo_stop")
                    ]
                ]
            )
        )
        
        # Обновляем информацию о таймере
        active_timers[user_id]['cycle_step'] = step
        active_timers[user_id]['next_session_type'] = session_type
        active_timers[user_id]['next_duration'] = duration
        
    except Exception as e:
        print(f"Ошибка в автоцикле: {e}")

@router.callback_query(F.data.startswith("auto_continue_"))
async def continue_auto_cycle(callback: types.CallbackQuery):
    """Продолжение автоцикла"""
    user_id = callback.from_user.id
    step = int(callback.data.replace("auto_continue_", ""))
    
    if user_id not in active_timers:
        await callback.answer("❌ Автоцикл не найден")
        return
    
    timer_info = active_timers[user_id]
    session_type = timer_info['next_session_type']
    duration = timer_info['next_duration']
    
    session_names = {
        'work': 'Работа',
        'break': 'Короткий перерыв', 
        'long_break': 'Длинный перерыв'
    }
    
    # Запускаем новую сессию
    gif_file = await create_and_send_timer_gif(duration, session_type)
   
    initial_caption = (
        f"🔄 **Автоцикл Pomodoro**\n\n"
        f"📍 Сессия {step}/8: {session_names[session_type]}\n"
        f"⏰ Длительность: {duration // 60} минут\n"
        f"🎬 Запускаем сессию..."
    )
    
    if gif_file:
        new_message = await callback.message.answer_animation(
            animation=gif_file,
            caption=initial_caption,
            reply_markup=create_active_timer_buttons(session_type)
        )
    else:
        new_message = await callback.message.answer(
            initial_caption,
            reply_markup=create_active_timer_buttons(session_type)
        )
   
    # Обновляем активный таймер
    active_timers[user_id].update({
        'task': asyncio.create_task(pomodoro_timer_seconds(user_id, duration, session_type, new_message)),
        'start_time': datetime.now(),
        'duration': duration,
        'message_id': new_message.message_id,
        'chat_id': new_message.chat.id,
        'session_type': session_type,
        'paused': False,
        'remaining_seconds': duration,
        'cycle_step': step
    })
   
    await callback.answer(f"▶️ Продолжаем: {session_names[session_type]}")

# Новые улучшенные функции
@router.callback_query(F.data == "pomo_settings")
async def pomodoro_settings(callback: types.CallbackQuery):
    """Настройки Pomodoro таймера"""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏱️ 15 мин Работа", callback_data="pomo_start_work_15"),
                types.InlineKeyboardButton(text="⏱️ 30 мин Работа", callback_data="pomo_start_work_30")
            ],
            [
                types.InlineKeyboardButton(text="⏱️ 45 мин Работа", callback_data="pomo_start_work_45"),
                types.InlineKeyboardButton(text="⏱️ 50 мин Работа", callback_data="pomo_start_work_50")
            ],
            [
                types.InlineKeyboardButton(text="☕ 3 мин Отдых", callback_data="pomo_start_break_3"),
                types.InlineKeyboardButton(text="☕ 10 мин Отдых", callback_data="pomo_start_break_10")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="pomo_menu")
            ]
        ]
    )
    
    await callback.message.edit_text(
        "⚙️ **Настройки Pomodoro**\n\n"
        "Выберите альтернативные интервалы:\n\n"
        "📚 **Для учебы:**\n"
        "• 15 мин - короткие сессии\n"
        "• 30 мин - средние сессии\n\n"
        "💼 **Для глубокой работы:**\n"
        "• 45 мин - длинные сессии\n"  
        "• 50 мин - марафон фокуса\n\n"
        "☕ **Отдых по настроению:**\n"
        "• 3 мин - быстрый отдых\n"
        "• 10 мин - основательный отдых",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "pomo_stats")
async def pomodoro_statistics(callback: types.CallbackQuery):
    """Статистика Pomodoro сессий"""
    from database import get_user_id, get_user_stats
    user_internal_id = get_user_id(callback.from_user.id)
    
    if not user_internal_id:
        await callback.answer("❌ Ошибка получения данных пользователя")
        return
        
    stats = get_user_stats(user_internal_id)
    pomodoro_count = stats.get('pomodoro_sessions', 0)
    completed_tasks = stats.get('completed_tasks', 0)
    
    # Расчёт времени в часах (25 мин на сессию)
    total_minutes = pomodoro_count * 25
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    # Уровень продуктивности
    if pomodoro_count >= 20:
        level = "🏆 Мастер продуктивности"
    elif pomodoro_count >= 10:
        level = "🔥 Продуктивный"
    elif pomodoro_count >= 5:
        level = "⭐ Начинающий"
    else:
        level = "🌱 Новичок"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="pomo_menu")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"📊 **Ваша статистика Pomodoro**\n\n"
        f"🍅 Завершенных сессий: **{pomodoro_count}**\n"
        f"⏰ Общее время фокуса: **{hours}ч {minutes}м**\n"
        f"✅ Выполненных задач: **{completed_tasks}**\n"
        f"📈 Уровень: **{level}**\n\n"
        f"💡 **Советы:**\n"
        f"• Идеальный ритм: 4 сессии + длинный отдых\n"
        f"• Фокусируйтесь на одной задаче за сессию\n"
        f"• Не забывайте про перерывы!",
        reply_markup=keyboard,
        parse_mode="Markdown"  
    )
    await callback.answer()

@router.callback_query(F.data == "pomo_auto")
async def pomodoro_auto_sequence(callback: types.CallbackQuery):
    """Автоматическая последовательность Pomodoro"""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🚀 Начать цикл", callback_data="pomo_auto_start")
            ],
            [
                types.InlineKeyboardButton(text="📚 Что это?", callback_data="pomo_auto_info"),
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="pomo_menu")
            ]
        ]
    )
    
    await callback.message.edit_text(
        "🔄 **Автопоследовательность Pomodoro**\n\n"
        "Классический цикл:\n"
        "1️⃣ 25 мин работы\n"
        "2️⃣ 5 мин отдыха\n"
        "3️⃣ 25 мин работы\n"
        "4️⃣ 5 мин отдыха\n"
        "5️⃣ 25 мин работы\n"
        "6️⃣ 5 мин отдыха\n"
        "7️⃣ 25 мин работы\n"
        "8️⃣ 15 мин длинного отдыха\n\n"
        "🎯 **Итого:** 4 рабочих сессии за ~2 часа",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pomo_start_work_"))
async def start_custom_work(callback: types.CallbackQuery):
    duration_str = callback.data.replace("pomo_start_work_", "")
    duration = int(duration_str) * 60  
    
    await start_custom_pomodoro(callback, "work", duration)

@router.callback_query(F.data.startswith("pomo_start_break_"))
async def start_custom_break(callback: types.CallbackQuery):
    duration_str = callback.data.replace("pomo_start_break_", "")
    duration = int(duration_str) * 60 
    
    await start_custom_pomodoro(callback, "break", duration)

async def start_custom_pomodoro(callback: types.CallbackQuery, session_type: str, duration: int):
    user_id = callback.from_user.id
   
    if user_id in active_timers:
        await stop_pomodoro(user_id)
   
    session_names = {
        'work': 'Работа',
        'break': 'Короткий перерыв',
        'long_break': 'Длинный перерыв'
    }
    
    session_name = session_names.get(session_type, 'Сессия')
    
    gif_file = await create_and_send_timer_gif(duration, session_type)
   
    if gif_file:
        initial_message = await callback.message.answer_animation(
            animation=gif_file,
            caption=create_initial_caption(session_type, duration),
            reply_markup=create_active_timer_buttons(session_type)
        )
    else:
        initial_message = await callback.message.answer(
            create_initial_caption(session_type, duration),
            reply_markup=create_active_timer_buttons(session_type)
        )
   
    active_timers[user_id] = {
        'task': asyncio.create_task(pomodoro_timer_seconds(user_id, duration, session_type, initial_message)),
        'start_time': datetime.now(),
        'duration': duration,
        'message_id': initial_message.message_id,
        'chat_id': initial_message.chat.id,
        'session_type': session_type,
        'paused': False,
        'remaining_seconds': duration
    }
   
    await callback.answer(f"🍅 {session_name} сессия ({duration//60} мин) запущена!")

@router.callback_query(F.data == "pomo_auto_info")
async def pomodoro_auto_info(callback: types.CallbackQuery):
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🚀 Начать цикл", callback_data="pomo_auto_start")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="pomo_auto")
            ]
        ]
    )
    
    await callback.message.edit_text(
        "📚 **Что такое автопоследовательность?**\n\n"
        "🍅 **Классическая техника Pomodoro:**\n"
        "Разработана Франческо Чирилло в 1980-х\n\n"
        "⚡ **Принцип работы:**\n"
        "• 25 минут сосредоточенной работы\n"
        "• 5 минут отдыха\n"
        "• После 4 циклов - длинный отдых 15-30 мин\n\n"
        "🎯 **Преимущества:**\n"
        "• Улучшает концентрацию\n"
        "• Снижает усталость\n"
        "• Повышает продуктивность\n"
        "• Помогает против прокрастинации\n\n"
        "🔄 **Автоцикл в боте:**\n"
        "Автоматически переключает между работой и отдыхом",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "pomo_auto_start")
async def start_auto_pomodoro(callback: types.CallbackQuery):
    user_id = callback.from_user.id
   
    if user_id in active_timers:
        await stop_pomodoro(user_id)

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏸️ Пауза", callback_data="pomo_pause"),
                types.InlineKeyboardButton(text="⏹️ Остановить", callback_data="pomo_stop")
            ],
            [
                types.InlineKeyboardButton(text="🔄 Главное меню", callback_data="pomo_menu")
            ]
        ]
    )
    
    duration = 25 * 60  
    session_type = "work"
    
    gif_file = await create_and_send_timer_gif(duration, session_type)
   
    initial_caption = (
        f"🔄 **Автоцикл Pomodoro начат!**\n\n"
        f"📍 Сессия 1/8: Работа\n"
        f"⏰ Длительность: 25 минут\n"
        f"🎬 Запускаем первую сессию..."
    )
    
    if gif_file:
        initial_message = await callback.message.answer_animation(
            animation=gif_file,
            caption=initial_caption,
            reply_markup=keyboard
        )
    else:
        initial_message = await callback.message.answer(
            initial_caption,
            reply_markup=keyboard
        )
   
    active_timers[user_id] = {
        'task': asyncio.create_task(pomodoro_timer_seconds(user_id, duration, session_type, initial_message)),
        'start_time': datetime.now(),
        'duration': duration,
        'message_id': initial_message.message_id,
        'chat_id': initial_message.chat.id,
        'session_type': session_type,
        'paused': False,
        'remaining_seconds': duration,
        'auto_cycle': True,
        'cycle_step': 1,   
        'total_steps': 8   
    }
   
    await callback.answer("🔄 Автоцикл Pomodoro запущен!")

@router.callback_query(F.data == "pomo_menu")
async def show_pomodoro_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
   
    if user_id in active_timers:
        await stop_pomodoro(user_id)
   
    from database import get_user_id, get_user_stats
    user_internal_id = get_user_id(callback.from_user.id)
    stats_text = ""
    
    if user_internal_id:
        stats = get_user_stats(user_internal_id)
        pomodoro_count = stats.get('pomodoro_sessions', 0)
        if pomodoro_count > 0:
            stats_text = f"\n📊 Сегодня завершено: {pomodoro_count} сессий"

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="⏱️ 25 мин Работа", callback_data="pomo_start_work"),
                types.InlineKeyboardButton(text="☕ 5 мин Отдых", callback_data="pomo_start_break")
            ],
            [
                types.InlineKeyboardButton(text="🌴 15 мин Длинный отдых", callback_data="pomo_start_long_break"),
                types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="pomo_settings")
            ],
            [
                types.InlineKeyboardButton(text="📊 Моя статистика", callback_data="pomo_stats"),
                types.InlineKeyboardButton(text="🔄 Автопоследовательность", callback_data="pomo_auto")
            ]
        ]
    )
   
    try:
        await callback.message.edit_text(
            f"🍅 **Pomodoro Таймер**\n\n"
            f"Выберите тип сессии:\n"
            f"• ⏱️ 25 мин - Фокусировка на работе\n"
            f"• ☕ 5 мин - Короткий перерыв\n"
            f"• 🌴 15 мин - Длинный перерыв{stats_text}\n\n"
            f"💡 Классический Pomodoro: 25 мин работы → 5 мин отдыха",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            f"🍅 **Pomodoro Таймер**\n\n"
            f"Выберите тип сессии:\n"
            f"• ⏱️ 25 мин - Фокусировка на работе\n"
            f"• ☕ 5 мин - Короткий перерыв\n"
            f"• 🌴 15 мин - Длинный перерыв{stats_text}\n\n"
            f"💡 Классический Pomodoro: 25 мин работы → 5 мин отдыха",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    await callback.answer()
