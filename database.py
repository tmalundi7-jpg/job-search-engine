"""
Database abstraction layer supporting SQLite (default) and optional PostgreSQL.
Implements schema migrations, connection pooling, and async operations.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import config
from models import ScoredJob

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.backend = None
        self.lock = asyncio.Lock()  # for SQLite write serialization

    async def connect(self):
        if config.DATABASE_URL:
            import asyncpg
            self.backend = "postgres"
            self.pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=1,
                max_size=10,
            )
            await self._run_migrations_postgres()
        else:
            import aiosqlite
            self.backend = "sqlite"
            self.conn = await aiosqlite.connect(config.SQLITE_PATH)
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA foreign_keys=ON")
            await self._run_migrations_sqlite()
        logger.info(f"Connected to {self.backend} database")

    async def close(self):
        if self.backend == "sqlite":
            await self.conn.close()
        elif self.backend == "postgres" and hasattr(self, 'pool'):
            await self.pool.close()

    async def _run_migrations_sqlite(self):
        async with self.lock:
            cursor = await self.conn.execute("PRAGMA user_version")
            row = await cursor.fetchone()
            current_version = row[0] if row else 0
            target_version = config.DB_USER_VERSION

            if current_version < 1:
                await self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        title TEXT,
                        company TEXT,
                        link TEXT UNIQUE,
                        match_score INTEGER,
                        explanation TEXT,
                        active INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_match_score ON jobs(match_score)")
                await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)")
                current_version = 1
                await self.conn.execute(f"PRAGMA user_version = {current_version}")

            if current_version < 2:
                await self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        job_url TEXT PRIMARY KEY,
                        feedback TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                current_version = 2
                await self.conn.execute(f"PRAGMA user_version = {current_version}")

            if current_version < 3:
                # Add notified column if it doesn't exist
                cursor = await self.conn.execute("PRAGMA table_info(jobs)")
                cols = [c[1] for c in await cursor.fetchall()]
                if "notified" not in cols:
                    try:
                        await self.conn.execute("ALTER TABLE jobs ADD COLUMN notified INTEGER DEFAULT 0")
                    except Exception as e:
                        logger.warning(f"Could not add notified column: {e}")
                current_version = 3
                await self.conn.execute(f"PRAGMA user_version = {current_version}")

            await self.conn.commit()

    async def _run_migrations_postgres(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    title TEXT,
                    company TEXT,
                    link TEXT UNIQUE,
                    match_score INTEGER,
                    explanation TEXT,
                    active INTEGER,
                    notified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_match_score ON jobs(match_score)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    job_url TEXT PRIMARY KEY,
                    feedback TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def get_recent_score(self, link: str, ttl_hours: int) -> Optional[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        if self.backend == "sqlite":
            async with self.lock:
                cursor = await self.conn.execute(
                    "SELECT title, company, link, match_score, explanation, active, notified, created_at FROM jobs WHERE link = ? AND created_at > ?",
                    (link, cutoff.isoformat())
                )
                row = await cursor.fetchone()
        else:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT title, company, link, match_score, explanation, active, notified, created_at FROM jobs WHERE link = $1 AND created_at > $2",
                    link, cutoff
                )
        if row:
            result = dict(row)
            if isinstance(result.get("created_at"), str):
                try:
                    result["created_at"] = datetime.fromisoformat(result["created_at"])
                except Exception:
                    pass
            return result
        return None

    async def upsert_job(self, job: ScoredJob):
        created_at_val = job.created_at.isoformat() if isinstance(job.created_at, datetime) else str(job.created_at)
        if self.backend == "sqlite":
            async with self.lock:
                await self.conn.execute(
                    """
                    INSERT INTO jobs (title, company, link, match_score, explanation, active, notified, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(link) DO UPDATE SET
                        match_score = excluded.match_score,
                        explanation = excluded.explanation,
                        active = excluded.active,
                        notified = excluded.notified
                    """,
                    (job.title, job.company, job.link, job.match_score, job.explanation, job.active, job.notified, created_at_val)
                )
                await self.conn.commit()
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO jobs (title, company, link, match_score, explanation, active, notified, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (link) DO UPDATE SET
                        match_score = EXCLUDED.match_score,
                        explanation = EXCLUDED.explanation,
                        active = EXCLUDED.active,
                        notified = EXCLUDED.notified
                    """,
                    job.title, job.company, job.link, job.match_score, job.explanation, job.active, job.notified, job.created_at
                )

    async def get_all_matching_jobs(self, threshold: int = config.MATCH_THRESHOLD) -> List[ScoredJob]:
        if self.backend == "sqlite":
            async with self.lock:
                cursor = await self.conn.execute(
                    "SELECT * FROM jobs WHERE match_score >= ? ORDER BY match_score DESC, created_at DESC",
                    (threshold,)
                )
                rows = await cursor.fetchall()
        else:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM jobs WHERE match_score >= $1 ORDER BY match_score DESC, created_at DESC",
                    threshold
                )
        jobs = []
        for row in rows:
            created_at = row["created_at"]
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except Exception:
                    created_at = datetime.now(timezone.utc)
            jobs.append(ScoredJob(
                title=row["title"],
                company=row["company"],
                link=row["link"],
                match_score=row["match_score"],
                explanation=row["explanation"],
                active=row["active"],
                notified=row["notified"],
                created_at=created_at
            ))
        return jobs

    async def add_feedback(self, job_url: str, feedback: str):
        if self.backend == "sqlite":
            async with self.lock:
                await self.conn.execute(
                    "INSERT OR REPLACE INTO feedback (job_url, feedback) VALUES (?, ?)",
                    (job_url, feedback)
                )
                await self.conn.commit()
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO feedback (job_url, feedback) VALUES ($1, $2) ON CONFLICT (job_url) DO UPDATE SET feedback = $2",
                    job_url, feedback
                )

    async def get_feedback(self, job_url: str) -> Optional[str]:
        if self.backend == "sqlite":
            async with self.lock:
                cursor = await self.conn.execute(
                    "SELECT feedback FROM feedback WHERE job_url = ?", (job_url,)
                )
                row = await cursor.fetchone()
        else:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT feedback FROM feedback WHERE job_url = $1", job_url
                )
        return row["feedback"] if row else None

    async def mark_as_notified(self, link: str):
        if self.backend == "sqlite":
            async with self.lock:
                await self.conn.execute(
                    "UPDATE jobs SET notified = 1 WHERE link = ?", (link,)
                )
                await self.conn.commit()
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE jobs SET notified = 1 WHERE link = $1", link
                )
