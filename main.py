import time
import logging
from crewai import Crew, Process
from agents import get_all_agents
from tasks import get_search_tasks, get_matching_task, get_validation_task, get_compilation_task

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JobSearchEngine")

cv_text = """
MALUNDI THEOPHIL CHRISTIAN
Part-Qualified Accountant | MSc Accounting & Finance
tmalundi7@gmail.com | +255797353877
"""

def run_engine_cycle():
    logger.info("Starting new continuous job search cycle...")
    
    all_agents = get_all_agents()
    scraper_agents = all_agents[:-3]
    matcher = all_agents[-3]
    validator = all_agents[-2]
    compiler = all_agents[-1]

    search_tasks = get_search_tasks(scraper_agents, cv_text)
    matching_task = get_matching_task(matcher, cv_text)
    validation_task = get_validation_task(validator)
    compilation_task = get_compilation_task(compiler)

    crew = Crew(
        agents=all_agents,
        tasks=[*search_tasks, matching_task, validation_task, compilation_task],
        process=Process.sequential,
        verbose=True
    )

    result = crew.kickoff()
    
    # Save Output locally to the engine folder
    with open("job_matches_report.md", "w", encoding="utf-8") as f:
        f.write(result)
        
    logger.info("Cycle complete. Report saved to job_matches_report.md.")

def start_continuous_loop():
    logger.info("Starting 24/7 Continuous Engine Loop")
    cycle_count = 1
    
    while True:
        try:
            logger.info(f"--- BEGINNING SCAN CYCLE {cycle_count} ---")
            run_engine_cycle()
            logger.info(f"--- FINISHED SCAN CYCLE {cycle_count} ---")
            
            # Short 5-minute cooldown to prevent API rate limits and IP bans from job boards
            logger.info("Cooling down for 5 minutes before the next continuous scan...")
            time.sleep(300) 
            cycle_count += 1
            
        except Exception as e:
            logger.error(f"Error in continuous loop: {e}")
            logger.info("Restarting loop in 1 minute due to error...")
            time.sleep(60)

if __name__ == "__main__":
    start_continuous_loop()
