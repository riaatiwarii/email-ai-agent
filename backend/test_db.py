from app.core.database import SessionLocal

try:
    db = SessionLocal()
    print("DB Connected")
except Exception as e:
    print("Error:", e)