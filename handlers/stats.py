from aiogram import Router, types, F
from aiogram.filters import Command
from database import get_user_stats, get_user_pomodoro_stats, get_user_id

router = Router()

@router.message(F.text == "📊 Статистика")
@router.message(Command("stats"))
async def show_stats(message: types.Message):

    user_internal_id = get_user_id(message.from_user.id)
    
    if not user_internal_id:
        await message.answer("❌ Сначала создайте задачу через /start")
        return
    
    user_stats = get_user_stats(user_internal_id)
    pomodoro_stats = get_user_pomodoro_stats(user_internal_id)
    
    stats_text = "📊 **Ваша статистика**\n\n"
    
    stats_text += "📋 **Задачи:**\n"
    stats_text += f"• Всего задач: {user_stats['total_tasks']}\n"
    stats_text += f"• Выполнено: {user_stats['completed_tasks']}\n"
    stats_text += f"• Активные: {user_stats['active_tasks']}\n"
    stats_text += f"• Просроченные: {user_stats['overdue_tasks']}\n"
    stats_text += f"• Процент выполнения: {user_stats['completion_rate']}%\n\n"
    
    stats_text += "🍅 **Pomodoro:**\n"
    stats_text += f"• Всего сессий: {pomodoro_stats['total_sessions']}\n"
    stats_text += f"• Общее время: {pomodoro_stats['total_duration_minutes']} мин\n"
    stats_text += f"• Средняя сессия: {pomodoro_stats['avg_duration_minutes']} мин\n\n"
    
    if user_stats['categories']:
        stats_text += "📂 **Распределение по категориям:**\n"
        for category, count in user_stats['categories'].items():
            stats_text += f"• {category}: {count}\n"
    
    await message.answer(stats_text, parse_mode="Markdown")
