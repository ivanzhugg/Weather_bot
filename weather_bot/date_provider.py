from datetime import datetime


class DateProvider:
    def __init__(self, date_format: str = "%Y-%m-%d") -> None:
        self.date_format = date_format

    def current_date(self) -> str:
        return datetime.now().strftime(self.date_format)