from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import datetime, timedelta
from database import (
    add_user, add_task, get_user_tasks, update_task_status, 
    delete_task, get_task_by_id, get_user_id,
    get_active_tasks, get_completed_tasks, get_today_tasks,
    get_upcoming_tasks, search_tasks
)

router = Router()

class TaskCreation(StatesGroup):
    title = State()
    category = State()
    deadline = State()

class TaskVoiceInput(StatesGroup):
    voice_text = State()

class TaskEditing(StatesGroup):
    selecting_field = State()
    editing_title = State()
    editing_category = State()
    editing_deadline = State()

@router.message(F.text == "📝 Задачи")
async def tasks_main_menu(message: types.Message):

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
            [types.InlineKeyboardButton(text="📋 Мои задачи", callback_data="my_tasks")],
            [types.InlineKeyboardButton(text="🎤 Голосовой ввод", callback_data="voice_input")],
            [
                types.InlineKeyboardButton(text="🟢 Активные", callback_data="active_tasks"),
                types.InlineKeyboardButton(text="✅ Выполненные", callback_data="completed_tasks")
            ],
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="today_tasks"),
                types.InlineKeyboardButton(text="⏰ Просроченные", callback_data="overdue_tasks")
            ]
        ]
    )
    
    user_internal_id = get_user_id(message.from_user.id)
    stats_text = ""
    if user_internal_id:
        tasks = get_user_tasks(user_internal_id)
        active_count = len([t for t in tasks if not t[6]])
        completed_count = len([t for t in tasks if t[6]])
        
        stats_text = f"\n📊 **Статистика:**\n• Активные: {active_count}\n• Выполненные: {completed_count}\n• Всего: {len(tasks)}"
    
    await message.answer(
        f"**Управление задачами**{stats_text}\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "add_task")
async def add_task_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TaskCreation.title)
    await callback.message.edit_text(
        "**Создание новой задачи**\n\n"
        "Введите название задачи:",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(TaskCreation.title)
async def process_task_title(message: types.Message, state: FSMContext):
    if len(message.text) > 200:
        await message.answer("❌ Слишком длинное название! Максимум 200 символов.")
        return
        
    await state.update_data(title=message.text)
    await state.set_state(TaskCreation.category)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🎓 Учеба", callback_data="category_study"),
                types.InlineKeyboardButton(text="💼 Работа", callback_data="category_work")
            ],
            [
                types.InlineKeyboardButton(text="🏠 Личное", callback_data="category_personal"),
                types.InlineKeyboardButton(text="🏋️ Здоровье", callback_data="category_health")
            ],
            [
                types.InlineKeyboardButton(text="🎉 Развлечения", callback_data="category_fun"),
                types.InlineKeyboardButton(text="🔧 Другое", callback_data="category_other")
            ]
        ]
    )
    
    await message.answer(
        f"**Выберите категорию для задачи:**\n\"{message.text}\"",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("category_"), TaskCreation.category)
async def process_task_category(callback: types.CallbackQuery, state: FSMContext):
    category_map = {
        "category_study": "🎓 Учеба",
        "category_work": "💼 Работа", 
        "category_personal": "🏠 Личное",
        "category_health": "🏋️ Здоровье",
        "category_fun": "🎉 Развлечения",
        "category_other": "🔧 Другое"
    }
    
    category = category_map[callback.data]
    await state.update_data(category=category)
    await state.set_state(TaskCreation.deadline)
    
    quick_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="deadline_today"),
                types.InlineKeyboardButton(text="📅 Завтра", callback_data="deadline_tomorrow")
            ],
            [
                types.InlineKeyboardButton(text="❌ Без дедлайна", callback_data="deadline_none"),
                types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="deadline_custom")
            ]
        ]
    )
    
    data = await state.get_data()
    await callback.message.edit_text(
        f"📅 **Установите дедлайн**\n\n"
        f"• 📝 *Название:* {data['title']}\n"
        f"• 📂 *Категория:* {category}\n\n"
        f"Выберите вариант:",
        reply_markup=quick_kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("deadline_"), TaskCreation.deadline)
async def process_quick_deadline(callback: types.CallbackQuery, state: FSMContext):
    now = datetime.now()
    
    if callback.data == "deadline_today":
        deadline_date = now.date()
        await state.update_data(deadline_date=deadline_date.strftime("%d.%m.%y"))
        await ask_deadline_time(callback.message, state)
        
    elif callback.data == "deadline_tomorrow":
        deadline_date = (now + timedelta(days=1)).date()
        await state.update_data(deadline_date=deadline_date.strftime("%d.%m.%y"))
        await ask_deadline_time(callback.message, state)
        
    elif callback.data == "deadline_none":
        await save_task_with_deadline(callback, state, None)
        
    elif callback.data == "deadline_custom":
        calendar_kb = await SimpleCalendar().start_calendar()
        calendar_kb.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_deadline_menu")
        ])
        
        await callback.message.edit_text(
            "📅 *Выберите дату:*",
            reply_markup=calendar_kb,
            parse_mode="Markdown"
        )
    
    await callback.answer()

