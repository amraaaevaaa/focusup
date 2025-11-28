from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ai_helper import ai_assistant
from database import get_user_id, get_user_tasks, get_user_stats
import re

router = Router()


def _plain_ai_text(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    
    t = text.strip()

    max_length = 1000
    if len(t) > max_length:
        cut_pos = t.rfind('.', 0, max_length)
        if cut_pos == -1:
            cut_pos = t.rfind('!', 0, max_length)
        if cut_pos == -1:
            cut_pos = t.rfind('?', 0, max_length)
        if cut_pos == -1:
            cut_pos = max_length
        
        t = t[:cut_pos + 1] + "\n\n✂️ *Ответ сокращён для удобства чтения*"
    
    t = re.sub(r' +', ' ', t) 
    t = re.sub(r'\n{3,}', '\n\n', t)
    
    return t


def _normalize_ai_response(text):
    if not isinstance(text, str):
        return text
    s = text.strip()
    
    if len(s) < 200 and re.match(r"^\{[^\}]*\}$", s):
        return "AI вернул некорректный ответ. Попробуйте ещё раз или уточните запрос."
    if len(s) <= 64 and ' ' not in s and re.match(r'^[A-Za-z0-9_\-+/=]+$', s):
        return "AI вернул некорректный ответ (короткий системный токен). Попробуйте ещё раз или уточните запрос."

    s = re.sub(r'#{1,6}\s*', '', s)
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s) 
    s = re.sub(r'\*(.*?)\*', r'\1', s)
    s = re.sub(r'__(.*?)__', r'\1', s) 
    s = re.sub(r'_(.*?)_', r'\1', s)  
    s = re.sub(r'~~(.*?)~~', r'\1', s)  
    s = re.sub(r'`(.*?)`', r'\1', s) 
    s = re.sub(r'```[^`]*```', '', s)  
    
    return s



class AIChat(StatesGroup):
    waiting_question = State()

class AIPlanning(StatesGroup):
    waiting_goal = State()
    waiting_timeframe = State()

@router.message(F.text == "🤖 AI-помощник")
async def ai_main_menu(message: types.Message):
    ai_status = "Доступен" if ai_assistant.is_available else "Недоступен"
    status_emoji = "🟢" if ai_assistant.is_available else "🔴"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="� Чат с AI", callback_data="ai_chat"),
                InlineKeyboardButton(text="📊 Анализ задач", callback_data="ai_analyze")
            ],
            [
                InlineKeyboardButton(text="🎯 Создать план", callback_data="ai_plan"),
                InlineKeyboardButton(text="💡 Советы", callback_data="ai_tips")
            ],
            [
                InlineKeyboardButton(text="📋 Мои задачи", callback_data="show_all_tasks"),
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
            ]
        ]
    )
    
    await message.answer(
        f"**AI-Ассистент FocusUp**\n\n"
        f"Статус: {status_emoji} {ai_status}\n\n"
        f"**Доступные функции:**\n"
        f"• Консультации по тайм-менеджменту\n"
        f"• Анализ эффективности задач\n"
        f"• Создание планов и стратегий\n"
        f"• Персональные рекомендации\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "ai_chat")
async def start_ai_chat(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AIChat.waiting_question)
    
    await callback.message.edit_text(
        "**Чат с AI-ассистентом**\n\n"
        "Задайте любой вопрос о тайм-менеджменте, продуктивности или планировании.\n\n"
        "*Примеры вопросов:*\n"
        "• Как победить прокрастинацию?\n"
        "• Как лучше планировать день?\n"
        "• Методы повышения концентрации?\n\n"
        "Введите ваш вопрос:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ai_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(AIChat.waiting_question)
async def process_ai_question(message: types.Message, state: FSMContext):
    await state.clear()
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    user_internal_id = get_user_id(message.from_user.id)
    user_context = None
    
    if user_internal_id:
        tasks = get_user_tasks(user_internal_id)
        stats = get_user_stats(user_internal_id)
        user_context = f"Задач всего: {len(tasks)}, активных: {stats['active_tasks']}, выполнено: {stats['completed_tasks']}"
    
    ai_response = await ai_assistant.generate_response(message.text, user_context)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Новый вопрос", callback_data="ai_chat"),
            InlineKeyboardButton(text="📊 Анализ задач", callback_data="ai_analyze")
        ],
        [InlineKeyboardButton(text="🔙 К AI-меню", callback_data="back_to_ai_menu")]
    ])
    
    await message.answer(
        f"Ответ AI-ассистента:\n\n{_plain_ai_text(_normalize_ai_response(ai_response))}",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "ai_analyze")
