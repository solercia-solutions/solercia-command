"""`GET /assistant/health` response payload (spec `assistant-health`,
"Sobre de respuesta y campos de configuración"). Never carries
`LLM_API_KEY` nor the full `LLM_BASE_URL`.
"""

from pydantic import BaseModel

from app.ai.ports import Reachability


class AssistantHealthData(BaseModel):
    provider: str
    model: str
    base_url_host: str
    api_key_configured: bool
    timeout_seconds: float
    max_tokens: int
    structured_output_mode: str
    reachability: Reachability
    reachability_reason: str | None = None