@router.callback_query(SimpleCalendarCallback.filter(), TaskCreation.deadline)
async def process_calendar(callback: types.CallbackQuery, callback_data: dict, state: FSMContext):
    calendar = SimpleCalendar()
    calendar.set_dates_range(datetime(2024, 1, 1), datetime(2025, 12, 31))
    selected, date = await calendar.process_selection(callback, callback_data)
    
    if selected:
        await state.update_data(deadline_date=date.strftime("%d.%m.%y"))
        await ask_deadline_time(callback.message, state)

async def ask_deadline_time(message: types.Message, state: FSMContext):

    data = await state.get_data()
    
    time_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🕘 09:00", callback_data="time_09:00"),
                types.InlineKeyboardButton(text="🕙 10:00", callback_data="time_10:00"),
                types.InlineKeyboardButton(text="🕚 11:00", callback_data="time_11:00")
            ],
            [
                types.InlineKeyboardButton(text="🕛 12:00", callback_data="time_12:00"),
                types.InlineKeyboardButton(text="🕐 13:00", callback_data="time_13:00"),
                types.InlineKeyboardButton(text="🕑 14:00", callback_data="time_14:00")
            ],
            [
                types.InlineKeyboardButton(text="🕒 15:00", callback_data="time_15:00"),
                types.InlineKeyboardButton(text="🕓 16:00", callback_data="time_16:00"),
                types.InlineKeyboardButton(text="🕔 17:00", callback_data="time_17:00")
            ],
            [
                types.InlineKeyboardButton(text="🕕 18:00", callback_data="time_18:00"),
                types.InlineKeyboardButton(text="🕖 19:00", callback_data="time_19:00"),
                types.InlineKeyboardButton(text="🕗 20:00", callback_data="time_20:00")
            ],
            [
                types.InlineKeyboardButton(text="🕘 21:00", callback_data="time_21:00"),
                types.InlineKeyboardButton(text="🕙 22:00", callback_data="time_22:00"),
                types.InlineKeyboardButton(text="🎯 Другое время", callback_data="time_custom")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад к дате", callback_data="back_to_date_selection")
            ]
        ]
    )
    
    await message.edit_text(
        f"⏰ **Выберите время для {data['deadline_date']}**\n\n"
        f"• 📝 *Задача:* {data['title']}\n"
        f"• 📂 *Категория:* {data['category']}\n\n"
        f"*Выберите подходящее время:*",
        reply_markup=time_kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("time_"), TaskCreation.deadline)
async def process_time_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "time_custom":
        await ask_custom_time(callback, state)
        return
    
    time_str = callback.data.replace("time_", "")
    data = await state.get_data()
    deadline = f"{data['deadline_date']} {time_str}"
    
    await save_task_with_deadline(callback, state, deadline)
    await callback.answer()

