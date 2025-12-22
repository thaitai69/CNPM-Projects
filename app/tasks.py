import time
from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import DATABASE_URL, Analysis

celery = Celery("tasks", broker="redis://redis:6379/0", backend="rpc://")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@celery.task(name="tasks.process_image")
def process_image(task_id, file_path):
    db = SessionLocal()
    record = db.query(Analysis).filter(Analysis.id == task_id).first()

    record.status = "PROCESSING"
    db.commit()

    # Fake AI processing
    time.sleep(5)

    record.status = "DONE"
    record.result = f"Processed file: {file_path}"
    db.commit()
    db.close()

    return True
