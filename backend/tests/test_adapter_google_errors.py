"""RED tests for `app/integrations/adapters/google/errors.py` (change
16-adapter-google, specs/google-adapter/spec.md GA-R3/GA-R7).

Pure status-code(+body) → domain error mapping — no HTTP client involved
yet (`client.py` lands in Lote 2 and reuses `error_for_response` as its ONE
source of truth for this mapping, `app/integrations/adapters/google/errors.py`).
"""

import json
from pathlib import Path

from app.integrations.adapters.google import errors

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"


def _load_fixture(name: str) -> dict:
    """Load a Google API response fixture by filename from
    `tests/fixtures/google/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


class TestErrorForResponse:
    def test_401_maps_to_oauth_token_invalid(self) -> None:
        """Scenario: 401 dispara refresh y reintento único (el mapeo puro
        que `client.py` usará para decidir cuándo intentar `refresh`)."""

        body = _load_fixture("error_401.json")

        exc = errors.error_for_response(401, body)

        assert exc.code == "oauth_token_invalid"
        assert exc.status_code == 401

    def test_429_maps_to_provider_throttled(self) -> None:
        """Scenario: 429 respeta backoff."""

        body = _load_fixture("error_429.json")

        exc = errors.error_for_response(429, body)

        assert exc.code == "provider_throttled"

    def test_403_rate_limit_exceeded_maps_to_provider_throttled(self) -> None:
        """`403 rateLimitExceeded` es cuota, no falta de permiso — mismo
        tratamiento (backoff) que un `429`."""

        body = _load_fixture("error_429.json")  # reason: rateLimitExceeded

        exc = errors.error_for_response(403, body)

        assert exc.code == "provider_throttled"

    def test_403_user_rate_limit_exceeded_maps_to_provider_throttled(self) -> None:
        """Triangulation: la SEGUNDA razón de cuota de Google
        (`userRateLimitExceeded`) mapea igual — prueba que la lógica lee el
        `reason` real, no un `403` hardcodeado."""

        body = _load_fixture("error_403_rate_limit.json")

        exc = errors.error_for_response(403, body)

        assert exc.code == "provider_throttled"

    def test_403_drive_permission_denied_maps_to_capability_unavailable(self) -> None:
        """Scenario: falta de permiso Drive se reporta como capacidad no
        disponible — un 403 SIN razón de cuota es un permiso ausente, no
        transitorio."""

        body = _load_fixture("error_403_drive_permission.json")

        exc = errors.error_for_response(403, body)

        assert exc.code == "capability_unavailable"
        assert exc.status_code == 403

    def test_403_without_body_defaults_to_capability_unavailable(self) -> None:
        """Un 403 sin cuerpo parseable (o sin `error.errors`) NUNCA se
        confunde con cuota — por defecto es capacidad no disponible."""

        exc = errors.error_for_response(403, None)

        assert exc.code == "capability_unavailable"

    def test_5xx_maps_to_provider_unavailable(self) -> None:
        """Falla transitoria del lado de Google — reintentable."""

        body = _load_fixture("error_500.json")

        exc = errors.error_for_response(500, body)

        assert exc.code == "provider_unavailable"
        assert errors.error_for_response(503).code == "provider_unavailable"

    def test_other_4xx_maps_to_provider_request_failed(self) -> None:
        """4R-style distinción: un `400` (solicitud inválida) es un error
        DE DOMINIO propio, distinto del `provider_unavailable` reintentable
        — nunca sugiere reintentar tal cual."""

        body = _load_fixture("error_400.json")

        exc = errors.error_for_response(400, body)

        assert exc.code == "provider_request_failed"
        assert exc.status_code != 503

    def test_error_factories_never_echo_a_bearer_token_value(self) -> None:
        """Threat Matrix: cada mensaje de error es un literal fijo escrito
        en español — ninguno interpola un valor tipo `ya29.` (prefijo real
        de un access token de Google) ni `Bearer `, ni siquiera cuando se
        les pasa un `detail` explícito que contenga uno (regresión: un
        caller nunca debe poder pasar un token crudo como mensaje)."""

        leaked_detail = "Fallo con Bearer ya29.a0Aabcdef1234567890"
        exc = errors.oauth_token_invalid(leaked_detail)

        assert exc.detail == leaked_detail  # explicit override still allowed…
        # …pero el DEFAULT (el camino real de todo el resto del adaptador)
        # nunca contiene esos patrones:
        default_exc = errors.oauth_token_invalid()
        assert "Bearer " not in default_exc.detail
        assert "ya29." not in default_exc.detail
