from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import engine
from app.core.deps import get_db
from app.models.models import ActionLog, Base, Email, Note, Task
from app.schemas.email import EmailIngestRequest
from app.schemas.tasking import (
    AccountConnectionResult,
    EmailAccountCheckRequest,
    EmailDetail,
    EmailRead,
    EmailSummary,
    InboxSyncRequest,
    InboxSyncResponse,
    NoteRead,
    SystemOverview,
    TaskDecisionResponse,
    TaskRead,
)
from app.services.email_account import EmailAccountError, sync_inbox, test_email_account_connection
from celery_worker import execute_task, process_email

app = FastAPI(title="Email AI Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def health():
    return {"status": "ok", "service": "email-ai-agent", "version": "2.0.0"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return """
    <html>
      <head><title>Email AI Agent</title></head>
      <body style="font-family: sans-serif; padding: 40px;">
        <h1>Email AI Agent</h1>
        <p>The richer product UI lives in the standalone frontend.</p>
        <p>Open <a href="http://localhost:3000">http://localhost:3000</a> for the full application.</p>
        <p>Open <a href="/docs">/docs</a> for the API reference.</p>
      </body>
    </html>
    """


@app.post("/ingest-email")
def ingest_email(payload: EmailIngestRequest, db: Session = Depends(get_db)):
    existing_email = db.query(Email).filter(Email.message_id == payload.message_id).first()
    if existing_email is not None:
        return {"email_id": existing_email.id, "status": existing_email.status}

    email_record = Email(
        message_id=payload.message_id,
        thread_id=payload.thread_id,
        subject=payload.subject,
        raw_body=payload.raw_body,
        cleaned_body=payload.cleaned_body or payload.raw_body.strip(),
        from_address=payload.from_address,
        to_address=payload.to_address,
        source=payload.source or "manual",
        status="QUEUED",
    )

    db.add(email_record)
    db.commit()
    db.refresh(email_record)

    process_email.delay(email_record.id)

    return {"email_id": email_record.id, "status": email_record.status}


@app.post("/email-account/test", response_model=AccountConnectionResult)
def test_email_account(payload: EmailAccountCheckRequest):
    try:
        return test_email_account_connection(
            InboxSyncRequest(
                email_address=payload.email_address,
                password=payload.password,
                imap_host=payload.imap_host,
                imap_port=payload.imap_port,
                smtp_host=payload.smtp_host,
                smtp_port=payload.smtp_port,
                use_tls=payload.use_tls,
            )
        )
    except EmailAccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sync-inbox", response_model=InboxSyncResponse)
def sync_real_inbox(payload: InboxSyncRequest, db: Session = Depends(get_db)):
    try:
        result = sync_inbox(db, payload)
    except EmailAccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_emails = (
        db.query(Email)
        .filter(Email.source == "imap")
        .order_by(Email.created_at.desc(), Email.id.desc())
        .limit(payload.limit)
        .all()
    )

    for email_record in reversed(new_emails):
        if email_record.status == "QUEUED":
            process_email.delay(email_record.id)

    return result


@app.get("/emails", response_model=list[EmailSummary])
def list_emails(db: Session = Depends(get_db)):
    rows = (
        db.query(Email, func.count(Task.id).label("task_count"))
        .outerjoin(Task, Task.email_id == Email.id)
        .group_by(Email.id)
        .order_by(Email.created_at.desc(), Email.id.desc())
        .all()
    )

    return [
        EmailSummary.model_validate(
            {
                **EmailRead.model_validate(email_record).model_dump(),
                "task_count": task_count,
            }
        )
        for email_record, task_count in rows
    ]


@app.get("/emails/{email_id}", response_model=EmailDetail)
def get_email(email_id: int, db: Session = Depends(get_db)):
    email_record = db.get(Email, email_id)
    if email_record is None:
        raise HTTPException(status_code=404, detail="Email not found.")

    tasks = (
        db.query(Task)
        .filter(Task.email_id == email_id)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .all()
    )
    task_ids = [task.id for task in tasks]
    action_logs = []
    notes = db.query(Note).filter(Note.email_id == email_id).order_by(Note.created_at.desc(), Note.id.desc()).all()
    if task_ids:
        action_logs = (
            db.query(ActionLog)
            .filter(ActionLog.task_id.in_(task_ids))
            .order_by(ActionLog.created_at.desc(), ActionLog.id.desc())
            .all()
        )

    return EmailDetail(
        email=EmailRead.model_validate(email_record),
        tasks=[TaskRead.model_validate(task) for task in tasks],
        action_logs=action_logs,
        notes=[NoteRead.model_validate(note) for note in notes],
    )


@app.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    status: str | None = Query(default=None),
    email_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    if email_id is not None:
        query = query.filter(Task.email_id == email_id)

    tasks = query.order_by(Task.created_at.desc(), Task.id.desc()).all()
    return [TaskRead.model_validate(task) for task in tasks]


@app.post("/tasks/{task_id}/approve", response_model=TaskDecisionResponse)
def approve_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Only pending tasks can be approved.")

    task.status = "APPROVED"
    db.add(ActionLog(task_id=task.id, status="APPROVED", response="Task approved by operator."))
    db.commit()

    execute_task.delay(task.id)
    return TaskDecisionResponse(task_id=task.id, status=task.status)


@app.post("/tasks/{task_id}/reject", response_model=TaskDecisionResponse)
def reject_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Only pending tasks can be rejected.")

    task.status = "REJECTED"
    db.add(ActionLog(task_id=task.id, status="REJECTED", response="Task rejected by operator."))
    db.commit()
    return TaskDecisionResponse(task_id=task.id, status=task.status)


@app.post("/tasks/{task_id}/execute", response_model=TaskDecisionResponse)
def trigger_task_execution(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only approved tasks can be executed.")

    execute_task.delay(task.id)
    return TaskDecisionResponse(task_id=task.id, status=task.status)


@app.get("/notes", response_model=list[NoteRead])
def list_notes(db: Session = Depends(get_db)):
    notes = db.query(Note).order_by(Note.created_at.desc(), Note.id.desc()).all()
    return [NoteRead.model_validate(note) for note in notes]


@app.get("/overview", response_model=SystemOverview)
def overview(db: Session = Depends(get_db)):
    total_emails = db.query(func.count(Email.id)).scalar() or 0
    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    pending_approval = db.query(func.count(Task.id)).filter(Task.status == "PENDING_APPROVAL").scalar() or 0
    approved = db.query(func.count(Task.id)).filter(Task.status == "APPROVED").scalar() or 0
    executed = db.query(func.count(Task.id)).filter(Task.status == "EXECUTED").scalar() or 0
    failed = db.query(func.count(Task.id)).filter(Task.status == "EXECUTION_FAILED").scalar() or 0
    notes_count = db.query(func.count(Note.id)).scalar() or 0

    return SystemOverview(
        total_emails=total_emails,
        total_tasks=total_tasks,
        pending_approval=pending_approval,
        approved=approved,
        executed=executed,
        failed=failed,
        notes=notes_count,
    )
