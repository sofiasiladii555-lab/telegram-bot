from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, unique=True)
    full_name = Column(String)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    due_date = Column(DateTime, nullable=False)
    user_tg_id = Column(Integer, nullable=False)
    task_type = Column(String)
    description = Column(Text)
    week = Column(String)
    reminder_sent_14 = Column(Boolean, default=False)
    reminder_sent_7 = Column(Boolean, default=False)
    reminder_sent_1 = Column(Boolean, default=False)
    reminder_sent_2h = Column(Boolean, default=False)

class Duty(Base):
    __tablename__ = "duties"
    id = Column(Integer, primary_key=True)
    duty_date = Column(DateTime, nullable=False)
    reminder_sent = Column(Boolean, default=False)

_db_dir = "/data" if os.path.isdir("/data") else "."
engine = create_engine(f"sqlite:///{_db_dir}/duties.db", echo=False)
Session = sessionmaker(bind=engine)

def init_db():
    # Создаёт новые таблицы (существующие не трогает)
    Base.metadata.create_all(engine)

    # Миграция: добавляем новый столбец reminder_sent_2h если его нет
    with engine.connect() as conn:
        existing = [
            row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))
        ]
        if "reminder_sent_2h" not in existing:
            conn.execute(text(
                "ALTER TABLE tasks ADD COLUMN reminder_sent_2h BOOLEAN DEFAULT 0"
            ))
            conn.commit()
