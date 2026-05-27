"""Runs the full discover -> research -> write -> create-draft pipeline,
emitting events to the EventBus so the UI can follow along.
"""
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from cold_emailer import CompanyData  # type: ignore

from .browser_agent import BrowserAgent
from .copywriter import AsyncCopywriter, load_resume, split_subject_body
from .event_bus import AgentEvent, EventBus
from .gmail_client import GmailClient
from .lead_finder import Contact, LeadFinder

DRAFTS_FILE = Path(__file__).resolve().parents[1] / "data" / "drafts.json"


@dataclass
class Draft:
    id: str
    company: str
    website: str
    to_email: str
    to_name: str
    subject: str
    body: str
    gmail_draft_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _load_drafts() -> list[Draft]:
    if not DRAFTS_FILE.exists():
        return []
    try:
        raw = json.loads(DRAFTS_FILE.read_text())
        return [Draft(**d) for d in raw]
    except Exception:
        return []


def _save_drafts(drafts: list[Draft]):
    DRAFTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS_FILE.write_text(json.dumps([asdict(d) for d in drafts], indent=2))


class Orchestrator:
    def __init__(self, bus: EventBus, gmail: GmailClient, headless_browser: bool = False):
        self.bus = bus
        self.gmail = gmail
        self.headless_browser = headless_browser
        self.copywriter = AsyncCopywriter()
        self.lead_finder = LeadFinder(bus)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def run_campaign(
        self,
        query: str,
        max_companies: int = 5,
        additional_interests: str = "",
        create_gmail_drafts: bool = True,
    ):
        if self._running:
            await self.bus.error("Campaign already running")
            return
        self._running = True
        try:
            await self._run(query, max_companies, additional_interests, create_gmail_drafts)
        except Exception as e:
            await self.bus.error(f"Campaign failed: {e}")
        finally:
            self._running = False
            await self.bus.emit(AgentEvent(type="done", message="Campaign finished"))

    async def _run(
        self,
        query: str,
        max_companies: int,
        additional_interests: str,
        create_gmail_drafts: bool,
    ):
        resume = load_resume()
        await self.bus.status(f"Loaded resume for {resume.name}")

        async with BrowserAgent(self.bus, headless=self.headless_browser) as agent:
            await self.bus.status("Discovering companies...")
            discovered = await agent.discover(query, max_results=max_companies)

            if not discovered:
                await self.bus.error("No companies found for that query")
                return

            for dc in discovered:
                await self.bus.status(f"Processing {dc.name}")
                contacts = await self.lead_finder.find_contacts(dc.website, dc.emails)
                if not contacts:
                    await self.bus.log(f"  no usable contacts for {dc.name}, skipping")
                    continue

                company = CompanyData(
                    name=dc.name,
                    website=dc.website,
                    industry=dc.industry or "Unknown",
                    size="Unknown",
                    location="Unknown",
                )

                await self.bus.log(f"  researching {dc.name}...")
                company = await self.copywriter.research(company)
                await self.bus.log(
                    f"  core problem: {company.core_problem[:80]}"
                )

                # Pick best contact (highest Hunter confidence, else first)
                contact = max(contacts, key=lambda c: c.confidence)
                await self.bus.log(
                    f"  writing email to {contact.email}"
                    + (f" ({contact.full_name}, {contact.position})" if contact.full_name else "")
                )

                email_text = await self.copywriter.write_email(
                    company, resume, additional_interests or None
                )
                subject, body = split_subject_body(email_text)

                draft = Draft(
                    id=str(uuid.uuid4()),
                    company=company.name,
                    website=company.website,
                    to_email=contact.email,
                    to_name=contact.full_name,
                    subject=subject,
                    body=body,
                )

                if create_gmail_drafts and self.gmail.is_authenticated():
                    try:
                        await self.bus.log(f"  creating Gmail draft...")
                        gmail_resp = await asyncio.to_thread(
                            self.gmail.create_draft,
                            contact.email,
                            subject,
                            body,
                        )
                        draft.gmail_draft_id = gmail_resp.get("id")
                        await self.bus.log(f"  draft saved in Gmail (id: {draft.gmail_draft_id})")
                    except Exception as e:
                        await self.bus.error(f"Gmail draft failed for {dc.name}: {e}")
                elif create_gmail_drafts:
                    await self.bus.log("  skipping Gmail draft (not authenticated)")

                drafts = _load_drafts()
                drafts.append(draft)
                _save_drafts(drafts)

                await self.bus.emit(AgentEvent(
                    type="draft_created",
                    message=f"Draft for {company.name}",
                    data=asdict(draft),
                ))


def list_drafts() -> list[dict]:
    return [asdict(d) for d in _load_drafts()]


def delete_draft(draft_id: str) -> bool:
    drafts = _load_drafts()
    new_drafts = [d for d in drafts if d.id != draft_id]
    if len(new_drafts) == len(drafts):
        return False
    _save_drafts(new_drafts)
    return True
