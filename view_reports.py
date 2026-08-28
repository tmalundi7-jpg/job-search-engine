import os
import sys

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(base_dir, "data", "job_matches_report.md")
    
    # Fallback to root if not in data/
    if not os.path.exists(report_path):
        report_path = os.path.join(base_dir, "job_matches_report.md")
        
    if not os.path.exists(report_path):
        print("\n=======================================================")
        print("⚠️  No report found yet!")
        print("=======================================================")
        print("The engine hasn't completed a scan or generated 'job_matches_report.md'.")
        print("Please ensure the engine is running: python lightweight_engine.py\n")
        sys.exit(1)
        
    print("\n" + "="*60)
    print(" 📄 LIVE JOB MATCHES REPORT")
    print("="*60 + "\n")
    
    with open(report_path, "r", encoding="utf-8") as f:
        print(f.read())
        
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
