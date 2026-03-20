from datetime import date

from src.domain.entities import InternalData
from src.domain.equity import Currency


class Exchange(InternalData):
    """``Exchange`` represents the 'currency exchange' operation

    [example]
    John exchange 100 USD to UAH. price: 40UAH for 1USD.
    in that case the value of the operation = 100*40=4000

    params:
        ``from_currency`` - USD from example
        ``to_currency`` - UAH from example
        ``value`` - 4000
    """

    id: int
    from_value: int
    to_value: int
    timestamp: date

    user_id: int
    from_currency: Currency
    to_currency: Currency
