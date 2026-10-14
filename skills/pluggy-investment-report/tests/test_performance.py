import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import performance
import snapshot_diff

T1 = datetime(2026, 10, 1, 12, 0).astimezone()
T0 = T1 - timedelta(days=100)


def inv(id_, value, amount=None, type_="FIXED_INCOME", name=None, **extra):
    return {"id": id_, "name": name or id_, "institution": "Banco", "type": type_, "value": value,
            "amount": amount, **extra}


def baseline(invs, ts=T0):
    return {"timestamp": ts.isoformat(), "totals": {}, "investments": invs}


class DietzTests(unittest.TestCase):
    def test_no_flow_is_simple_return(self):
        r = performance.dietz([{"v0": 1000, "v1": 1100, "flows": []}], T0, T1)
        self.assertAlmostEqual(r["rate"], 10.0)
        self.assertAlmostEqual(r["profit"], 100)

    def test_deposit_is_not_counted_as_return(self):
        # 1000 -> 1210 with a 100 deposit in the middle: profit is 110, not 210.
        mid = T0 + (T1 - T0) / 2
        r = performance.dietz([{"v0": 1000, "v1": 1210, "flows": [(mid, 100)]}], T0, T1)
        self.assertAlmostEqual(r["profit"], 110)
        self.assertAlmostEqual(r["rate"], 110 / 1050 * 100)

    def test_undated_flow_is_weighted_mid_period(self):
        r = performance.dietz([{"v0": 1000, "v1": 1210, "flows": [(None, 100)]}], T0, T1)
        self.assertAlmostEqual(r["rate"], 110 / 1050 * 100)

    def test_withdrawal(self):
        r = performance.dietz([{"v0": 1000, "v1": 560, "flows": [(None, -500)]}], T0, T1)
        self.assertAlmostEqual(r["profit"], 60)

    def test_annualization_only_for_long_periods(self):
        long = performance.dietz([{"v0": 100, "v1": 110, "flows": []}], T0, T1)
        self.assertAlmostEqual(long["annualized_rate"], (1.1 ** (365 / 100) - 1) * 100)
        short = performance.dietz([{"v0": 100, "v1": 110, "flows": []}], T1 - timedelta(days=10), T1)
        self.assertIsNone(short["annualized_rate"])

    def test_zero_base_has_no_rate(self):
        self.assertIsNone(performance.dietz([{"v0": 0, "v1": 0, "flows": []}], T0, T1)["rate"])


class FlowTests(unittest.TestCase):
    def test_transactions_inside_period_only(self):
        txs = [{"date": (T0 - timedelta(days=5)).isoformat(), "type": "BUY", "amount": 999},
               {"date": (T0 + timedelta(days=10)).isoformat(), "type": "BUY", "amount": 100},
               {"date": (T0 + timedelta(days=20)).isoformat(), "type": "SELL", "amount": 30},
               {"date": (T0 + timedelta(days=30)).isoformat(), "type": "AMORTIZATION", "amount": 20},
               {"date": (T0 + timedelta(days=40)).isoformat(), "type": "INTEREST", "amount": 5},
               {"date": (T0 + timedelta(days=50)).isoformat(), "type": "TAX", "amount": 1},
               {"date": "garbage", "type": "BUY", "amount": 77}]
        flows, source = performance.asset_flows(inv("a", 1), inv("a", 1, transactions=txs), T0, T1)
        self.assertEqual(source, "transactions")
        self.assertEqual(sorted(a for _, a in flows), [-30, -20, 100])

    def test_known_empty_transactions_mean_no_flow(self):
        flows, source = performance.asset_flows(inv("a", 1, 100), inv("a", 1, 500, transactions=[]), T0, T1)
        self.assertEqual((flows, source), ([], "transactions"))

    def test_estimated_from_cost_basis_change(self):
        flows, source = performance.asset_flows(inv("a", 1, 100), inv("a", 1, 160), T0, T1)
        self.assertEqual((flows, source), ([(None, 60)], "estimated"))
        self.assertEqual(performance.asset_flows(inv("a", 1, 100), inv("a", 1, 100), T0, T1), ([], "estimated"))

    def test_unknown_cost_is_assumed_all_return(self):
        self.assertEqual(performance.asset_flows(inv("a", 1), inv("a", 1, 100), T0, T1), ([], "assumed"))


