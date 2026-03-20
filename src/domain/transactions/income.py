from datetime import date
from typing import Literal

from src.domain.entities import InternalData
from src.domain.equity import Currency

IncomeSource = Literal["revenue", "gift", "debt", "other"]


class Income(InternalData):
    id: int
    name: str
    value: int
    timestamp: date
    source: IncomeSource

    user_id: int
    currency: Currency
