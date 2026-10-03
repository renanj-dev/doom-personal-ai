"""Doom v1.13 multimodal services: image understanding + provider routing."""
from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass

import httpx

from .config import get_settings
from .personality import DOOM_PERSONALITY

settings = get_settings()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class VisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionResult:
    reply: str
    provider: str
    model: str


def normalize_mime(mime_type: str, filename: str = "") -> str:
    mime = (mime_type or "").strip().lower()
    if mime in ALLOWED_IMAGE_TYPES:
        return mime
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed in ALLOWED_IMAGE_TYPES:
        return guessed
    raise VisionError("Formato de imagem não suportado. Use JPG, PNG, WebP ou GIF.")


def validate_image(image_bytes: bytes, mime_type: str, filename: str = "") -> str:
    if not settings.multimodal_enabled:
        raise VisionError("A camada multimodal está desativada no servidor.")
    if not image_bytes:
        raise VisionError("A imagem enviada está vazia.")
    max_bytes = max(1, settings.vision_max_file_mb) * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise VisionError(f"A imagem excede o limite de {settings.vision_max_file_mb} MB.")
    return normalize_mime(mime_type, filename)


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if not text:
        raise VisionError("O modelo de visão respondeu sem conteúdo.")
    return text


def _prompt(user_prompt: str, context_text: str | None = None, knowledge_text: str | None = None) -> str:
    safe_context = context_text or "Nenhum contexto adicional foi recuperado."
    knowledge = knowledge_text or "Nenhuma fonte de conhecimento foi recuperada."
    return (
        DOOM_PERSONALITY
        + "\n\nMODO MULTIMODAL — VISÃO\n"
        + "Analise somente a imagem enviada e a solicitação atual do usuário. "
          "O contexto abaixo é apenas apoio e nunca substitui a solicitação atual. "
          "Não invente detalhes que não estejam visíveis. Se não puder determinar algo, diga claramente.\n"
        + "\nSOLICITAÇÃO ATUAL:\n" + user_prompt.strip()
        + "\n\nCONTEXTO DE APOIO:\n" + safe_context
        + "\n\nCONHECIMENTO DE APOIO:\n" + knowledge
    )


def _ask_openai(image_data_url: str, prompt: str) -> VisionResult:
    if not settings.openai_api_key:
        raise VisionError("OPENAI_API_KEY não foi configurada.")
    from openai import OpenAI
    model = settings.openai_vision_model or settings.openai_model
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url, "detail": "auto"},
                ],
            }
        ],
        store=False,
    )
    return VisionResult(_clean(response.output_text), "openai", model)


def _ask_openrouter(image_data_url: str, prompt: str) -> VisionResult:
    if not settings.openrouter_api_key:
        raise VisionError("OPENROUTER_API_KEY não foi configurada.")
    from openai import OpenAI
    model = settings.openrouter_vision_model or settings.openrouter_model
    headers = {}
    if settings.openrouter_site_url:
        headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_site_name:
        headers["X-Title"] = settings.openrouter_site_name
    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers=headers or None,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
    )
    return VisionResult(_clean(response.choices[0].message.content or ""), "openrouter", model)


def _ask_ollama(image_b64: str, prompt: str) -> VisionResult:
    model = settings.ollama_vision_model or settings.ollama_model
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.4},
    }
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        raise VisionError(f"Ollama não conseguiu analisar a imagem: {exc}") from exc
    return VisionResult(_clean(data.get("message", {}).get("content", "")), "ollama", model)


def analyze_image(image_bytes: bytes, mime_type: str, prompt: str, context_text: str | None = None, knowledge_text: str | None = None) -> VisionResult:
    mime = validate_image(image_bytes, mime_type)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    prepared_prompt = _prompt(prompt, context_text=context_text, knowledge_text=knowledge_text)
    selected = settings.provider
    if selected == "openai":
        return _ask_openai(data_url, prepared_prompt)
    if selected == "openrouter":
        return _ask_openrouter(data_url, prepared_prompt)
    if selected == "ollama":
        return _ask_ollama(data_url.split(',', 1)[1], prepared_prompt)
    raise VisionError(f"Provedor desconhecido para visão: {selected}")


def status() -> dict:
    providers = []
    if settings.openai_api_key and settings.openai_vision_model:
        providers.append({"provider": "openai", "model": settings.openai_vision_model})
    if settings.openrouter_api_key and settings.openrouter_vision_model:
        providers.append({"provider": "openrouter", "model": settings.openrouter_vision_model})
    if settings.ollama_vision_model:
        providers.append({"provider": "ollama", "model": settings.ollama_vision_model})
    return {
        "enabled": bool(settings.multimodal_enabled),
        "vision": bool(settings.multimodal_enabled and providers),
        "voice_input": True,
        "voice_output": True,
        "max_image_mb": settings.vision_max_file_mb,
        "providers": providers,
    }