class AnalyzeTests(unittest.TestCase):
    def test_no_baseline(self):
        result = performance.analyze(None, [inv("a", 100, 90)], T1)
        self.assertIn("error", result)
        self.assertEqual(result["since_inception"]["known_count"], 1)
        self.assertIn("Sem histórico", performance.render(result))

    def test_reconciliation_and_exclusion_of_new_and_removed(self):
        base = baseline([inv("a", 1000, 1000), inv("gone", 500, 500)])
        curr = [inv("a", 1210, 1100), inv("new", 300, 300, type_="ETF")]
        result = performance.analyze(base, curr, T1)
        w = result["wallet_change"]
        self.assertAlmostEqual(w["v1"] - w["v0"], w["return_effect"] + w["net_flow"] + w["new_assets"] + w["removed_assets"])
        self.assertAlmostEqual(result["portfolio"]["profit"], 110)  # 1210-1000-100 deposit
        self.assertEqual(result["flow_sources"]["estimated"], 1)
        self.assertEqual([n["name"] for n in result["new"]], ["new"])
        self.assertEqual([n["name"] for n in result["removed"]], ["gone"])
        self.assertTrue(any("novos/removidos" in c for c in result["caveats"]))

    def test_groups_best_worst_and_caveats(self):
        base = baseline([inv(str(i), 1000, 1000, type_="FIXED_INCOME" if i % 2 else "EQUITY") for i in range(8)])
        curr = [inv(str(i), 1000 + i * 10, 1000, type_="FIXED_INCOME" if i % 2 else "EQUITY") for i in range(8)]
        result = performance.analyze(base, curr, T1)
        self.assertEqual({r["name"] for r in result["by_category"]}, {"Renda Fixa", "Ações"})
        self.assertEqual(result["best"][0]["name"], "7")
        self.assertEqual(result["worst"][0]["name"], "0")
        text = performance.render(result)
        self.assertIn("Melhores e piores", text)
        self.assertIn("líquidos de impostos", text)

    def test_short_period_and_assumed_cost_caveats(self):
        result = performance.analyze(baseline([inv("a", 100)], T1 - timedelta(days=2)), [inv("a", 101)], T1)
        joined = " ".join(result["caveats"])
        self.assertIn("Período curto", joined)
        self.assertIn("sem custo informado", joined)

    def test_transactions_drive_flows_in_analysis(self):
        txs = [{"date": (T0 + timedelta(days=50)).isoformat(), "type": "BUY", "amount": 100}]
        result = performance.analyze(baseline([inv("a", 1000, 1000)]), [inv("a", 1110, 1100, transactions=txs)], T1)
        self.assertEqual(result["flow_sources"]["transactions"], 1)
        self.assertAlmostEqual(result["portfolio"]["profit"], 10)

    def test_baseline_note_is_surfaced(self):
        result = performance.analyze(baseline([inv("a", 100, 100)]), [inv("a", 100, 100)], T1, note="Histórico começa em 01/01/2026")
        self.assertIn("Histórico começa", " ".join(result["caveats"]))


