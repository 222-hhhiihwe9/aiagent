from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel,Field

class MemoryCategory(StrEnum):
    IDENTITY  = 'identity'
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    HABIT = "habit"
    BOUNDARY = "boundary"
    EVENT = "event"
    OTHER = "other"

class MemoryImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class MemoryWriteDecision(BaseModel):
    should_store : bool =False
    category : MemoryCategory = MemoryCategory.OTHER
    importance : MemoryImportance = MemoryImportance.MEDIUM
    reason:str =""
    memory_hint : str =""
    metadata:dict[str,Any] = Field(default_factory=dict)

    