@router.callback_query(F.data == "time_custom")
async def ask_custom_time(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    
    quick_times_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🕤 09:30", callback_data="time_09:30"),
                types.InlineKeyboardButton(text="🕥 10:30", callback_data="time_10:30"),
                types.InlineKeyboardButton(text="🕦 11:30", callback_data="time_11:30")
            ],
            [
                types.InlineKeyboardButton(text="🕧 12:30", callback_data="time_12:30"),
                types.InlineKeyboardButton(text="🕜 13:30", callback_data="time_13:30"),
                types.InlineKeyboardButton(text="🕝 14:30", callback_data="time_14:30")
            ],
            [
                types.InlineKeyboardButton(text="🕞 15:30", callback_data="time_15:30"),
                types.InlineKeyboardButton(text="🕟 16:30", callback_data="time_16:30"),
                types.InlineKeyboardButton(text="🕠 17:30", callback_data="time_17:30")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад к выбору времени", callback_data="back_to_time_selection")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"⏰ **Введите время вручную**\n\n"
        f"• 📅 *Дата:* {data['deadline_date']}\n"
        f"• 📝 *Задача:* {data['title']}\n\n"
        f"*Отправьте время в формате:* **ЧЧ:ММ**\n"
        f"*Пример:* 14:30 или 09:15\n\n"
        f"*Или выберите из вариантов ниже:*",
        reply_markup=quick_times_kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(F.text.regexp(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'), TaskCreation.deadline)
async def process_custom_time(message: types.Message, state: FSMContext):

    time_str = message.text.strip()
    
    try:
        hours, minutes = map(int, time_str.split(':'))
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            raise ValueError("Некорректное время")
    except:
        await message.answer(
            "❌ *Некорректное время!*\n\n"
            "Пожалуйста, введите время в формате **ЧЧ:ММ**\n"
            "*Пример:* 14:30 или 09:05",
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    deadline = f"{data['deadline_date']} {time_str}"
    
    await save_task_with_deadline(message, state, deadline)

async def save_task_with_deadline(message_or_callback, state: FSMContext, deadline = None):
    data = await state.get_data()
    
    if isinstance(message_or_callback, types.CallbackQuery):
        user_telegram_id = message_or_callback.from_user.id
        response_target = message_or_callback.message
        print(f"🔍 DEBUG save_task: CallbackQuery from user {user_telegram_id}")
    else:
        user_telegram_id = message_or_callback.from_user.id
        response_target = message_or_callback
        print(f"🔍 DEBUG save_task: Message from user {user_telegram_id}")
    
    user_internal_id = get_user_id(user_telegram_id)
    
    if not user_internal_id:
        user_internal_id = add_user(
            user_telegram_id,
            message_or_callback.from_user.username if hasattr(message_or_callback, 'from_user') else None,
            message_or_callback.from_user.first_name if hasattr(message_or_callback, 'from_user') else None,
            message_or_callback.from_user.last_name if hasattr(message_or_callback, 'from_user') else None
        )
        
        if not user_internal_id:
            user_internal_id = get_user_id(user_telegram_id)
    
    if not user_internal_id:
        error_text = "❌ Ошибка: не удалось создать пользователя. Пожалуйста, начните с команды /start"
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer(error_text)
        else:
            await message_or_callback.answer(error_text)
        await state.clear()
        return
    
    task_id = add_task(
        user_id=user_internal_id,
        title=data['title'],
        category=data['category'],
        deadline=deadline
    )
    
    if not task_id:
        error_text = "❌ Ошибка при создании задачи. Попробуйте снова."
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer(error_text)
        else:
            await message_or_callback.answer(error_text)
        await state.clear()
        return
    
    await state.clear()
    
    response = f"**Задача создана**\n\n"
    response += f"**Название:** {data['title']}\n"
    response += f"**Категория:** {data['category']}\n"
    response += f"**Дедлайн:** {deadline if deadline else 'Не установлен'}\n"
    response += f"**ID:** #{task_id}"
    
    action_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Выполнить", callback_data=f"complete_task_{task_id}"),
                types.InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_task_{task_id}")
            ],
            [
                types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_task_{task_id}"),
                types.InlineKeyboardButton(text="📋 К задачам", callback_data="my_tasks")
            ]
        ]
    )
    
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(response, reply_markup=action_kb, parse_mode="Markdown")
    else:
        await message_or_callback.answer(response, reply_markup=action_kb, parse_mode="Markdown")

@router.callback_query(F.data == "my_tasks")
async def show_my_tasks_list(callback: types.CallbackQuery):

    print(f"🔍 DEBUG my_tasks: telegram_id={callback.from_user.id}")
    user_internal_id = get_user_id(callback.from_user.id)
    print(f"🔍 DEBUG my_tasks: user_internal_id={user_internal_id}")
    
    if not user_internal_id:
        print("❌ DEBUG: user_internal_id is None!")
        await callback.message.edit_text("❌ Пользователь не найден. Начните с /start")
        await callback.answer()
        return
    
    tasks = get_user_tasks(user_internal_id)
    print(f"🔍 DEBUG my_tasks: found {len(tasks)} tasks for user_id {user_internal_id}")
    
    if not tasks:
        print("❌ DEBUG: tasks list is empty!")
        await callback.message.edit_text(
            "📭 *У вас пока нет задач!*\n\n"
            "Создайте первую задачу с помощью кнопки ниже:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")]
                ]
            ),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    keyboard = []
    
    for task in tasks[:8]:
        task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task

        status_emoji = "✅" if completed else "🟢"

        short_title = title[:30] + "..." if isinstance(title, str) and len(title) > 30 else title
        button_text = f"{status_emoji} {short_title}"

        keyboard.append([types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"view_task_{task_id}"
        )])
    
    response = f"📋 **Мои задачи** ({len(tasks)})\n\nВыберите задачу для просмотра:"

    keyboard.extend([
        [
            types.InlineKeyboardButton(text="🟢 Активные", callback_data="active_tasks"),
            types.InlineKeyboardButton(text="✅ Выполненные", callback_data="completed_tasks")
        ],
        [
            types.InlineKeyboardButton(text="➕ Новая задача", callback_data="add_task"),
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")
        ]
    ])
    
    nav_kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(response, reply_markup=nav_kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "active_tasks")
