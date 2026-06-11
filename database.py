from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, unique=True)      # без @
    full_name = Column(String)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    due_date = Column(DateTime, nullable=False)
    user_tg_id = Column(Integer, nullable=False)
    task_type = Column(String)                  # "выступление" или "перевод"
    description = Column(Text)
    week = Column(String)
    reminder_sent_14 = Column(Boolean, default=False)
    reminder_sent_7 = Column(Boolean, default=False)
    reminder_sent_1 = Column(Boolean, default=False)

import os
_db_dir = "/data" if os.path.isdir("/data") else "."
engine = create_engine(f"sqlite:///{_db_dir}/duties.db", echo=False)
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)