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
        # 5000 + 2000 = 7000
        html = self._html()
        self.assertIn("7.000,00", html)

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

    def test_positive_return_class(self):
        html = self._html()
        self.assertIn('class="number positive"', html)

    def test_negative_return_class(self):
        html = self._html()
        self.assertIn('class="number negative"', html)

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

    def test_bar_chart_data_injected(self):
        html = self._html()
        self.assertIn("barChart", html)

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


if __name__ == "__main__":
    unittest.main()
