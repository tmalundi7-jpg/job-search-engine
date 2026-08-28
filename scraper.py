"""
Web scraper for Reed.co.uk with retries, proxy rotation, selectors fallback,
detail page fetching, and Playwright fallback.
"""
import asyncio
import random
import aiohttp
from selectolax.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin
import logging
import config
from models import JobListing
from utils import extract_domain

logger = logging.getLogger(__name__)

class Scraper:
    def __init__(self):
        self.proxy_list = [p.strip() for p in config.PROXY_LIST.split(",") if p.strip()]
        self.session: Optional[aiohttp.ClientSession] = None
        self.detail_semaphore = asyncio.Semaphore(config.JOB_DETAILS_CONCURRENCY)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": config.USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT),
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _fetch(self, url: str, use_proxy: bool = True) -> Optional[str]:
        """Fetch page content with retries and optional proxy. Reuses session."""
        for attempt in range(config.RETRY_COUNT):
            proxy = None
            if use_proxy and self.proxy_list:
                proxy = random.choice(self.proxy_list)
            try:
                async with self.session.get(url, proxy=proxy) as response:
                    if response.status == 200:
                        html = await response.text()
                        if self._is_blocked(html):
                            logger.warning(f"Blocked/CAPTCHA detected on {url}")
                            return None
                        return html
                    elif response.status in (429, 503):
                        logger.warning(f"Rate limited on {url}, status {response.status}, attempt {attempt+1}")
                    else:
                        logger.warning(f"Unexpected status {response.status} for {url}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Request failed for {url}: {e}, attempt {attempt+1}")

            delay = config.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)

        logger.error(f"Failed to fetch {url} after {config.RETRY_COUNT} attempts")
        return None

    def _is_blocked(self, html: str) -> bool:
        """Check for common CAPTCHA/blocking indicators."""
        lower = html.lower()
        indicators = ["captcha", "verify you are human", "access denied", "blocked"]
        return any(ind in lower for ind in indicators)

    async def scrape_jobs(self, base_url: str, max_pages: int = config.MAX_PAGES) -> List[JobListing]:
        """Scrape job listings, then fetch details (descriptions)."""
        all_jobs = []
        for page in range(1, max_pages + 1):
            page_url = f"{base_url}?p={page}" if page > 1 else base_url
            html = await self._fetch(page_url)
            if not html:
                break
            jobs = self._parse_listings(html, page_url)
            if not jobs:
                logger.warning(f"No jobs found on page {page}, stopping pagination")
                break
            all_jobs.extend(jobs)
            await asyncio.sleep(1)  # polite delay

        if not all_jobs and config.USE_PLAYWRIGHT_FALLBACK:
            logger.info("Standard scraping found no jobs, attempting Playwright fallback...")
            html = await self._fetch_with_playwright(base_url)
            if html:
                all_jobs = self._parse_listings(html, base_url)

        # Deduplicate by link
        deduped = {}
        for job in all_jobs:
            deduped[job.link] = job
        unique_jobs = list(deduped.values())

        # Phase 2: Fetch details concurrently
        if unique_jobs:
            logger.info(f"Fetching details for {len(unique_jobs)} jobs...")
            await asyncio.gather(*[self._enrich_job(job) for job in unique_jobs], return_exceptions=True)

        return unique_jobs

    async def _enrich_job(self, job: JobListing):
        """Fetch job detail page and extract description, location, salary."""
        async with self.detail_semaphore:
            html = await self._fetch(job.link, use_proxy=False)
            if not html:
                return
            tree = HTMLParser(html)
            desc_selectors = [
                "div.description",
                "div.job-description",
                "section.job-description",
                "div[itemprop='description']",
                "div#jobDescription",
                "article",
            ]
            description = None
            for sel in desc_selectors:
                node = tree.css_first(sel)
                if node:
                    description = node.text(strip=True)
                    break
            if description:
                job.description = description[:config.MAX_DESCRIPTION_LENGTH]
            loc_node = tree.css_first("span.location, div.location, li.location, [itemprop='jobLocation']")
            if loc_node:
                job.location = loc_node.text(strip=True)
            sal_node = tree.css_first("span.salary, div.salary, li.salary, [itemprop='baseSalary']")
            if sal_node:
                job.salary = sal_node.text(strip=True)

    def _parse_listings(self, html: str, base_url: str) -> List[JobListing]:
        """Parse job listings from HTML using selectolax with multiple selector fallbacks."""
        tree = HTMLParser(html)
        jobs = []

        selectors = [
            "article",
            "div.job-result",
            "div.job-card",
            "div.job-result-card",
            "li.job-result",
        ]

        cards = []
        for sel in selectors:
            cards = tree.css(sel)
            if cards:
                break

        if not cards:
            for a in tree.css("a[href*='/jobs/']"):
                title = a.text(strip=True)
                link = urljoin(base_url, a.attributes.get("href", ""))
                if title and link:
                    jobs.append(JobListing(title=title, company="", link=link))
            return jobs

        for card in cards:
            title = ""
            for title_sel in ["h2", "h3", "a.title", "a.job-title"]:
                title_node = card.css_first(title_sel)
                if title_node:
                    title = title_node.text(strip=True)
                    break
            if not title:
                a_node = card.css_first("a")
                if a_node:
                    title = a_node.text(strip=True)

            if not title:
                continue

            company = ""
            for comp_sel in ["span.company", "div.company", "a.company", "span.recruiter", "a.gtmJobListingPostedBy"]:
                comp_node = card.css_first(comp_sel)
                if comp_node:
                    company = comp_node.text(strip=True)
                    break

            link = ""
            a_node = card.css_first("a[href*='/jobs/']")
            if a_node:
                link = urljoin(base_url, a_node.attributes.get("href", ""))
                if '?' in link:
                    link = link.split('?')[0]

            if not link:
                continue

            location = ""
            for loc_sel in ["span.location", "div.location", "li.location"]:
                loc_node = card.css_first(loc_sel)
                if loc_node:
                    location = loc_node.text(strip=True)
                    break

            salary = ""
            for sal_sel in ["span.salary", "div.salary", "li.salary"]:
                sal_node = card.css_first(sal_sel)
                if sal_node:
                    salary = sal_node.text(strip=True)
                    break

            jobs.append(JobListing(
                title=title,
                company=company,
                link=link,
                location=location,
                salary=salary,
            ))

        return jobs

    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fallback: render page with headless browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Cannot use fallback.")
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(user_agent=config.USER_AGENT)
                try:
                    await page.goto(url, timeout=config.REQUEST_TIMEOUT * 1000)
                    await page.wait_for_load_state("networkidle", timeout=config.REQUEST_TIMEOUT * 1000)
                    content = await page.content()
                    return content
                except Exception as e:
                    logger.error(f"Playwright fallback navigation failed: {e}")
                    return None
                finally:
                    await browser.close()
        except Exception as e:
            logger.error(f"Playwright initialization failed: {e}")
            return None
