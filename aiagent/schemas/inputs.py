"""Input payload schema definitions."""
from datetime import datetime
from enum import IntEnum , StrEnum
from uuid import uuid4

from pydantic import BaseModel,Field


class InputSource(StrEnum):
    CHAT = "chat"
    DNAMUKU = "danmaku"
    ASR = "asr"
    SYSTEM = "system"

class EventPriority(IntEnum):
    LOW = 1
    NORMAL = 5
    HIGH = 10

class InputEvent(BaseModel):
    event_id : str = Field(default_factory=lambda: str(uuid4()))
    source: InputSource
    user_id : str
    user_name : str
    text : str
    timestamp : datetime = Field(default_factory=datetime.now)
    priority : EventPriority = EventPriority.NORMAL
    metadata: dict[str,str] = Field(default_factory=dict)