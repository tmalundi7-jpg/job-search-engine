import os
import sys
import time
import sqlite3
import json
import re
import signal
import asyncio
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Ensure unbuffered real-time output in all terminals and log files
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# Base directory for absolute path resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")
REPORT_PATH = os.path.join(DATA_DIR, "job_matches_report.md")
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(dotenv_path=ENV_PATH)

# Global DB Lock for safe async writes
db_lock = asyncio.Lock()

# Target CV Profile
CV_TEXT = """
Candidate has ~2 years experience in accounting.
Target roles: Entry/Mid Management Accountant, FP&A Analyst, Public Sector Finance, Assistant Accountant, Trainee Accountant, Finance Assistant, Accounts Assistant, Cost Accountant, Commercial Analyst.
Location: Scotland or Remote UK.
Salary: £25k-£45k.
AVOID: Big 4 Audit, CFO, Senior Partner roles.
"""

POSITIVE_KEYWORDS = [
    "management accountant", "assistant accountant", "fp&a", "finance analyst",
    "accounts assistant", "trainee accountant", "public sector finance",
    "junior accountant", "finance assistant", "accounts payable", "accounts receivable",
    "cost accountant", "commercial accountant", "financial accountant"
]

NEGATIVE_KEYWORDS = [
    "partner", "cfo", "chief financial officer", "audit senior", "head of audit",
    "tax director", "senior manager audit", "director of audit"
]

# Identify AI Provider
groq_key = os.getenv("GROQ_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")

ai_provider = None
groq_client = None
gemini_client = None

if groq_key and groq_key.startswith("gsk_"):
    try:
        from groq import AsyncGroq
        groq_client = AsyncGroq(api_key=groq_key)
        ai_provider = "GROQ"
        print("[Engine] Initialized with Groq AI Provider (llama-3.3-70b-versatile).", flush=True)
    except Exception as e:
        print(f"[Engine] Could not initialize Groq client: {e}", flush=True)

if not ai_provider and gemini_key:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=gemini_key)
        ai_provider = "GEMINI"
        print("[Engine] Initialized with Google Gemini AI Provider (gemini-2.5-flash).", flush=True)
    except Exception as e:
        print(f"[Engine] Could not initialize Gemini client: {e}", flush=True)

if not ai_provider:
    print("[Engine] Notice: No valid Groq or Gemini API key found in .env.", flush=True)
    print("[Engine] Active Engine: Smart UK Accounting Heuristic Matcher is ACTIVE.", flush=True)
    ai_provider = "HEURISTIC"

def setup_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (title TEXT, company TEXT, link TEXT UNIQUE, match_score INTEGER, explanation TEXT, active INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_match_score ON jobs(match_score)")
    
    # Auto-cleanup old 0-score / failed records from legacy runs so they get freshly evaluated
    c.execute("DELETE FROM jobs WHERE match_score <= 0")
    conn.commit()
    return conn

def scrape_jobs():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9',
    }
    
    # Multi-stream targeting Scotland & Remote Accounting Roles
    pages = [
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/management-accountant-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/assistant-accountant-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/finance-analyst-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/trainee-accountant-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-edinburgh",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-glasgow",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland?pageno=2",
        "https://www.reed.co.uk/jobs/remote-accounting-jobs"
    ]
    
    jobs = []
    print("[Scraper] Scanning Reed.co.uk across Scotland & Remote accounting job streams...", flush=True)
    
    for url in pages:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
                
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Try primary and fallback article selectors
            articles = soup.find_all("article")
            if not articles:
                articles = soup.find_all("div", class_=lambda x: x and ("job-result" in x or "job-card" in x))
                
            for article in articles:
                h2 = article.find(["h2", "h3"])
                if not h2: 
                    continue
                
                title = h2.text.strip()
                a = h2.find("a")
                link = ""
                if a and a.get("href"):
                    raw_href = a["href"].split("?")[0]
                    link = raw_href if raw_href.startswith("http") else "https://www.reed.co.uk" + raw_href
                    
                comp_a = article.find("a", class_=lambda x: x and ("PostedBy" in x or "posted-by" in x))
                if not comp_a:
                    comp_a = article.find(["div", "span"], class_=lambda x: x and "posted-by" in x)
                company = comp_a.text.strip() if comp_a else "Recruitment Partner / Direct"
                
                if title and link:
                    jobs.append({"title": title, "company": company, "link": link, "description": "Accounting role matching UK specifications."})
        except Exception as e:
            print(f"[Scraper] Warning on {url}: {e}", flush=True)
            
    # Deduplicate in-memory
    seen_links = set()
    unique_jobs = []
    for j in jobs:
        if j['link'] not in seen_links:
            seen_links.add(j['link'])
            unique_jobs.append(j)
            
    print(f"[Scraper] Successfully collected {len(unique_jobs)} live job postings for evaluation.", flush=True)
    return unique_jobs

def heuristic_score(title):
    t_lower = title.lower()
    for neg in NEGATIVE_KEYWORDS:
        if neg in t_lower:
            return 25, f"Excluded: matches senior/audit restriction ({neg})."
            
    for pos in POSITIVE_KEYWORDS:
        if pos in t_lower:
            return 82, f"High match: direct candidate profile match for '{pos}'."
            
    if "account" in t_lower or "finance" in t_lower:
        return 70, "Strong match: relevant finance/accounting role in target geography."
        
    return 40, "General professional role outside primary accounting targets."

