from crewai import Task
from agents import (
    create_job_board_scraper_agent,
    create_role_matching_agent,
    create_link_validation_agent,
    create_output_compiler_agent
)

def get_search_tasks(scraper_agents, candidate_cv_text):
    tasks = []
    
    # Read the strategic career guide constraints
    with open("career_guide_context.md", "r", encoding="utf-8") as f:
        strategy_context = f.read()
        
    for agent in scraper_agents:
        tasks.append(
            Task(
                description=f"Search your designated sources for finance/accounting roles suitable for:\n{candidate_cv_text}\n\nCRITICAL STRATEGY AND REALISTIC CONSTRAINTS:\n{strategy_context}\n\nOnly return roles the candidate is highly likely to actually get hired for based on these constraints.",
                expected_output="A JSON list of job dictionaries containing Job Title, Company, Location, Salary, Application Link, and Source.",
                agent=agent
            )
        )
    return tasks

def get_matching_task(matching_agent, cv_text):
    with open("career_guide_context.md", "r", encoding="utf-8") as f:
        strategy_context = f.read()
        
    return Task(
        description=f"Take the compiled list of jobs. Score each job from 0-100 based on fit with this CV:\n{cv_text}\n\nUse the following reality-check guidelines to penalize jobs out of their league or in the wrong track:\n{strategy_context}",
        expected_output="An updated JSON list of jobs with added 'Match Score', 'Key Requirements', and 'Why Candidate Fits' fields. Exclude anything scoring below 60.",
        agent=matching_agent
    )

def get_validation_task(validation_agent):
    return Task(
        description="Take the matched list of jobs and validate every 'Application Link' using the Validate Job Link tool. Remove any jobs with dead links.",
        expected_output="A filtered JSON list of valid, live jobs.",
        agent=validation_agent
    )

def get_compilation_task(compiler_agent):
    return Task(
        description="Format the final validated job list into a structured markdown report including a summary and top 20 best matches.",
        expected_output="A markdown formatted string containing the final report.",
        agent=compiler_agent
    )
