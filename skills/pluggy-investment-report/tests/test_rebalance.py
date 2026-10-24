import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import rebalance

TODAY = date(2026, 10, 13)


def inv(id_, value, **extra):
    return {"id": id_, "name": id_, "institution": "Corretora", "type": "FIXED_INCOME", "value": value, **extra}


def by_cat(plan):
    return {a["category"]: a for a in plan["actions"]}


class PlanTests(unittest.TestCase):
    CUR = {"Renda Fixa": 800.0, "Ações": 100.0, "ETF": 100.0}
    TGT = {"Renda Fixa": 60, "Ações": 20, "ETF": 20}

    def test_no_targets_or_empty_wallet(self):
        self.assertIsNone(rebalance.plan_rebalance(self.CUR, {}))
        self.assertIsNone(rebalance.plan_rebalance({}, self.TGT))

    def test_deposit_only_never_sells_and_goes_where_needed(self):
        plan = rebalance.plan_rebalance(self.CUR, self.TGT, aporte=500)
        acts = by_cat(plan)
        self.assertTrue(all(a["action"] == "comprar" for a in plan["actions"]))
        # Total becomes 1500: targets are RF 900, Ações 300, ETF 300, so the needs (100/200/200) use the deposit exactly.
        self.assertEqual({c: round(a["amount"]) for c, a in acts.items()}, {"Renda Fixa": 100, "Ações": 200, "ETF": 200})
        self.assertAlmostEqual(sum(a["amount"] for a in plan["actions"]), 500, places=1)

    def test_deposit_never_exceeds_aporte_when_gaps_are_larger(self):
        plan = rebalance.plan_rebalance({"Renda Fixa": 100.0, "Ações": 0.0}, {"Renda Fixa": 20, "Ações": 80}, aporte=100)
        self.assertAlmostEqual(sum(a["amount"] for a in plan["actions"]), 100, places=1)
        self.assertEqual([a["category"] for a in plan["actions"]], ["Ações"])

    def test_deposit_smaller_than_gap_is_split_proportionally_to_need(self):
        plan = rebalance.plan_rebalance({"A": 900.0, "B": 100.0}, {"A": 50, "B": 50}, aporte=100)
        self.assertEqual(by_cat(plan)["B"]["amount"], 100)
        self.assertNotIn("A", by_cat(plan))

    def test_remainder_after_reaching_targets_splits_by_target_weight(self):
        plan = rebalance.plan_rebalance({"A": 500.0, "B": 500.0}, {"A": 50, "B": 50}, aporte=200)
        self.assertEqual({a["category"]: a["amount"] for a in plan["actions"]}, {"A": 100, "B": 100})

    def test_zero_aporte_without_sell_has_no_actions_but_reports_minimum_deposit(self):
        plan = rebalance.plan_rebalance(self.CUR, self.TGT)
        self.assertEqual(plan["actions"], [])
        # Renda Fixa 800 must become 60% => total 1333.33, so 333.33 more is needed.
        self.assertAlmostEqual(plan["min_aporte_no_sell"], 800 / 0.6 - 1000, places=2)

    def test_blocked_class_with_zero_target_is_noted(self):
        plan = rebalance.plan_rebalance({"A": 500.0, "Outros": 500.0}, {"A": 100}, aporte=100)
        self.assertTrue(any("Outros" in n for n in plan["notes"]))

    def test_allow_sell_moves_out_of_band_classes(self):
        plan = rebalance.plan_rebalance(self.CUR, self.TGT, allow_sell=True)
        acts = by_cat(plan)
        self.assertEqual(acts["Renda Fixa"]["action"], "vender")
        self.assertAlmostEqual(acts["Renda Fixa"]["amount"], 200, places=1)
        self.assertEqual(acts["Ações"]["action"], "comprar")
        self.assertTrue(any("IR" in n for n in plan["notes"]))

    def test_tolerance_band_suppresses_small_moves(self):
        plan = rebalance.plan_rebalance({"A": 51.0, "B": 49.0}, {"A": 50, "B": 50}, allow_sell=True, tolerance=2)
        self.assertEqual(plan["actions"], [])

    def test_sell_plan_never_buys_more_than_funds(self):
        plan = rebalance.plan_rebalance({"A": 700.0, "B": 200.0, "C": 100.0}, {"A": 50, "B": 25, "C": 25},
                                        allow_sell=True, tolerance=0)
        buys = sum(a["amount"] for a in plan["actions"] if a["action"] == "comprar")
        sells = sum(a["amount"] for a in plan["actions"] if a["action"] == "vender")
        self.assertLessEqual(buys, sells + 0.02)

    def test_new_money_in_empty_class(self):
        plan = rebalance.plan_rebalance({}, {"A": 100}, aporte=1000)
        self.assertEqual(by_cat(plan)["A"]["amount"], 1000)


