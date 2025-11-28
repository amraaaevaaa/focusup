from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime, timedelta
from database import get_user_tasks
import logging
import calendar as cal_lib

router = Router()
logger = logging.getLogger(__name__)

user_calendars = {}

def parse_deadline(deadline_str):
    if not deadline_str:
        return None
    
    try:
        formats = ['%d.%m.%y %H:%M', '%d.%m.%Y %H:%M', '%d.%m.%y', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
        
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(deadline_str, fmt)
                
                if parsed_date.year < 1950:
                    parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                
                return parsed_date
            except ValueError:
                continue
        return None
    except Exception:
        return None

def get_tasks_for_date(telegram_user_id, target_date):
    from database import get_user_id_by_telegram_id
    
    user_id = get_user_id_by_telegram_id(telegram_user_id)
    if not user_id:
        return []
    
    tasks = get_user_tasks(user_id)
    date_tasks = []
    
    for task in tasks:
        if len(task) >= 6 and task[5]:
            deadline_str = task[5]
            deadline_date = parse_deadline(deadline_str)
            
            if deadline_date:
                parsed_date = deadline_date.date()
                if parsed_date == target_date:
                    date_tasks.append(task)
    
    return date_tasks

def get_date_status(telegram_user_id, target_date):
    tasks = get_tasks_for_date(telegram_user_id, target_date)
    
    if not tasks:
        return None
    
    total = len(tasks)
    completed = sum(1 for task in tasks if task[6])
    overdue = 0
    
    now = datetime.now()
    for task in tasks:
        if not task[6] and task[5]:
            deadline_date = parse_deadline(task[5])
            if deadline_date and deadline_date < now:
                overdue += 1
    
    return {
        'total': total,
        'completed': completed,
        'overdue': overdue,
        'pending': total - completed
    }

def get_day_emoji_and_count(telegram_user_id, target_date):
    today = datetime.now().date()
    status = get_date_status(telegram_user_id, target_date)
    
    if not status:
        if target_date == today:
            return "🔵", ""
        else:
            return "", ""
    
    count = status['total']
    
    if status['overdue'] > 0:
        return "🔴", str(count)
    elif status['completed'] == status['total']:
        return "✅", str(count)
    elif status['completed'] > 0:
        return "🟡", str(count)
    else:
        return "⏳", str(count)

def get_month_statistics(telegram_user_id, month, year):
    days_in_month = cal_lib.monthrange(year, month)[1]
    
    total_days = 0
    total_tasks = 0
    completed_tasks = 0
    overdue_tasks = 0
    
    for day in range(1, days_in_month + 1):
        date_obj = datetime(year, month, day).date()
        status = get_date_status(telegram_user_id, date_obj)
        
        if status:
            total_days += 1
            total_tasks += status['total']
            completed_tasks += status['completed']
            overdue_tasks += status['overdue']
    
    return {
        'total_days': total_days,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks
    }

def generate_calendar_header(month, year, telegram_user_id):
    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    
    today = datetime.now()
    is_current_month = (month == today.month and year == today.year)
    
    month_stats = get_month_statistics(telegram_user_id, month, year)
    
    header = f"📅 **Календарь задач - {month_names[month]} {year}**\n\n"
    
    if is_current_month:
        header += f"📍 **Сегодня:** {today.strftime('%d.%m.%Y')}\n"
        today_status = get_date_status(telegram_user_id, today.date())
        if today_status:
            header += f"   📋 Задач на сегодня: {today_status['total']}\n"
            if today_status['overdue'] > 0:
                header += f"   ⚠️ Просрочено: {today_status['overdue']}\n"
        else:
            header += f"   ✨ На сегодня задач нет!\n"
        header += "\n"
    
    if month_stats['total_days'] > 0:
        header += f"📊 **Статистика месяца:**\n"
        header += f"• Дней с задачами: {month_stats['total_days']}\n"
        header += f"• Всего задач: {month_stats['total_tasks']}\n"
        header += f"• Выполнено: {month_stats['completed_tasks']}\n"
        if month_stats['overdue_tasks'] > 0:
            header += f"• ⚠️ Просрочено: {month_stats['overdue_tasks']}\n"
        header += "\n"
    
    
    return header

def create_calendar_keyboard(telegram_user_id, month, year):
    cal = cal_lib.monthcalendar(year, month)
    keyboard = []
    

    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    header_row = []
    for day in week_days:
        header_row.append(types.InlineKeyboardButton(text=day, callback_data="ignore"))
    keyboard.append(header_row)
    
    for week in cal:
        week_row = []
        for day in week:
            if day == 0:
                week_row.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                current_date = datetime(year, month, day).date()
                emoji, count = get_day_emoji_and_count(telegram_user_id, current_date)
                
                if emoji:
                    if count:
                        button_text = f"{day}\n{emoji}{count}"
                    else:
                        button_text = f"{day}\n{emoji}"
                else:
                    button_text = str(day)
                
                week_row.append(
                    types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"cal_day_{year}_{month}_{day}"
                    )
                )
        keyboard.append(week_row)
    
    nav_row = []
    
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1
    nav_row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"cal_prev_{prev_month}_{prev_year}"))

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    current_month_name = month_names[month]
    nav_row.append(types.InlineKeyboardButton(text=current_month_name, callback_data="cal_today"))

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year = year + 1
    nav_row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"cal_next_{next_month}_{next_year}"))
    
    keyboard.append(nav_row)
    
    extra_row = [
        types.InlineKeyboardButton(text="📋 Все задачи", callback_data="cal_all_tasks"),
        types.InlineKeyboardButton(text="➕ Новая", callback_data="cal_add_task")
    ]
    keyboard.append(extra_row)
    
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(F.text == "📅 Календарь")
async def calendar_menu(message: types.Message):
    try:
        user_id = message.from_user.id
        current_date = datetime.now()
        
        user_calendars[user_id] = {
            'current_month': current_date.month,
            'current_year': current_date.year
        }
        
        await show_calendar(message, user_id)
    except Exception as e:
        logger.error(f"Ошибка в calendar_menu: {e}")
        await message.answer("❌ Ошибка при открытии календаря")

