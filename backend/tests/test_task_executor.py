import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import ActionLog, Base, Email, Note, Task
from app.services.task_executor import TaskExecutionError, execute_task_record


class TaskExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_local = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_execute_approved_reply_task(self) -> None:
        with self.session_local() as db:
            email = Email(
                message_id="reply-msg",
                subject="Need your resume",
                raw_body="Please send your resume.",
                from_address="recruiter@example.com",
                to_address="operator@example.com",
                status="COMPLETED",
            )
            db.add(email)
            db.commit()
            db.refresh(email)

            task = Task(
                email_id=email.id,
                action_type="REPLY",
                status="APPROVED",
                payload={
                    "recipient": "recruiter@example.com",
                    "subject": "Re: Need your resume",
                    "body": "Attached is my resume.",
                },
                retries=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            with patch("app.services.task_executor.settings.smtp_user", "operator@example.com"), patch(
                "app.services.task_executor.settings.smtp_password", "secret"
            ), patch("app.services.task_executor.send_smtp_email") as mocked_send:
                outcome = execute_task_record(db, task.id)

            logs = db.query(ActionLog).filter(ActionLog.task_id == task.id).all()

            self.assertEqual(outcome.status, "EXECUTED")
            self.assertEqual(len(logs), 2)
            mocked_send.assert_called_once()

    def test_note_task_creates_real_note_record(self) -> None:
        with self.session_local() as db:
            email = Email(
                message_id="note-msg",
                subject="Take note",
                raw_body="Remember the client feedback.",
                status="COMPLETED",
            )
            db.add(email)
            db.commit()
            db.refresh(email)

            task = Task(
                email_id=email.id,
                action_type="CREATE_NOTE",
                status="APPROVED",
                payload={"title": "Client feedback", "content": "Remember the client feedback."},
                retries=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            outcome = execute_task_record(db, task.id)
            note = db.query(Note).filter(Note.task_id == task.id).first()

            self.assertEqual(outcome.status, "EXECUTED")
            self.assertIsNotNone(note)
            self.assertEqual(note.title, "Client feedback")

    def test_rejects_unapproved_tasks(self) -> None:
        with self.session_local() as db:
            task = Task(
                email_id=1,
                action_type="REPLY",
                status="PENDING_APPROVAL",
                payload={
                    "recipient": "person@example.com",
                    "subject": "Re: Hello",
                    "body": "Thanks",
                },
                retries=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            with self.assertRaises(TaskExecutionError):
                execute_task_record(db, task.id)

    def test_invalid_payload_is_blocked(self) -> None:
        with self.session_local() as db:
            task = Task(
                email_id=1,
                action_type="SCHEDULE_MEETING",
                status="APPROVED",
                payload={"reply_type": "wrong_shape"},
                retries=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            with self.assertRaises(TaskExecutionError):
                execute_task_record(db, task.id)


if __name__ == "__main__":
    unittest.main()
