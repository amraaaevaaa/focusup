# database.py
import os
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, func
)
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------- Config ----------
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

# ---------- Models ----------
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
    user_id = Column(Integer, nullable=False)  # internal user id (users.id)
    title = Column(String(512))
    category = Column(String(128))
    deadline = Column(String(64))
    tags = Column(String(256))
    completed = Column(Boolean, server_default="false", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------- DB Init ----------
def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


# ---------- User helpers ----------
def add_user(tg_id: int, username: Optional[str] = None,
             first_name: Optional[str] = None, last_name: Optional[str] = None) -> int:
    """
    Add user if not exists. Returns internal user id.
    """
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
    """
    Return internal user id by telegram id or None.
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        return user.id if user else None
    finally:
        session.close()


# ---------- Task helpers ----------
def add_task(user_id: int, title: str, category: str = "Общие",
             deadline: Optional[str] = None, tags: Optional[str] = None) -> int:
    """
    Create and return new task id.
    """
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
    """
    Return task dict or None.
    """
    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return None
        return {
            "id": task.id,
            "user_id": task.user_id,
            "title": task.title,
            "category": task.category,
            "deadline": task.deadline,
            "tags": task.tags,
            "completed": bool(task.completed),
            "created_at": task.created_at
        }
    finally:
        session.close()


def get_user_tasks(user_internal_id: int) -> List[Dict[str, Any]]:
    """
    Return list of task dicts for a user.
    """
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).order_by(Task.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "category": r.category,
                "deadline": r.deadline,
                "tags": r.tags,
                "completed": bool(r.completed),
                "created_at": r.created_at
            }
            for r in rows
        ]
    finally:
        session.close()


def update_task(task_id: int, **fields) -> bool:
    """
    Update arbitrary fields of a task. Allowed keys: title, category, deadline, tags, completed.
    Returns True if updated, False if task not found.
    Example: update_task(5, title="New", deadline="01.01.25")
    """
    allowed = {"title", "category", "deadline", "tags", "completed"}
    update_data = {k: v for k, v in fields.items() if k in allowed}
    if not update_data:
        return False

    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return False
        for k, v in update_data.items():
            if k == "completed":
                setattr(task, k, bool(v))
            else:
                setattr(task, k, v)
        session.commit()
        return True
    finally:
        session.close()


def update_task_status(task_id: int, completed: bool = True) -> bool:
    """
    Shortcut to mark task completed/uncompleted.
    Returns True if updated, False if not found.
    """
    return update_task(task_id, completed=completed)


def delete_task(task_id: int) -> bool:
    """
    Delete task by id. Returns True if deleted, False if not found.
    """
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


# ---------- Stats ----------
def get_user_stats(user_internal_id: int) -> Dict[str, int]:
    """
    Return basic stats for user:
      { "total_tasks": int, "active_tasks": int, "completed_tasks": int }
    """
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