async def evaluate_job(job):
    title = job['title']
    company = job['company']
    
    # Provider: HEURISTIC
    if ai_provider == "HEURISTIC":
        score, explanation = heuristic_score(title)
        return score, explanation

    prompt = f"""
    You are an expert UK accounting career coach. Evaluate this job against the candidate's CV.
    CV & Target Criteria:
    {CV_TEXT}
    
    Job Title: {title}
    Company: {company}
    
    Return ONLY a JSON object with EXACTLY these keys:
    "score": integer 0-100 (Be generous for junior/mid accounting, management accountant, or FP&A).
    "explanation": brief 1-sentence explanation of suitability.
    """
    
    # Provider: GROQ
    if ai_provider == "GROQ" and groq_client:
        try:
            response = await asyncio.wait_for(
                groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.1,
                    response_format={"type": "json_object"}
                ),
                timeout=12.0
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"): content = content[7:]
            elif content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            data = json.loads(content)
            return data.get("score", 0), data.get("explanation", "AI scored.")
        except Exception as e:
            score, explanation = heuristic_score(title)
            return score, f"[Heuristic] {explanation}"
            
    # Provider: GEMINI
    if ai_provider == "GEMINI" and gemini_client:
        try:
            from google.genai import types
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    gemini_client.models.generate_content,
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                ),
                timeout=12.0
            )
            content = response.text.strip()
            if content.startswith("```json"): content = content[7:]
            elif content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            data = json.loads(content)
            return data.get("score", 0), data.get("explanation", "Gemini scored.")
        except Exception as e:
            score, explanation = heuristic_score(title)
            return score, f"[Heuristic] {explanation}"
            
    return heuristic_score(title)

async def agent_worker(name, queue, db_conn):
    c = db_conn.cursor()
    
    while True:
        job = await queue.get()
        
        try:
            # Safe async check: Only skip if already evaluated with a positive valid score
            async with db_lock:
                c.execute("SELECT match_score FROM jobs WHERE link=? AND match_score > 0", (job['link'],))
                existing = c.fetchone()
                
            if existing:
                queue.task_done()
                continue
                
            score, explanation = await evaluate_job(job)
            
            async with db_lock:
                try:
                    c.execute(
                        """INSERT INTO jobs (title, company, link, match_score, explanation, active) 
                           VALUES (?, ?, ?, ?, ?, 1)
                           ON CONFLICT(link) DO UPDATE SET 
                           match_score=excluded.match_score, 
                           explanation=excluded.explanation, 
                           title=excluded.title, 
                           company=excluded.company""",
                        (job['title'], job['company'], job['link'], score, explanation)
                    )
                    db_conn.commit()
                except Exception as db_err:
                    print(f"[{name}] DB insert error: {db_err}", flush=True)
                    
            print(f"[{name}] {job['title'][:32]} @ {job['company'][:18]} -> Score: {score}/100", flush=True)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[{name}] Worker error on {job.get('title')}: {e}", flush=True)
        finally:
            await asyncio.sleep(0.3)
            queue.task_done()

def generate_report(conn):
    c = conn.cursor()
    # Pull all jobs scoring 50+ (high matches)
    c.execute("SELECT title, company, link, match_score, explanation, created_at FROM jobs WHERE match_score >= 50 ORDER BY match_score DESC, created_at DESC")
    jobs = c.fetchall()
    
    with open(REPORT_PATH, "w", encoding='utf-8') as f:
        f.write("# Highly Matched Jobs Report\n\n")
        f.write(f"*Last updated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}*\n\n")
        f.write(f"Total qualified matches found: **{len(jobs)}**\n\n---\n\n")
        
        if not jobs:
            f.write("No matching jobs scored 50+ yet. The engine is continually searching for new postings.\n")
        else:
            for j in jobs:
                f.write(f"### {j[0]} - {j[1]} (Match Score: {j[3]}/100)\n")
                f.write(f"- **Rationale:** {j[4]}\n")
                f.write(f"- **Apply Link:** [{j[2]}]({j[2]})\n\n")
                
    print(f"\n[Report] Updated job match summary: {REPORT_PATH} ({len(jobs)} matches)", flush=True)

async def run_swarm_cycle():
    conn = setup_db()
    
    print("\n=======================================================", flush=True)
    print(f"🚀 Job Search Swarm Engine Started [{ai_provider} Engine Mode]", flush=True)
    print("=======================================================\n", flush=True)
    
    while True:
        jobs = scrape_jobs()
        
        if jobs:
            queue = asyncio.Queue()
            for job in jobs:
                await queue.put(job)
                
            # Run 5 concurrent workers
            workers = []
            for i in range(5):
                w = asyncio.create_task(agent_worker(f"Agent-{i+1}", queue, conn))
                workers.append(w)
                
            await queue.join()
            
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        else:
            print("[Engine] No new jobs fetched in this cycle. Will retry next interval.", flush=True)
            
        generate_report(conn)
        
        print("\n[Engine] Cycle completed. Sleeping for 15 minutes before the next scan...\n", flush=True)
        await asyncio.sleep(900)

if __name__ == "__main__":
    try:
        asyncio.run(run_swarm_cycle())
    except (KeyboardInterrupt, SystemExit):
        print("\n[Engine] Gracefully stopped by user.", flush=True)
