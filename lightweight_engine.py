import os
import time
import sqlite3
import json
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key or api_key == "gsk_your_actual_key_here":
    print("\nCRITICAL ERROR: Your Groq API key is missing or invalid in the .env file!")
    exit(1)

client = Groq(api_key=api_key)

CV_TEXT = """
Candidate has ~2 years experience in accounting.
Target roles: Entry/Mid Management Accountant, FP&A Analyst, Public Sector Finance, Assistant Accountant, Trainee Accountant.
Location: Scotland or Remote.
Salary: £25k-£45k.
AVOID: Big 4 Audit, CFO, Senior Partner roles.
"""

def setup_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/jobs.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (title TEXT, company TEXT, link TEXT UNIQUE, match_score INTEGER, explanation TEXT, active INTEGER)''')
    conn.commit()
    return conn

def scrape_jobs():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    jobs = []
    
    # Reed is much friendlier to cloud servers than CV-Library
    pages = [
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland?pageno=2",
        "https://www.reed.co.uk/jobs/accounting-jobs-in-scotland?pageno=3"
    ]
    
    print(f"Scraping Reed.co.uk to bypass Oracle Cloud server blocks...")
    
    for url in pages:
        try:
            r = requests.get(url, headers=headers)
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

def evaluate_job(job):
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
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192",
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("score", 0), result.get("explanation", "No explanation")
    except Exception as e:
        print(f"Groq API Error: {e}")
        return 0, "Error evaluating"

def generate_report():
    conn = sqlite3.connect("data/jobs.db")
    c = conn.cursor()
    c.execute("SELECT title, company, link, match_score, explanation FROM jobs WHERE match_score >= 50 ORDER BY match_score DESC")
    jobs = c.fetchall()
    
    with open("data/job_matches_report.md", "w", encoding='utf-8') as f:
        f.write("# Highly Matched Jobs\n\n")
        if not jobs:
            f.write("No jobs matched your criteria with a score of 50+ yet. The AI might be scoring too harshly, or your API key is invalid.\n")
        for j in jobs:
            f.write(f"### {j[0]} at {j[1]} (Score: {j[3]}/100)\n")
            f.write(f"**Why:** {j[4]}\n")
            f.write(f"**Link:** {j[2]}\n\n")
    print("\nReport generated at data/job_matches_report.md")

def main():
    conn = setup_db()
    c = conn.cursor()
    while True:
        jobs = scrape_jobs()
        print(f"Found {len(jobs)} jobs across 3 pages. Scoring them now...\n")
        
        for job in jobs:
            c.execute("SELECT match_score FROM jobs WHERE link=?", (job['link'],))
            if c.fetchone():
                continue
                
            score, explanation = evaluate_job(job)
            print(f"Evaluated: {job['title'][:40]} at {job['company'][:30]} --> AI Score: {score}/100")
            
            try:
                c.execute("INSERT INTO jobs (title, company, link, match_score, explanation, active) VALUES (?, ?, ?, ?, ?, 1)",
                          (job['title'], job['company'], job['link'], score, explanation))
                conn.commit()
            except sqlite3.IntegrityError:
                pass
            time.sleep(1)
            
        generate_report()
        print("\nCycle complete! Sleeping for 15 minutes before checking for new jobs...\n")
        time.sleep(900)

if __name__ == "__main__":
    main()
