from __future__ import annotations

from aiagent.persona.persona_loader import PersonaLoader
from aiagent.persona.persona_runtime import PersonaRuntime


class PersonaManager:
    def __init__(
        self,
        loader: PersonaLoader,
        default_persona_id: str = "yzl",
    ) -> None:
        self.loader = loader
        self.default_persona_id = default_persona_id
        self._active_persona: PersonaRuntime | None = None

    def load_default_persona(self) -> PersonaRuntime:
        config = self.loader.load_persona(self.default_persona_id)
        self._active_persona = PersonaRuntime(config)
        return self._active_persona

    def get_active_persona(self) -> PersonaRuntime:
        if self._active_persona is None:
            return self.load_default_persona()
        return self._active_persona

    def switch_persona(self, persona_id: str) -> PersonaRuntime:
        config = self.loader.load_persona(persona_id)
        self._active_persona = PersonaRuntime(config)
        self.default_persona_id = persona_id
        return self._active_persona
