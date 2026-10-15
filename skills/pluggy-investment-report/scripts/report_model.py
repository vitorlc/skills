"""Shared report semantics and private, atomic local writes (Python 3.10+)."""
import json
import math
import os
import tempfile
from pathlib import Path

TYPE_LABELS = {
    "FIXED_INCOME": "Renda Fixa", "EQUITY": "Ações", "STOCK": "Ações",
    "FUND": "Fundos", "MUTUAL_FUND": "Fundos", "ETF": "ETF",
    "TREASURY": "Tesouro Direto", "REAL_ESTATE": "FIIs", "OTHER": "Outros",
}


def get_type_label(code):
    return TYPE_LABELS.get(code, "Outros")


def number(value, field, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def investments_list(data):
    if isinstance(data, dict):
        data = data.get("investments")
    if not isinstance(data, list):
        raise ValueError("Expected an investments array or {investments: [...]} object")
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("Each investment must be an object")
        number(row.get("value"), "value")
        for field in ("amount", "return_amount", "return_rate"):
            number(row.get(field), field, optional=True)
        for field in ("id", "name", "institution", "type", "maturity_date"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError(f"{field} must be a string or null")
    return data


def aggregate(invs):
    # A missing cost basis is unknown, not zero. Empty portfolios still total zero.
    invested = None if any(i.get("amount") is None for i in invs) else sum(i["amount"] for i in invs)
    current = sum((i.get("value") or 0) for i in invs)
    profits = [i.get("return_amount") if i.get("return_amount") is not None else
               ((i.get("value") or 0) - i["amount"] if i.get("amount") is not None else None) for i in invs]
    profit = None if any(p is None for p in profits) else sum(profits)
    rate = None if profit is None or invested is None else (profit / invested * 100 if invested else 0)
    return {"invested": invested, "current": current, "return_amount": profit, "return_rate": rate, "count": len(invs)}


TARGET_CATEGORIES = set(TYPE_LABELS.values())


def validate_targets(targets):
    if not isinstance(targets, dict):
        raise ValueError("Allocation targets must be an object")
    for category, value in targets.items():
        if category not in TARGET_CATEGORIES:
            raise ValueError(f"Unknown allocation category: {category}")
        number(value, "target")
        if not 0 <= value <= 100:
            raise ValueError("Allocation targets must be between 0 and 100")
    if targets and abs(sum(targets.values()) - 100) > 0.05:
        raise ValueError("Allocation targets must sum to 100")
    return targets


def private_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def private_json(path, data):
    private_write(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
