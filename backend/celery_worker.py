from celery import Celery

celery = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

celery.autodiscover_tasks(['celery_worker'])

@celery.task
def process_email(email_id):
    print(f"Processing email {email_id}")