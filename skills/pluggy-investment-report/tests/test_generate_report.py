import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

SAMPLE_INVESTMENTS = [
    {
        "name": "Tesouro IPCA+ 2029",
        "institution": "Nubank",
        "type": "FIXED_INCOME",
        "amount": 5000.00,
        "value": 5430.50,
        "return_amount": 430.50,
        "return_rate": 8.61,
        "maturity_date": "2029-05-15",
    },
    {
        "name": "PETR4",
        "institution": "XP Investimentos",
        "type": "STOCK",
        "amount": 2000.00,
        "value": 1850.00,
        "return_amount": -150.00,
        "return_rate": -7.50,
        "maturity_date": None,
    },
]


class TestFormatHelpers(unittest.TestCase):
    def setUp(self):
        from generate_report import format_currency, format_percentage, get_type_label
        self.format_currency = format_currency
        self.format_percentage = format_percentage
        self.get_type_label = get_type_label

    def test_format_currency_integer(self):
        self.assertEqual(self.format_currency(7000.00), "R$ 7.000,00")

    def test_format_currency_decimals(self):
        self.assertEqual(self.format_currency(5430.50), "R$ 5.430,50")

    def test_format_currency_negative(self):
        self.assertEqual(self.format_currency(-150.00), "-R$ 150,00")

    def test_format_currency_zero(self):
        self.assertEqual(self.format_currency(0), "R$ 0,00")

    def test_format_percentage_positive(self):
        self.assertEqual(self.format_percentage(8.61), "8,61%")

    def test_format_percentage_negative(self):
        self.assertEqual(self.format_percentage(-7.50), "-7,50%")

    def test_get_type_label_fixed_income(self):
        self.assertEqual(self.get_type_label("FIXED_INCOME"), "Renda Fixa")

    def test_get_type_label_stock(self):
        self.assertEqual(self.get_type_label("STOCK"), "Ações")

    def test_get_type_label_fund(self):
        self.assertEqual(self.get_type_label("FUND"), "Fundos")

    def test_get_type_label_mutual_fund(self):
        self.assertEqual(self.get_type_label("MUTUAL_FUND"), "Fundos")

    def test_get_type_label_etf(self):
        self.assertEqual(self.get_type_label("ETF"), "ETF")

    def test_get_type_label_unknown_passthrough(self):
        self.assertEqual(self.get_type_label("CUSTOM_TYPE"), "CUSTOM_TYPE")


class TestGenerateHTML(unittest.TestCase):
    def setUp(self):
        from generate_report import generate_html
        self.generate_html = generate_html
        self.tmpdir = tempfile.mkdtemp()
        self.output = os.path.join(self.tmpdir, "report.html")

    def _html(self, investments=None):
        inv = investments if investments is not None else SAMPLE_INVESTMENTS
        self.generate_html(inv, self.output)
        with open(self.output, encoding="utf-8") as f:
            return f.read()

    def test_creates_file(self):
        self._html()
        self.assertTrue(os.path.exists(self.output))

    def test_total_invested_in_output(self):
        # 5430.50 + 1850.00 = 7280.50 (current value, not original invested amount)
        html = self._html()
        self.assertIn("7.280,50", html)

    def test_total_current_value_in_output(self):
        # 5430.50 + 1850.00 = 7280.50
        html = self._html()
        self.assertIn("7.280,50", html)

    def test_asset_names_in_output(self):
        html = self._html()
        self.assertIn("Tesouro IPCA+ 2029", html)
        self.assertIn("PETR4", html)

    def test_institution_names_in_output(self):
        html = self._html()
        self.assertIn("Nubank", html)
        self.assertIn("XP Investimentos", html)

    def test_chartjs_loaded(self):
        html = self._html()
        self.assertIn("chart.js", html.lower())

    def test_print_button_present(self):
        html = self._html()
        self.assertIn("window.print()", html)

    def test_media_print_css(self):
        html = self._html()
        self.assertIn("@media print", html)

    def test_unchanged_assets_show_neutral_delta_when_no_diff(self):
        html = self._html()
        self.assertIn('class="number neutral"', html)

    def test_chartjs_onerror_fallback_present(self):
        html = self._html()
        self.assertIn('chart-error', html)
        self.assertIn('onerror=', html)

    def test_empty_investments_generates_file(self):
        html = self._html([])
        self.assertIn("R$ 0,00", html)
        self.assertTrue(os.path.exists(self.output))

    def test_null_maturity_date_renders_dash(self):
        html = self._html()
        # PETR4 has maturity_date=None, should show "-"
        self.assertIn("-</td>", html)

    def test_pie_chart_data_injected(self):
        html = self._html()
        self.assertIn("Renda Fixa", html)
        self.assertIn("doughnut", html)

    def test_line_chart_data_injected(self):
        html = self._html()
        self.assertIn("lineChart", html)

    def test_sortable_table_script(self):
        html = self._html()
        self.assertIn("sortTable", html)

    def test_returns_output_path(self):
        from generate_report import generate_html
        result = generate_html(SAMPLE_INVESTMENTS, self.output)
        self.assertEqual(result, self.output)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_cli_reads_json_file_and_generates_html(self):
        json_path = os.path.join(self.tmpdir, "investments.json")
        output_path = os.path.join(self.tmpdir, "out.html")
        with open(json_path, "w") as f:
            json.dump(SAMPLE_INVESTMENTS, f)

        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script, json_path, output_path],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_path))

    def test_cli_accepts_list_wrapped_in_dict(self):
        json_path = os.path.join(self.tmpdir, "wrapped.json")
        output_path = os.path.join(self.tmpdir, "out2.html")
        with open(json_path, "w") as f:
            json.dump({"investments": SAMPLE_INVESTMENTS}, f)

        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script, json_path, output_path],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_path))

    def test_cli_exits_nonzero_without_args(self):
        import subprocess
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'generate_report.py')
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)


