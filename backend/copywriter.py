"""Wraps the existing ResearcherAgent + CopywriterAgent from cold_emailer.py
so they can be called from async code without blocking the event loop.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Make cold_emailer.py importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cold_emailer import (  # type: ignore
    CompanyData,
    ResumeData,
    ResearcherAgent,
    CopywriterAgent,
)


def load_resume(path: str = "resume.json") -> ResumeData:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    data = json.loads(p.read_text())
    return ResumeData(
        name=data.get("name", "Your Name"),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        skills=data.get("skills", []),
        past_projects=data.get("projects", []),
        certifications=data.get("certifications", []),
        interests=data.get("interests", []),
        writing_style=data.get("writing_style", {
            "tone": "professional yet conversational",
            "length": "concise",
            "signature": "Best regards,",
        }),
    )


class AsyncCopywriter:
    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5")
        self.researcher = ResearcherAgent(self.model)
        self.copywriter = CopywriterAgent(self.model)

    async def research(self, company: CompanyData) -> CompanyData:
        return await asyncio.to_thread(self.researcher.research_company, company)

    async def write_email(
        self,
        company: CompanyData,
        resume: ResumeData,
        additional_interests: Optional[str] = None,
    ) -> str:
        return await asyncio.to_thread(
            self.copywriter.write_email, company, resume, additional_interests
        )


def split_subject_body(email_text: str) -> tuple[str, str]:
    """If the LLM included a 'Subject:' line, peel it off; otherwise pick a default."""
    lines = email_text.strip().splitlines()
    subject = ""
    body_start = 0
    for i, line in enumerate(lines[:5]):
        low = line.lower().strip()
        if low.startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    if not subject:
        subject = "Quick question"
    return subject, body
