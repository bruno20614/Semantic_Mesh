"""
Cliente simples para LLM local via Ollama.

O serviço assume que o Ollama está rodando em http://localhost:11434.
Se não estiver disponível, retorna erro para o RAG usar o fallback extrativo.
"""
import os

import requests


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


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
