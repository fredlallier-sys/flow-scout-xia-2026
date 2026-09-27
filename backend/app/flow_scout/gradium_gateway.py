"""Pont serveur Gradium avec vérification de crédits et consentement explicite."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_DEFAULT_BASE_URL = "https://api.gradium.ai/api"
_SUPPORTED_AUDIO_TYPES = {"audio/wav", "audio/pcm", "audio/ogg", "audio/opus"}


class GradiumGatewayError(RuntimeError):
    """L'appel vocal est refusé ou Gradium a retourné une réponse invalide."""


@dataclass(frozen=True)
class GradiumHttpResponse:
    status_code: int
    content: bytes
    headers: dict[str, str]

    def json(self) -> object:
        return json.loads(self.content.decode("utf-8"))


GradiumTransport = Callable[..., Awaitable[GradiumHttpResponse]]


class GradiumGateway:
    """Client minimal ; aucune méthode coûteuse ne part sans confirmation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: GradiumTransport | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("GRADIUM_API_KEY", "")).strip()
        self.base_url = (
            base_url or os.getenv("GRADIUM_API_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self._transport = transport or _urllib_transport

    async def credits(self) -> dict[str, object]:
        """Lit le solde ; cette opération ne produit ni audio ni transcription."""
        response = await self._request("GET", "/usages/credits")
        try:
            payload = response.json()
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GradiumGatewayError("Réponse de crédits Gradium invalide.") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("remaining_credits"), int
        ):
            raise GradiumGatewayError("Solde Gradium absent de la réponse.")
        return {
            "remaining_credits": payload["remaining_credits"],
            "allocated_credits": payload.get("allocated_credits"),
            "billing_period": payload.get("billing_period"),
            "next_rollover_date": payload.get("next_rollover_date"),
            "plan_name": payload.get("plan_name", ""),
        }

    async def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/wav",
        language: str = "fr",
        confirmed_existing_credits: bool = False,
    ) -> dict[str, object]:
        """Transcrit un fichier audio après consentement et contrôle du solde."""
        self._require_confirmation(confirmed_existing_credits)
        if content_type not in _SUPPORTED_AUDIO_TYPES:
            raise GradiumGatewayError(f"Format audio Gradium non autorisé : {content_type}.")
        if not audio:
            raise GradiumGatewayError("Le fichier audio est vide.")
        credit_state = await self._require_positive_credits()
        response = await self._request(
            "POST",
            "/post/speech/asr",
            params={"json_config": json.dumps({"language": language})},
            content=audio,
            headers={"Content-Type": content_type},
        )
        messages: list[dict[str, Any]] = []
        for raw_line in response.content.decode("utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                message = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise GradiumGatewayError("Flux de transcription Gradium invalide.") from exc
            if isinstance(message, dict):
                messages.append(message)
        transcript = " ".join(
            str(message.get("text", "")).strip()
            for message in messages
            if message.get("type") == "text" and str(message.get("text", "")).strip()
        ).strip()
        if not transcript:
            raise GradiumGatewayError("Gradium n'a retourné aucune transcription.")
        return {
            "schema_version": "flow-scout-gradium-transcription-v1",
            "transcript": transcript,
            "transcript_trust": "untrusted_human_declaration",
            "language": language,
            "credit_check": credit_state,
        }

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        confirmed_existing_credits: bool = False,
    ) -> bytes:
        """Produit un WAV après consentement et contrôle du solde."""
        self._require_confirmation(confirmed_existing_credits)
        if not text.strip():
            raise GradiumGatewayError("Le texte à lire est vide.")
        if not voice_id.strip():
            raise GradiumGatewayError("L'identifiant de voix Gradium est obligatoire.")
        await self._require_positive_credits()
        response = await self._request(
            "POST",
            "/post/speech/tts",
            json_body={
                "text": text,
                "voice_id": voice_id,
                "output_format": "wav",
                "only_audio": True,
            },
        )
        if not response.content:
            raise GradiumGatewayError("Gradium n'a retourné aucun audio.")
        return response.content

    async def _require_positive_credits(self) -> dict[str, object]:
        state = await self.credits()
        remaining = int(state["remaining_credits"])
        if remaining <= 0:
            raise GradiumGatewayError(
                "Aucun crédit Gradium restant : appel vocal bloqué pour éviter une dépense."
            )
        return state

    def _require_confirmation(self, confirmed: bool) -> None:
        if not confirmed:
            raise GradiumGatewayError(
                "Confirmation des crédits existants requise avant l'appel Gradium."
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> GradiumHttpResponse:
        if not self.api_key:
            raise GradiumGatewayError("GRADIUM_API_KEY n'est pas configurée côté serveur.")
        request_headers = {"x-api-key": self.api_key, **(headers or {})}
        try:
            response = await self._transport(
                method=method,
                url=f"{self.base_url}{path}",
                headers=request_headers,
                params=params or {},
                content=content,
                json_body=json_body,
            )
        except (HTTPError, URLError, OSError) as exc:
            raise GradiumGatewayError("Échec de l'appel Gradium.") from exc
        if response.status_code >= 400:
            raise GradiumGatewayError(
                f"Échec de l'appel Gradium (HTTP {response.status_code})."
            )
        return response


async def _urllib_transport(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, str],
    content: bytes | None,
    json_body: dict[str, object] | None,
) -> GradiumHttpResponse:
    """Transport standard sans dépendance supplémentaire, exécuté hors event loop."""

    def send() -> GradiumHttpResponse:
        target = f"{url}?{urlencode(params)}" if params else url
        body = content
        request_headers = dict(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(target, data=body, headers=request_headers, method=method)
        with urlopen(request, timeout=60) as response:  # noqa: S310
            return GradiumHttpResponse(
                status_code=response.status,
                content=response.read(),
                headers=dict(response.headers.items()),
            )

    return await asyncio.to_thread(send)
