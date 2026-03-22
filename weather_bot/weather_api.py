from __future__ import annotations

import requests
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Optional


class OpenMeteoError(Exception):
    """Базовая ошибка для работы с Open-Meteo."""
    pass


class LocationNotFoundError(OpenMeteoError):
    """Регион не найден."""
    pass


class InvalidWeatherRequestError(OpenMeteoError):
    """Некорректный payload от LLM."""
    pass


@dataclass
class Location:
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeatherRequest:
    region_query: str
    target_date: str
    date_type: str = "unknown"

    @classmethod
    def from_llm_payload(cls, payload: dict[str, Any]) -> "WeatherRequest":
        if not isinstance(payload, dict):
            raise InvalidWeatherRequestError("Payload должен быть словарём.")

        is_valid = payload.get("is_valid", True)
        errors = payload.get("errors", [])

        if not is_valid:
            raise InvalidWeatherRequestError(
                f"LLM вернул невалидный payload: errors={errors}"
            )

        region_query = payload.get("region_query")
        target_date = payload.get("target_date")
        date_type = payload.get("date_type", "unknown")

        if not region_query:
            raise InvalidWeatherRequestError("Отсутствует region_query.")
        if not target_date:
            raise InvalidWeatherRequestError("Отсутствует target_date.")

        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as error:
            raise InvalidWeatherRequestError(
                "target_date должен быть в формате YYYY-MM-DD."
            ) from error

        return cls(
            region_query=region_query.strip(),
            target_date=target_date,
            date_type=date_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeatherForecast:
    location_name: str
    country: str
    forecast_date: str
    temperature_max: Optional[float]
    temperature_min: Optional[float]
    precipitation_sum: Optional[float]
    weather_code: Optional[int]
    weather_description: str
    timezone: str
    source: str
    latitude: float
    longitude: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeatherCodeMapper:
    WEATHER_CODES = {
        0: "Ясно",
        1: "Преимущественно ясно",
        2: "Переменная облачность",
        3: "Пасмурно",
        45: "Туман",
        48: "Туман с инеем",
        51: "Легкая морось",
        53: "Умеренная морось",
        55: "Сильная морось",
        56: "Легкая ледяная морось",
        57: "Сильная ледяная морось",
        61: "Небольшой дождь",
        63: "Умеренный дождь",
        65: "Сильный дождь",
        66: "Легкий ледяной дождь",
        67: "Сильный ледяной дождь",
        71: "Небольшой снег",
        73: "Умеренный снег",
        75: "Сильный снег",
        77: "Снежные зерна",
        80: "Небольшие ливни",
        81: "Умеренные ливни",
        82: "Сильные ливни",
        85: "Небольшой снегопад",
        86: "Сильный снегопад",
        95: "Гроза",
        96: "Гроза с небольшим градом",
        99: "Гроза с сильным градом",
    }

    @classmethod
    def get_description(cls, code: Optional[int]) -> str:
        if code is None:
            return "Нет данных"
        return cls.WEATHER_CODES.get(code, "Неизвестное погодное состояние")


class OpenMeteoClient:
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise OpenMeteoError(f"Ошибка запроса к Open-Meteo: {error}") from error

    def get_location(self, region_name: str) -> Location:
        params = {
            "name": region_name,
            "count": 1,
            "language": "ru",
            "format": "json",
        }

        data = self._request_json(self.GEOCODING_URL, params)
        results = data.get("results")

        if not results:
            raise LocationNotFoundError(f"Регион '{region_name}' не найден.")

        item = results[0]

        return Location(
            name=item.get("name", "Неизвестно"),
            country=item.get("country", "Неизвестно"),
            latitude=item["latitude"],
            longitude=item["longitude"],
            timezone=item.get("timezone", "auto"),
        )

    def get_weather(self, request_data: WeatherRequest) -> WeatherForecast:
        location = self.get_location(request_data.region_query)

        try:
            requested_date = datetime.strptime(
                request_data.target_date, "%Y-%m-%d"
            ).date()
        except ValueError as error:
            raise InvalidWeatherRequestError(
                "Дата должна быть в формате YYYY-MM-DD."
            ) from error

        if self._should_use_forecast(request_data.date_type, requested_date):
            return self._get_forecast(location, requested_date)

        return self._get_archive_weather(location, requested_date)

    def get_weather_from_llm_payload(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Главный метод для будущей интеграции с LLM.
        Принимает payload от LLM и возвращает dict.
        """
        request_data = WeatherRequest.from_llm_payload(payload)
        forecast = self.get_weather(request_data)

        return {
            "ok": True,
            "request": request_data.to_dict(),
            "location": {
                "name": forecast.location_name,
                "country": forecast.country,
                "latitude": forecast.latitude,
                "longitude": forecast.longitude,
                "timezone": forecast.timezone,
            },
            "forecast": forecast.to_dict(),
        }

    def safe_get_weather_from_llm_payload(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Без выброса исключения наружу.
        Удобно для Telegram-бота и пайплайна с LLM.
        """
        try:
            return self.get_weather_from_llm_payload(payload)
        except OpenMeteoError as error:
            return {
                "ok": False,
                "error_type": error.__class__.__name__,
                "message": str(error),
                "request": payload,
            }
        except Exception as error:
            return {
                "ok": False,
                "error_type": error.__class__.__name__,
                "message": f"Неожиданная ошибка: {error}",
                "request": payload,
            }

    def _should_use_forecast(
        self, date_type: str, requested_date: date
    ) -> bool:
        if date_type == "forecast":
            return True
        if date_type == "historical":
            return False
        return requested_date >= date.today()

    def _get_forecast(self, location: Location, requested_date: date) -> WeatherForecast:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
            ]),
            "timezone": "auto",
            "start_date": requested_date.isoformat(),
            "end_date": requested_date.isoformat(),
        }

        data = self._request_json(self.FORECAST_URL, params)
        daily = data.get("daily")

        if not daily or not daily.get("time"):
            raise OpenMeteoError("Нет данных прогноза на указанную дату.")

        code = self._safe_get(daily, "weather_code")

        return WeatherForecast(
            location_name=location.name,
            country=location.country,
            forecast_date=daily["time"][0],
            temperature_max=self._safe_get(daily, "temperature_2m_max"),
            temperature_min=self._safe_get(daily, "temperature_2m_min"),
            precipitation_sum=self._safe_get(daily, "precipitation_sum"),
            weather_code=code,
            weather_description=WeatherCodeMapper.get_description(code),
            timezone=data.get("timezone", location.timezone),
            source="Forecast API",
            latitude=location.latitude,
            longitude=location.longitude,
        )

    def _get_archive_weather(
        self, location: Location, requested_date: date
    ) -> WeatherForecast:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
            ]),
            "timezone": "auto",
            "start_date": requested_date.isoformat(),
            "end_date": requested_date.isoformat(),
        }

        data = self._request_json(self.ARCHIVE_URL, params)
        daily = data.get("daily")

        if not daily or not daily.get("time"):
            raise OpenMeteoError("Нет исторических данных на указанную дату.")

        code = self._safe_get(daily, "weather_code")

        return WeatherForecast(
            location_name=location.name,
            country=location.country,
            forecast_date=daily["time"][0],
            temperature_max=self._safe_get(daily, "temperature_2m_max"),
            temperature_min=self._safe_get(daily, "temperature_2m_min"),
            precipitation_sum=self._safe_get(daily, "precipitation_sum"),
            weather_code=code,
            weather_description=WeatherCodeMapper.get_description(code),
            timezone=data.get("timezone", location.timezone),
            source="Historical Weather API",
            latitude=location.latitude,
            longitude=location.longitude,
        )

    @staticmethod
    def _safe_get(data: dict[str, Any], key: str) -> Any:
        values = data.get(key)
        if isinstance(values, list) and values:
            return values[0]
        return None