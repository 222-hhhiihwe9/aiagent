"""SiliconFlow client placeholder."""
class SiliconFlowClient:
    def __init__(self, api_key: str | None, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def generate(self, messages) -> str:
        if not self.api_key:
            raise RuntimeError("SILICONFLOW_API is not configured.")
        raise NotImplementedError("SiliconFlow client is not implemented in week 1.")