class BenchmarkTests(unittest.TestCase):
    def fake_fetch(self, code, start, end):
        if code == performance.CDI_SERIES:
            return [(start + timedelta(days=i), 0.05) for i in range(10)]
        return [(date(2026, 7, 1), 0.2), (date(2026, 8, 1), 0.4), (date(2026, 9, 1), 0.5), (date(2026, 10, 1), 0.9)]

    def test_accumulation(self):
        b = performance.benchmarks_for(T0, T1, self.fake_fetch)
        self.assertAlmostEqual(b["cdi_pct"], ((1.0005 ** 10) - 1) * 100)
        # Baseline 2026-06-23, period end 2026-10-01: July..September are full months; October is not.
        self.assertEqual(b["ipca_months"], 3)
        self.assertAlmostEqual(b["ipca_pct"], (1.002 * 1.004 * 1.005 - 1) * 100)

    def test_failures_never_raise(self):
        def broken(*a):
            raise performance.BenchmarkError("Banco Central indisponível")
        b = performance.benchmarks_for(T0, T1, broken)
        self.assertIsNone(b["cdi_pct"])
        self.assertIn("Banco Central indisponível", b["notes"][0])

    def test_vs_benchmarks(self):
        r = performance.vs_benchmarks(12.0, {"cdi_pct": 10.0, "ipca_pct": 2.0})
        self.assertAlmostEqual(r["pct_of_cdi"], 120.0)
        self.assertAlmostEqual(r["excess_over_cdi"], 2.0)
        self.assertAlmostEqual(r["real_rate"], (1.12 / 1.02 - 1) * 100)
        self.assertIsNone(performance.vs_benchmarks(None, {"cdi_pct": 1})["pct_of_cdi"])
        self.assertIsNone(performance.vs_benchmarks(5, {"cdi_pct": 0, "ipca_pct": None})["pct_of_cdi"])

    def test_benchmarks_flow_into_analysis_and_render(self):
        result = performance.analyze(baseline([inv("a", 1000, 1000)]), [inv("a", 1100, 1000)], T1, self.fake_fetch)
        self.assertIsNotNone(result["portfolio"]["pct_of_cdi"])
        self.assertIn("% do CDI", performance.render(result))

    def test_cache_hit_avoids_network_and_miss_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            start, end = date(2026, 1, 1), date(2026, 1, 3)
            (cache / "bcb_12_20260101_20260103.json").write_text(json.dumps([["2026-01-02", 0.05]]))
            with patch.object(performance, "build_opener", side_effect=AssertionError("network used")):
                self.assertEqual(performance.fetch_sgs(12, start, end, cache), [(date(2026, 1, 2), 0.05)])
            with patch.object(performance, "build_opener") as opener:
                opener.return_value.open.side_effect = OSError("down")
                with self.assertRaises(performance.BenchmarkError):
                    performance.fetch_sgs(433, start, end, cache)

    def test_fetch_parses_and_caches(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return json.dumps([{"data": "02/01/2026", "valor": "0.055131"}]).encode()
        with tempfile.TemporaryDirectory() as tmp, patch.object(performance, "build_opener") as opener:
            opener.return_value.open.return_value = Response()
            points = performance.fetch_sgs(12, date(2026, 1, 1), date(2026, 1, 3), Path(tmp))
            self.assertEqual(points, [(date(2026, 1, 2), 0.055131)])
            self.assertTrue(list(Path(tmp).glob("bcb_12_*.json")))


class CliTests(unittest.TestCase):
    def test_main_reads_history_and_does_not_write_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snaps = root / "snapshots"
            snaps.mkdir()
            moment = datetime.now().astimezone() - timedelta(days=40)
            (snaps / (moment.strftime("%Y-%m-%d_%H%M%S_%f") + ".json")).write_text(
                json.dumps(baseline([inv("a", 1000, 1000)], moment)))
            source, out = root / "in.json", root / "perf.json"
            source.write_text(json.dumps([inv("a", 1100, 1000)]))
            with patch.object(snapshot_diff, "SNAPSHOT_DIR", snaps), patch("builtins.print") as printed:
                self.assertEqual(performance.main(["performance.py", str(source), "--since", "30d", "--json", str(out)]), 0)
            self.assertEqual(len(list(snaps.glob("*.json"))), 1)
            self.assertAlmostEqual(json.loads(out.read_text())["portfolio"]["rate"], 10.0)
            self.assertIn("Rentabilidade", printed.call_args[0][0])

    def test_main_rejects_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp, patch("sys.stderr"):
            bad = Path(tmp) / "bad.json"
            bad.write_text('{"x": 1}')
            self.assertEqual(performance.main(["performance.py", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
