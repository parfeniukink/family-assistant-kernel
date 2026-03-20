from datetime import date

from src.domain.entities import InternalData
from src.domain.equity import Currency


class CostCategory(InternalData):
    id: int
    name: str


class Cost(InternalData):
    id: int
    name: str
    value: int
    timestamp: date

    user_id: int
    currency: Currency
    category: CostCategory