class AlertTests(unittest.TestCase):
    def test_fgc_limit_is_per_issuer_not_per_broker(self):
        invs = [inv("1", 200_000, subtype="CDB", issuer="Banco X"), inv("2", 100_000, subtype="LCI", issuer="Banco X"),
                inv("3", 210_000, subtype="CDB", issuer="Banco Y"), inv("4", 90_000, subtype="CDB", issuer="Banco Z"),
                inv("5", 900_000, subtype="TREASURY", issuer="Tesouro"), inv("6", 10, subtype="CDB")]
        alerts = rebalance.build_alerts(invs, TODAY)["alerts"]
        fgc = [a for a in alerts if a["kind"] == "fgc"]
        self.assertTrue(any("Banco X" in a["message"] and a["severity"] == "alto" for a in fgc))
        self.assertTrue(any("Banco Y" in a["message"] and a["severity"] == "atenção" for a in fgc))
        self.assertFalse(any("Banco Z" in a["message"] for a in fgc))
        self.assertFalse(any("Tesouro" in a["message"] and a["kind"] == "fgc" for a in fgc))
        self.assertTrue(any("sem emissor" in a["message"] for a in fgc))

    def test_concentration_ignores_sovereign(self):
        treasury = {**inv("b", 50, subtype="TREASURY", issuer="Tesouro Nacional"), "type": "TREASURY"}
        invs = [inv("a", 50, issuer="Banco X", subtype="CDB"), treasury]
        alerts = [a["message"] for a in rebalance.build_alerts(invs, TODAY)["alerts"] if a["kind"] == "concentracao"]
        self.assertTrue(any("Banco X" in m for m in alerts))
        self.assertFalse(any("Tesouro" in m or m.startswith("b ") for m in alerts))

    def test_thresholds_are_configurable(self):
        invs = [inv("a", 30), inv("b", 70)]
        none = rebalance.build_alerts(invs, TODAY, max_issuer_pct=100, max_asset_pct=100)["alerts"]
        self.assertEqual([a for a in none if a["kind"] == "concentracao"], [])
        some = rebalance.build_alerts(invs, TODAY, max_asset_pct=50)["alerts"]
        self.assertEqual(len([a for a in some if a["kind"] == "concentracao"]), 1)

    def test_indexers(self):
        invs = [inv("a", 60, rate_type="CDI"), inv("b", 20, rate_type="IPCA"), inv("c", 10, fixed_annual_rate=12.0),
                inv("d", 10), inv("e", 500, type="EQUITY")]
        rows = {r["indexer"]: r for r in rebalance.build_alerts(invs, TODAY)["indexers"]}
        self.assertEqual(set(rows), {"CDI", "IPCA+", "Pré-fixado", "Não informado"})
        self.assertAlmostEqual(rows["CDI"]["pct"], 60.0)

    def test_maturity_buckets(self):
        invs = [inv("past", 1, maturity_date="2026-10-01T00:00:00.000Z"), inv("soon", 2, maturity_date="2026-10-20"),
                inv("mid", 3, maturity_date="2026-12-01"), inv("far", 4, maturity_date="2030-01-01"),
                inv("none", 5), inv("bad", 6, maturity_date="not-a-date")]
        result = rebalance.build_alerts(invs, TODAY)
        m = result["maturities"]
        self.assertEqual([x["name"] for x in m["overdue"]], ["past"])
        self.assertEqual([x["name"] for x in m["next_30"]], ["soon"])
        self.assertEqual([x["name"] for x in m["next_90"]], ["mid"])
        kinds = {a["kind"] for a in result["alerts"]}
        self.assertIn("vencimento", kinds)

    def test_empty_portfolio(self):
        result = rebalance.build_alerts([], TODAY)
        self.assertEqual(result["alerts"], [])


class RenderAndCliTests(unittest.TestCase):
    def test_render_with_and_without_plan(self):
        invs = [inv("a", 800, subtype="CDB", issuer="Banco X", maturity_date="2026-10-20"), inv("b", 200, type="ETF")]
        full = rebalance.render(rebalance.analyze(invs, {"Renda Fixa": 60, "ETF": 40}, aporte=100, today=TODAY))
        for needle in ("Movimentações sugeridas", "somente aporte", "Aporte mínimo", "Vencimentos", "não constituem recomendação"):
            self.assertIn(needle, full)
        bare = rebalance.render(rebalance.analyze(invs, {}, today=TODAY))
        self.assertIn("Sem metas", bare)
        self.assertIn("Renda fixa por indexador", bare)

    def test_no_actions_message_explains_how_to_get_one(self):
        text = rebalance.render(rebalance.analyze([inv("a", 800), inv("b", 200, type="ETF")], {"Renda Fixa": 60, "ETF": 40}, today=TODAY))
        self.assertIn("--aporte", text)

    def test_cli_writes_json_and_validates_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "in.json", Path(tmp) / "reb.json"
            source.write_text(json.dumps([inv("a", 800), inv("b", 200, type="ETF")]))
            with patch.object(rebalance, "load_targets", return_value={"Renda Fixa": 60, "ETF": 40}), patch("builtins.print"):
                self.assertEqual(rebalance.main(["r", str(source), "--aporte", "300", "--json", str(out)]), 0)
            data = json.loads(out.read_text())
            self.assertEqual(data["plan"]["actions"][0]["category"], "ETF")
            with patch("sys.stderr"):
                self.assertEqual(rebalance.main(["r", str(source), "--aporte", "-1"]), 2)
                source.write_text("{}")
                self.assertEqual(rebalance.main(["r", str(source)]), 1)


if __name__ == "__main__":
    unittest.main()
