from __future__ import annotations

import json
from urllib import request


class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434", timeout: float = 120.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        top_p: float = 0.9,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        if "message" in body and "content" in body["message"]:
            return str(body["message"]["content"]).strip()
        if "response" in body:
            return str(body["response"]).strip()
        raise ValueError("Ollama response did not contain translated content")
