"""
Main entry point for the Swarm Engine.
Coordinates scraping, scoring, database, notifications, and dashboard.
"""
import asyncio
import signal
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
import config
from logging_setup import setup_logging, get_logger
from scraper import Scraper
from scoring import Scorer
from database import Database
from notifications import Notifier
from models import ScoredJob
from metrics import jobs_scraped, jobs_processed, queue_length

logger = get_logger(__name__)

class SwarmEngine:
    def __init__(self):
        self.db = Database()
        self.scorer = None
        self.notifier = Notifier(self.db)
        self.shutdown_event = asyncio.Event()
        self.cycle_stop_event = asyncio.Event()
        self.worker_tasks = []
        self.queue = asyncio.Queue(maxsize=config.QUEUE_MAX_SIZE)
        self.dashboard_task = None

    async def setup(self):
        await self.db.connect()
        self.scorer = Scorer(self.db)
        logger.info("Engine setup complete")

    async def shutdown(self):
        logger.info("Shutting down...")
        self.shutdown_event.set()
        self.cycle_stop_event.set()
        # Wait for workers to finish
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        if self.scorer:
            await self.scorer.close()
        await self.db.close()
        if self.dashboard_task:
            self.dashboard_task.cancel()
            await asyncio.gather(self.dashboard_task, return_exceptions=True)
        logger.info("Shutdown complete")

    async def scrape_and_process(self):
        async with Scraper() as scraper:
            jobs = await scraper.scrape_jobs(config.SCRAPE_URL, config.MAX_PAGES)
            jobs_scraped.inc(len(jobs))
            logger.info(f"Scraped {len(jobs)} jobs")
            for job in jobs:
                await self.queue.put(job)
                queue_length.set(self.queue.qsize())

    async def worker(self, worker_id: int):
        logger.info(f"Worker {worker_id} started")
        while not self.cycle_stop_event.is_set():
            try:
                job = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.5)
                continue

            try:
                scored = await self.scorer.score_job(job)
                await self.db.upsert_job(scored)
                jobs_processed.inc()
                queue_length.set(self.queue.qsize())
                logger.info(f"[Worker {worker_id}] Scored: {job.title[:30]} -> {scored.match_score}/100")
            except Exception as e:
                logger.error(f"Error processing job {job.link}: {e}", exc_info=True)
            finally:
                self.queue.task_done()
        logger.info(f"Worker {worker_id} stopped")

    async def generate_report(self):
        jobs = await self.db.get_all_matching_jobs(config.MATCH_THRESHOLD)
        if not jobs:
            logger.info("No matching jobs to report")
            return

        Path(config.REPORT_HISTORY_DIR).mkdir(parents=True, exist_ok=True)

        report_path = Path(config.REPORT_OUTPUT_PATH)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        if report_path.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            history_path = Path(config.REPORT_HISTORY_DIR) / f"report_{timestamp}.md"
            try:
                report_path.rename(history_path)
            except Exception:
                pass
            history_files = sorted(Path(config.REPORT_HISTORY_DIR).glob("report_*.md"))
            if len(history_files) > config.REPORT_HISTORY_MAX:
                for f in history_files[:-config.REPORT_HISTORY_MAX]:
                    try:
                        f.unlink()
                    except Exception:
                        pass

        report_lines = [
            "# Highly Matched Jobs Report",
            f"*Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*",
            f"Total qualified matches found: {len(jobs)}",
            "",
        ]
        for job in jobs:
            report_lines.extend([
                f"### [{job.title}] - {job.company} (Match Score: {job.match_score}/100)",
                f"- **Rationale:** {job.explanation}",
                f"- **Apply Link:** {job.link}",
                "",
            ])
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        logger.info(f"Report written to {report_path}")

    async def run_cycle(self):
        logger.info("Starting new scan cycle")
        self.cycle_stop_event.clear()
        self.worker_tasks = []
        for i in range(config.INITIAL_WORKER_COUNT):
            task = asyncio.create_task(self.worker(i+1))
            self.worker_tasks.append(task)

        await self.scrape_and_process()

        # Wait for queue to be empty, with timeout
        try:
            await asyncio.wait_for(self.queue.join(), timeout=config.QUEUE_JOIN_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error("Queue join timed out, proceeding anyway")

        # Signal workers to stop
        self.cycle_stop_event.set()
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks = []

        await self.generate_report()
        await self.notifier.send_high_match_notifications()

        logger.info("Scan cycle complete")

    async def run_forever(self):
        await self.setup()
        if config.ENABLE_DASHBOARD:
            from dashboard import start_dashboard
            self.dashboard_task = asyncio.create_task(start_dashboard(self.db, self))
        try:
            while not self.shutdown_event.is_set():
                try:
                    await self.run_cycle()
                except Exception as e:
                    logger.error(f"Error in scan cycle: {e}", exc_info=True)
                logger.info(f"Sleeping for {config.POLL_INTERVAL_SECONDS} seconds")
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=config.POLL_INTERVAL_SECONDS)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.shutdown()

    def handle_signal(self, sig, frame=None):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        asyncio.create_task(self.shutdown())

async def main():
    setup_logging()
    engine = SwarmEngine()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: engine.handle_signal(s, None))
        except (NotImplementedError, AttributeError):
            pass
    await engine.run_forever()

if __name__ == "__main__":
    asyncio.run(main())
