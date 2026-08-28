"""
Utility functions.
"""
from urllib.parse import urlparse

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc
