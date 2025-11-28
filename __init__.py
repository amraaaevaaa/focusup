from .tasks import router as tasks_router
from .pomodoro import router as pomodoro_router
from .stats import router as stats_router
from .help import router as help_router
from .kalendar import router as kalendar_router
from .ai import router as ai_router

__all__ = [
    'tasks_router',
    'pomodoro_router', 
    'stats_router',
    'help_router',
    'kalendar_router',
    'ai_router'
]