import os
import time
import sqlite3
import json
import cloudscraper
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

CV_TEXT = """
Candidate has ~2 years experience in accounting.
Target roles: Entry/Mid Management Accountant, FP&A Analyst, Public Sector Finance.
Location: Scotland or Remote.
Salary: £25k-£45k.
AVOID: Big 4 Audit, CFO, Senior roles.
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
    scraper = cloudscraper.create_scraper()
    jobs = []
    print("Scraping CV-Library for Accounting jobs in Scotland...")
    try:
        html = scraper.get("https://www.cv-library.co.uk/accounting-jobs-in-scotland").text
        soup = BeautifulSoup(html, "html.parser")
        for title_elem in soup.find_all("h2"):
            a_tag = title_elem.find("a")
            if not a_tag:
                continue
            title = title_elem.text.strip()
            link = "https://www.cv-library.co.uk" + a_tag["href"]
            
            # Find company
            company_span = title_elem.parent.find("span", attrs={"data-qa": lambda x: x and x.startswith("job-card-company")})
            company_name = company_span.text.strip() if company_span else "Unknown"
            
            # Find description by going up to the job card container
            job_card = title_elem.find_parent("div", class_=lambda x: x and "JobCard_jobCardBody" in x)
            desc_p = job_card.find("p", class_=lambda x: x and "JobCard_descText" in x) if job_card else None
            description = desc_p.text.strip() if desc_p else ""
            
            jobs.append({"title": title, "company": company_name, "link": link, "description": description})
    except Exception as e:
        print(f"Error scraping: {e}")
    return jobs

def evaluate_job(job):
    print(f"Evaluating: {job['title']}...")
    prompt = f"""
    You are an expert UK accounting career coach. Evaluate this job against the candidate's CV and strict rules.
    CV & Rules: {CV_TEXT}
    
    Job Title: {job['title']}
    Company: {job['company']}
    Description: {job['description']}
    
    Return ONLY a valid JSON object with EXACTLY these keys:
    "score": an integer from 0 to 100
    "explanation": a short 2-sentence explanation of why it fits or doesn't fit.
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
    c.execute("SELECT title, company, link, match_score, explanation FROM jobs WHERE match_score >= 60 ORDER BY match_score DESC")
    jobs = c.fetchall()
    
    with open("data/job_matches_report.md", "w", encoding='utf-8') as f:
        f.write("# Highly Matched Jobs\n\n")
        if not jobs:
            f.write("No jobs matched your criteria with a score of 60+ yet.\n")
        for j in jobs:
            f.write(f"### {j[0]} at {j[1]} (Score: {j[3]}/100)\n")
            f.write(f"**Why:** {j[4]}\n")
            f.write(f"**Link:** {j[2]}\n\n")
    print("Report generated at data/job_matches_report.md")

def main():
    conn = setup_db()
    c = conn.cursor()
    while True:
        jobs = scrape_jobs()
        print(f"Found {len(jobs)} jobs. Scoring them...")
        for job in jobs:
            c.execute("SELECT match_score FROM jobs WHERE link=?", (job['link'],))
            if c.fetchone():
                continue
                
            score, explanation = evaluate_job(job)
            try:
                c.execute("INSERT INTO jobs (title, company, link, match_score, explanation, active) VALUES (?, ?, ?, ?, ?, 1)",
                          (job['title'], job['company'], job['link'], score, explanation))
                conn.commit()
            except sqlite3.IntegrityError:
                pass
            time.sleep(1)
            
        generate_report()
        print("Cycle complete! Sleeping for 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    main()
