from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import ActionLog, Email, Note, Task
from app.schemas.tasking import (
    FollowUpPayload,
    NotePayload,
    ReminderPayload,
    ReplyPayload,
    ScheduleMeetingPayload,
    UnknownPayload,
)
from app.services.email_account import send_smtp_email


class TaskExecutionError(Exception):
    pass


@dataclass
class TaskExecutionOutcome:
    task_id: int
    status: str
    response: str


def validate_task_payload(task: Task) -> None:
    payload = task.payload or {}

    try:
        if task.action_type == "REPLY":
            ReplyPayload.model_validate(payload)
        elif task.action_type == "SCHEDULE_MEETING":
            ScheduleMeetingPayload.model_validate(payload)
        elif task.action_type == "SEND_REMINDER":
            ReminderPayload.model_validate(payload)
        elif task.action_type == "FOLLOW_UP":
            FollowUpPayload.model_validate(payload)
        elif task.action_type == "CREATE_NOTE":
            NotePayload.model_validate(payload)
        elif task.action_type == "UNKNOWN":
            UnknownPayload.model_validate(payload)
        else:
            raise TaskExecutionError(f"Unsupported action type: {task.action_type}")
    except ValidationError as exc:
        raise TaskExecutionError(f"Invalid payload for {task.action_type}: {exc}") from exc


def execute_task_record(db: Session, task_id: int) -> TaskExecutionOutcome:
    task = db.get(Task, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} was not found.")

    if task.status != "APPROVED":
        raise TaskExecutionError("Only APPROVED tasks can be executed.")

    validate_task_payload(task)

    task.status = "EXECUTING"
    db.add(
        ActionLog(
            task_id=task.id,
            status="EXECUTING",
            response=f"Execution started for action {task.action_type}.",
        )
    )
    db.commit()

    response = perform_action(db, task)
    task.status = "EXECUTED"
    db.add(ActionLog(task_id=task.id, status="EXECUTED", response=response))
    db.commit()

    return TaskExecutionOutcome(task_id=task.id, status=task.status, response=response)


def mark_task_execution_failed(db: Session, task_id: int, reason: str) -> None:
    task = db.get(Task, task_id)
    if task is None:
        return

    task.status = "EXECUTION_FAILED"
    task.retries = (task.retries or 0) + 1
    db.add(ActionLog(task_id=task.id, status="EXECUTION_FAILED", response=reason))
    db.commit()


def perform_action(db: Session, task: Task) -> str:
    payload = task.payload or {}

    if task.action_type == "REPLY":
        sender = settings.smtp_user or infer_sender_email(db, task.email_id)
        password = settings.smtp_password
        if not sender or not password:
            raise TaskExecutionError(
                "SMTP credentials are missing. Set SMTP_USER and SMTP_PASSWORD to send real replies."
            )

        send_smtp_email(
            recipient=payload["recipient"],
            subject=payload["subject"],
            body=payload["body"],
            sender=sender,
            password=password,
            host=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=settings.smtp_use_tls,
        )
        return f"Reply sent to {payload['recipient']} with subject '{payload['subject']}'."

    if task.action_type == "SCHEDULE_MEETING":
        return f"Calendar draft ready: {payload['google_calendar_url']}"

    if task.action_type == "SEND_REMINDER":
        create_note(
            db,
            email_id=task.email_id,
            task_id=task.id,
            title=payload["title"],
            content=f"Reminder: {payload['reminder_text']}\nDue: {payload['due_hint']}",
        )
        return f"Reminder saved to notes for '{payload['title']}'."

    if task.action_type == "FOLLOW_UP":
        create_note(
            db,
            email_id=task.email_id,
            task_id=task.id,
            title=payload["title"],
            content=f"Follow-up: {payload['follow_up_text']}\nWhen: {payload['due_hint']}",
        )
        return f"Follow-up note saved for '{payload['title']}'."

    if task.action_type == "CREATE_NOTE":
        create_note(
            db,
            email_id=task.email_id,
            task_id=task.id,
            title=payload["title"],
            content=payload["content"],
        )
        return f"Note created: {payload['title']}."

    if task.action_type == "UNKNOWN":
        return f"Stored unknown task for manual review: {payload.get('reason', 'unspecified')}."

    raise TaskExecutionError(f"Unsupported action type: {task.action_type}")


def create_note(db: Session, email_id: int, task_id: int, title: str, content: str) -> None:
    db.add(Note(email_id=email_id, task_id=task_id, title=title, content=content))
    db.commit()


def infer_sender_email(db: Session, email_id: int) -> str:
    email_record = db.get(Email, email_id)
    if email_record is None:
        return ""
    return email_record.to_address or ""
