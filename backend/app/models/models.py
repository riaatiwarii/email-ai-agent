from sqlalchemy import Column, ForeignKey, Integer, JSON, TEXT, TIMESTAMP
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(TEXT, unique=True)
    thread_id = Column(TEXT)
    subject = Column(TEXT)
    raw_body = Column(TEXT)
    cleaned_body = Column(TEXT)
    from_address = Column(TEXT)
    to_address = Column(TEXT)
    source = Column(TEXT, default="manual")
    status = Column(TEXT, default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    action_type = Column(TEXT)
    status = Column(TEXT)
    payload = Column(JSON)
    retries = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())


class ActionLog(Base):
    __tablename__ = "actions_log"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    status = Column(TEXT)
    response = Column(TEXT)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    title = Column(TEXT)
    content = Column(TEXT)
    created_at = Column(TIMESTAMP, server_default=func.now())
