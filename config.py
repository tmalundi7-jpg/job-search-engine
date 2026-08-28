"""
Central configuration for the Swarm Engine.
All settings are loaded from environment variables with sensible defaults.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Scraping ---
SCRAPE_URL = os.getenv("SCRAPE_URL", "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland")
MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))
BASE_DELAY = float(os.getenv("BASE_DELAY", "1.0"))
PROXY_LIST = os.getenv("PROXY_LIST", "")  # comma-separated
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
USE_PLAYWRIGHT_FALLBACK = os.getenv("USE_PLAYWRIGHT_FALLBACK", "true").lower() == "true"
FALLBACK_TRIGGER_ATTEMPTS = int(os.getenv("FALLBACK_TRIGGER_ATTEMPTS", "2"))
JOB_DETAILS_CONCURRENCY = int(os.getenv("JOB_DETAILS_CONCURRENCY", "10"))
MAX_DESCRIPTION_LENGTH = int(os.getenv("MAX_DESCRIPTION_LENGTH", "500"))  # characters for AI prompt

# --- Concurrency ---
INITIAL_WORKER_COUNT = int(os.getenv("INITIAL_WORKER_COUNT", "5"))
MAX_WORKER_COUNT = int(os.getenv("MAX_WORKER_COUNT", "10"))
MIN_WORKER_COUNT = int(os.getenv("MIN_WORKER_COUNT", "1"))
QUEUE_MAX_SIZE = int(os.getenv("QUEUE_MAX_SIZE", "50"))
QUEUE_JOIN_TIMEOUT = int(os.getenv("QUEUE_JOIN_TIMEOUT", "300"))  # seconds

# --- AI / Scoring ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_RETRY_COUNT = int(os.getenv("AI_RETRY_COUNT", "2"))
AI_RETRY_BASE_DELAY = float(os.getenv("AI_RETRY_BASE_DELAY", "1.0"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "12"))
AI_CACHE_TTL_HOURS = int(os.getenv("AI_CACHE_TTL_HOURS", "72"))
GROQ_MAX_CONCURRENT = int(os.getenv("GROQ_MAX_CONCURRENT", "3"))
GEMINI_MAX_CONCURRENT = int(os.getenv("GEMINI_MAX_CONCURRENT", "3"))
USE_FEEDBACK_IN_SCORING = os.getenv("USE_FEEDBACK_IN_SCORING", "true").lower() == "true"
FEEDBACK_WEIGHT_GOOD = int(os.getenv("FEEDBACK_WEIGHT_GOOD", "10"))
FEEDBACK_WEIGHT_BAD = int(os.getenv("FEEDBACK_WEIGHT_BAD", "20"))

# --- Scoring thresholds / criteria ---
MATCH_THRESHOLD = int(os.getenv("MATCH_THRESHOLD", "50"))
HIGH_MATCH_THRESHOLD = int(os.getenv("HIGH_MATCH_THRESHOLD", "70"))
SALARY_MIN = int(os.getenv("SALARY_MIN", "25000"))
SALARY_MAX = int(os.getenv("SALARY_MAX", "45000"))
EXCLUDED_TITLES = [s.strip().lower() for s in os.getenv("EXCLUDED_TITLES", "audit senior,tax director,cfo,senior partner,audit manager").split(",")]
TARGET_LOCATIONS = [s.strip().lower() for s in os.getenv("TARGET_LOCATIONS", "edinburgh,glasgow,aberdeen,dundee,remote,scotland").split(",")]

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "")  # if empty, use SQLite
SQLITE_PATH = os.getenv("SQLITE_PATH", str(Path("data") / "jobs.db"))
DB_USER_VERSION = int(os.getenv("DB_USER_VERSION", "3"))

# --- Reporting ---
REPORT_OUTPUT_PATH = os.getenv("REPORT_OUTPUT_PATH", str(Path("data") / "job_matches_report.md"))
REPORT_HISTORY_DIR = os.getenv("REPORT_HISTORY_DIR", str(Path("data") / "reports"))
REPORT_HISTORY_MAX = int(os.getenv("REPORT_HISTORY_MAX", "30"))

# --- Notifications ---
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# --- Dashboard / Health ---
ENABLE_DASHBOARD = os.getenv("ENABLE_DASHBOARD", "false").lower() == "true"
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

# --- Logging ---
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # 'json' or 'text'
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Runtime ---
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))

# Module alias for transparent `from config import config` support
config = sys.modules[__name__]