async def ai_analyze_tasks(callback: types.CallbackQuery):
    """AI анализ задач пользователя"""
    await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")
    
    user_internal_id = get_user_id(callback.from_user.id)
    
    if not user_internal_id:
        await callback.message.edit_text(
            "Для анализа задач необходимо сначала создать хотя бы одну задачу.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ai_menu")]
            ])
        )
        await callback.answer()
        return
    
    tasks = get_user_tasks(user_internal_id)
    stats = get_user_stats(user_internal_id)
    
    if not tasks:
        await callback.message.edit_text(
            "У вас пока нет задач для анализа. Создайте несколько задач и возвращайтесь!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ai_menu")]
            ])
        )
        await callback.answer()
        return
    
    tasks_data = f"""
    Статистика задач:
    - Всего задач: {len(tasks)}
    - Активных: {stats['active_tasks']}
    - Выполненных: {stats['completed_tasks']}
    - Просроченных: {stats['overdue_tasks']}
    - Процент выполнения: {stats['completion_rate']}%
    
    Категории: {', '.join([f"{k}: {v}" for k, v in stats['categories'].items()])}
    
    Последние 10 задач:
    """
    
    for i, task in enumerate(tasks[:10], 1):
        status = "✅ Выполнена" if task[6] else "⏳ Активна"
        deadline = f", дедлайн: {task[5]}" if task[5] else ""
        tasks_data += f"{i}. {task[2]} ({task[3]}) - {status}{deadline}\n"
    
    analysis = await ai_assistant.analyze_productivity(tasks_data)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Создать план", callback_data="ai_plan"),
            InlineKeyboardButton(text="💬 Задать вопрос", callback_data="ai_chat")
        ],
        [InlineKeyboardButton(text="🔙 К AI-меню", callback_data="back_to_ai_menu")]
    ])
    
    await callback.message.edit_text(
        f"Анализ продуктивности:\n\n{_plain_ai_text(_normalize_ai_response(analysis))}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "ai_plan")
async def start_ai_planning(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AIPlanning.waiting_goal)
    
    await callback.message.edit_text(
        "**Создание плана с AI**\n\n"
        "Опишите вашу цель или проект, для которого нужен план.\n\n"
        "*Примеры:*\n"
        "• Подготовиться к экзамену по математике\n"
        "• Запустить собственный блог\n"
        "• Изучить Python за месяц\n\n"
        "Введите вашу цель:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ai_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(AIPlanning.waiting_goal)
async def process_planning_goal(message: types.Message, state: FSMContext):
    await state.update_data(goal=message.text)
    await state.set_state(AIPlanning.waiting_timeframe)
    
    await message.answer(
        f"**Цель:** {message.text}\n\n"
        "Теперь укажите временные рамки:\n\n"
        "*Примеры:*\n"
        "• За неделю\n" 
        "• В течение месяца\n"
        "• К концу года\n\n"
        "Введите временные рамки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="� Назад", callback_data="back_to_ai_menu")]
        ]),
        parse_mode="Markdown"
    )

@router.message(AIPlanning.waiting_timeframe)
async def process_planning_timeframe(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    plan = await ai_assistant.create_task_plan(data['goal'], message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Новый план", callback_data="ai_plan"),
            InlineKeyboardButton(text="📊 Анализ задач", callback_data="ai_analyze")
        ],
        [InlineKeyboardButton(text="🔙 К AI-меню", callback_data="back_to_ai_menu")]
    ])
    
    await message.answer(
        f"План достижения цели:\n\n{_plain_ai_text(_normalize_ai_response(plan))}",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "ai_tips")
async def ai_productivity_tips(callback: types.CallbackQuery):
    await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")
    
    tips_prompt = "Дай 5 практических советов по повышению продуктивности и тайм-менеджменту. Советы должны быть конкретными и применимыми."
    tips = await ai_assistant.generate_response(tips_prompt)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Новый план", callback_data="ai_plan"),
            InlineKeyboardButton(text="📊 Анализ задач", callback_data="ai_analyze")
        ],
        [InlineKeyboardButton(text="🔙 К AI-меню", callback_data="back_to_ai_menu")]
    ])
    
    await callback.message.edit_text(
        f"💡 Советы по продуктивности:\n\n{_plain_ai_text(_normalize_ai_response(tips))}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_ai_menu")
async def back_to_ai_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()

    ai_status = "🟢 Активен" if ai_assistant.is_available else "🔴 Недоступен"
    status_emoji = "🤖" if ai_assistant.is_available else "⚠️"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Чат с AI", callback_data="ai_chat"),
            InlineKeyboardButton(text="📊 Анализ задач", callback_data="ai_analyze")
        ],
        [
            InlineKeyboardButton(text="🎯 Создать план", callback_data="ai_plan"),
            InlineKeyboardButton(text="💡 Советы", callback_data="ai_tips")
        ],
        [
            InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")
        ]
    ])
    
    await callback.message.edit_text(
        f"**AI-Ассистент FocusUp**\n\n"
        f"Статус: {status_emoji} {ai_status}\n\n"
        f"**Доступные функции:**\n"
        f"• Консультации по тайм-менеджменту\n"
        f"• Анализ эффективности задач\n"
        f"• Создание планов и стратегий\n"
        f"• Персональные рекомендации\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "show_all_tasks")
async def show_all_tasks_from_ai(callback: types.CallbackQuery):
    from .tasks import show_my_tasks_list
    await show_my_tasks_list(callback)
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Возвращаемся в главное меню")

@router.message(F.text & ~F.text.startswith('/') & ~F.text.in_(['📝 Задачи', '🍅 Pomodoro', '📅 Календарь', '🤖 AI-помощник', '📊 Статистика', '⚙️ Помощь']))
async def handle_general_chat(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return  
    
    try:
        await message.answer("🤖 Думаю...")
        
        user_internal_id = get_user_id(message.from_user.id)
        user_context = None
        
        if user_internal_id:
            tasks = get_user_tasks(user_internal_id)
            stats = get_user_stats(user_internal_id)
            user_context = f"Задач всего: {len(tasks)}, активных: {stats['active_tasks']}, выполнено: {stats['completed_tasks']}"

        response = await ai_assistant.generate_response(message.text, user_context)
        
        formatted_response = _normalize_ai_response(response)
        formatted_response = _plain_ai_text(formatted_response)
        
        
        if not formatted_response or formatted_response.strip() == "":
            formatted_response = "Извините, не удалось получить ответ от AI. Попробуйте ещё раз."
        
        await message.answer(formatted_response)
        
    except Exception as e:
        print(f"❌ Ошибка в общем чате: {e}")
        await message.answer("Извините, произошла ошибка при обработке вашего сообщения. Попробуйте ещё раз.")
