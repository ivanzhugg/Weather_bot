import os
from dotenv import load_dotenv
from pathlib import Path

class Config:
    def __init__(self):
        self.path = Path(__file__).resolve().parent / "data" / ".env"
        load_dotenv(self.path)
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.telegram_key = os.getenv("TELEGRAM_API_KEY")


