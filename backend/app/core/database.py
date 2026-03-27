from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:%40Zucku12@localhost:5432/email_ai"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)