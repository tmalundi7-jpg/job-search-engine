import os
import time
import sqlite3
import json
import requests
import asyncio
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "AIza_your_actual_key_here":
    print("\nCRITICAL ERROR: Your Google Gemini API key is missing or invalid in the .env file!")
    print("Please open .env and add: GEMINI_API_KEY=AIza...")
    exit(1)

# Initialize the state-of-the-art Gemini Client
client = genai.Client(api_key=api_key)

CV_TEXT = """
Candidate has ~2 years experience in accounting.
Target roles: Entry/Mid Management Accountant, FP&A Analyst, Public Sector Finance, Assistant Accountant, Trainee Accountant.
Location: Scotland or Remote.
Salary: £25k-£45k.
AVOID: Big 4 Audit, CFO, Senior Partner roles.
"""

def setup_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/jobs.db", timeout=15)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (title TEXT, company TEXT, link TEXT UNIQUE, match_score INTEGER, explanation TEXT, active INTEGER)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_match_score ON jobs(match_score)")
    conn.commit()
    return conn

def scrape_jobs():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    jobs = []
    
    pages = [
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland?pageno=2",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland?pageno=3"
    ]
    
    print(f"Scraping Reed.co.uk to find jobs...")
    
    for url in pages:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            
            for article in soup.find_all("article"):
                h2 = article.find("h2")
                if not h2: continue
                
                title = h2.text.strip()
                a = h2.find("a")
                link = "https://www.reed.co.uk" + a["href"].split("?")[0] if a else ""
                
                comp_a = article.find("a", class_=lambda x: x and "gtmJobListingPostedBy" in x)
                if not comp_a: comp_a = article.find("div", class_=lambda x: x and "posted-by" in x)
                company = comp_a.text.strip() if comp_a else "Unknown Company"
                
                jobs.append({"title": title, "company": company, "link": link, "description": "See link for full details."})
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            
    return jobs

async def evaluate_job(job):
    prompt = f"""
    You are an expert UK accounting career coach. Evaluate this job against the candidate's CV.
    CV & Rules: {CV_TEXT}
    
    Job Title: {job['title']}
    Company: {job['company']}
    Description: {job['description']}
    
    Return ONLY a valid JSON object with EXACTLY these keys:
    "score": an integer from 0 to 100 (Be lenient! If it is junior/mid accounting, give it a 60-80).
    "explanation": a short 1-sentence explanation of why it fits.
    """
    try:
        # Wrap the sync Gemini API call in asyncio.to_thread to maintain the Async Swarm architecture
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3.7-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        content = response.text.strip()
        
        if content.startswith("```json"): content = content[7:]
        elif content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
            
        result = json.loads(content)
        return result.get("score", 0), result.get("explanation", "No explanation")
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None, str(e)

async def agent_worker(name, queue, db_conn):
    """An asynchronous swarm agent powered by Gemini 3.7 Flash."""
    print(f"[{name}] Activated with Gemini brain.")
    c = db_conn.cursor()
    
    while True:
        job = await queue.get()
        
        c.execute("SELECT match_score FROM jobs WHERE link=?", (job['link'],))
        if c.fetchone():
            queue.task_done()
            continue
            
        score, explanation = await evaluate_job(job)
        
        if score is None:
            print(f"[{name}] Skipped {job['title'][:30]} due to temporary API error.")
        else:
            print(f"[{name}] Evaluated: {job['title'][:30]} at {job['company'][:20]} --> AI Score: {score}/100")
            try:
                c.execute("INSERT INTO jobs (title, company, link, match_score, explanation, active) VALUES (?, ?, ?, ?, ?, 1)",
                          (job['title'], job['company'], job['link'], score, explanation))
                db_conn.commit()
            except sqlite3.IntegrityError:
                pass
                
        # Small sleep to be polite to the Gemini API limits
        await asyncio.sleep(1.5)
        queue.task_done()

def generate_report(conn):
    c = conn.cursor()
    c.execute("SELECT title, company, link, match_score, explanation FROM jobs WHERE match_score >= 50 ORDER BY match_score DESC")
    jobs = c.fetchall()
    
    with open("data/job_matches_report.md", "w", encoding='utf-8') as f:
        f.write("# Highly Matched Jobs\n\n")
        if not jobs:
            f.write("No jobs matched your criteria with a score of 50+ yet.\n")
        for j in jobs:
            f.write(f"### {j[0]} at {j[1]} (Score: {j[3]}/100)\n")
            f.write(f"**Why:** {j[4]}\n")
            f.write(f"**Link:** {j[2]}\n\n")
    print("\n--- Report generated at data/job_matches_report.md ---\n")

async def run_swarm_cycle():
    conn = setup_db()
    
    while True:
        jobs = scrape_jobs()
        print(f"Found {len(jobs)} jobs. Waking up the Gemini Agent Swarm to process them concurrently...\n")
        
        queue = asyncio.Queue()
        for job in jobs:
            await queue.put(job)
            
        workers = []
        for i in range(10):
            w = asyncio.create_task(agent_worker(f"Agent-{i+1}", queue, conn))
            workers.append(w)
            
        await queue.join()
        
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        
        generate_report(conn)
        print("Swarm cycle complete! Sleeping for 15 minutes before checking for new jobs...\n")
        await asyncio.sleep(900)

if __name__ == "__main__":
    print("Initializing Asynchronous Gemini Swarm Architecture...")
    asyncio.run(run_swarm_cycle())
