# database.py
import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Boolean, func
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Получаем DATABASE_URL из окружения; если его нет — используем sqlite файл
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Render может дать postgres:// — SQLAlchemy предпочитает postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, future=True)
else:
    engine = create_engine("sqlite:///focusup.db", connect_args={"check_same_thread": False}, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# --- Models (адаптированы под простой прежний интерфейс) ---
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
    user_id = Column(Integer, nullable=False)  # internal user id
    title = Column(String(512))
    category = Column(String(128))
    deadline = Column(String(64))  # keep as string for simplicity
    tags = Column(String(256))
    completed = Column(Boolean, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()

# --- Convenience functions used in code (names сохранены как в старом проекте) ---
def add_user(tg_id, username=None, first_name=None, last_name=None):
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        if user:
            return user.id
        new = User(tg_id=tg_id, username=username, first_name=first_name, last_name=last_name)
        session.add(new)
        session.commit()
        session.refresh(new)
        return new.id
    finally:
        session.close()

def get_user_id(tg_id):
    session = get_session()
    try:
        user = session.query(User).filter_by(tg_id=tg_id).first()
        return user.id if user else None
    finally:
        session.close()

def add_task(user_id, title, category="Общие", deadline=None, tags=None):
    session = get_session()
    try:
        t = Task(user_id=user_id, title=title, category=category, deadline=deadline, tags=tags)
        session.add(t)
        session.commit()
        t_id = t.id
        return t_id
    finally:
        session.close()

def get_user_tasks(user_internal_id):
    session = get_session()
    try:
        rows = session.query(Task).filter_by(user_id=user_internal_id).all()
        return [ {"id": r.id, "title": r.title, "category": r.category, "deadline": r.deadline, "tags": r.tags, "completed": r.completed} for r in rows ]
    finally:
        session.close()
