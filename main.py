import time
import schedule
import logging
from crewai import Crew, Process
from agents import get_all_agents, create_role_matching_agent, create_link_validation_agent, create_output_compiler_agent
from tasks import get_search_tasks, get_matching_task, get_validation_task, get_compilation_task

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JobSearchEngine")

cv_text = """
MALUNDI THEOPHIL CHRISTIAN
Part-Qualified Accountant | MSc Accounting & Finance
tmalundi7@gmail.com | +255797353877
... (Full CV goes here) ...
"""

def run_engine_cycle():
    logger.info("Starting new job search cycle...")
    
    # 1. Initialize Agents
    all_agents = get_all_agents()
    scraper_agents = all_agents[:-3] # Assuming last 3 are matcher, validator, compiler
    matcher = all_agents[-3]
    validator = all_agents[-2]
    compiler = all_agents[-1]

    # 2. Define Tasks
    search_tasks = get_search_tasks(scraper_agents, cv_text)
    matching_task = get_matching_task(matcher, cv_text)
    validation_task = get_validation_task(validator)
    compilation_task = get_compilation_task(compiler)

    # 3. Form the Crew
    crew = Crew(
        agents=all_agents,
        tasks=[*search_tasks, matching_task, validation_task, compilation_task],
        process=Process.sequential, # Or hierarchical if using a manager
        verbose=True
    )

    # 4. Kickoff
    result = crew.kickoff()
    
    # 5. Save Output
    with open("job_matches_report.md", "w", encoding="utf-8") as f:
        f.write(result)
        
    logger.info("Cycle complete. Report saved.")

def start_24_7_loop():
    logger.info("Starting 24/7 Engine Loop")
    # Run immediately once
    run_engine_cycle()
    
    # Schedule to run every 12 hours
    schedule.every(12).hours.do(run_engine_cycle)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60) # Wait a minute
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            logger.info("Restarting loop in 5 minutes...")
            time.sleep(300)

if __name__ == "__main__":
    start_24_7_loop()
