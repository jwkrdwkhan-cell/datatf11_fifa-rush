from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uvicorn
import os
import shutil
from datetime import datetime, timedelta
import json
import asyncio

app = FastAPI(title="ALBRAZIL WORM", description="Smart AI System with Training")

# Folders
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Simple in-memory state (for demo - later can use DB)
app_state = {
    "is_locked": False,
    "lock_until": None,
    "training_status": "idle",
    "last_training": None,
    "current_description": "",
    "uploaded_files": []
}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    locked = app_state["is_locked"]
    lock_until = app_state["lock_until"]
    now = datetime.now()

    if locked and lock_until and now < lock_until:
        remaining = lock_until - now
        return templates.TemplateResponse("locked.html", {
            "request": request,
            "remaining_hours": round(remaining.total_seconds() / 3600, 1)
        })
    else:
        # Unlock if time passed
        if locked:
            app_state["is_locked"] = False
            app_state["lock_until"] = None
            app_state["training_status"] = "completed"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": app_state["training_status"]
    })


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for file in files:
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        saved.append(file.filename)
        app_state["uploaded_files"].append(file.filename)
    return {"message": f"تم رفع {len(saved)} ملف", "files": saved}


@app.post("/start-training")
async def start_training(
    description: str = Form(...),
    lock_days: int = Form(...)
):
    if lock_days < 1 or lock_days > 7:
        raise HTTPException(status_code=400, detail="المدة لازم تكون بين 1 و 7 أيام")

    if not description.strip():
        raise HTTPException(status_code=400, detail="اكتب وصف للبيانات أولاً")

    # Lock the app
    lock_until = datetime.now() + timedelta(days=lock_days)
    app_state["is_locked"] = True
    app_state["lock_until"] = lock_until
    app_state["training_status"] = "training"
    app_state["current_description"] = description
    app_state["last_training"] = datetime.now().isoformat()

    # Here later we will trigger actual training + simulation
    # For now just lock

    return {
        "message": "تم بدء التدريب وقفل التطبيق",
        "lock_until": lock_until.isoformat(),
        "days": lock_days
    }


@app.get("/status")
async def get_status():
    return {
        "is_locked": app_state["is_locked"],
        "lock_until": app_state["lock_until"].isoformat() if app_state["lock_until"] else None,
        "training_status": app_state["training_status"],
        "uploaded_files": app_state["uploaded_files"],
        "description": app_state["current_description"]
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)