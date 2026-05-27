"""Playwright-driven discovery agent. Runs a visible Chrome window."""
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .event_bus import EventBus

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@dataclass
class DiscoveredCompany:
    name: str
    website: str
    snippet: str = ""
    industry: str = ""
    emails: list[str] = field(default_factory=list)


class BrowserAgent:
    """Searches the web for companies matching a target description.

    Runs Chromium in headed mode by default so the user sees what's happening.
    """

    def __init__(self, bus: EventBus, headless: bool = False):
        self.bus = bus
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--start-maximized"],
        )
        self._context = await self._browser.new_context(
            viewport=None,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        finally:
            if self._playwright:
                await self._playwright.stop()

    async def discover(self, query: str, max_results: int = 5) -> list[DiscoveredCompany]:
        """Search for companies matching `query` and return discovered leads."""
        await self.bus.status(f"Opening browser and searching: {query}")
        page = await self._context.new_page()

        results: list[DiscoveredCompany] = []
        try:
            search_url = f"https://duckduckgo.com/?q={quote_plus(query)}&ia=web"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await self.bus.log(f"Loaded search results for '{query}'", url=search_url)

            await page.wait_for_selector("article[data-testid='result']", timeout=15000)
            result_handles = await page.query_selector_all("article[data-testid='result']")
            await self.bus.log(f"Found {len(result_handles)} raw search hits")

            seen_domains: set[str] = set()
            for handle in result_handles:
                if len(results) >= max_results:
                    break

                title_el = await handle.query_selector("h2 a")
                snippet_el = await handle.query_selector("[data-result='snippet']")
                if not title_el:
                    continue

                href = await title_el.get_attribute("href")
                name = (await title_el.inner_text() or "").strip()
                snippet = (await snippet_el.inner_text() if snippet_el else "").strip()

                if not href:
                    continue

                domain = urlparse(href).netloc.lower().lstrip("www.")
                # Skip aggregators / social
                bad_domains = {"linkedin.com", "facebook.com", "twitter.com", "x.com",
                               "youtube.com", "wikipedia.org", "reddit.com", "medium.com"}
                if any(bd in domain for bd in bad_domains):
                    continue
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                company = DiscoveredCompany(name=name, website=f"https://{domain}", snippet=snippet)
                results.append(company)
                await self.bus.log(f"  -> {name} ({domain})")

            for company in results:
                emails = await self._scrape_emails_from_site(company.website)
                company.emails = emails
                if emails:
                    await self.bus.log(f"  emails on {company.website}: {emails[:3]}")
                else:
                    await self.bus.log(f"  no public emails on {company.website}")
        finally:
            await page.close()

        await self.bus.status(f"Discovery complete: {len(results)} companies")
        return results

    async def _scrape_emails_from_site(self, website: str) -> list[str]:
        """Visit the homepage + likely contact pages, collect mailto/text emails."""
        emails: set[str] = set()
        page = await self._context.new_page()
        try:
            try:
                await page.goto(website, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                await self.bus.log(f"  could not open {website}: {e}")
                return []
            emails.update(await self._extract_emails(page))

            # Try common contact pages
            base = website.rstrip("/")
            for path in ("/contact", "/contact-us", "/about", "/team"):
                if len(emails) >= 3:
                    break
                try:
                    await page.goto(base + path, wait_until="domcontentloaded", timeout=10000)
                    emails.update(await self._extract_emails(page))
                except Exception:
                    continue
        finally:
            await page.close()
        # Filter junk
        cleaned = [e for e in emails if not e.lower().endswith((".png", ".jpg", ".svg"))]
        return cleaned

    async def _extract_emails(self, page: Page) -> set[str]:
        emails: set[str] = set()
        # mailto links
        for el in await page.query_selector_all("a[href^='mailto:']"):
            href = await el.get_attribute("href") or ""
            addr = href.replace("mailto:", "").split("?")[0].strip()
            if addr and "@" in addr:
                emails.add(addr)
        # text scan
        try:
            html = await page.content()
            for m in EMAIL_RE.findall(html):
                emails.add(m)
        except Exception:
            pass
        return emails