class TestLoadTargets(unittest.TestCase):
    def setUp(self):
        import generate_report
        self.load_targets = generate_report.load_targets
        self.module = generate_report

    def test_returns_empty_dict_when_file_missing(self):
        original = self.module.TARGETS_PATH
        try:
            self.module.TARGETS_PATH = "/nonexistent/path/targets.json"
            result = self.load_targets()
            self.assertEqual(result, {})
        finally:
            self.module.TARGETS_PATH = original

    def test_returns_data_when_file_exists(self):
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"Renda Fixa": 70, "Ações": 30}, f)
            tmp = f.name
        original = self.module.TARGETS_PATH
        try:
            self.module.TARGETS_PATH = tmp
            result = self.load_targets()
            self.assertEqual(result, {"Renda Fixa": 70, "Ações": 30})
        finally:
            self.module.TARGETS_PATH = original
            pathlib.Path(tmp).unlink(missing_ok=True)

    def test_returns_empty_dict_on_invalid_json(self):
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not json")
            tmp = f.name
        original = self.module.TARGETS_PATH
        try:
            self.module.TARGETS_PATH = tmp
            result = self.load_targets()
            self.assertEqual(result, {})
        finally:
            self.module.TARGETS_PATH = original
            pathlib.Path(tmp).unlink(missing_ok=True)


class TestBuildAllocationAnalysis(unittest.TestCase):
    def setUp(self):
        from generate_report import build_allocation_analysis
        self.fn = build_allocation_analysis

    def test_returns_none_when_targets_empty(self):
        result = self.fn({"Renda Fixa": 76}, {}, 100)
        self.assertIsNone(result)

    def test_returns_none_when_total_current_is_zero(self):
        result = self.fn({"Renda Fixa": 0}, {"Renda Fixa": 70}, 0)
        self.assertIsNone(result)

    def test_computes_deviation_correctly(self):
        # 76 out of 100 total → 76% actual; target 70% → deviation +6
        result = self.fn({"Renda Fixa": 76, "ETF": 8, "Outros": 16},
                         {"Renda Fixa": 70, "ETF": 15, "Outros": 15}, 100)
        rows = {r["category"]: r for r in result["rows"]}
        self.assertAlmostEqual(rows["Renda Fixa"]["actual_pct"], 76.0)
        self.assertAlmostEqual(rows["Renda Fixa"]["deviation"], 6.0)
        self.assertAlmostEqual(rows["ETF"]["deviation"], -7.0)

    def test_recommendations_only_for_deviation_gte_2(self):
        # Outros: 16% actual, 15% target → +1 → no recommendation
        result = self.fn({"Renda Fixa": 76, "ETF": 8, "Outros": 16},
                         {"Renda Fixa": 70, "ETF": 15, "Outros": 15}, 100)
        rec_cats = " ".join(result["recommendations"])
        self.assertIn("Renda Fixa", rec_cats)
        self.assertIn("ETF", rec_cats)
        self.assertNotIn("Outros", rec_cats)

    def test_overweight_recommendation_says_reduzir(self):
        result = self.fn({"Renda Fixa": 76}, {"Renda Fixa": 70}, 76)
        self.assertTrue(any("Reduzir" in r for r in result["recommendations"]))

    def test_underweight_recommendation_says_comprar(self):
        result = self.fn({"ETF": 8}, {"ETF": 15}, 100)
        self.assertTrue(any("Comprar" in r for r in result["recommendations"]))

    def test_imbalance_is_category_with_largest_abs_deviation(self):
        # Renda Fixa: +6, ETF: -7 → ETF has largest absolute deviation
        result = self.fn({"Renda Fixa": 76, "ETF": 8, "Outros": 16},
                         {"Renda Fixa": 70, "ETF": 15, "Outros": 15}, 100)
        self.assertEqual(result["imbalance"]["category"], "ETF")
        self.assertAlmostEqual(result["imbalance"]["pct"], -7.0)

    def test_categories_missing_from_portfolio_default_to_zero(self):
        # "Ações" not in type_totals → actual 0%, target 10% → deviation -10
        result = self.fn({}, {"Ações": 10}, 100)
        rows = {r["category"]: r for r in result["rows"]}
        self.assertAlmostEqual(rows["Ações"]["actual_pct"], 0.0)
        self.assertAlmostEqual(rows["Ações"]["deviation"], -10.0)


