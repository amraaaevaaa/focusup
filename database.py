import sqlite3
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('focusup.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT,
            deadline TEXT,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN tags TEXT')
        logger.info("✅ Добавлено поле tags")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            logger.info("ℹ️ Поле tags уже существует")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            task_id INTEGER,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pomodoro_user_id ON pomodoro_sessions(user_id)')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована с правильными связями")

def get_connection():
    return sqlite3.connect('focusup.db', check_same_thread=False)

def get_user_id_by_telegram_id(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске пользователя {telegram_id}: {e}")
        return None
    finally:
        conn.close()

def add_user(telegram_id, username=None, first_name=None, last_name=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name) 
            VALUES (?, ?, ?, ?)
        ''', (telegram_id, username, first_name, last_name))
        conn.commit()
        
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        user_id = result[0] if result else None
        
        logger.info(f"✅ Пользователь добавлен: {telegram_id} -> ID: {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении пользователя {telegram_id}: {e}")
        return None
    finally:
        conn.close()


def add_task(user_id, title, category='general', tags=None, deadline=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        logger.info(f"🔍 DEBUG add_task: adding task '{title}' for user_id={user_id} (type: {type(user_id)})")
        cursor.execute('''
            INSERT INTO tasks (user_id, title, category, tags, deadline) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, title, category, tags, deadline))
        task_id = cursor.lastrowid
        conn.commit()
        logger.info(f"✅ Задача добавлена: ID {task_id} для пользователя {user_id}")
        return task_id
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении задачи: {e}")
        return None
    finally:
        conn.close()

def get_user_tasks(user_id, include_completed=True):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        logger.info(f"🔍 DEBUG get_user_tasks: searching for tasks with user_id={user_id} (type: {type(user_id)})")
        if include_completed:
            cursor.execute('''
                SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
                WHERE user_id = ? 
                ORDER BY 
                    completed ASC,
                    CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
                    deadline ASC,
                    created_at DESC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
                WHERE user_id = ? AND completed = FALSE
                ORDER BY 
                    CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
                    deadline ASC,
                    created_at DESC
            ''', (user_id,))
        
        tasks = cursor.fetchall()
        logger.info(f"📋 Получено {len(tasks)} задач для пользователя {user_id}")
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении задач: {e}")
        return []
    finally:
        conn.close()

def get_active_tasks(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
            WHERE user_id = ? AND completed = 0 
            ORDER BY 
                CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
                deadline ASC,
                created_at DESC
        ''', (user_id,))
        tasks = cursor.fetchall()
        logger.info(f"🟢 Получено {len(tasks)} активных задач для пользователя {user_id}")
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении активных задач: {e}")
        return []
    finally:
        conn.close()

def get_completed_tasks(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
            WHERE user_id = ? AND completed = 1 
            ORDER BY created_at DESC
        ''', (user_id,))
        tasks = cursor.fetchall()
        logger.info(f"✅ Получено {len(tasks)} выполненных задач для пользователя {user_id}")
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении выполненных задач: {e}")
        return []
    finally:
        conn.close()

def get_user_id(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        user_id = result[0] if result else None
        logger.info(f"🔍 Поиск user_id для {telegram_id}: {user_id}")
        return user_id
    except Exception as e:
        logger.error(f"❌ Ошибка при получении user_id: {e}")
        return None
    finally:
        conn.close()

def update_task_status(task_id: int, completed: bool) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE tasks 
            SET completed = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (completed, task_id))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            status = "выполнена" if completed else "активна"
            logger.info(f"✅ Статус задачи {task_id} изменен на '{status}'")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении статуса задачи: {e}")
        return False
    finally:
        conn.close()

def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"🗑️ Задача {task_id} удалена")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении задачи: {e}")
        return False
    finally:
        conn.close()

def get_task_by_id(user_id, task_id):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
        task = cursor.fetchone()
        return task
    except Exception as e:
        logger.error(f"❌ Ошибка при получении задачи по ID: {e}")
        return None
    finally:
        conn.close()

def get_tasks_by_date(user_id, date):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        date_str = date.strftime('%d.%m.%y')
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = ? AND deadline LIKE ?
            ORDER BY deadline
        ''', (user_id, f'{date_str}%'))
        
        tasks = cursor.fetchall()
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении задач по дате: {e}")
        return []
    finally:
        conn.close()

def add_pomodoro_session(user_id, duration, task_id=None):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO pomodoro_sessions (user_id, duration, task_id) 
            VALUES (?, ?, ?)
        ''', (user_id, duration, task_id))
        
        conn.commit()
        session_id = cursor.lastrowid
        logger.info(f"🍅 Pomodoro сессия добавлена: ID {session_id}")
        return session_id
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении Pomodoro сессии: {e}")
        return None
    finally:
        conn.close()

def get_user_pomodoro_stats(user_id, days=30):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM pomodoro_sessions WHERE user_id = ?', (user_id,))
        total_sessions = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(duration) FROM pomodoro_sessions WHERE user_id = ?', (user_id,))
        total_duration = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT DATE(completed_at), COUNT(*), SUM(duration)
            FROM pomodoro_sessions 
            WHERE user_id = ? AND completed_at >= date('now', ?)
            GROUP BY DATE(completed_at)
            ORDER BY DATE(completed_at) DESC
        ''', (user_id, f'-{days} days'))
        sessions_by_date = cursor.fetchall()
        
        avg_duration = total_duration / total_sessions if total_sessions > 0 else 0
        
        return {
            'total_sessions': total_sessions,
            'total_duration_seconds': total_duration,
            'total_duration_minutes': total_duration // 60,
            'avg_duration_minutes': round(avg_duration / 60, 1),
            'sessions_by_date': sessions_by_date
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при получении статистики Pomodoro: {e}")
        return {
            'total_sessions': 0,
            'total_duration_seconds': 0,
            'total_duration_minutes': 0,
            'avg_duration_minutes': 0,
            'sessions_by_date': []
        }
    finally:
        conn.close()

def get_user_stats(user_id):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ?', (user_id,))
        total_tasks = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = TRUE', (user_id,))
        completed_tasks = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT category, COUNT(*) 
            FROM tasks 
            WHERE user_id = ? 
            GROUP BY category
        ''', (user_id,))
        categories = cursor.fetchall()
        
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = FALSE', (user_id,))
        active_tasks = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM tasks 
            WHERE user_id = ? AND completed = FALSE AND deadline IS NOT NULL
            AND datetime(deadline) < datetime('now')
        ''', (user_id,))
        overdue_tasks = cursor.fetchone()[0] or 0
        
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        cursor.execute('''
            SELECT MAX(updated_at) FROM tasks 
            WHERE user_id = ? AND updated_at IS NOT NULL
        ''', (user_id,))
        last_activity = cursor.fetchone()[0]
        
        return {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'active_tasks': active_tasks,
            'overdue_tasks': overdue_tasks,
            'completion_rate': round(completion_rate, 1),
            'categories': dict(categories),
            'last_activity': last_activity
        }
    except Exception as e:
        logger.error(f"❌ Ошибка при получении статистики пользователя: {e}")
        return {
            'total_tasks': 0,
            'completed_tasks': 0,
            'active_tasks': 0,
            'overdue_tasks': 0,
            'completion_rate': 0,
            'categories': {},
            'last_activity': None
        }
    finally:
        conn.close()

def get_today_tasks(user_id):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        today = datetime.now().strftime('%d.%m.%y')
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = ? AND deadline LIKE ? AND completed = FALSE
            ORDER BY deadline
        ''', (user_id, f'{today}%'))
        
        tasks = cursor.fetchall()
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении сегодняшних задач: {e}")
        return []
    finally:
        conn.close()

def update_task_deadline(task_id, new_deadline):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE tasks 
            SET deadline = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_deadline, task_id))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"📅 Дедлайн задачи {task_id} обновлен")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении дедлайна: {e}")
        return False
    finally:
        conn.close()

def update_task_title(task_id: int, new_title: str) -> bool:

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE tasks 
            SET title = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_title, task_id))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"📝 Название задачи {task_id} обновлено")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении названия задачи: {e}")
        return False
    finally:
        conn.close()

def update_task_category(task_id: int, new_category: str) -> bool:

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE tasks 
            SET category = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_category, task_id))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"📂 Категория задачи {task_id} изменена на '{new_category}'")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении категории задачи: {e}")
        return False
    finally:
        conn.close()

def get_upcoming_tasks(user_id, days=7):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        end_date = (datetime.now() + timedelta(days=days)).strftime('%d.%m.%y')
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = ? AND completed = FALSE AND deadline IS NOT NULL
            AND deadline <= ?
            ORDER BY deadline
        ''', (user_id, end_date))
        
        tasks = cursor.fetchall()
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении предстоящих задач: {e}")
        return []
    finally:
        conn.close()

def search_tasks(user_id, query):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = ? AND title LIKE ? 
            ORDER BY created_at DESC
        ''', (user_id, f'%{query}%'))
        
        tasks = cursor.fetchall()
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске задач: {e}")
        return []
    finally:
        conn.close()

def get_user_by_telegram_id(telegram_id):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        return user
    except Exception as e:
        logger.error(f"❌ Ошибка при получении пользователя: {e}")
        return None
    finally:
        conn.close()

def update_task_tags(task_id: int, new_tags: str) -> bool:

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE tasks 
            SET tags = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_tags, task_id))
        conn.commit()
        success = cursor.rowcount > 0
        if success:
            logger.info(f"✅ Теги задачи {task_id} обновлены")
        return success
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении тегов задачи: {e}")
        return False
    finally:
        conn.close()

def search_tasks_by_tags(user_id, tag):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
            WHERE user_id = ? AND tags LIKE ? 
            ORDER BY created_at DESC
        ''', (user_id, f'%{tag}%'))
        
        tasks = cursor.fetchall()
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске задач по тегам: {e}")
        return []
    finally:
        conn.close()

def get_overdue_tasks(user_id):

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id, user_id, title, category, tags, deadline, completed, created_at, updated_at FROM tasks 
            WHERE user_id = ? AND completed = FALSE AND deadline IS NOT NULL
            AND datetime(deadline) < datetime('now')
            ORDER BY deadline ASC
        ''', (user_id,))
        
        tasks = cursor.fetchall()
        logger.info(f"⏰ Получено {len(tasks)} просроченных задач для пользователя {user_id}")
        return tasks
    except Exception as e:
        logger.error(f"❌ Ошибка при получении просроченных задач: {e}")
        return []
    finally:
        conn.close()