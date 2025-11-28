# database.py
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, func, ForeignKey, text
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

# NOTE: removed deprecated `autocommit` arg; use `future=True` and explicit commits.
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True, expire_on_commit=False)
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
    # связка на users.id — полезно для целостности
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(512))
    category = Column(String(128))
    # храню строкой (как у вас было) — парсинг даты делает helper
    deadline = Column(String(64))
    tags = Column(String(256))
    # Для совместимости с SQLite/PG: используем server_default как текст и python default
    completed = Column(Boolean, nullable=False, server_default=text('0'), default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# ===============================
# INIT
# ===============================
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


# ===============================
# INTERNAL HELPERS
# ===============================
def _task_to_dict(r: Task) -> Dict[str, Any]:
    if r is None:
        return None
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
    Ищет дату в строке deadline ("dd.mm.yy", "dd.mm.yyyy", опционально + время).
    """
    if not deadline_str:
        return None

    m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', deadline_str)
    if not m:
        return None

    date_part = m.group(1)

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
def add_user(tg_id: int, username=None, first_name=None, last_name=None) -> int:
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        if user:
            return user.id

        new_user = User(
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
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
def add_task(user_id: int, title: str, category="Общие",
             deadline=None, tags=None) -> int:
    session = get_session()
    try:
        t = Task(user_id=user_id, title=title, category=category,
                 deadline=deadline, tags=tags)
        session.add(t)
        session.commit()
        session.refresh(t)
        return t.id
    finally:
        session.close()


def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    session = get_session()
    try:
        task = session.get(Task, task_id)
        return _task_to_dict(task) if task else None
    finally:
        session.close()


def get_user_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = (
            session.query(Task)
            .filter_by(user_id=user_internal_id)
            .order_by(Task.created_at.desc())
            .all()
        )
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_active_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = (
            session.query(Task)
            .filter_by(user_id=user_internal_id, completed=False)
            .order_by(Task.created_at.desc())
            .all()
        )
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_completed_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        rows = (
            session.query(Task)
            .filter_by(user_id=user_internal_id, completed=True)
            .order_by(Task.created_at.desc())
            .all()
        )
        return [_task_to_dict(r) for r in rows]
    finally:
        session.close()


def get_today_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    today = datetime.utcnow().date()

    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).all()
        result = []

        for r in rows:
            d = _extract_date_from_deadline(r.deadline)
            if d == today:
                result.append(_task_to_dict(r))

        result.sort(key=lambda x: x["created_at"], reverse=True)
        return result
    finally:
        session.close()


def get_upcoming_tasks(user_internal_id: int, days: int = 7) -> List[Dict[str, Any]]:
    today = datetime.utcnow().date()
    end_date = today + timedelta(days=days)

    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).all()
        result = []

        for r in rows:
            d = _extract_date_from_deadline(r.deadline)
            if d and today <= d <= end_date:
                result.append(_task_to_dict(r))

        result.sort(key=lambda x: (
            _extract_date_from_deadline(x["deadline"]) or datetime.max.date(),
            x["created_at"]
        ))
        return result
    finally:
        session.close()


def update_task(task_id: int, **fields) -> bool:
    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return False

        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)

        session.commit()
        return True
    finally:
        session.close()


def update_task_status(task_id: int, completed=True) -> bool:
    return update_task(task_id, completed=bool(completed))


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

        return {
            "total_tasks": total,
            "active_tasks": active,
            "completed_tasks": completed
        }
    finally:
        session.close()
