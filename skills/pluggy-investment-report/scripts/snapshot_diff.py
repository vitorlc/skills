#!/usr/bin/env python3
"""
Snapshot + diff for pluggy-investment-report.

Usage:
  python snapshot_diff.py <investments.json> <diff_output.json>

Reads the normalized investments list, computes a diff vs. the most recent
prior snapshot (if any), writes the diff JSON to <diff_output.json>, and
appends a new timestamped snapshot. Keeps at most 12 snapshots.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from report_model import aggregate, investments_list, private_json

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "tmp" / "snapshots"
MAX_SNAPSHOTS = 12


def id_key(inv: dict) -> str | None:
    return inv.get("id") or None


def name_key(inv: dict) -> tuple:
    return (inv.get("institution") or "", inv.get("name") or "")


def load_latest_snapshot() -> dict | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


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


def diff_assets(prev_invs: list[dict], curr_invs: list[dict]) -> dict:
    """Match in two passes: by Pluggy id first, then by (institution, name)
    for assets unmatched in either side (handles item recreation, where ids
    rotate but the underlying asset is the same)."""

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


def save_snapshot(invs: list[dict], totals: dict) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = datetime.now()
    fname = now.strftime("%Y-%m-%d_%H%M%S_%f") + ".json"
    path = SNAPSHOT_DIR / fname
    private_json(path, {
        "timestamp": now.isoformat(timespec="microseconds"),
        "totals": totals,
        "investments": invs,
    })
    return path


def prune_snapshots() -> None:
    if not SNAPSHOT_DIR.exists():
        return
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    for f in files[:-MAX_SNAPSHOTS]:
        f.unlink()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    invs_path = Path(argv[1])
    diff_out = Path(argv[2])

    curr_invs = investments_list(json.loads(invs_path.read_text()))
    curr_tot = aggregate(curr_invs)

    prev_snapshot = load_latest_snapshot()

    if prev_snapshot is None:
        result = {
            "first_run": True,
            "previous_timestamp": None,
            "current_timestamp": datetime.now().isoformat(timespec="microseconds"),
            "totals": diff_totals({}, curr_tot),
            "assets": {"changed": [], "new": [], "removed": []},
        }
    else:
        prev_invs = prev_snapshot.get("investments", [])
        prev_tot = prev_snapshot.get("totals") or aggregate(prev_invs)
        result = {
            "first_run": False,
            "previous_timestamp": prev_snapshot.get("timestamp"),
            "current_timestamp": datetime.now().isoformat(timespec="microseconds"),
            "totals": diff_totals(prev_tot, curr_tot),
            "assets": diff_assets(prev_invs, curr_invs),
        }

    private_json(diff_out, result)
    save_snapshot(curr_invs, curr_tot)
    prune_snapshots()
    print(f"Diff written to {diff_out} (first_run={result['first_run']})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except (ValueError, OSError) as exc:
        print(f"Snapshot failed: {exc}", file=sys.stderr)
        sys.exit(1)
