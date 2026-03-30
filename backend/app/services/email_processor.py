from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Email, Task
from app.schemas.extraction import EmailExtractionResult, ExtractedTask


@dataclass
class ProcessingOutcome:
    email_id: int
    email_status: str
    created_tasks: int
    mode: str
    warnings: list[str]


class ExtractionError(Exception):
    pass


class LLMExtractionClient:
    def extract(self, email: Email) -> Any:
        if not settings.llm_enabled or settings.llm_provider == "mock":
            raise ExtractionError("LLM provider is not configured.")

        raise ExtractionError("Live LLM integration is not implemented yet.")


def process_email_record(db: Session, email_id: int) -> ProcessingOutcome:
    email = db.get(Email, email_id)
    if email is None:
        raise ValueError(f"Email {email_id} was not found.")

    existing_tasks = db.query(Task).filter(Task.email_id == email_id).count()
    if existing_tasks > 0:
        email.status = "TASKS_ALREADY_CREATED"
        db.commit()
        return ProcessingOutcome(
            email_id=email_id,
            email_status=email.status,
            created_tasks=0,
            mode="idempotent-skip",
            warnings=["Existing tasks detected for this email."],
        )

    email.status = "PROCESSING"
    db.commit()

    extraction = extract_tasks(email)
    created_tasks = persist_tasks(db, email_id=email.id, extraction=extraction)

    email.status = "COMPLETED" if created_tasks else "NO_ACTION"
    db.commit()

    return ProcessingOutcome(
        email_id=email.id,
        email_status=email.status,
        created_tasks=created_tasks,
        mode=extraction.mode,
        warnings=extraction.warnings,
    )


def extract_tasks(email: Email) -> EmailExtractionResult:
    warnings: list[str] = []
    llm_client = LLMExtractionClient()

    try:
        llm_result = llm_client.extract(email)
        return validate_extraction_result(llm_result)
    except ExtractionError as exc:
        warnings.append(str(exc))
        fallback_result = run_rule_based_extraction(email)
        fallback_result.warnings.extend(warnings)
        return fallback_result


def validate_extraction_result(raw_result: Any) -> EmailExtractionResult:
    try:
        if isinstance(raw_result, EmailExtractionResult):
            return raw_result

        if hasattr(raw_result, "model_dump"):
            return EmailExtractionResult.model_validate(raw_result.model_dump())

        if hasattr(raw_result, "dict"):
            return EmailExtractionResult.model_validate(raw_result.dict())

        if isinstance(raw_result, dict):
            return EmailExtractionResult.model_validate(raw_result)

        raise ExtractionError("LLM returned an unsupported response shape.")
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"LLM output validation failed: {exc}") from exc


def run_rule_based_extraction(email: Email) -> EmailExtractionResult:
    body = " ".join(filter(None, [email.subject, email.cleaned_body, email.raw_body]))
    content = body.lower()
    tasks: list[ExtractedTask] = []

    if "resume" in content or "cv" in content:
        tasks.append(
            ExtractedTask(
                action_type="REPLY",
                title="Reply with requested resume",
                confidence=0.93,
                rationale="The email explicitly asks for a resume or CV.",
                payload={
                    "recipient": email.from_address or email.to_address or "",
                    "subject": build_reply_subject(email.subject),
                    "body": build_resume_reply_body(email),
                },
            )
        )

    if "schedule" in content or "meeting" in content or "calendar" in content:
        tasks.append(
            ExtractedTask(
                action_type="SCHEDULE_MEETING",
                title="Create meeting event draft",
                confidence=0.81,
                rationale="The message references scheduling or a meeting.",
                payload=build_calendar_payload(email),
            )
        )

    if "remind" in content or "reminder" in content:
        tasks.append(
            ExtractedTask(
                action_type="SEND_REMINDER",
                title="Capture reminder",
                confidence=0.76,
                rationale="The message includes reminder-related language.",
                payload={
                    "title": email.subject or "Reminder",
                    "reminder_text": extract_sentence(body, ["remind", "reminder"]) or email.raw_body,
                    "due_hint": "Tomorrow morning",
                },
            )
        )

    if "follow up" in content or "follow-up" in content:
        tasks.append(
            ExtractedTask(
                action_type="FOLLOW_UP",
                title="Prepare follow-up task",
                confidence=0.74,
                rationale="The email suggests a follow-up action.",
                payload={
                    "title": email.subject or "Follow up",
                    "follow_up_text": extract_sentence(body, ["follow up", "follow-up"]) or email.raw_body,
                    "due_hint": "Within 2 business days",
                },
            )
        )

    if "note" in content or "remember" in content or "take note" in content:
        tasks.append(
            ExtractedTask(
                action_type="CREATE_NOTE",
                title="Save note from email",
                confidence=0.7,
                rationale="The email asks to remember or note something important.",
                payload={
                    "title": email.subject or "Email note",
                    "content": email.raw_body,
                },
            )
        )

    if not tasks and body.strip():
        tasks.append(
            ExtractedTask(
                action_type="CREATE_NOTE",
                title="Save email summary as note",
                confidence=0.55,
                rationale="No direct automation intent matched, so the email is stored as a note for review.",
                payload={
                    "title": email.subject or "Review email",
                    "content": email.raw_body,
                },
            )
        )

    return EmailExtractionResult(mode="fallback", tasks=tasks)


def persist_tasks(db: Session, email_id: int, extraction: EmailExtractionResult) -> int:
    created_tasks = 0

    for extracted_task in extraction.tasks:
        task = Task(
            email_id=email_id,
            action_type=extracted_task.action_type,
            status=extracted_task.status,
            payload={
                **extracted_task.payload,
                "title": extracted_task.title,
                "confidence": extracted_task.confidence,
                "rationale": extracted_task.rationale,
                "processing_mode": extraction.mode,
            },
        )
        db.add(task)
        created_tasks += 1

    db.commit()
    return created_tasks


def build_reply_subject(subject: str | None) -> str:
    if not subject:
        return "Re: Your email"
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def build_resume_reply_body(email: Email) -> str:
    sender_name = (email.from_address or "there").split("@")[0]
    return (
        f"Hi {sender_name},\n\n"
        "Thanks for reaching out. I am sharing the requested resume here.\n\n"
        "Best regards,\n"
        f"{(email.to_address or 'Your Name').split('@')[0]}"
    )


def build_calendar_payload(email: Email) -> dict[str, str]:
    title = email.subject or "Meeting from email"
    details = email.raw_body or "Meeting requested from email."
    start_hint = "Next available slot"
    end_hint = "30 minutes after start"
    text = quote(title)
    details_encoded = quote(details)
    google_calendar_url = (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={text}&details={details_encoded}"
    )
    return {
        "title": title,
        "details": details,
        "start_hint": start_hint,
        "end_hint": end_hint,
        "google_calendar_url": google_calendar_url,
    }


def extract_sentence(content: str, keywords: list[str]) -> str | None:
    for line in content.splitlines():
        lowered = line.lower()
        if any(keyword in lowered for keyword in keywords):
            return line.strip()
    return None
