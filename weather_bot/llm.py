from google import genai
from google.genai import types
from Config import Config
from date_provider import DateProvider

import json
from pathlib import Path


class Request:
    def __init__(self, prompt_key: str, model: str = "gemini-3-flash-preview") -> None:
        api_key = Config().gemini_key

        self.path = Path(__file__).resolve().parent / "data" / "config.json"
        self.client = genai.Client(api_key=api_key)
        self.prompt_key = prompt_key
        self.model = model
        self.date_provider = DateProvider()

    def _load_config(self) -> dict:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def prompt(self) -> str:
        config = self._load_config()
        prompt_template = config[self.prompt_key]
        return prompt_template.format(self.date_provider.current_date())

    def _generate(self, context: str, json_mode: bool = False) -> str:
        config = None

        if json_mode:
            config = types.GenerateContentConfig(
                response_mime_type="application/json"
            )

        response = self.client.models.generate_content(
            model=self.model,
            contents=f"{self.prompt()}\n\n{context}",
            config=config,
        )

        return (response.text or "").strip()


class WeatherQueryRequest(Request):
    def __init__(self) -> None:
        super().__init__(prompt_key="weather_query_prompt")

    def _validate_result(self, data: dict) -> dict:
        result = {
            "region_query": data.get("region_query"),
            "target_date": data.get("target_date"),
            "date_type": data.get("date_type", "unknown"),
            "is_valid": data.get("is_valid", False),
            "errors": data.get("errors", []),
        }

        if not isinstance(result["errors"], list):
            result["errors"] = ["invalid_errors"]

        if not result["region_query"] and "missing_region" not in result["errors"]:
            result["errors"].append("missing_region")

        if not result["target_date"] and "missing_date" not in result["errors"]:
            result["errors"].append("missing_date")

        result["errors"] = list(dict.fromkeys(result["errors"]))
        result["is_valid"] = (
            bool(result["region_query"])
            and bool(result["target_date"])
            and len(result["errors"]) == 0
        )

        return result

    def response(self, context: str) -> dict:
        raw_json = self._generate(context=context, json_mode=True)

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return {
                "region_query": None,
                "target_date": None,
                "date_type": "unknown",
                "is_valid": False,
                "errors": ["invalid_json_from_llm"],
            }

        return self._validate_result(data)


class WeatherAnswerRequest(Request):
    def __init__(self) -> None:
        super().__init__(prompt_key="weather_answer_prompt")

    def response(self, context: dict | str) -> str:
        if isinstance(context, dict):
            context = json.dumps(context, ensure_ascii=False, indent=2)

        return self._generate(context=context, json_mode=False)