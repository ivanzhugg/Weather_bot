import json
from pathlib import Path


class PromptRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path(__file__).resolve().parent / "data" / "prompts.json")

    def get(self, key: str) -> str:
        with self.path.open("r", encoding="utf-8") as file:
            prompts = json.load(file)

        if key not in prompts:
            raise KeyError(f"Ключ промпта '{key}' не найден в {self.path}")

        return prompts[key]