from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
from typing import Any


def cents(value: Decimal | int | float | str) -> int:
    return int(Decimal(str(value)) * 100)


def daterange_month_start(value: date) -> date:
    return value.replace(day=1)


def json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value

