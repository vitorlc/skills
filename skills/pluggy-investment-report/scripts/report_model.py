"""Shared report semantics and private, atomic local writes (Python 3.10+)."""
import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TYPE_LABELS = {
    "FIXED_INCOME": "Renda Fixa", "EQUITY": "Ações", "STOCK": "Ações",
    "FUND": "Fundos", "MUTUAL_FUND": "Fundos", "ETF": "ETF",
    "TREASURY": "Tesouro Direto", "REAL_ESTATE": "FIIs", "OTHER": "Outros",
}

SKILL_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR_ENV = "PLUGGY_REPORT_DATA_DIR"


def get_type_label(code):
    return TYPE_LABELS.get(code, "Outros")


# ── Formatting (pt-BR) ───────────────────────────────────────────────────────

def format_currency(value: float) -> str:
    sign = "-R$ " if value < 0 else "R$ "
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{formatted}"


def format_percentage(value: float) -> str:
    return f"{value:.2f}%".replace(".", ",")


def money_or_unknown(value) -> str:
    return format_currency(value) if value is not None else "não informado"


def percent_or_unknown(value) -> str:
    return format_percentage(value) if value is not None else "não informado"


# ── Local state location ─────────────────────────────────────────────────────

def legacy_dir() -> Path:
    """Per-installation state directory used by earlier versions."""
    return SKILL_ROOT / "tmp"


def data_dir() -> Path:
    """History/targets location. Defaults to the installation's tmp/ so the
    installer keeps preserving it; PLUGGY_REPORT_DATA_DIR moves it elsewhere
    (e.g. one history shared by every host that has the skill installed)."""
    override = os.environ.get(DATA_DIR_ENV)
    return Path(override).expanduser() if override else legacy_dir()


def migrate_legacy() -> int:
    """Copy (never move) history and targets from tmp/ into a custom data dir
    the first time it is used. Returns the number of files copied."""
    dest, legacy = data_dir(), legacy_dir()
    if dest.resolve() == legacy.resolve() or not legacy.exists():
        return 0
    copied = 0
    src_snaps, dst_snaps = legacy / "snapshots", dest / "snapshots"
    if src_snaps.exists() and not any(dst_snaps.glob("*.json")):
        for f in sorted(src_snaps.glob("*.json")):
            private_write(dst_snaps / f.name, f.read_text(encoding="utf-8"))
            copied += 1
    src_t, dst_t = legacy / "allocation_targets.json", dest / "allocation_targets.json"
    if src_t.exists() and not dst_t.exists():
        private_write(dst_t, src_t.read_text(encoding="utf-8"))
        copied += 1
    return copied


# ── Validation ───────────────────────────────────────────────────────────────

def number(value, field, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


TEXT_FIELDS = ("id", "name", "institution", "type", "maturity_date", "subtype", "rate_type",
               "issuer", "issue_date", "as_of", "status")
NUMBER_FIELDS = ("amount", "return_amount", "return_rate", "rate", "fixed_annual_rate",
                 "quantity", "last_twelve_months_rate")


def investments_list(data):
    if isinstance(data, dict):
        data = data.get("investments")
    if not isinstance(data, list):
        raise ValueError("Expected an investments array or {investments: [...]} object")
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("Each investment must be an object")
        number(row.get("value"), "value")
        for field in NUMBER_FIELDS:
            number(row.get(field), field, optional=True)
        for field in TEXT_FIELDS:
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError(f"{field} must be a string or null")
        txs = row.get("transactions")
        if txs is not None:
            if not isinstance(txs, list):
                raise ValueError("transactions must be a list or null")
            for tx in txs:
                if not isinstance(tx, dict) or not isinstance(tx.get("date"), str) or not isinstance(tx.get("type"), str):
                    raise ValueError("Each transaction needs string date and type")
                number(tx.get("amount"), "transaction amount")
    return data


def strip_transactions(invs):
    """Snapshots keep values, not the (potentially large) transaction lists."""
    return [{k: v for k, v in row.items() if k != "transactions"} for row in invs]


# ── Aggregation ──────────────────────────────────────────────────────────────

def _profit(i):
    if i.get("return_amount") is not None:
        return i["return_amount"]
    if i.get("amount") is not None:
        return (i.get("value") or 0) - i["amount"]
    return None


profit_of = _profit


def aggregate(invs):
    # A missing cost basis is unknown, not zero. Empty portfolios still total zero.
    invested = None if any(i.get("amount") is None for i in invs) else sum(i["amount"] for i in invs)
    current = sum((i.get("value") or 0) for i in invs)
    profits = [_profit(i) for i in invs]
    profit = None if any(p is None for p in profits) else sum(profits)
    rate = None if profit is None or invested is None else (profit / invested * 100 if invested else 0)
    return {"invested": invested, "current": current, "return_amount": profit, "return_rate": rate, "count": len(invs)}


TARGET_CATEGORIES = set(TYPE_LABELS.values())


def coverage(invs):
    """Return known-cost subtotal so one unknown cost does not hide the whole result."""
    known = [i for i in invs if i.get("amount") is not None and _profit(i) is not None]
    total_value = sum((i.get("value") or 0) for i in invs)
    known_value = sum((i.get("value") or 0) for i in known)
    invested = sum(i["amount"] for i in known)
    profit = sum(_profit(i) for i in known)
    return {
        "count": len(invs), "known_count": len(known),
        "value_total": total_value, "value_known": known_value,
        "value_pct": known_value / total_value * 100 if total_value else 100.0,
        "invested": invested, "return_amount": profit,
        "return_rate": profit / invested * 100 if invested else None,
        "complete": len(known) == len(invs),
    }


def category_totals(invs):
    totals = defaultdict(float)
    for row in invs:
        totals[get_type_label(row.get("type") or "OTHER")] += row.get("value") or 0
    return dict(totals)


# ── Targets and allocation analysis ──────────────────────────────────────────

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


def build_allocation_analysis(type_totals: dict, targets: dict, total_current: float,
                              tolerance: float = 2.0) -> dict | None:
    if not targets or not total_current:
        return None

    rows = []
    for category in sorted(set(type_totals) | set(targets)):
        target_pct = targets.get(category, 0)
        actual_pct = round(type_totals.get(category, 0) / total_current * 100, 1)
        rows.append({"category": category, "target_pct": target_pct, "actual_pct": actual_pct,
                     "deviation": round(actual_pct - target_pct, 1)})
    if not rows:
        return None

    recommendations = []
    for row in sorted(rows, key=lambda r: abs(r["deviation"]), reverse=True):
        if abs(row["deviation"]) >= tolerance:
            if row["deviation"] > 0:
                recommendations.append(f"↓ Reduzir {row['category']} ({abs(row['deviation']):.0f}% acima da meta)")
            else:
                recommendations.append(f"↑ Comprar {row['category']} ({abs(row['deviation']):.0f}% abaixo da meta)")

    worst = max(rows, key=lambda r: abs(r["deviation"]))
    return {"rows": rows, "recommendations": recommendations,
            "imbalance": {"category": worst["category"], "pct": worst["deviation"]}}


# ── Dates ────────────────────────────────────────────────────────────────────

def parse_ts(value):
    """Parse an ISO timestamp. Naive values (older snapshots) are local time."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone() if dt.tzinfo is None else dt


# ── Private atomic writes ────────────────────────────────────────────────────

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
