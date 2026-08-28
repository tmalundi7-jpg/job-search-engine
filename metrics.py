"""
Prometheus metrics collection.
"""
from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY

jobs_scraped = Counter("swarm_jobs_scraped_total", "Total jobs scraped")
jobs_processed = Counter("swarm_jobs_processed_total", "Total jobs processed")
queue_length = Gauge("swarm_queue_length", "Current queue length")
ai_call_duration = Histogram("swarm_ai_call_duration_seconds", "Duration of AI scoring calls", buckets=[0.1, 0.5, 1, 2, 5, 10])
ai_call_errors = Counter("swarm_ai_call_errors_total", "Total AI call errors")

def get_metrics():
    return generate_latest(REGISTRY)