async def show_active_tasks_list(callback: types.CallbackQuery):
    user_internal_id = get_user_id(callback.from_user.id)
    tasks = get_active_tasks(user_internal_id)
    
    if not tasks:
        await callback.message.edit_text(
            "📭 *У вас пока нет активных задач!*\n\n"
            "Создайте первую задачу с помощью кнопки ниже:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")]
                ]
            ),
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    keyboard = []
    
    for task in tasks[:8]:
        task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task
        
        status_emoji = "🟢"
        
        short_title = title[:30] + "..." if isinstance(title, str) and len(title) > 30 else title
        button_text = f"{status_emoji} {short_title}"
        
        keyboard.append([types.InlineKeyboardButton(
            text=button_text, 
            callback_data=f"view_task_{task_id}"
        )])
    
    keyboard.extend([
        [
            types.InlineKeyboardButton(text="✅ Выполненные", callback_data="completed_tasks"),
            types.InlineKeyboardButton(text="📋 Все задачи", callback_data="my_tasks")
        ],
        [
            types.InlineKeyboardButton(text="➕ Новая задача", callback_data="add_task"),
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")
        ]
    ])
    
    nav_kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    response = f"🟢 **Активные задачи** ({len(tasks)})\n\nВыберите задачу для просмотра:"
    
    await callback.message.edit_text(response, reply_markup=nav_kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "completed_tasks")
async def show_completed_tasks_list(callback: types.CallbackQuery):
    user_internal_id = get_user_id(callback.from_user.id)
    tasks = get_completed_tasks(user_internal_id)
    
    if not tasks:
        await callback.message.edit_text(
            "📭 *У вас пока нет выполненных задач!*\n\n"
            "Выполните задачи, чтобы они появились здесь:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🟢 Активные задачи", callback_data="active_tasks")],
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")]
                ]
            ),
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    keyboard = []
    
    for task in tasks[:8]:
        task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task
        
        status_emoji = "✅"
        
        short_title = title[:30] + "..." if isinstance(title, str) and len(title) > 30 else title
        button_text = f"{status_emoji} {short_title}"
        
        keyboard.append([types.InlineKeyboardButton(
            text=button_text, 
            callback_data=f"view_task_{task_id}"
        )])
    
    keyboard.extend([
        [
            types.InlineKeyboardButton(text="🟢 Активные", callback_data="active_tasks"),
            types.InlineKeyboardButton(text="📋 Все задачи", callback_data="my_tasks")
        ],
        [
            types.InlineKeyboardButton(text="➕ Новая задача", callback_data="add_task"),
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")
        ]
    ])
    
    nav_kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    response = f"✅ **Выполненные задачи** ({len(tasks)})\n\nВыберите задачу для просмотра:"
    
    await callback.message.edit_text(response, reply_markup=nav_kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "today_tasks")
async def show_today_tasks(callback: types.CallbackQuery):
    user_internal_id = get_user_id(callback.from_user.id)
    tasks = get_today_tasks(user_internal_id)
    
    response = format_task_list(tasks, "today")
    await send_task_list(callback, response, "today")

@router.callback_query(F.data == "overdue_tasks")
async def show_overdue_tasks(callback: types.CallbackQuery):
    user_internal_id = get_user_id(callback.from_user.id)
    tasks = get_user_tasks(user_internal_id)
    
    overdue_tasks = []
    now = datetime.now()
    
    for task in tasks:
        if not task[6] and task[5]:
            try:
                deadline_date = datetime.strptime(task[5], '%d.%m.%y %H:%M')
                if deadline_date < now:
                    overdue_tasks.append(task)
            except:
                continue
    
    response = format_task_list(overdue_tasks, "overdue")
    await send_task_list(callback, response, "overdue")

