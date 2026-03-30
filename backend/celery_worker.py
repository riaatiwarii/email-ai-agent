from celery import Celery

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import Email
from app.services.email_processor import process_email_record
from app.services.task_executor import (
    TaskExecutionError,
    execute_task_record,
    mark_task_execution_failed,
)

celery = Celery(
    "worker",
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery.autodiscover_tasks(['celery_worker'])

@celery.task
def process_email(email_id):
    db = SessionLocal()
    try:
        outcome = process_email_record(db, email_id)
        print(
            f"Processed email {outcome.email_id} "
            f"status={outcome.email_status} "
            f"tasks={outcome.created_tasks} "
            f"mode={outcome.mode}"
        )
        return {
            "email_id": outcome.email_id,
            "email_status": outcome.email_status,
            "created_tasks": outcome.created_tasks,
            "mode": outcome.mode,
            "warnings": outcome.warnings,
        }
    except Exception:
        email = db.get(Email, email_id)
        if email is not None:
            email.status = "FAILED"
            db.commit()
        raise
    finally:
        db.close()


@celery.task
def execute_task(task_id):
    db = SessionLocal()
    try:
        outcome = execute_task_record(db, task_id)
        print(
            f"Executed task {outcome.task_id} "
            f"status={outcome.status} "
            f"response={outcome.response}"
        )
        return {
            "task_id": outcome.task_id,
            "status": outcome.status,
            "response": outcome.response,
        }
    except TaskExecutionError as exc:
        mark_task_execution_failed(db, task_id, str(exc))
        raise
    finally:
        db.close()
