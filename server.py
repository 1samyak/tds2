# server.py
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from pydantic_settings import BaseSettings

from solver.browser import fetch_rendered_html
from solver.parser import parse_quiz_page
from solver.logic import solve_quiz_task
from solver.submit import submit_answer_to_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm-quiz")


class Settings(BaseSettings):
    STUDENT_EMAIL: str
    STUDENT_SECRET: str
    OPENAI_API_KEY: str = ""

    class Config:
        env_file = ".env"


# we intentionally load from env; silence call-arg type complaint
settings = Settings()  # type: ignore[call-arg]

app = FastAPI()
QUIZ_TIMEOUT_SECONDS = 180


@app.get("/")
async def root() -> Dict[str, Any]:
    return {"status": "LLM Quiz Server Ready"}


@app.post("/quiz")
async def quiz(req: Request) -> Dict[str, Any]:
    try:
        payload: Dict[str, Any] = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("secret") != settings.STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Secret")

    url: Optional[str] = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url missing")

    deadline = time.time() + QUIZ_TIMEOUT_SECONDS
    current: Optional[str] = url
    last: Optional[Dict[str, Any]] = None

    while current and time.time() < deadline:
        html = await fetch_rendered_html(current)
        task = parse_quiz_page(html, current)
        answer = await solve_quiz_task(task, settings, deadline)

        submission: Dict[str, Any] = {
            "email": settings.STUDENT_EMAIL,
            "secret": settings.STUDENT_SECRET,
            "url": current,
            "answer": answer,
        }

        result = await submit_answer_to_url(task["submit_url"], submission)
        last = result
        current = result.get("url")

    return last or {"correct": False, "reason": "Timeout"}