@router.callback_query(F.data == "voice_input")
async def start_voice_input(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TaskVoiceInput.voice_text)
    await callback.message.edit_text(
        "**Голосовой ввод задачи**\n\n"
        "Отправьте голосовое сообщение или опишите задачу текстом.\n\n"
        "*Пример:* \"Завтра в 18:30 встреча с клиентом\"",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(F.voice, TaskVoiceInput.voice_text)
async def process_voice_message(message: types.Message, state: FSMContext):

    await message.answer("🎤 Обрабатываю голосовое сообщение...")
    
    try:
        voice_file = await message.bot.get_file(message.voice.file_id)
        voice_data = await message.bot.download_file(voice_file.file_path)
        
        from voice_recognition import voice_recognizer
        recognized_text = await voice_recognizer.recognize_voice(voice_data.read())
        
        if recognized_text:
            await state.update_data(title=recognized_text, category="🔧 Другое")
            await state.set_state(TaskCreation.deadline)
            
            await message.answer(
                f"**Текст распознан:**\n{recognized_text}\n\n"
                "Установите дедлайн:",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(text="📅 Сегодня", callback_data="deadline_today"),
                            types.InlineKeyboardButton(text="📅 Завтра", callback_data="deadline_tomorrow")
                        ],
                        [
                            types.InlineKeyboardButton(text="❌ Без дедлайна", callback_data="deadline_none"),
                            types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="deadline_custom")
                        ]
                    ]
                ),
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                "❌ Не удалось распознать голосовое сообщение.\n"
                "Попробуйте ввести задачу текстом или повторите запись."
            )
            
    except Exception as e:
        print(f"Ошибка обработки голоса: {e}")
        await message.answer(
            "❌ Ошибка при обработке голосового сообщения.\n"
            "Попробуйте ввести задачу текстом."
        )

@router.message(TaskVoiceInput.voice_text)
async def process_voice_input(message: types.Message, state: FSMContext):

    await state.update_data(title=message.text, category="🔧 Другое")
    await state.set_state(TaskCreation.deadline)
    
    await message.answer(
        f"**Задача получена:** {message.text}\n\n"
        "Установите дедлайн:",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="📅 Сегодня", callback_data="deadline_today"),
                    types.InlineKeyboardButton(text="📅 Завтра", callback_data="deadline_tomorrow")
                ],
                [
                    types.InlineKeyboardButton(text="❌ Без дедлайна", callback_data="deadline_none"),
                    types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="deadline_custom")
                ]
            ]
        ),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "back_to_tasks_menu")
async def back_to_tasks_menu(callback: types.CallbackQuery):
    await tasks_main_menu_callback(callback)
    await callback.answer()

async def tasks_main_menu_callback(callback: types.CallbackQuery):

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
            [types.InlineKeyboardButton(text="📋 Мои задачи", callback_data="my_tasks")],
            [types.InlineKeyboardButton(text="🎤 Голосовой ввод", callback_data="voice_input")],
            [
                types.InlineKeyboardButton(text="🟢 Активные", callback_data="active_tasks"),
                types.InlineKeyboardButton(text="✅ Выполненные", callback_data="completed_tasks")
            ],
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="today_tasks"),
                types.InlineKeyboardButton(text="⏰ Просроченные", callback_data="overdue_tasks")
            ]
        ]
    )
    
    telegram_id = callback.from_user.id
    print(f"🔍 DEBUG tasks_main_menu_callback: callback.from_user.id = {telegram_id}")
    user_internal_id = get_user_id(telegram_id)
    print(f"🔍 DEBUG tasks_main_menu_callback: user_internal_id = {user_internal_id}")
    stats_text = ""
    if user_internal_id:
        tasks = get_user_tasks(user_internal_id)
        active_count = len([t for t in tasks if not t[5]])
        completed_count = len([t for t in tasks if t[5]])
        
        stats_text = f"\n📊 **Статистика:**\n• Активные: {active_count}\n• Выполненные: {completed_count}\n• Всего: {len(tasks)}"
    
    await callback.message.edit_text(
        f"📝 **Управление задачами**{stats_text}\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "back_to_date_selection")
async def back_to_date_selection(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    
    quick_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="deadline_today"),
                types.InlineKeyboardButton(text="📅 Завтра", callback_data="deadline_tomorrow")
            ],
            [
                types.InlineKeyboardButton(text="❌ Без дедлайна", callback_data="deadline_none"),
                types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="deadline_custom")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"📅 **Установите дедлайн**\n\n"
        f"• 📝 *Название:* {data['title']}\n"
        f"• 📂 *Категория:* {data['category']}\n\n"
        f"Выберите вариант:",
        reply_markup=quick_kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_deadline_menu")
async def back_to_deadline_menu(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    
    quick_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="deadline_today"),
                types.InlineKeyboardButton(text="📅 Завтра", callback_data="deadline_tomorrow")
            ],
            [
                types.InlineKeyboardButton(text="❌ Без дедлайна", callback_data="deadline_none"),
                types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="deadline_custom")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"📅 **Установите дедлайн**\n\n"
        f"• 📝 *Название:* {data['title']}\n"
        f"• 📂 *Категория:* {data['category']}\n\n"
        f"Выберите вариант:",
        reply_markup=quick_kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_time_selection")
