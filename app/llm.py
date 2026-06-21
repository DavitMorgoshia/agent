"""
LLM provider abstraction.

Supports Anthropic (Claude) and Google (Gemini).
Set LLM_PROVIDER=anthropic (default) or LLM_PROVIDER=gemini in .env,
along with ANTHROPIC_API_KEY or GEMINI_API_KEY (plain key or path to
a service account JSON file).
"""

import base64
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GEMINI = "gemini"

# fast = cheaper/faster model  |  smart = stronger model for reasoning tasks
_MODELS = {
    PROVIDER_ANTHROPIC: {
        "fast": "claude-haiku-4-5-20251001",
        "smart": "claude-sonnet-4-6",
    },
    PROVIDER_GEMINI: {
        "fast": "gemini-2.5-flash",
        "smart": "gemini-2.5-pro",
    },
}


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", PROVIDER_ANTHROPIC).lower()


class _GeminiServiceAccountClient:
    """
    Minimal Gemini client using OAuth2 Bearer tokens from a service account JSON.

    The google-genai SDK only accepts plain API keys for the Developer API endpoint.
    This class bypasses the SDK and calls generativelanguage.googleapis.com directly
    with a refreshed OAuth2 access token — no Vertex AI required.
    """

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, json_key_path: str):
        from google.oauth2 import service_account
        self._creds = service_account.Credentials.from_service_account_file(
            json_key_path,
            scopes=["https://www.googleapis.com/auth/generative-language"],
        )
        self._refresh()
        logger.info("Gemini via service account OAuth2 (generativelanguage.googleapis.com)")

    def _refresh(self):
        from google.auth.transport.requests import Request
        if not self._creds.valid:
            self._creds.refresh(Request())

    def generate_content(self, model: str, body: dict) -> str:
        import httpx
        self._refresh()
        url = f"{self._BASE}/{model}:generateContent"
        resp = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {self._creds.token}"},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _build_gemini_client(api_key: str):
    """
    Return an authenticated Gemini client:
      - plain API key string  → google.genai.Client (SDK)
      - path to service account JSON → _GeminiServiceAccountClient (direct HTTP + OAuth2)
    """
    if os.path.isfile(api_key):
        return _GeminiServiceAccountClient(api_key)

    from google import genai
    return genai.Client(api_key=api_key)


class LLMClient:
    """
    Unified interface over Anthropic and Gemini.

    All methods return plain strings (the model's response text).
    Callers own JSON parsing — this layer handles only the transport.
    """

    def __init__(self, provider: str, api_key: str):
        self.provider = provider
        self._anthropic = None
        self._gemini = None

        if provider == PROVIDER_ANTHROPIC:
            import anthropic as _anthropic_lib
            self._anthropic = _anthropic_lib.Anthropic(api_key=api_key)

        elif provider == PROVIDER_GEMINI:
            self._gemini = _build_gemini_client(api_key)

        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use 'anthropic' or 'gemini'.")

        logger.info("LLMClient initialized: provider=%s", provider)

    def _gemini_generate(self, model_name: str, body: dict) -> str:
        """Route to SDK (api key) or HTTP client (service account)."""
        if isinstance(self._gemini, _GeminiServiceAccountClient):
            return self._gemini.generate_content(model_name, body)
        # SDK path: reconstruct contents from body for the SDK's typed API
        contents = body.get("contents", [])
        all_parts = []
        for content in contents:
            for part in content.get("parts", []):
                if "text" in part:
                    all_parts.append(part["text"])
                elif "inline_data" in part:
                    from google.genai import types
                    d = part["inline_data"]
                    all_parts.append(types.Part.from_bytes(
                        data=base64.b64decode(d["data"]), mime_type=d["mime_type"]
                    ))
        resp = self._gemini.models.generate_content(model=model_name, contents=all_parts)
        return resp.text

    # ──────────────────────────────────────────────
    # Text completion
    # ──────────────────────────────────────────────

    def complete(self, prompt: str, tier: str = "fast", max_tokens: int = 2048) -> str:
        """Send a plain text prompt, return the response string."""
        if self.provider == PROVIDER_ANTHROPIC:
            model = _MODELS[PROVIDER_ANTHROPIC][tier]
            resp = self._anthropic.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text

        model_name = _MODELS[PROVIDER_GEMINI][tier]
        return self._gemini_generate(model_name, {"contents": [{"parts": [{"text": prompt}]}]})

    # ──────────────────────────────────────────────
    # Single-image completion (for image file attachments)
    # ──────────────────────────────────────────────

    def complete_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        media_type: str,
        tier: str = "fast",
        max_tokens: int = 4096,
    ) -> str:
        """Send one image + text prompt, return the response string."""
        if self.provider == PROVIDER_ANTHROPIC:
            b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
            model = _MODELS[PROVIDER_ANTHROPIC][tier]
            resp = self._anthropic.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return resp.content[0].text

        model_name = _MODELS[PROVIDER_GEMINI][tier]
        body = {"contents": [{"parts": [
            {"inline_data": {"mime_type": media_type, "data": base64.b64encode(image_bytes).decode()}},
            {"text": prompt},
        ]}]}
        return self._gemini_generate(model_name, body)

    # ──────────────────────────────────────────────
    # Multi-page image completion (for scanned PDFs)
    # ──────────────────────────────────────────────

    def complete_with_pages(
        self,
        prompt: str,
        pages_b64: List[str],
        tier: str = "fast",
        max_tokens: int = 8192,
    ) -> str:
        """
        Send multiple page images (base64 PNG) + text prompt.
        Used for scanned PDF extraction.
        """
        if self.provider == PROVIDER_ANTHROPIC:
            content = []
            for i, b64 in enumerate(pages_b64):
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })
                content.append({"type": "text", "text": f"[Page {i + 1}]"})
            content.append({"type": "text", "text": prompt})

            model = _MODELS[PROVIDER_ANTHROPIC][tier]
            resp = self._anthropic.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
            )
            return resp.content[0].text

        model_name = _MODELS[PROVIDER_GEMINI][tier]
        parts = []
        for i, b64 in enumerate(pages_b64):
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
            parts.append({"text": f"[Page {i + 1}]"})
        parts.append({"text": prompt})
        return self._gemini_generate(model_name, {"contents": [{"parts": parts}]})


def create_client() -> LLMClient:
    """Build an LLMClient from environment variables."""
    provider = get_provider()

    if provider == PROVIDER_ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return LLMClient(provider, api_key)

    if provider == PROVIDER_GEMINI:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set (LLM_PROVIDER=gemini)")
        return LLMClient(provider, api_key)

    raise ValueError(f"Unknown LLM_PROVIDER={provider!r}. Set to 'anthropic' or 'gemini'.")
