from crewai import Agent
from tools import validate_job_link, scrape_job_description, extract_cv_keywords
import os
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()

# CrewAI uses LiteLLM under the hood, so we can just pass the string
# formatted as provider/model_name
groq_llm_string = "groq/llama3-70b-8192"

def create_job_board_scraper_agent():
    return Agent(
        role="Job Board Scraper",
        goal="Scrape Indeed, Reed, Totaljobs, and other major boards for relevant roles.",
        backstory="An expert web scraper specialized in extracting job listings from aggregator sites.",
        verbose=True,
        allow_delegation=False,
        llm=groq_llm_string,
        tools=[scrape_job_description]
    )

def create_company_career_page_scraper():
    return Agent(
        role="Company Career Page Scraper",
        goal="Scrape career pages of FTSE 250, banks, Big 4, and public sector employers.",
        backstory="A diligent agent that navigates corporate career sites to find hidden roles.",
        verbose=True,
        allow_delegation=False,
        llm=groq_llm_string
    )

def create_gov_public_sector_agent():
    return Agent(
        role="Government & Public Sector Jobs Agent",
        goal="Search Civil Service, NHS, and local council portals for finance roles.",
        backstory="Specializes in navigating public sector job boards like myjobscotland.",
        verbose=True,
        llm=groq_llm_string
    )

def create_role_matching_agent():
    return Agent(
        role="Role Matching & Scoring Agent",
        goal="Compare each found role against the CV and assign a match score (0-100).",
        backstory="An analytical HR expert that evaluates candidate fit based on strict criteria.",
        verbose=True,
        llm=groq_llm_string
    )

def create_link_validation_agent():
    return Agent(
        role="Application Link Validation Agent",
        goal="Open each application link and verify it returns HTTP 200.",
        backstory="A QA specialist ensuring no broken links are presented to the candidate.",
        verbose=True,
        llm=groq_llm_string,
        tools=[validate_job_link]
    )

def create_output_compiler_agent():
    return Agent(
        role="Output Compiler & Report Agent",
        goal="Merge all findings into a single structured markdown report.",
        backstory="A meticulous data entry clerk formatting results into final outputs.",
        verbose=True,
        llm=groq_llm_string
    )

def get_all_agents():
    # Returns a list of all instantiated agents
    return [
        create_job_board_scraper_agent(),
        create_company_career_page_scraper(),
        create_gov_public_sector_agent(),
        create_role_matching_agent(),
        create_link_validation_agent(),
        create_output_compiler_agent()
    ]
