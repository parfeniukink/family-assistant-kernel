import functools

from src import domain
from src.infrastructure import database
from src.infrastructure.responses import PublicData


class Equity(PublicData):
    currency: domain.equity.Currency
    amount: float

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Equity":
        raise NotImplementedError(
            f"Can not convert {type(instance)} into the Equity contract"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.Currency):
        return cls(
            currency=domain.equity.Currency(
                id=instance.id,
                name=instance.name,
                sign=instance.sign,
            ),
            amount=domain.transactions.pretty_money(instance.equity),
        )
