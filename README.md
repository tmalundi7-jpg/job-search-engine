# 24/7 Job Search Engine Deployment Guide

This repository contains the multi-agent system designed to run 24/7 to find jobs for Malundi Theophil Christian.

## Architecture
- **Agents Framework:** CrewAI
- **LLM:** Groq (Llama-3-70b)
- **Scraping:** BeautifulSoup4, Requests
- **Scheduling:** `schedule` library

## Setup Instructions

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables:**
   Create a `.env` file in this directory and add your Groq API key (which is free):
   ```env
   GROQ_API_KEY=your_free_groq_api_key_here
   ```

3. **Run the Engine Locally:**
   ```bash
   python main.py
   ```
   The script uses `schedule.every(12).hours.do(run_engine_cycle)` to run twice a day continuously.

## Deploying 24/7 to Cloud (Free Tier)

To ensure this runs 24/7 without keeping your computer on, deploy it to a free cloud service.

### Option A: GitHub Actions (Recommended, 100% Free)
1. Fork this repository to your GitHub account.
2. Go to repository Settings -> Secrets and variables -> Actions.
3. Add a New repository secret named `GROQ_API_KEY`.
4. Create a `.github/workflows/job_search.yml` file with a CRON trigger (e.g., `cron: '0 */12 * * *'`) that runs `python main.py` and commits `job_matches_report.md` back to the repository.

### Option B: Oracle Cloud Free Tier
1. Sign up for Oracle Cloud (Always Free).
2. Provision a Micro VM (Ubuntu).
3. SSH into the machine, clone this code, install python3-pip, and install dependencies.
4. Use `tmux` or `screen` to keep the session alive.
5. Run `python3 main.py`.

## Output
The engine will continuously overwrite/update `job_matches_report.md` with the latest live, verified jobs, match scores, and analysis.
