# Email AI Agent

Email-to-action system with async processing, approvals, notes, and a friendlier frontend.

Current product flow:

`Email -> ingest or IMAP sync -> queue -> async extraction -> validated tasks -> approval -> execution`

Execution currently supports:

- real SMTP replies when credentials are configured
- note creation
- reminder capture into notes
- follow-up capture into notes
- Google Calendar draft links for meeting tasks

## Included

- FastAPI backend
- PostgreSQL persistence
- Redis queue
- Celery worker
- IMAP inbox sync
- SMTP reply execution
- task approval flow
- notes storage
- standalone frontend workspace in `frontend/`
- Docker Compose setup

## Real email support

You can test this with a real Gmail account using:

- IMAP: `imap.gmail.com`
- SMTP: `smtp.gmail.com`
- an App Password, not your normal Gmail password

For Gmail:

1. Turn on 2-Step Verification in your Google account
2. Create an App Password
3. Use that app password in the frontend's "Connect Email" form

Inbox sync uses the credentials you enter in the UI.

Real reply sending uses backend environment variables:

- `SMTP_USER`
- `SMTP_PASSWORD`

If those are missing, reply tasks will fail safely with a clear error.

## Docker run

### 1. Optional: configure SMTP for real replies

Copy `.env.example` to `.env` and edit the values:

```powershell
Copy-Item .env.example .env
```

Set:

- `SMTP_USER`
- `SMTP_PASSWORD`

### 2. Start Docker Desktop

Wait until Docker is fully running.

### 3. Start the stack

From the repo root:

```powershell
docker compose up --build
```

This starts:

- PostgreSQL on `localhost:5432`
- FastAPI backend on `http://localhost:8000`
- frontend on `http://localhost:3000`
- Celery worker in the background

Redis stays internal to Docker, so it is not exposed on a host port.

### 4. Open the app

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`

### 5. Stop everything

```powershell
docker compose down
```

Remove the database volume too:

```powershell
docker compose down -v
```

## Manual local run

### 1. Start PostgreSQL

Make sure PostgreSQL is running on `localhost:5432`.

Create a database:

- `email_ai`

### 2. Start Redis

Make sure Redis is running on `localhost:6379`.

### 3. Start the backend API

Open a PowerShell terminal:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/email_ai"
$env:REDIS_URL="redis://localhost:6379/0"
$env:LLM_ENABLED="false"
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your-email@gmail.com"
$env:SMTP_PASSWORD="your-app-password"
$env:SMTP_USE_TLS="true"
uvicorn app.main:app --reload
```

### 4. Start the Celery worker

Open a second terminal:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/email_ai"
$env:REDIS_URL="redis://localhost:6379/0"
$env:LLM_ENABLED="false"
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your-email@gmail.com"
$env:SMTP_PASSWORD="your-app-password"
$env:SMTP_USE_TLS="true"
celery -A celery_worker.celery worker --loglevel=info --pool=solo
```

### 5. Start the frontend

Open a third terminal:

```powershell
cd frontend
python -m http.server 3000
```

Open:

- `http://localhost:3000`

## How to test with a real inbox

### In the frontend

1. Open `http://localhost:3000`
2. Make sure API URL is `http://localhost:8000`
3. In "Connect Email", enter:
   - your Gmail address
   - your Gmail app password
   - `imap.gmail.com`
   - `smtp.gmail.com`
4. Click `Test`
5. Click `Sync Inbox`

This imports recent unread messages and queues them for processing.

### Then verify the workflow

1. Wait a few seconds for the worker to process emails
2. Refresh the dashboard
3. Click a synced email in the inbox list
4. Review the extracted tasks
5. Approve one of the tasks

What happens:

- `REPLY` tries to send a real email through SMTP
- `CREATE_NOTE` stores a note in the app
- `SEND_REMINDER` stores a reminder note
- `FOLLOW_UP` stores a follow-up note
- `SCHEDULE_MEETING` creates a Google Calendar draft link

## API highlights

- `POST /ingest-email`
- `POST /email-account/test`
- `POST /sync-inbox`
- `GET /emails`
- `GET /emails/{id}`
- `GET /tasks`
- `POST /tasks/{id}/approve`
- `POST /tasks/{id}/reject`
- `GET /notes`
- `GET /overview`

## Tests

From `backend/`:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Verified locally

The following passed in the project venv:

- backend unit tests
- Python compile checks for backend and frontend-adjacent files

## Current limits

- LLM extraction is still stubbed behind the validation boundary
- Gmail OAuth is not implemented; current real-email support is IMAP/SMTP with app passwords
- Google Calendar API write access is not implemented; meeting tasks currently generate Google Calendar draft links rather than writing directly to a calendar
