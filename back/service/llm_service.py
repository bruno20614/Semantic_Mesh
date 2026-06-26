"""
Cliente simples para geração com LLM.

Por padrão usa Ollama local. Quando LLM_PROVIDER=openai, usa a API da OpenAI
com OPENAI_API_KEY. Se o provedor falhar, retorna erro para o RAG usar fallback.
"""
import os

import requests
from dotenv import load_dotenv


load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/responses")


def _extract_openai_text(data: dict) -> str:
    text = (data.get("output_text") or "").strip()
    if text:
        return text

    parts = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                parts.append(content.get("text", ""))
    return "\n".join(part.strip() for part in parts if part).strip()


def generate_with_ollama(prompt: str, model: str | None = None, timeout: int = 90) -> dict:
    payload = {
        "model": model or OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = (data.get("response") or "").strip()
        if not text:
            return {"ok": False, "error": "Ollama não retornou texto."}
        return {
            "ok": True,
            "model": payload["model"],
            "text": text,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"Ollama indisponível: {exc}",
        }


def generate_with_openai(prompt: str, model: str | None = None, timeout: int = 90) -> dict:
    if not OPENAI_API_KEY:
        return {
            "ok": False,
            "error": "OPENAI_API_KEY não configurada.",
        }

    payload = {
        "model": model or OPENAI_MODEL,
        "input": prompt,
        "temperature": 0.2,
        "max_output_tokens": 900,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            OPENAI_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        if response.status_code == 429:
            return {
                "ok": False,
                "error": (
                    "OpenAI retornou 429 (limite de uso ou cota excedida). "
                    "Verifique créditos, billing, limites de uso da conta ou tente novamente mais tarde."
                ),
            }
        if response.status_code == 401:
            return {
                "ok": False,
                "error": "OpenAI retornou 401 (API key inválida, revogada ou ausente).",
            }
        response.raise_for_status()
        data = response.json()
        text = _extract_openai_text(data)
        if not text:
            return {"ok": False, "error": "OpenAI não retornou texto."}
        return {
            "ok": True,
            "model": payload["model"],
            "provider": "openai",
            "text": text,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": f"OpenAI indisponível: {exc}",
        }


def generate_llm_response(
    prompt: str,
    model: str | None = None,
    timeout: int = 90,
    provider: str | None = None,
) -> dict:
    selected_provider = (provider or LLM_PROVIDER).strip().lower()
    if selected_provider == "openai":
        return generate_with_openai(prompt, model=model, timeout=timeout)
    if selected_provider == "ollama":
        result = generate_with_ollama(prompt, model=model, timeout=timeout)
        if result.get("ok"):
            result["provider"] = "ollama"
        return result
    return {
        "ok": False,
        "error": f"LLM_PROVIDER inválido: {selected_provider}",
    }