async def back_to_time_selection(callback: types.CallbackQuery, state: FSMContext):

    await ask_deadline_time(callback.message, state)
    await callback.answer()

async def send_task_list(callback, response, task_type):
    nav_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📋 Все задачи", callback_data="my_tasks"),
                types.InlineKeyboardButton(text="🟢 Активные", callback_data="active_tasks"),
                types.InlineKeyboardButton(text="✅ Выполненные", callback_data="completed_tasks")
            ],
            [
                types.InlineKeyboardButton(text="➕ Новая задача", callback_data="add_task"),
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tasks_menu")
            ]
        ]
    )
    
    await callback.message.edit_text(response, reply_markup=nav_kb, parse_mode="Markdown")
    await callback.answer()

def format_task_list(tasks, list_type="all"):

    if not tasks:
        type_texts = {
            "active": "активных задач",
            "completed": "выполненных задач", 
            "today": "задач на сегодня",
            "overdue": "просроченных задач",
            "all": "задач"
        }
        return f"📭 *У вас пока нет {type_texts.get(list_type, 'задач')}*"
    
    type_headers = {
        "active": "🟢 АКТИВНЫЕ ЗАДАЧИ",
        "completed": "✅ ВЫПОЛНЕННЫЕ ЗАДАЧИ", 
        "today": "📅 ЗАДАЧИ НА СЕГОДНЯ",
        "overdue": "⏰ ПРОСРОЧЕННЫЕ ЗАДАЧИ",
        "all": "📋 ВСЕ ЗАДАЧИ"
    }
    
    response = f"{type_headers.get(list_type, '📋 ЗАДАЧИ')}\n\n"
    
    for task in tasks[:15]:
        task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task

        status_emoji = "✅" if completed else "🟢"
        deadline_text = f" | ⏰ {deadline}" if deadline else ""

        response += f"{status_emoji} **{title}**\n"
        response += f"   📂 {category}{deadline_text}\n"
        response += f"   🎫 #{task_id}\n\n"
    
    if len(tasks) > 15:
        response += f"*... и еще {len(tasks) - 15} задач*"
    
    return response

@router.callback_query(F.data.startswith("complete_task_"))
async def complete_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[-1])
    user_internal_id = get_user_id(callback.from_user.id)
    
    success = update_task_status(task_id, completed=True)
    
    if success:
        task = get_task_by_id(user_internal_id, task_id)
        if task:
            response = f"✅ **ЗАДАЧА ВЫПОЛНЕНА!**\n\n"
            response += f"📝 *{task[2]}*\n"
            response += f"📂 Категория: {task[3]}\n"
            response += f"🎫 ID: #{task_id}"
            
            await callback.message.edit_text(response, parse_mode="Markdown")
            await callback.answer("Задача отмечена как выполненная! 🎉")
        else:
            await callback.answer("❌ Ошибка: задача не найдена")
    else:
        await callback.answer("❌ Ошибка при обновлении задачи")

@router.callback_query(F.data.startswith("delete_task_"))
async def delete_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[-1])
    
    delete_task(task_id)
    await callback.message.edit_text("🗑️ **Задача удалена**", parse_mode="Markdown")
    await callback.answer("✅ Задача успешно удалена!")

@router.callback_query(F.data.startswith("reopen_task_"))
async def reopen_task_handler(callback: types.CallbackQuery):

    task_id = int(callback.data.split("_")[-1])
    user_internal_id = get_user_id(callback.from_user.id)
    
    success = update_task_status(task_id, completed=False)
    
    if success:
        task = get_task_by_id(user_internal_id, task_id)
        if task:
            response = f"🔄 **ЗАДАЧА ВОЗВРАЩЕНА В АКТИВНЫЕ!**\n\n"
            response += f"📝 *{task[2]}*\n"
            response += f"📂 Категория: {task[3]}\n"
            response += f"🎫 ID: #{task_id}"
            
            await callback.message.edit_text(response, parse_mode="Markdown")
            await callback.answer("Задача снова активна! 🟢")
        else:
            await callback.answer("❌ Ошибка: задача не найдена")
    else:
        await callback.answer("❌ Ошибка при обновлении задачи")

