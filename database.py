import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_NAME = "jobs_database.db"

def init_db():
    """Initializes the SQLite database with the required schema."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create jobs table
    # Using 'link' as the UNIQUE constraint to prevent duplicate job entries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            salary TEXT,
            link TEXT UNIQUE,
            source TEXT,
            match_score INTEGER,
            why_fits TEXT,
            status TEXT DEFAULT 'ACTIVE',
            date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def upsert_jobs(jobs_list):
    """
    Inserts a list of job dictionaries into the database.
    If the link already exists, updates the match_score, why_fits, and last_checked.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0
    
    for job in jobs_list:
        link = job.get('Application Link') or job.get('link')
        if not link:
            continue
            
        title = job.get('Job Title') or job.get('title', 'Unknown Title')
        company = job.get('Company') or job.get('company', 'Unknown Company')
        location = job.get('Location') or job.get('location', 'Unknown Location')
        salary = str(job.get('Salary') or job.get('salary', 'Competitive'))
        source = job.get('Source', 'AI Search')
        
        # Try to parse match score
        try:
            score = int(job.get('Match Score', 0))
        except:
            score = 0
            
        why_fits = job.get('Why Candidate Fits', '')
        
        try:
            cursor.execute('''
                INSERT INTO jobs (title, company, location, salary, link, source, match_score, why_fits, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            ''', (title, company, location, salary, link, source, score, why_fits))
            inserted += 1
        except sqlite3.IntegrityError:
            # Job exists, update it
            cursor.execute('''
                UPDATE jobs 
                SET match_score = ?, why_fits = ?, last_checked = CURRENT_TIMESTAMP, status = 'ACTIVE'
                WHERE link = ?
            ''', (score, why_fits, link))
            updated += 1
            
    conn.commit()
    conn.close()
    logger.info(f"Database sync: {inserted} new jobs inserted, {updated} existing jobs updated.")

def generate_markdown_report(filepath="job_matches_report.md"):
    """Reads the active jobs from the database and generates a markdown report."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Fetch top 50 active jobs, ordered by match score
    cursor.execute('''
        SELECT title, company, location, salary, link, match_score, why_fits, date_found 
        FROM jobs 
        WHERE status = 'ACTIVE' AND match_score >= 60
        ORDER BY match_score DESC 
        LIMIT 50
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 24/7 Engine: Validated Job Matches\n")
        f.write(f"*Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"Total live, matched roles in database: **{len(rows)}** (Showing Top 50)\n\n")
        f.write("---\n\n")
        
        if not rows:
            f.write("> **No jobs found matching the strict criteria yet. The engine is still searching...**\n")
            return
            
        for row in rows:
            title, company, location, salary, link, score, why_fits, date_found = row
            f.write(f"### {title} @ {company} (Score: {score}/100)\n")
            f.write(f"- **Location:** {location}\n")
            f.write(f"- **Salary:** {salary}\n")
            f.write(f"- **Why it fits:** {why_fits}\n")
            f.write(f"- **Date Found:** {date_found}\n")
            f.write(f"- **Application Link:** [Apply Here]({link})\n\n")
            
    logger.info(f"Markdown report generated with {len(rows)} jobs.")
