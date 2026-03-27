from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.models import Email
from celery_worker import process_email

app = FastAPI()


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/test-db")
def test_db(db: Session = Depends(get_db)):
    new_email = Email(
        message_id="test_1",
        subject="Hello",
        raw_body="Send resume"
    )

    db.add(new_email)
    db.commit()
    db.refresh(new_email)

    return {"id": new_email.id}

@app.post("/ingest-email")
def ingest_email(db: Session = Depends(get_db)):
    import time

    email = Email(
        message_id="msg_" + str(time.time()),
        subject="Job Opportunity",
        raw_body="Please send your resume"
    )

    db.add(email)
    db.commit()
    db.refresh(email)

    # PUSH TO QUEUE
    process_email.delay(email.id)

    return {"email_id": email.id}