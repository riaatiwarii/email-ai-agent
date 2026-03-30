from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import TaskActionType, TaskStatus


class ReplyPayload(BaseModel):
    recipient: str = Field(..., min_length=3)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


class ScheduleMeetingPayload(BaseModel):
    title: str = Field(..., min_length=1)
    details: str = Field(..., min_length=1)
    start_hint: str = Field(..., min_length=1)
    end_hint: str = Field(..., min_length=1)
    google_calendar_url: str = Field(..., min_length=1)


class ReminderPayload(BaseModel):
    title: str = Field(..., min_length=1)
    reminder_text: str = Field(..., min_length=1)
    due_hint: str = Field(..., min_length=1)


class FollowUpPayload(BaseModel):
    title: str = Field(..., min_length=1)
    follow_up_text: str = Field(..., min_length=1)
    due_hint: str = Field(..., min_length=1)


class NotePayload(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class UnknownPayload(BaseModel):
    reason: str = Field(..., min_length=1)


class TaskDecisionResponse(BaseModel):
    task_id: int
    status: TaskStatus


class InboxSyncRequest(BaseModel):
    email_address: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    imap_host: str = Field(default="imap.gmail.com", min_length=1)
    imap_port: int = 993
    mailbox: str = Field(default="INBOX", min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    unread_only: bool = True
    smtp_host: str | None = "smtp.gmail.com"
    smtp_port: int | None = 587
    use_tls: bool = True


class EmailAccountCheckRequest(BaseModel):
    email_address: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    imap_host: str = Field(default="imap.gmail.com", min_length=1)
    imap_port: int = 993
    smtp_host: str | None = "smtp.gmail.com"
    smtp_port: int | None = 587
    use_tls: bool = True


class AccountConnectionResult(BaseModel):
    imap_ok: bool
    smtp_ok: bool
    message: str


class InboxSyncResponse(BaseModel):
    imported: int
    queued: int
    message: str


class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    status: str
    response: str | None = None
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_id: int
    action_type: TaskActionType
    status: str
    payload: dict[str, Any]
    retries: int
    created_at: datetime


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_id: int | None = None
    task_id: int | None = None
    title: str | None = None
    content: str | None = None
    created_at: datetime


class EmailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: str
    thread_id: str | None = None
    subject: str | None = None
    raw_body: str | None = None
    cleaned_body: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    source: str | None = None
    status: str
    created_at: datetime


class EmailSummary(EmailRead):
    task_count: int = 0


class EmailDetail(BaseModel):
    email: EmailRead
    tasks: list[TaskRead]
    action_logs: list[ActionLogRead]
    notes: list[NoteRead]


class SystemOverview(BaseModel):
    total_emails: int
    total_tasks: int
    pending_approval: int
    approved: int
    executed: int
    failed: int
    notes: int
