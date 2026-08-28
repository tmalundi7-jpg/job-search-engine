"""
Send notifications for high-score jobs via Slack, Discord, or email.
Only sends for jobs where notified=0, then marks them as notified.
"""
import aiohttp
import asyncio
import logging
from typing import List
import config
from models import ScoredJob
from database import Database

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self, db: Database):
        self.db = db

    async def send_high_match_notifications(self):
        # Fetch high-score jobs that have not been notified
        all_jobs = await self.db.get_all_matching_jobs(config.HIGH_MATCH_THRESHOLD)
        to_notify = [job for job in all_jobs if job.notified == 0]
        if not to_notify:
            return
        message = self._format_message(to_notify)
        if config.SLACK_WEBHOOK_URL:
            await self._send_slack(message)
        if config.DISCORD_WEBHOOK_URL:
            await self._send_discord(message)
        if config.EMAIL_SMTP_HOST and config.EMAIL_TO:
            await self._send_email(message)
        # Mark as notified
        for job in to_notify:
            await self.db.mark_as_notified(job.link)

    def _format_message(self, jobs: List[ScoredJob]) -> str:
        lines = ["*New High-Match Jobs Found:*"]
        for job in jobs[:5]:  # limit to 5
            lines.append(f"- {job.title} at {job.company} (Score: {job.match_score})")
            lines.append(f"  {job.link}")
        return "\n".join(lines)

    async def _send_slack(self, message: str):
        payload = {"text": message}
        for attempt in range(config.RETRY_COUNT):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(config.SLACK_WEBHOOK_URL, json=payload) as resp:
                        if resp.status == 200:
                            return
                        else:
                            logger.warning(f"Slack notification failed with {resp.status}")
            except Exception as e:
                logger.error(f"Slack notification error: {e}")
            await asyncio.sleep(config.BASE_DELAY * (2 ** attempt))

    async def _send_discord(self, message: str):
        payload = {"content": message}
        for attempt in range(config.RETRY_COUNT):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(config.DISCORD_WEBHOOK_URL, json=payload) as resp:
                        if resp.status in (200, 204):
                            return
                        else:
                            logger.warning(f"Discord notification failed with {resp.status}")
            except Exception as e:
                logger.error(f"Discord notification error: {e}")
            await asyncio.sleep(config.BASE_DELAY * (2 ** attempt))

    async def _send_email(self, message: str):
        try:
            import aiosmtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["From"] = config.EMAIL_FROM
            msg["To"] = config.EMAIL_TO
            msg["Subject"] = "Job Matcher: High-Match Jobs Alert"
            msg.set_content(message)
            await aiosmtplib.send(
                msg,
                hostname=config.EMAIL_SMTP_HOST,
                port=config.EMAIL_SMTP_PORT,
                username=config.EMAIL_FROM,
                password=config.EMAIL_PASSWORD,
                start_tls=True,
            )
        except Exception as e:
            logger.error(f"Email notification error: {e}")
