#!/usr/bin/env python3
"""
Snapshot + diff for pluggy-investment-report.

Usage:
  python snapshot_diff.py <investments.json> <diff_output.json> [--since SPEC] [--no-record]
  python snapshot_diff.py <investments.json> --record-only

Reads the normalized investments list, diffs it against a baseline snapshot
(the previous observation, or the one at --since: 30d, 12m, ytd, YYYY-MM-DD),
writes the diff JSON and appends a new timestamped snapshot. Retention keeps
every snapshot of the last 7 days, one per day up to 90 days, then one per month.
"""
from __future__ import annotations

import argparse
import calendar
import contextlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from report_model import (aggregate, data_dir, investments_list, migrate_legacy, parse_ts,
                          private_json, strip_transactions)

try:  # POSIX only; on other platforms the lock degrades to a no-op.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

SNAPSHOT_DIR = data_dir() / "snapshots"
RECENT_DAYS = 7    # keep every observation from the last week
DAILY_DAYS = 90    # then the latest one per day, then the latest per month forever


def id_key(inv: dict) -> str | None:
    return inv.get("id") or None


def name_key(inv: dict) -> tuple:
    return (inv.get("institution") or "", inv.get("name") or "")


@contextlib.contextmanager
def locked():
    """Serialise read-modify-write of the history across concurrent runs."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if fcntl is None:  # pragma: no cover
        yield
        return
    with open(SNAPSHOT_DIR / ".lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def load_snapshot_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        parse_ts(data["timestamp"])
        if not isinstance(data.get("investments"), list):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_snapshots() -> list[dict]:
    """All readable snapshots, oldest first (unreadable files are skipped)."""
    if not SNAPSHOT_DIR.exists():
        return []
    snaps = []
    for f in SNAPSHOT_DIR.glob("*.json"):
        data = load_snapshot_file(f)
        if data:
            snaps.append(data)
    return sorted(snaps, key=lambda d: parse_ts(d["timestamp"]))


def load_latest_snapshot() -> dict | None:
    snaps = list_snapshots()
    return snaps[-1] if snaps else None


def resolve_since(spec: str | None, now: datetime) -> datetime | None:
    """Turn --since into a target moment; None means "previous observation".

    Accepts prev, <N>d, <N>m, ytd or YYYY-MM-DD.
    """
    if spec in (None, "", "prev"):
        return None
    spec = spec.strip().lower()
    if spec == "ytd":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if spec.endswith("d") and spec[:-1].isdigit():
        return now - timedelta(days=int(spec[:-1]))
    if spec.endswith("m") and spec[:-1].isdigit():
        months = now.year * 12 + now.month - 1 - int(spec[:-1])
        year, month = divmod(months, 12)
        day = min(now.day, calendar.monthrange(year, month + 1)[1])
        return now.replace(year=year, month=month + 1, day=day)
    try:
        return datetime.strptime(spec, "%Y-%m-%d").astimezone().replace(hour=23, minute=59, second=59)
    except ValueError:
        raise ValueError("--since must be prev, <N>d, <N>m, ytd or YYYY-MM-DD") from None


def pick_baseline(snaps: list[dict], target: datetime | None) -> tuple[dict | None, str | None]:
    """Latest snapshot at or before target; the oldest one (with a note) if history is shorter."""
    if not snaps:
        return None, None
    if target is None:
        return snaps[-1], None
    older = [s for s in snaps if parse_ts(s["timestamp"]) <= target]
    if older:
        return older[-1], None
    return snaps[0], f"Histórico começa em {parse_ts(snaps[0]['timestamp']).strftime('%d/%m/%Y')}, depois do período pedido"


def diff_totals(prev_tot: dict, curr_tot: dict) -> dict:
    def d(k):
        p = prev_tot.get(k, 0)
        c = curr_tot.get(k, 0)
        return {"prev": p, "curr": c, "delta": c - p if c is not None and p is not None else None}
    return {
        "invested": d("invested"),
        "current": d("current"),
        "return_amount": d("return_amount"),
        "return_rate": d("return_rate"),
        "count": d("count"),
    }


def match_assets(prev_invs: list[dict], curr_invs: list[dict]):
    """Match in two passes: by Pluggy id first, then by (institution, name)
    for assets unmatched in either side (handles item recreation, where ids
    rotate but the underlying asset is the same).
    Returns (pairs, unmatched_curr, unmatched_prev)."""

    unmatched_prev = list(prev_invs)
    unmatched_curr = list(curr_invs)
    pairs: list[tuple[dict, dict]] = []

    prev_by_id = {id_key(p): p for p in unmatched_prev if id_key(p)}
    next_unmatched_prev = []
    next_unmatched_curr = []
    matched_prev_ids: set[str] = set()
    for c in unmatched_curr:
        cid = id_key(c)
        if cid and cid in prev_by_id and cid not in matched_prev_ids:
            pairs.append((prev_by_id[cid], c))
            matched_prev_ids.add(cid)
        else:
            next_unmatched_curr.append(c)
    for p in unmatched_prev:
        if id_key(p) not in matched_prev_ids:
            next_unmatched_prev.append(p)

    prev_by_name: dict[tuple, list[dict]] = {}
    for p in next_unmatched_prev:
        prev_by_name.setdefault(name_key(p), []).append(p)
    final_unmatched_curr = []
    for c in next_unmatched_curr:
        bucket = prev_by_name.get(name_key(c))
        if bucket:
            pairs.append((bucket.pop(0), c))
        else:
            final_unmatched_curr.append(c)
    final_unmatched_prev = [p for bucket in prev_by_name.values() for p in bucket]
    return pairs, final_unmatched_curr, final_unmatched_prev


def diff_assets(prev_invs: list[dict], curr_invs: list[dict]) -> dict:
    pairs, final_unmatched_curr, final_unmatched_prev = match_assets(prev_invs, curr_invs)

    changed = []
    for prev, curr in pairs:
        v_prev = prev.get("value") or 0
        v_curr = curr.get("value") or 0
        r_prev = prev.get("return_amount")
        r_curr = curr.get("return_amount")
        changed.append({
            "id": curr.get("id"),
            "name": curr.get("name"),
            "institution": curr.get("institution"),
            "type": curr.get("type"),
            "value_prev": v_prev,
            "value_curr": v_curr,
            "value_delta": v_curr - v_prev,
            "return_prev": r_prev,
            "return_curr": r_curr,
            "return_delta": r_curr - r_prev if r_curr is not None and r_prev is not None else None,
        })

    new_items = [{
        "id": c.get("id"),
        "name": c.get("name"),
        "institution": c.get("institution"),
        "type": c.get("type"),
        "value_curr": c.get("value") or 0,
    } for c in final_unmatched_curr]

    removed = [{
        "name": p.get("name"),
        "institution": p.get("institution"),
        "type": p.get("type"),
        "value_prev": p.get("value") or 0,
    } for p in final_unmatched_prev]

    return {"changed": changed, "new": new_items, "removed": removed}


def save_snapshot(invs: list[dict], totals: dict, now: datetime | None = None) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = now or datetime.now().astimezone()
    fname = now.strftime("%Y-%m-%d_%H%M%S_%f") + ".json"
    path = SNAPSHOT_DIR / fname
    as_of = max((i["as_of"] for i in invs if i.get("as_of")), default=None)
    private_json(path, {
        "timestamp": now.isoformat(timespec="microseconds"),
        "as_of": as_of,
        "totals": totals,
        "investments": strip_transactions(invs),
    })
    return path


def _file_time(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.stem, "%Y-%m-%d_%H%M%S_%f").astimezone()
    except ValueError:
        return None


def prune_snapshots(now: datetime | None = None) -> None:
    """Tiered retention: all of the last week, one per day up to 90 days, one per month after."""
    if not SNAPSHOT_DIR.exists():
        return
    now = now or datetime.now().astimezone()
    dated = sorted(((t, f) for f in SNAPSHOT_DIR.glob("*.json") if (t := _file_time(f))), key=lambda x: x[0])
    keep: set[Path] = set()
    latest_in_bucket: dict[tuple, Path] = {}
    for moment, f in dated:  # ascending, so later files overwrite earlier ones in a bucket
        age = (now - moment).days
        if age <= RECENT_DAYS:
            keep.add(f)
        elif age <= DAILY_DAYS:
            latest_in_bucket[("d", moment.date())] = f
        else:
            latest_in_bucket[("m", moment.year, moment.month)] = f
    keep.update(latest_in_bucket.values())
    for _, f in dated:
        if f not in keep:
            f.unlink()


def build_diff(prev_snapshot: dict | None, curr_invs: list[dict], curr_tot: dict, now: datetime,
               since: str | None = None, note: str | None = None) -> dict:
    current_ts = now.isoformat(timespec="microseconds")
    if prev_snapshot is None:
        return {"first_run": True, "previous_timestamp": None, "current_timestamp": current_ts,
                "since": since, "baseline_note": note, "totals": diff_totals({}, curr_tot),
                "assets": {"changed": [], "new": [], "removed": []}}
    prev_invs = prev_snapshot.get("investments", [])
    prev_tot = prev_snapshot.get("totals") or aggregate(prev_invs)
    return {"first_run": False, "previous_timestamp": prev_snapshot.get("timestamp"),
            "current_timestamp": current_ts, "since": since, "baseline_note": note,
            "totals": diff_totals(prev_tot, curr_tot), "assets": diff_assets(prev_invs, curr_invs)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="snapshot_diff.py", description=__doc__.strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("investments")
    parser.add_argument("diff_output", nargs="?")
    parser.add_argument("--since", help="Baseline: prev (default), <N>d, <N>m, ytd or YYYY-MM-DD")
    parser.add_argument("--no-record", action="store_true", help="Compare without saving a new snapshot")
    parser.add_argument("--record-only", action="store_true", help="Save a snapshot without writing a diff")
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if not args.record_only and not args.diff_output:
        parser.print_usage(sys.stderr)
        return 2
    if args.record_only and args.no_record:
        print("--record-only and --no-record are mutually exclusive", file=sys.stderr)
        return 2

    curr_invs = investments_list(json.loads(Path(args.investments).read_text()))
    curr_tot = aggregate(curr_invs)
    now = datetime.now().astimezone()
    target = resolve_since(args.since, now)

    migrate_legacy()
    with locked():
        baseline, note = pick_baseline(list_snapshots(), target)
        result = build_diff(baseline, curr_invs, curr_tot, now, args.since, note)
        if not args.no_record:
            save_snapshot(curr_invs, curr_tot, now)
            prune_snapshots(now)

    if args.record_only:
        print("Snapshot recorded")
        return 0
    private_json(args.diff_output, result)
    print(f"Diff written to {args.diff_output} (first_run={result['first_run']})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (ValueError, OSError) as exc:
        print(f"Snapshot failed: {exc}", file=sys.stderr)
        sys.exit(1)
