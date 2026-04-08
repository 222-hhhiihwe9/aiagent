"""Memory schema definitions."""

from datetime import datetime

from pydantic import BaseModel,Field

class MemoryItem(BaseModel):
    user_id : str
    content : str
    timestamp : datetime = Field(default_factory=datetime.now)
    importance : float = 0.5