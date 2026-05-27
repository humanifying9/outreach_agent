"""Resolve a company website to contact emails using Hunter.io (if configured)
with a fallback to whatever the browser agent scraped from the public site.
"""
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from .event_bus import EventBus


@dataclass
class Contact:
    email: str
    full_name: str = ""
    position: str = ""
    confidence: int = 0
    source: str = "scrape"  # "hunter" | "scrape"


class LeadFinder:
    def __init__(self, bus: EventBus, hunter_api_key: Optional[str] = None):
        self.bus = bus
        self.hunter_api_key = hunter_api_key or os.environ.get("HUNTER_API_KEY") or None

    async def find_contacts(self, website: str, scraped_emails: list[str]) -> list[Contact]:
        domain = self._extract_domain(website)
        contacts: list[Contact] = []

        if self.hunter_api_key:
            await self.bus.log(f"  Hunter.io: looking up contacts for {domain}")
            contacts = await self._hunter_domain_search(domain)
            if contacts:
                await self.bus.log(f"  Hunter returned {len(contacts)} contacts")
                return contacts
            await self.bus.log(f"  Hunter returned no contacts; falling back to scraped emails")

        # Fallback: use whatever the browser scraped
        for email in scraped_emails:
            contacts.append(Contact(email=email, source="scrape"))
        return contacts

    def _extract_domain(self, website: str) -> str:
        parsed = urlparse(website if "://" in website else f"https://{website}")
        netloc = parsed.netloc or parsed.path
        return netloc.replace("www.", "").lower()

    async def _hunter_domain_search(self, domain: str) -> list[Contact]:
        url = "https://api.hunter.io/v2/domain-search"
        params = {"domain": domain, "api_key": self.hunter_api_key, "limit": 5}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            await self.bus.error(f"Hunter API error for {domain}: {e}")
            return []

        out: list[Contact] = []
        for item in data.get("data", {}).get("emails", []):
            out.append(Contact(
                email=item.get("value", ""),
                full_name=f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                position=item.get("position", "") or "",
                confidence=int(item.get("confidence") or 0),
                source="hunter",
            ))
        return [c for c in out if c.email]
