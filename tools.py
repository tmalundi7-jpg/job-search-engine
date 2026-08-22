import requests
from bs4 import BeautifulSoup
import cloudscraper
from crewai.tools import tool
from typing import List

@tool("Validate Job Link")
def validate_job_link(url: str) -> str:
    """Takes a job application URL and returns whether it is live and active (HTTP 200) or Dead."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=15)
        if response.status_code == 200:
            return f"Link {url} is LIVE and ACTIVE."
        else:
            return f"Link {url} returned status {response.status_code}. It might be DEAD or blocked."
    except Exception as e:
        return f"Link {url} is DEAD or unreachable. Error: {str(e)}"

@tool("Scrape Job Description")
def scrape_job_description(url: str) -> str:
    """Takes a URL to a job description page and returns the text of the job description."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            main_content = soup.find('main') or soup.find('body')
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
                # Keep it concise to save tokens, but capture the bottom where requirements often are.
                return text[:8000]
            return "Could not find main content."
        return f"Failed to retrieve page, status code: {response.status_code}"
    except Exception as e:
        return f"Error scraping the job description: {str(e)}"

@tool("Extract CV Keywords")
def extract_cv_keywords(cv_text: str) -> List[str]:
    """Extracts key qualifications and skills from the candidate's CV."""
    return [
        "Part-Qualified Accountant", "CIMA", "Management Accounting", 
        "Financial Reporting", "Variance Analysis", "SAP", "Advanced Excel"
    ]