@router.callback_query(F.data.startswith("edit_task_"))
async def edit_task_handler(callback: types.CallbackQuery, state: FSMContext):

    task_id = int(callback.data.split("_")[-1])
    user_internal_id = get_user_id(callback.from_user.id)
    task = get_task_by_id(user_internal_id, task_id)
    
    if not task:
        await callback.answer("❌ Задача не найдена")
        return
    
    await state.update_data(task_id=task_id, task=task)
    await state.set_state(TaskEditing.selecting_field)
    
    task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task
    status = "Выполнена" if completed else "Активна"
    deadline_text = deadline if deadline else "Не установлен"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📝 Изменить название", callback_data="edit_title"),
                types.InlineKeyboardButton(text="📂 Изменить категорию", callback_data="edit_category")
            ],
            [
                types.InlineKeyboardButton(text="📅 Изменить дедлайн", callback_data="edit_deadline"),
                types.InlineKeyboardButton(text="🔄 Сменить статус", callback_data=f"toggle_status_{task_id}")
            ],
            [
                types.InlineKeyboardButton(text="🗑️ Удалить задачу", callback_data=f"delete_task_{task_id}"),
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="my_tasks")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"**Редактирование задачи #{task_id}**\n\n"
    f"**Название:** {title}\n"
    f"**Категория:** {category}\n"
    f"**Дедлайн:** {deadline_text}\n"
    f"**Статус:** {status}\n\n"
        f"Выберите что изменить:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "edit_title", TaskEditing.selecting_field)
async def start_title_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task = data['task']
    
    await state.set_state(TaskEditing.editing_title)
    
    await callback.message.edit_text(
        f"**Редактирование названия**\n\n"
        f"Текущее название: *{task[2]}*\n\n"
        f"Введите новое название:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_editing")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(TaskEditing.editing_title)
async def process_title_editing(message: types.Message, state: FSMContext):

    data = await state.get_data()
    task_id = data['task_id']
    
    if len(message.text) > 200:
        await message.answer("❌ Слишком длинное название! Максимум 200 символов.")
        return
    
    from database import update_task_title
    success = update_task_title(task_id, message.text)
    
    if success:
        await message.answer(
            f"✅ **Название обновлено**\n\n"
            f"Новое название: *{message.text}*",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📋 К задачам", callback_data="my_tasks")]
            ]),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Ошибка при обновлении названия")
    
    await state.clear()

@router.callback_query(F.data == "edit_category", TaskEditing.selecting_field)
async def start_category_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task = data['task']
    
    await state.set_state(TaskEditing.editing_category)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🎓 Учеба", callback_data="new_category_study"),
                types.InlineKeyboardButton(text="💼 Работа", callback_data="new_category_work")
            ],
            [
                types.InlineKeyboardButton(text="🏠 Личное", callback_data="new_category_personal"),
                types.InlineKeyboardButton(text="🏋️ Здоровье", callback_data="new_category_health")
            ],
            [
                types.InlineKeyboardButton(text="🎉 Развлечения", callback_data="new_category_fun"),
                types.InlineKeyboardButton(text="🔧 Другое", callback_data="new_category_other")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_editing")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"**Изменение категории**\n\n"
        f"Текущая категория: *{task[3]}*\n\n"
        f"Выберите новую категорию:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("new_category_"), TaskEditing.editing_category)
async def process_category_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task_id = data['task_id']
    
    category_map = {
        "new_category_study": "🎓 Учеба",
        "new_category_work": "💼 Работа", 
        "new_category_personal": "🏠 Личное",
        "new_category_health": "🏋️ Здоровье",
        "new_category_fun": "🎉 Развлечения",
        "new_category_other": "🔧 Другое"
    }
    
    new_category = category_map[callback.data]
    
    from database import update_task_category
    success = update_task_category(task_id, new_category)
    
    if success:
        await callback.message.edit_text(
            f"✅ **Категория обновлена**\n\n"
            f"Новая категория: *{new_category}*",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📋 К задачам", callback_data="my_tasks")]
            ]),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при обновлении категории")
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "edit_deadline", TaskEditing.selecting_field)
async def start_deadline_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task = data['task']
    
    await state.set_state(TaskEditing.editing_deadline)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📅 Сегодня", callback_data="new_deadline_today"),
                types.InlineKeyboardButton(text="📅 Завтра", callback_data="new_deadline_tomorrow")
            ],
            [
                types.InlineKeyboardButton(text="❌ Убрать дедлайн", callback_data="new_deadline_none"),
                types.InlineKeyboardButton(text="📅 Выбрать дату", callback_data="new_deadline_custom")
            ],
            [
                types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_editing")
            ]
        ]
    )
    
    current_deadline = task[5] if task[5] else "Не установлен"
    
    await callback.message.edit_text(
        f"**Изменение дедлайна**\n\n"
        f"Текущий дедлайн: *{current_deadline}*\n\n"
        f"Выберите новый дедлайн:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("new_deadline_"), TaskEditing.editing_deadline)
async def process_deadline_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task_id = data['task_id']
    
    now = datetime.now()
    
    if callback.data == "new_deadline_today":
        new_deadline = now.strftime("%d.%m.%y 18:00")
    elif callback.data == "new_deadline_tomorrow":
        tomorrow = now + timedelta(days=1)
        new_deadline = tomorrow.strftime("%d.%m.%y 18:00")
    elif callback.data == "new_deadline_none":
        new_deadline = None
    elif callback.data == "new_deadline_custom":
        await callback.answer("📅 Выбор через календарь будет добавлен в следующем обновлении")
        return
    
    from database import update_task_deadline
    success = update_task_deadline(task_id, new_deadline)
    
    if success:
        deadline_text = new_deadline if new_deadline else "Убран"
        await callback.message.edit_text(
            f"✅ **Дедлайн обновлен**\n\n"
            f"Новый дедлайн: *{deadline_text}*",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📋 К задачам", callback_data="my_tasks")]
            ]),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при обновлении дедлайна")
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_status_"))
async def toggle_task_status(callback: types.CallbackQuery):

    task_id = int(callback.data.replace("toggle_status_", ""))
    user_internal_id = get_user_id(callback.from_user.id)
    task = get_task_by_id(user_internal_id, task_id)
    
    if not task:
        await callback.answer("❌ Задача не найдена")
        return
    
    current_status = task[6]
    new_status = not current_status
    success = update_task_status(task_id, new_status)
    
    if success:
        status_text = "выполнена" if new_status else "активна"
        status_emoji = "✅" if new_status else "⏳"
        
        await callback.message.edit_text(
            f"{status_emoji} **Статус изменен**\n\n"
            f"Задача *{task[2]}* теперь **{status_text}**",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📋 К задачам", callback_data="my_tasks")]
            ]),
            parse_mode="Markdown"
        )
        await callback.answer(f"Задача помечена как {status_text}")
    else:
        await callback.answer("❌ Ошибка при изменении статуса")

