import os

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "job_matches_report.md")

def view_report():
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print(f"Report not found at {REPORT_PATH}. Please ensure the Job Search Engine has run and generated matches.")

if __name__ == "__main__":
    view_report()
