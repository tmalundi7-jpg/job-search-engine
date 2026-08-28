"""
Data models used across the engine.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

@dataclass
class JobListing:
    title: str
    company: str
    link: str
    description: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    source: str = "reed"

@dataclass
class ScoredJob:
    title: str
    company: str
    link: str
    match_score: int
    explanation: str
    active: int = 1
    notified: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "title": self.title,
            "company": self.company,
            "link": self.link,
            "match_score": self.match_score,
            "explanation": self.explanation,
            "active": self.active,
            "notified": self.notified,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
        }
