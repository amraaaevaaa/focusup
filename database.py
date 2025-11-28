# database.py
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, date

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, func
)
from sqlalchemy.orm import sessionmaker, declarative_base

# ===============================
#    DATABASE URL (Postgres / SQLite)
# ===============================
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
else:
    engine = create_engine(
        "sqlite:///focusup.db",
        connect_args={"check_same_thread": False},
        future=True
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# ===============================
# MODELS
# ===============================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(256))
    first_name = Column(String(256))
    last_name = Column(String(256))


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    title = Column(String(512))
    category = Column(String(128))
    deadline = Column(String(64))  # stored as string in legacy project
    tags = Column(String(256))
    completed = Column(Boolean, server_default="false", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ===============================
# INIT
# ===============================
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


# ===============================
# HELPERS (internal)
# ===============================
def _task_to_dict(r: Task) -> Dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "title": r.title,
        "category": r.category,
        "deadline": r.deadline,
        "tags": r.tags,
        "completed": bool(r.completed),
        "created_at": r.created_at
    }

def _extract_date_from_deadline(deadline_str: Optional[str]) -> Optional[date]:
    """
    Попытка извлечь дату из строки deadline.
    Поддерживает форматы вида:
      - "DD.MM.YY HH:MM"
      - "DD.MM.YYYY HH:MM"
      - "DD.MM.YY"
      - "DD.MM.YYYY"
    Возвращает datetime.date или None.
    """
    if not deadline_str:
        return None

    # ищем шаблон dd.mm.yy или dd.mm.yyyy
    m = re.search(r'(\b\d{1,2}\.\d{1,2}\.\d{2,4}\b)', deadline_str)
    if not m:
        return None
    date_part = m.group(1)

    # Попробуем несколько форматов
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            dt = datetime.strptime(date_part, fmt)
            return dt.date()
        except Exception:
            continue
    return None


# ===============================
# USER HELPERS
# ===============================
def add_user(tg_id: int, username: Optional[str] = None,
             first_name: Optional[str] = None, last_name: Optional[str] = None) -> int:
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        if user:
            return user.id
        new_user = User(tg_id=tg_id, username=username, first_name=first_name, last_name=last_name)
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return new_user.id
    finally:
        session.close()


def get_user_id(tg_id: int) -> Optional[int]:
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        return user.id if user else None
    finally:
        session.close()


# ===============================
# TASK HELPERS
# ===============================
def add_task(user_id: int, title: str, category: str = "Общие",
             deadline: Optional[str] = None, tags: Optional[str] = None) -> int:
    session = get_session()
    try:
        task = Task(user_id=user_id, title=title, category=category, deadline=deadline, tags=tags)
        session.add(task)
        session.commit()
        session.refresh(task)
        return task.id
    finally:
        session.close()


def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return None
        return _task_to_dict(task)
    finally:
        session.close()


def get_user_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).order_by(Task.created_at.desc()).all()
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_active_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id, completed=False).order_by(Task.created_at.desc()).all()
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_completed_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id, completed=True).order_by(Task.created_at.desc()).all()
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_today_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает задачи, у которых дедлайн совпадает с сегодняшней датой.
    Сравнение делается по дате, извлечённой из поля deadline (строка).
    """
    today = datetime.utcnow().date()  # используем UTC; если нужен другой TZ — скажи
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).all()
        result = []
        for r in rows:
            d = _extract_date_from_deadline(r.deadline)
            if d and d == today:
                result.append(_task_to_dict(r))
        # сортируем по created_at desc
        result.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
        return result
    finally:
        session.close()


def update_task(task_id: int, **fields) -> bool:
    allowed = {"title", "category", "deadline", "tags", "completed"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return False

    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return False
        for k, v in data.items():
            if k == "completed":
                setattr(task, k, bool(v))
            else:
                setattr(task, k, v)
        session.commit()
        return True
    finally:
        session.close()


def update_task_status(task_id: int, completed: bool = True) -> bool:
    return update_task(task_id, completed=completed)


def delete_task(task_id: int) -> bool:
    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return False
        session.delete(task)
        session.commit()
        return True
    finally:
        session.close()


# ===============================
# STATS
# ===============================
def get_user_stats(user_internal_id: int) -> Dict[str, int]:
    session = get_session()
    try:
        total = session.query(Task).filter_by(user_id=user_internal_id).count()
        completed = session.query(Task).filter_by(user_id=user_internal_id, completed=True).count()
        active = total - completed
        return {"total_tasks": total, "active_tasks": active, "completed_tasks": completed}
    finally:
        session.close()
