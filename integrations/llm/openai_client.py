"""OpenAI-compatible client placeholder."""
class OpenAIClient:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate(self, messages) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        raise NotImplementedError("OpenAI client is not implemented in week 1.")
