"""Conversation continuity state."""

from pydantic import BaseModel,Field

from aiagent.schemas.inputs import InputEvent
from aiagent.schemas.outputs import OutputEvent

class ConversationState(BaseModel):
    recent_inputs : list[InputEvent] = Field(default_factory=list)
    recent_outputs : list[OutputEvent] = Field(default_factory=list)
    max_turns : int = 10
    
    def add_input(self, event: InputEvent) -> None:
        self.recent_inputs.append(event)
        self.recent_inputs = self.recent_inputs[-self.max_turns :]

    def add_output(self, event: OutputEvent) -> None:
        self.recent_outputs.append(event)
        self.recent_outputs = self.recent_outputs[-self.max_turns :]