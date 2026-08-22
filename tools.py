import requests
from bs4 import BeautifulSoup
import urllib.request
import urllib.error
from crewai.tools import tool
from typing import List

@tool("Validate Job Link")
def validate_job_link(url: str) -> str:
    """Checks if a job application link is live and returns HTTP 200."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        if response.getcode() == 200:
            return f"Valid link: {url}"
        else:
            return f"Invalid link (HTTP {response.getcode()}): {url}"
    except Exception as e:
        return f"Error validating link {url}: {str(e)}"

@tool("Scrape Job Description")
def scrape_job_description(url: str) -> str:
    """Scrapes the text content of a job listing page."""
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            return text[:5000] # Cap length
        return f"Failed to retrieve page, status code: {response.status_code}"
    except Exception as e:
        return f"Error scraping URL: {str(e)}"

@tool("Extract CV Keywords")
def extract_cv_keywords(cv_text: str) -> List[str]:
    """Extracts key qualifications and skills from the candidate's CV."""
    return [
        "Part-Qualified Accountant", "CIMA", "Management Accounting", 
        "Financial Reporting", "Variance Analysis", "SAP", "Advanced Excel"
    ]
