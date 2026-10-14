import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import report_model
import snapshot_diff

NOW = datetime(2026, 10, 13, 12, 0).astimezone()


def _snap(ts, value=100, **extra):
    return {"timestamp": ts.isoformat(), "totals": {"current": value},
            "investments": [{"id": "a", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": value, **extra}]}


class HistoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.object(snapshot_diff, "SNAPSHOT_DIR", self.root / "snapshots")
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_snapshot(self, moment, value=100):
        path = snapshot_diff.SNAPSHOT_DIR / (moment.strftime("%Y-%m-%d_%H%M%S_%f") + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_snap(moment, value)))
        return path

    def run_cli(self, invs, *flags):
        source, diff = self.root / "in.json", self.root / "diff.json"
        source.write_text(json.dumps(invs))
        rc = snapshot_diff.main(["snapshot_diff.py", str(source), str(diff), *flags])
        return rc, (json.loads(diff.read_text()) if diff.exists() else None)


class ResolveSinceTests(unittest.TestCase):
    def test_variants(self):
        self.assertIsNone(snapshot_diff.resolve_since(None, NOW))
        self.assertIsNone(snapshot_diff.resolve_since("prev", NOW))
        self.assertEqual(snapshot_diff.resolve_since("30d", NOW), NOW - timedelta(days=30))
        self.assertEqual(snapshot_diff.resolve_since("ytd", NOW).strftime("%m-%d %H"), "01-01 00")
        self.assertEqual(snapshot_diff.resolve_since("2m", NOW).month, 8)
        self.assertEqual(snapshot_diff.resolve_since("12m", NOW).year, 2025)
        self.assertEqual(snapshot_diff.resolve_since("2026-09-01", NOW).day, 1)

    def test_month_end_clamps(self):
        end = datetime(2026, 3, 31, 10).astimezone()
        self.assertEqual(snapshot_diff.resolve_since("1m", end).day, 28)

    def test_invalid(self):
        for bad in ("soon", "d", "-3d", "2026-13-01"):
            with self.assertRaises(ValueError):
                snapshot_diff.resolve_since(bad, NOW)


class PickBaselineTests(unittest.TestCase):
    def setUp(self):
        self.snaps = [_snap(NOW - timedelta(days=d)) for d in (60, 31, 10, 2)]

    def test_previous_is_latest(self):
        snap, note = snapshot_diff.pick_baseline(self.snaps, None)
        self.assertEqual(snap, self.snaps[-1])
        self.assertIsNone(note)

    def test_at_or_before_target(self):
        snap, note = snapshot_diff.pick_baseline(self.snaps, NOW - timedelta(days=30))
        self.assertEqual(snap, self.snaps[1])
        self.assertIsNone(note)

    def test_history_shorter_than_requested_uses_oldest_with_note(self):
        snap, note = snapshot_diff.pick_baseline(self.snaps, NOW - timedelta(days=365))
        self.assertEqual(snap, self.snaps[0])
        self.assertIn("Histórico começa", note)

    def test_no_history(self):
        self.assertEqual(snapshot_diff.pick_baseline([], NOW), (None, None))


class RetentionTests(HistoryCase):
    def test_tiered_retention(self):
        keep_recent = [self.write_snapshot(NOW - timedelta(hours=h)) for h in (1, 30, 100)]
        day = NOW - timedelta(days=40)
        early, late = self.write_snapshot(day.replace(hour=8)), self.write_snapshot(day.replace(hour=20))
        month = NOW - timedelta(days=200)
        m_early, m_late = self.write_snapshot(month.replace(day=3)), self.write_snapshot(month.replace(day=20))
        snapshot_diff.prune_snapshots(NOW)
        remaining = set(snapshot_diff.SNAPSHOT_DIR.glob("*.json"))
        self.assertTrue(set(keep_recent) <= remaining)
        self.assertIn(late, remaining)
        self.assertNotIn(early, remaining)
        self.assertIn(m_late, remaining)
        self.assertNotIn(m_early, remaining)

    def test_dozens_of_same_day_runs_do_not_evict_old_history(self):
        old = self.write_snapshot(NOW - timedelta(days=45))
        for minute in range(30):
            self.write_snapshot(NOW - timedelta(minutes=minute))
        snapshot_diff.prune_snapshots(NOW)
        self.assertTrue(old.exists())
        self.assertEqual(len(list(snapshot_diff.SNAPSHOT_DIR.glob("*.json"))), 31)

    def test_unparseable_names_are_never_deleted(self):
        keep = snapshot_diff.SNAPSHOT_DIR / "manual-backup.json"
        keep.parent.mkdir(parents=True)
        keep.write_text("{}")
        snapshot_diff.prune_snapshots(NOW)
        self.assertTrue(keep.exists())


class MainTests(HistoryCase):
    INVS = [{"id": "a", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 120, "amount": 100,
             "as_of": "2026-10-12T00:00:00.000Z", "transactions": [{"date": "2026-01-01", "type": "BUY", "amount": 100}]}]

    def test_snapshot_is_timezone_aware_slim_and_matches_diff_timestamp(self):
        rc, diff = self.run_cli(self.INVS)
        self.assertEqual(rc, 0)
        (path,) = snapshot_diff.SNAPSHOT_DIR.glob("*.json")
        snap = json.loads(path.read_text())
        self.assertIsNotNone(datetime.fromisoformat(snap["timestamp"]).tzinfo)
        self.assertEqual(snap["timestamp"], diff["current_timestamp"])
        self.assertEqual(snap["as_of"], "2026-10-12T00:00:00.000Z")
        self.assertNotIn("transactions", snap["investments"][0])

    def test_since_compares_against_older_baseline(self):
        self.write_snapshot(NOW - timedelta(days=40), value=100)
        self.write_snapshot(NOW - timedelta(days=1), value=110)
        rc, diff = self.run_cli(self.INVS, "--since", "30d")
        self.assertEqual(diff["totals"]["current"]["prev"], 100)
        self.assertEqual(diff["since"], "30d")
        rc, diff = self.run_cli(self.INVS)
        self.assertEqual(diff["totals"]["current"]["prev"], 120)  # previous run just recorded

    def test_no_record_leaves_history_untouched(self):
        self.write_snapshot(NOW - timedelta(days=1))
        self.run_cli(self.INVS, "--no-record")
        self.assertEqual(len(list(snapshot_diff.SNAPSHOT_DIR.glob("*.json"))), 1)

    def test_record_only_needs_no_output_and_writes_no_diff(self):
        source = self.root / "in.json"
        source.write_text(json.dumps(self.INVS))
        self.assertEqual(snapshot_diff.main(["x", str(source), "--record-only"]), 0)
        self.assertEqual(len(list(snapshot_diff.SNAPSHOT_DIR.glob("*.json"))), 1)

    def test_bad_arguments(self):
        source = self.root / "in.json"
        source.write_text("[]")
        with patch("sys.stderr"):
            self.assertEqual(snapshot_diff.main(["x", str(source)]), 2)
            self.assertEqual(snapshot_diff.main(["x", str(source), "--record-only", "--no-record"]), 2)
            self.assertEqual(snapshot_diff.main(["x"]), 2)

    def test_corrupt_snapshot_is_ignored(self):
        snapshot_diff.SNAPSHOT_DIR.mkdir(parents=True)
        (snapshot_diff.SNAPSHOT_DIR / "2026-01-01_000000_000000.json").write_text("{not json")
        good = self.write_snapshot(NOW - timedelta(days=1), value=90)
        self.assertEqual([s["totals"]["current"] for s in snapshot_diff.list_snapshots()], [90])
        rc, diff = self.run_cli(self.INVS)
        self.assertEqual(rc, 0)
        self.assertEqual(diff["totals"]["current"]["prev"], 90)

    def test_invalid_since_is_reported(self):
        with self.assertRaises(ValueError):
            self.run_cli(self.INVS, "--since", "bogus")

    def test_lock_file_does_not_count_as_snapshot(self):
        self.run_cli(self.INVS)
        self.assertEqual(len(snapshot_diff.list_snapshots()), 1)


class DataDirTests(unittest.TestCase):
    def test_default_is_installation_tmp(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(report_model.DATA_DIR_ENV, None)
            self.assertEqual(report_model.data_dir(), report_model.legacy_dir())

    def test_override_and_one_time_copy_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy, dest = Path(tmp) / "legacy", Path(tmp) / "shared"
            (legacy / "snapshots").mkdir(parents=True)
            (legacy / "snapshots" / "2026-01-01_000000_000000.json").write_text("{}")
            (legacy / "allocation_targets.json").write_text('{"ETF": 100}')
            with patch.dict(os.environ, {report_model.DATA_DIR_ENV: str(dest)}), \
                    patch.object(report_model, "legacy_dir", lambda: legacy):
                self.assertEqual(report_model.data_dir(), dest)
                self.assertEqual(report_model.migrate_legacy(), 2)
                self.assertEqual(report_model.migrate_legacy(), 0)  # idempotent
            self.assertTrue((legacy / "allocation_targets.json").exists())  # copied, never moved
            self.assertEqual((dest / "allocation_targets.json").read_text(), '{"ETF": 100}')
            if os.name == "posix":
                self.assertEqual((dest / "allocation_targets.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