@router.callback_query(F.data == "back_to_editing")
async def back_to_editing(callback: types.CallbackQuery, state: FSMContext):

    data = await state.get_data()
    task_id = data['task_id']
    
    await state.clear()
    fake_callback_data = f"edit_task_{task_id}"
    fake_callback = types.CallbackQuery(
        id=callback.id,
        from_user=callback.from_user,
        message=callback.message,
        data=fake_callback_data,
        chat_instance=callback.chat_instance
    )
    await edit_task_handler(fake_callback, state)
    await callback.answer()

@router.callback_query(F.data.startswith("view_task_"))
async def view_single_task(callback: types.CallbackQuery):

    task_id = int(callback.data.split("_")[-1])
    user_internal_id = get_user_id(callback.from_user.id)
    
    if not user_internal_id:
        await callback.message.edit_text("❌ Пользователь не найден. Начните с /start")
        await callback.answer()
        return
    
    task = get_task_by_id(user_internal_id, task_id)
    
    if not task:
        await callback.message.edit_text("❌ Задача не найдена")
        await callback.answer()
        return
    
    task_id, user_id, title, category, tags, deadline, completed, created_at, updated_at = task
    
    status_emoji = "✅ Выполнена" if completed else "🟢 Активна"
    deadline_text = f"⏰ {deadline}" if deadline else "⏰ Не установлен"
    tags_text = f"🏷️ {tags}" if tags else "🏷️ Нет тегов"
    
    response = f"📋 **{title}**\n\n"
    response += f"📊 Статус: {status_emoji}\n"
    response += f"📂 Категория: {category}\n"
    response += f"📅 Срок: {deadline_text}\n"
    response += f"{tags_text}\n\n"
    
    keyboard = []
    
    if not completed:
        keyboard.append([types.InlineKeyboardButton(text="✅ Отметить выполненной", callback_data=f"complete_task_{task_id}")])
    else:
        keyboard.append([types.InlineKeyboardButton(text="🔄 Вернуть в активные", callback_data=f"reopen_task_{task_id}")])
    
    keyboard.extend([
        [types.InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_task_{task_id}")],
        [types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_task_{task_id}")],
        [types.InlineKeyboardButton(text="🔙 К списку задач", callback_data="my_tasks")]
    ])
    
    nav_kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(response, reply_markup=nav_kb, parse_mode="Markdown")
    await callback.answer()
