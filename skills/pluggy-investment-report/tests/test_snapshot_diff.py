import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


class TestAggregate(unittest.TestCase):
    def setUp(self):
        from snapshot_diff import aggregate
        self.aggregate = aggregate

    def test_empty_list(self):
        result = self.aggregate([])
        self.assertEqual(result["invested"], 0)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["return_amount"], 0)
        self.assertEqual(result["return_rate"], 0)
        self.assertEqual(result["count"], 0)

    def test_single_investment(self):
        invs = [{"amount": 1000, "value": 1200}]
        result = self.aggregate(invs)
        self.assertEqual(result["invested"], 1000)
        self.assertEqual(result["current"], 1200)
        self.assertEqual(result["return_amount"], 200)
        self.assertEqual(result["return_rate"], 20.0)
        self.assertEqual(result["count"], 1)

    def test_multiple_investments(self):
        invs = [
            {"amount": 5000, "value": 5430.50},
            {"amount": 2000, "value": 1850.00},
        ]
        result = self.aggregate(invs)
        self.assertAlmostEqual(result["invested"], 7000.0)
        self.assertAlmostEqual(result["current"], 7280.50)
        self.assertAlmostEqual(result["return_amount"], 280.50)

    def test_handles_none_values(self):
        invs = [{"amount": None, "value": None}]
        result = self.aggregate(invs)
        self.assertEqual(result["invested"], 0)
        self.assertEqual(result["current"], 0)


class TestFirstRun(unittest.TestCase):
    def setUp(self):
        from snapshot_diff import main
        self.main = main

    def test_first_run_returns_zero_and_creates_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            invs_path = Path(tmp) / "investments.json"
            diff_path = Path(tmp) / "diff.json"
            invs_path.write_text(json.dumps([
                {"id": "1", "name": "CDB", "amount": 1000, "value": 1100, "institution": "X", "type": "FIXED_INCOME"},
            ]))
            rv = self.main(["snapshot_diff.py", str(invs_path), str(diff_path)])
            self.assertEqual(rv, 0)
            self.assertTrue(diff_path.exists())
            data = json.loads(diff_path.read_text())
            self.assertTrue(data["first_run"])
            self.assertIsNone(data["previous_timestamp"])


class TestDiffAssets(unittest.TestCase):
    def setUp(self):
        from snapshot_diff import diff_assets
        self.diff_assets = diff_assets

    def test_match_by_id(self):
        prev = [{"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 100, "return_amount": 5}]
        curr = [{"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 110, "return_amount": 15}]
        result = self.diff_assets(prev, curr)
        self.assertEqual(len(result["changed"]), 1)
        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["removed"]), 0)
        self.assertAlmostEqual(result["changed"][0]["value_delta"], 10)

    def test_new_asset_appears(self):
        prev = [{"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 100, "return_amount": 5}]
        curr = [
            {"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 110, "return_amount": 15},
            {"id": "a2", "name": "PETR4", "institution": "Y", "type": "STOCK", "value": 50, "return_amount": 0},
        ]
        result = self.diff_assets(prev, curr)
        self.assertEqual(len(result["changed"]), 1)
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(result["new"][0]["name"], "PETR4")

    def test_removed_asset_detected(self):
        prev = [
            {"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 100, "return_amount": 5},
            {"id": "a2", "name": "PETR4", "institution": "Y", "type": "STOCK", "value": 50, "return_amount": 0},
        ]
        curr = [{"id": "a1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 110, "return_amount": 15}]
        result = self.diff_assets(prev, curr)
        self.assertEqual(len(result["removed"]), 1)
        self.assertEqual(result["removed"][0]["name"], "PETR4")

    def test_fuzzy_match_by_name_when_id_changes(self):
        prev = [{"id": "old1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 100, "return_amount": 5}]
        curr = [{"id": "new1", "name": "CDB", "institution": "X", "type": "FIXED_INCOME", "value": 110, "return_amount": 15}]
        result = self.diff_assets(prev, curr)
        self.assertEqual(len(result["changed"]), 1, "Should match by (institution, name) when id changes")
        self.assertAlmostEqual(result["changed"][0]["value_delta"], 10)

    def test_empty_both_sides(self):
        result = self.diff_assets([], [])
        self.assertEqual(len(result["changed"]), 0)
        self.assertEqual(len(result["new"]), 0)
        self.assertEqual(len(result["removed"]), 0)


if __name__ == "__main__":
    unittest.main()