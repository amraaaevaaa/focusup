import os
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, func
)
from sqlalchemy.orm import sessionmaker, declarative_base

# Получаем DATABASE_URL из окружения; если его нет — используем sqlite файл
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Render иногда даёт postgres:// — SQLAlchemy требует postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True
    )
else:
    # локальная SQLite для разработки
    engine = create_engine(
        "sqlite:///focusup.db",
        connect_args={"check_same_thread": False},
        future=True
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


# ================================
# MODELS
# ================================
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
    deadline = Column(String(64))
    tags = Column(String(256))
    completed = Column(Boolean, server_default="false", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ================================
# DB INIT
# ================================
def init_db():
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


# ================================
# USER HELPERS
# ================================
def add_user(tg_id, username=None, first_name=None, last_name=None):
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


def get_user_id(tg_id):
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        return user.id if user else None
    finally:
        session.close()


# ================================
# TASK HELPERS
# ================================
def add_task(user_id, title, category="Общие", deadline=None, tags=None):
    session = get_session()
    try:
        task = Task(
            user_id=user_id,
            title=title,
            category=category,
            deadline=deadline,
            tags=tags
        )
        session.add(task)
        session.commit()
        return task.id
    finally:
        session.close()


def get_user_tasks(user_internal_id):
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "category": r.category,
                "deadline": r.deadline,
                "tags": r.tags,
                "completed": r.completed,
            }
            for r in rows
        ]
    finally:
        session.close()


# ================================
# STATISTICS
# ================================
def get_user_stats(user_internal_id):
    session = get_session()
    try:
        total = session.query(Task).filter_by(user_id=user_internal_id).count()
        completed = session.query(Task).filter_by(
            user_id=user_internal_id,
            completed=True
        ).count()
        active = total - completed

        return {
            "total_tasks": total,
            "active_tasks": active,
            "completed_tasks": completed
        }

    finally:
        session.close()


# ================================
# UPDATE STATUS
# ================================
def update_task_status(task_id: int, completed: bool = True) -> bool:
    session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            return False

        task.completed = bool(completed)
        session.commit()
        return True
    finally:
        session.close()
