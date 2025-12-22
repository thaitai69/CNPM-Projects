import os
import uuid
import shutil
import jwt
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from celery import Celery
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER = REDIS_URL
CELERY_BACKEND = "rpc://"

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
ALGORITHM = "HS256"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@db:5432/aura"
)

os.makedirs(UPLOAD_DIR, exist_ok=True)

celery = Celery("tasks", broker=CELERY_BROKER, backend=CELERY_BACKEND)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

class Analysis(Base):
    __tablename__ = "analysis"
    id = Column(String, primary_key=True)
    filename = Column(String)
    status = Column(String, default="PENDING")
    result = Column(Text, nullable=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

Base.metadata.create_all(engine)

app = FastAPI(title="AURA AI Core")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_user(token: str = Depends(oauth2_scheme)):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(401, "Invalid Token")

def require_role(role: str):
    def wrapper(user=Depends(get_user)):
        if user.get("role") not in [role, "Admin"]:
            raise HTTPException(403, "Forbidden")
        return user
    return wrapper

class Token(BaseModel):
    access_token: str
    token_type: str

@app.post("/token")
def login(username: str, role: str = "Clinic"):
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

@app.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(require_role("Clinic"))):
    uid = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    final_name = f"{uid}{ext}"
    path = os.path.join(UPLOAD_DIR, final_name)

    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    db = SessionLocal()
    record = Analysis(id=uid, filename=final_name, status="QUEUED")
    db.add(record)
    db.commit()
    db.close()

    celery.send_task("tasks.process_image", args=[uid, path])

    return {"task_id": uid, "status": "QUEUED"}

@app.get("/result/{task_id}")
def result(task_id: str):
    db = SessionLocal()
    r = db.query(Analysis).filter(Analysis.id == task_id).first()
    db.close()
    if not r:
        raise HTTPException(404)
    return {"id": task_id, "status": r.status, "result": r.result}

@app.get("/health")
def health():
    return {"ok": True}
