"""
Scoring engine with tri-tier fallback: Groq -> Gemini -> Heuristic.
Includes caching, retries, feedback integration, and description usage.
"""
import asyncio
import json
import re
import time
import logging
from typing import Optional, Dict, Any
import aiohttp
import config
from models import JobListing, ScoredJob
from database import Database
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Scorer:
    def __init__(self, db: Database):
        self.db = db
        self.groq_sem = asyncio.Semaphore(config.GROQ_MAX_CONCURRENT)
        self.gemini_sem = asyncio.Semaphore(config.GEMINI_MAX_CONCURRENT)
        self.ai_cache = {}
        self.groq_session: Optional[aiohttp.ClientSession] = None

    async def _ensure_groq_session(self):
        if self.groq_session is None or self.groq_session.closed:
            self.groq_session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}
            )

    async def close(self):
        if self.groq_session and not self.groq_session.closed:
            await self.groq_session.close()

    async def score_job(self, job: JobListing) -> ScoredJob:
        # Check cache
        cached = await self._get_cached(job.link)
        if cached:
            logger.debug(f"Cache hit for {job.link}")
            return cached

        # Try Groq
        if config.GROQ_API_KEY:
            try:
                result = await self._score_with_groq(job)
                if result:
                    await self._cache_result(job.link, result)
                    return result
            except Exception as e:
                logger.warning(f"Groq scoring failed for {job.link}: {e}")

        # Try Gemini
        if config.GEMINI_API_KEY:
            try:
                result = await self._score_with_gemini(job)
                if result:
                    await self._cache_result(job.link, result)
                    return result
            except Exception as e:
                logger.warning(f"Gemini scoring failed for {job.link}: {e}")

        # Heuristic fallback
        result = await self._heuristic_score(job)
        await self._cache_result(job.link, result)
        return result

    async def _get_cached(self, link: str) -> Optional[ScoredJob]:
        # In-memory cache
        if link in self.ai_cache:
            score, explanation, notified, ts = self.ai_cache[link]
            if time.time() - ts < config.AI_CACHE_TTL_HOURS * 3600:
                return ScoredJob(
                    title="", company="", link=link,
                    match_score=score, explanation=explanation, notified=notified
                )
            else:
                del self.ai_cache[link]
        # Database cache
        db_result = await self.db.get_recent_score(link, config.AI_CACHE_TTL_HOURS)
        if db_result:
            if isinstance(db_result.get("created_at"), str):
                try:
                    db_result["created_at"] = datetime.fromisoformat(db_result["created_at"])
                except Exception:
                    db_result["created_at"] = datetime.now(timezone.utc)
            return ScoredJob(**db_result)
        return None

    async def _cache_result(self, link: str, scored: ScoredJob):
        self.ai_cache[link] = (scored.match_score, scored.explanation, scored.notified, time.time())
        await self.db.upsert_job(scored)

    async def _score_with_groq(self, job: JobListing) -> Optional[ScoredJob]:
        await self._ensure_groq_session()
        async with self.groq_sem:
            for attempt in range(config.AI_RETRY_COUNT):
                try:
                    payload = self._build_ai_payload(job)
                    async with self.groq_session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=config.AI_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            raise Exception(f"Groq HTTP {resp.status}")
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        # Clean JSON ticks if present
                        content_clean = content.strip()
                        if content_clean.startswith("```json"): content_clean = content_clean[7:]
                        elif content_clean.startswith("```"): content_clean = content_clean[3:]
                        if content_clean.endswith("```"): content_clean = content_clean[:-3]
                        parsed = json.loads(content_clean)
                        score = int(parsed.get("match_score", parsed.get("score", 0)))
                        explanation = parsed.get("explanation", "AI evaluation")
                        return ScoredJob(
                            title=job.title,
                            company=job.company,
                            link=job.link,
                            match_score=score,
                            explanation=explanation,
                        )
                except Exception as e:
                    logger.warning(f"Groq attempt {attempt+1} failed: {e}")
                    if attempt < config.AI_RETRY_COUNT - 1:
                        await asyncio.sleep(config.AI_RETRY_BASE_DELAY * (2 ** attempt))
            return None

    async def _score_with_gemini(self, job: JobListing) -> Optional[ScoredJob]:
        async with self.gemini_sem:
            for attempt in range(config.AI_RETRY_COUNT):
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=config.GEMINI_API_KEY)
                    model = genai.GenerativeModel(config.GEMINI_MODEL)
                    prompt = self._build_prompt_text(job)
                    response = await asyncio.to_thread(
                        model.generate_content,
                        prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    text = response.text
                    text_clean = text.strip()
                    if text_clean.startswith("```json"): text_clean = text_clean[7:]
                    elif text_clean.startswith("```"): text_clean = text_clean[3:]
                    if text_clean.endswith("```"): text_clean = text_clean[:-3]
                    parsed = json.loads(text_clean)
                    score = int(parsed.get("match_score", parsed.get("score", 0)))
                    explanation = parsed.get("explanation", "AI evaluation")
                    return ScoredJob(
                        title=job.title,
                        company=job.company,
                        link=job.link,
                        match_score=score,
                        explanation=explanation,
                    )
                except Exception as e:
                    logger.warning(f"Gemini attempt {attempt+1} failed: {e}")
                    if attempt < config.AI_RETRY_COUNT - 1:
                        await asyncio.sleep(config.AI_RETRY_BASE_DELAY * (2 ** attempt))
            return None

    def _build_ai_payload(self, job: JobListing) -> Dict[str, Any]:
        prompt = self._build_prompt_text(job)
        return {
            "model": config.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "You are a job matching assistant. Evaluate the job against the candidate profile and return JSON with keys 'match_score' (0-100) and 'explanation'."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

    def _build_prompt_text(self, job: JobListing) -> str:
        criteria = f"""
        Candidate profile:
        - ~2 years experience in accounting/finance
        - Target roles: Management Accountant, FP&A Analyst, Public Sector Finance, Assistant Accountant, Trainee Accountant, Accounts Assistant
        - Geography: Scotland (Edinburgh, Glasgow, Aberdeen, etc.) or Remote UK
        - Salary band: £{config.SALARY_MIN} - £{config.SALARY_MAX}
        - Exclusions: {', '.join(config.EXCLUDED_TITLES)}
        """
        job_text = f"""
        Job Title: {job.title}
        Company: {job.company}
        Location: {job.location or 'Not specified'}
        Salary: {job.salary or 'Not specified'}
        Description: {job.description or 'Not available'}
        """
        return f"{criteria}\n\nEvaluate this job:\n{job_text}\n\nReturn JSON with 'match_score' (integer 0-100) and 'explanation'."

    async def _heuristic_score(self, job: JobListing) -> ScoredJob:
        score = 0
        reasons = []

        title_lower = job.title.lower()
        target_keywords = [
            "management accountant", "fp&a", "financial planning",
            "assistant accountant", "trainee accountant", "accounts assistant",
            "public sector finance", "finance analyst", "accounting", "financial accountant"
        ]
        matched_keywords = [kw for kw in target_keywords if kw in title_lower]
        if matched_keywords:
            score += 50
            reasons.append(f"Title matches: {', '.join(matched_keywords)}")
        else:
            if any(word in title_lower for word in ["account", "finance", "financial"]):
                score += 30
                reasons.append("Accounting/finance related title")
            else:
                score -= 20
                reasons.append("Title not accounting/finance related")

        for excl in config.EXCLUDED_TITLES:
            if excl in title_lower:
                score -= 40
                reasons.append(f"Excluded title: {excl}")
                break

        loc = (job.location or "").lower()
        if any(target_loc in loc for target_loc in config.TARGET_LOCATIONS):
            score += 20
            reasons.append("Location matches target")
        elif "remote" in loc:
            score += 25
            reasons.append("Remote position")
        else:
            score += 10
            reasons.append("Location default/Scotland general")

        salary_text = job.salary or ""
        if salary_text:
            numbers = re.findall(r'\d[\d,]*', salary_text)
            if numbers:
                try:
                    salary = int(numbers[0].replace(',', ''))
                    if config.SALARY_MIN <= salary <= config.SALARY_MAX:
                        score += 20
                        reasons.append("Salary within target band")
                    elif salary < config.SALARY_MIN:
                        score -= 10
                        reasons.append("Salary below target")
                    elif salary > config.SALARY_MAX:
                        score -= 10
                        reasons.append("Salary above target")
                except Exception:
                    pass

        company_lower = job.company.lower()
        if "recruitment" in company_lower or "staffing" in company_lower:
            score += 5
            reasons.append("Recruitment partner")

        # Apply feedback if enabled
        if config.USE_FEEDBACK_IN_SCORING:
            feedback = await self.db.get_feedback(job.link)
            if feedback == 'good':
                score += config.FEEDBACK_WEIGHT_GOOD
                reasons.append("Positive feedback applied")
            elif feedback == 'bad':
                score -= config.FEEDBACK_WEIGHT_BAD
                reasons.append("Negative feedback applied")

        score = max(0, min(100, score))
        explanation = "; ".join(reasons) if reasons else "General candidate alignment"

        return ScoredJob(
            title=job.title,
            company=job.company,
            link=job.link,
            match_score=score,
            explanation=explanation,
        )
