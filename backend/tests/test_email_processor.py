import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Base, Email, Task
from app.services.email_processor import process_email_record


class EmailProcessorTests(unittest.TestCase):
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

    def test_invalid_llm_output_falls_back_to_rules(self) -> None:
        with self.session_local() as db:
            email = Email(
                message_id="msg-1",
                subject="Job opportunity",
                raw_body="Please send your resume.",
                from_address="recruiter@example.com",
                to_address="me@example.com",
                status="QUEUED",
            )
            db.add(email)
            db.commit()
            db.refresh(email)

            with patch("app.services.email_processor.settings.llm_enabled", True), patch(
                "app.services.email_processor.settings.llm_provider", "test"
            ), patch(
                "app.services.email_processor.LLMExtractionClient.extract",
                return_value={"mode": "llm", "tasks": [{"action_type": "BAD_ACTION"}]},
            ):
                outcome = process_email_record(db, email.id)

            tasks = db.query(Task).filter(Task.email_id == email.id).all()

            self.assertEqual(outcome.email_status, "COMPLETED")
            self.assertEqual(outcome.mode, "fallback")
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].action_type, "REPLY")
            self.assertIn("recipient", tasks[0].payload)
            self.assertTrue(
                any("LLM output validation failed" in warning for warning in outcome.warnings)
            )

    def test_existing_tasks_skip_duplicate_processing(self) -> None:
        with self.session_local() as db:
            email = Email(
                message_id="msg-2",
                subject="Interview schedule",
                raw_body="Can we schedule a meeting?",
                from_address="manager@example.com",
                to_address="me@example.com",
                status="QUEUED",
            )
            db.add(email)
            db.commit()
            db.refresh(email)

            first_outcome = process_email_record(db, email.id)
            second_outcome = process_email_record(db, email.id)

            task_count = db.query(Task).filter(Task.email_id == email.id).count()

            self.assertEqual(first_outcome.created_tasks, 1)
            self.assertEqual(second_outcome.created_tasks, 0)
            self.assertEqual(second_outcome.mode, "idempotent-skip")
            self.assertEqual(second_outcome.email_status, "TASKS_ALREADY_CREATED")
            self.assertEqual(task_count, 1)

    def test_email_can_generate_multiple_realistic_tasks(self) -> None:
        with self.session_local() as db:
            email = Email(
                message_id="msg-3",
                subject="Schedule and remind",
                raw_body="Please remind me tomorrow, take note of this update, and schedule a meeting.",
                from_address="client@example.com",
                to_address="me@example.com",
                status="QUEUED",
            )
            db.add(email)
            db.commit()
            db.refresh(email)

            outcome = process_email_record(db, email.id)
            tasks = db.query(Task).filter(Task.email_id == email.id).all()
            action_types = {task.action_type for task in tasks}

            self.assertEqual(outcome.email_status, "COMPLETED")
            self.assertGreaterEqual(len(tasks), 3)
            self.assertIn("SCHEDULE_MEETING", action_types)
            self.assertIn("SEND_REMINDER", action_types)
            self.assertIn("CREATE_NOTE", action_types)


if __name__ == "__main__":
    unittest.main()
