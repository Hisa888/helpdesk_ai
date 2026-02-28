import requests

class OllamaClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages, timeout=(10, 300), temperature=0.2, num_predict=220, num_ctx=1536):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(num_predict),
                "num_ctx": int(num_ctx),
            },
        }
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]