async def show_calendar(message: types.Message, user_id, edit_message=False):
    try:
        month = user_calendars[user_id]['current_month']
        year = user_calendars[user_id]['current_year']
        
        calendar_text = generate_calendar_header(month, year, user_id)
        keyboard = create_calendar_keyboard(user_id, month, year)
        
        if edit_message:
            try:
                await message.edit_text(calendar_text, reply_markup=keyboard, parse_mode="Markdown")
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    pass
                else:
                    raise edit_error
        else:
            await message.answer(calendar_text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"Ошибка в show_calendar: {e}")
        if not edit_message:
            await message.answer("❌ Ошибка при загрузке календаря")

@router.callback_query(F.data.startswith("cal_day_"))
async def calendar_day_handler(callback: types.CallbackQuery):
    try:
        _, _, year, month, day = callback.data.split('_')
        year = int(year)
        month = int(month)
        day = int(day)
        
        selected_date = datetime(year, month, day)
        user_id = callback.from_user.id
        
        day_tasks = get_tasks_for_date(user_id, selected_date.date())
        
        if day_tasks:
            tasks_text = f"📅 **Задачи на {selected_date.strftime('%d.%m.%Y')}**\n\n"
            
            for i, task in enumerate(day_tasks, 1):
                task_id, _, title, category, tags, deadline, completed, _, _ = task
                
                status_emoji = "✅" if completed else "⏳"
                time_str = ""
                
                if deadline:
                    deadline_dt = parse_deadline(deadline)
                    if deadline_dt:
                        time_str = f" в {deadline_dt.strftime('%H:%M')}"
                
                tasks_text += f"{i}. {status_emoji} **{title}**{time_str}\n"
                tasks_text += f"   📁 {category}"
                
                if tags:
                    tasks_text += f" | 🏷️ {tags}"
                
                if not completed and deadline:
                    deadline_dt = parse_deadline(deadline)
                    if deadline_dt and deadline_dt < datetime.now():
                        tasks_text += f"\n   🚨 **ПРОСРОЧЕНО!**"
                
                tasks_text += "\n\n"
                
        else:
            tasks_text = f"🎉 **На {selected_date.strftime('%d.%m.%Y')} задач нет!**\n\n"
            tasks_text += "Можете отдохнуть или запланировать что-то новое! 😊"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="↩️ К календарю", callback_data="cal_back"),
                    types.InlineKeyboardButton(text="➕ Добавить", callback_data="cal_add_task")
                ]
            ]
        )
        
        try:
            await callback.message.edit_text(tasks_text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error):
                raise edit_error
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в calendar_day_handler: {e}")
        await callback.answer("❌ Ошибка при загрузке задач")

@router.callback_query(F.data == "cal_back")
async def back_to_calendar(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await show_calendar(callback.message, user_id, edit_message=True)
    await callback.answer()

@router.callback_query(F.data.startswith("cal_prev_"))
async def calendar_prev_month(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        _, _, month, year = callback.data.split('_')
        month = int(month)
        year = int(year)
        
        user_calendars[user_id]['current_month'] = month
        user_calendars[user_id]['current_year'] = year
        
        await show_calendar(callback.message, user_id, edit_message=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка перехода к предыдущему месяцу: {e}")
        await callback.answer("❌ Ошибка при переходе")

@router.callback_query(F.data.startswith("cal_next_"))
async def calendar_next_month(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        _, _, month, year = callback.data.split('_')
        month = int(month)
        year = int(year)
        
        user_calendars[user_id]['current_month'] = month
        user_calendars[user_id]['current_year'] = year
        
        await show_calendar(callback.message, user_id, edit_message=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка перехода к следующему месяцу: {e}")
        await callback.answer("❌ Ошибка при переходе")

@router.callback_query(F.data == "cal_today")
async def calendar_today(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        current_date = datetime.now()
        
        user_calendars[user_id]['current_month'] = current_date.month
        user_calendars[user_id]['current_year'] = current_date.year
        
        await show_calendar(callback.message, user_id, edit_message=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка возврата к сегодня: {e}")
        await callback.answer("❌ Ошибка при переходе")

@router.callback_query(F.data == "cal_all_tasks")
async def show_all_tasks_from_calendar(callback: types.CallbackQuery):
    from .tasks import show_my_tasks_list
    await show_my_tasks_list(callback)
    await callback.answer()

@router.callback_query(F.data == "cal_add_task")
async def add_task_from_calendar(callback: types.CallbackQuery):
    from .tasks import tasks_main_menu
    await tasks_main_menu(callback.message)
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_handler(callback: types.CallbackQuery):

    await callback.answer()