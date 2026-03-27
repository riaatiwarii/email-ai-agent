from sqlalchemy import Column, Integer, Text, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.sql import func
from app.core.database import engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Text, unique=True)
    thread_id = Column(Text)
    subject = Column(Text)
    raw_body = Column(Text)
    cleaned_body = Column(Text)
    status = Column(Text, default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    action_type = Column(Text)
    status = Column(Text)
    payload = Column(JSON)
    retries = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())

class ActionLog(Base):
    __tablename__ = "actions_log"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    status = Column(Text)
    response = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())