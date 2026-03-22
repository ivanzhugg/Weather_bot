import time
import telebot

from Config import Config
from llm import WeatherQueryRequest, WeatherAnswerRequest
from weather_api import OpenMeteoClient


class WeatherBot:
    def __init__(self) -> None:
        self.bot = telebot.TeleBot(Config().telegram_key)
        self.query_llm = WeatherQueryRequest()
        self.answer_llm = WeatherAnswerRequest()
        self.weather_client = OpenMeteoClient()

        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.bot.message_handler(commands=["start", "help"])
        def send_welcome(message):
            self.bot.reply_to(
                message,
                (
                    "Привет! Я бот погоды.\n"
                    "Напиши запрос обычным текстом.\n\n"
                    "Примеры:\n"
                    "- Какая погода в Москве завтра?\n"
                    "- Погода в Казани 2026-03-25\n"
                    "- Что по погоде в Сочи послезавтра?"
                ),
            )

        @self.bot.message_handler(content_types=["text"])
        def handle_text(message):
            self._handle_weather_message(message)

    def _handle_weather_message(self, message) -> None:
        user_text = (message.text or "").strip()

        if not user_text:
            self.bot.reply_to(message, "Напиши город и дату, например: погода в Москве завтра.")
            return

        try:
            self.bot.send_chat_action(message.chat.id, "typing")

            llm_payload = self.query_llm.response(user_text)
            weather_result = self.weather_client.safe_get_weather_from_llm_payload(llm_payload)

            answer = self.answer_llm.response(weather_result)
            self.bot.reply_to(message, answer)

        except Exception as error:
            print(f"Ошибка обработки сообщения: {error}")
            self.bot.reply_to(
                message,
                (
                    "Не получилось обработать запрос.\n"
                    "Попробуй так: 'Какая погода в Москве завтра?'"
                ),
            )

    def run(self) -> None:
        while True:
            try:
                print("Weather bot запущен...")
                self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
            except Exception as error:
                print(f"Ошибка: {error}")
                time.sleep(5)