class TestAllocationHTML(unittest.TestCase):
    def setUp(self):
        from generate_report import generate_html
        self.generate_html = generate_html
        self.tmpdir = tempfile.mkdtemp()
        self.output = os.path.join(self.tmpdir, "report.html")
        self.investments = [
            {"name": "CDB", "type": "FIXED_INCOME", "value": 76,
             "institution": "Banco", "amount": 70, "maturity_date": None},
            {"name": "Ações XP", "type": "EQUITY", "value": 12,
             "institution": "XP", "amount": 10, "maturity_date": None},
            {"name": "BOVA11", "type": "ETF", "value": 8,
             "institution": "XP", "amount": 10, "maturity_date": None},
            {"name": "Fundo A", "type": "FUND", "value": 4,
             "institution": "Banco", "amount": 5, "maturity_date": None},
        ]

    def _html(self, targets=None):
        self.generate_html(self.investments, self.output, targets=targets or {})
        with open(self.output, encoding="utf-8") as f:
            return f.read()

    def test_targets_panel_always_present(self):
        html = self._html()
        self.assertIn("targetsPanel", html)
        self.assertIn("Metas de Alocação", html)

    def test_toggle_button_present(self):
        html = self._html()
        self.assertIn("toggleTargets()", html)

    def test_save_button_triggers_download(self):
        html = self._html()
        self.assertIn("saveTargets()", html)
        self.assertIn("allocation_targets.json", html)

    def test_inputs_generated_for_each_portfolio_category(self):
        html = self._html()
        self.assertIn('data-category="Renda Fixa"', html)
        self.assertIn('data-category="Ações"', html)
        self.assertIn('data-category="ETF"', html)
        self.assertIn('data-category="Fundos"', html)

    def test_inputs_include_categories_without_holdings(self):
        html = self._html()
        self.assertIn('data-category="FIIs"', html)
        self.assertIn('data-category="Tesouro Direto"', html)
        self.assertIn('data-category="Outros"', html)

    def test_targets_prefilled_when_provided(self):
        html = self._html(targets={"Renda Fixa": 70, "Ações": 10, "ETF": 15, "Fundos": 5})
        self.assertIn('value="70"', html)
        self.assertIn('value="15"', html)

    def test_no_analysis_section_without_targets(self):
        html = self._html()
        self.assertNotIn("Análise de Alocação", html)

    def test_analysis_section_present_with_targets(self):
        html = self._html(targets={"Renda Fixa": 70, "Ações": 10, "ETF": 15, "Fundos": 5})
        self.assertIn("Análise de Alocação", html)

    def test_analysis_shows_recommendations(self):
        html = self._html(targets={"Renda Fixa": 70, "Ações": 10, "ETF": 15, "Fundos": 5})
        # Renda Fixa 76% actual vs 70% target → Reduzir
        self.assertIn("Reduzir", html)
        # ETF 8% actual vs 15% target → Comprar
        self.assertIn("Comprar", html)

    def test_analysis_shows_imbalance_message(self):
        html = self._html(targets={"Renda Fixa": 70, "Ações": 10, "ETF": 15, "Fundos": 5})
        self.assertIn("desbalanceada", html)

    def test_category_label_is_html_escaped(self):
        html = self._html(targets={"<b>Renda</b>": 100})
        self.assertNotIn("<b>Renda</b>", html)
        self.assertIn("&lt;b&gt;Renda&lt;/b&gt;", html)


if __name__ == "__main__":
    unittest.main()
