import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import collect_investments as ci
import generate_report
import report_model
import snapshot_diff
from collect_investments import ApiError, collect, normalize
from summary import summary, summary_data


def api(investments, transactions=None, fail_transactions_for=()):
    calls = []

    def request(endpoint, api_key=None, payload=None):
        calls.append(endpoint)
        if endpoint == '/auth':
            return {'apiKey': 'k'}
        if endpoint == '/items/item':
            return {'id': 'item', 'status': 'UPDATED', 'connector': {'name': 'Corretora'}}
        if endpoint.startswith('/investments?'):
            return {'total': len(investments), 'results': investments}
        for inv in investments:
            if endpoint.startswith(f"/investments/{inv['id']}/transactions"):
                if inv['id'] in fail_transactions_for:
                    raise ApiError('Pluggy returned HTTP 404')
                return {'total': 1, 'totalPages': 1, 'page': 1, 'results': (transactions or {}).get(inv['id'], [])}
        raise AssertionError(endpoint)
    request.calls = calls
    return request


RAW = {'id': 'a', 'name': 'CDB X', 'balance': 1100, 'amountOriginal': 1000, 'type': 'FIXED_INCOME', 'subtype': 'CDB',
       'rateType': 'CDI', 'rate': 110, 'fixedAnnualRate': 1.5, 'issuer': 'Banco X', 'issueDate': '2025-01-01T00:00:00.000Z',
       'quantity': 2, 'date': '2026-10-12T00:00:00.000Z', 'lastTwelveMonthsRate': 11.2, 'status': 'ACTIVE'}


class CollectorFieldTests(unittest.TestCase):
    def test_new_fields_are_normalized(self):
        row = normalize(RAW, 'Corretora')
        self.assertEqual((row['subtype'], row['rate_type'], row['rate'], row['fixed_annual_rate']), ('CDB', 'CDI', 110, 1.5))
        self.assertEqual((row['issuer'], row['issue_date'], row['quantity'], row['as_of']),
                         ('Banco X', '2025-01-01T00:00:00.000Z', 2, '2026-10-12T00:00:00.000Z'))
        self.assertEqual((row['last_twelve_months_rate'], row['status']), (11.2, 'ACTIVE'))
        report_model.investments_list([row])

    def test_informational_fields_never_abort_collection(self):
        row = normalize({**RAW, 'rate': 'abc', 'quantity': float('nan'), 'issuer': 42, 'rateType': None}, 'Corretora')
        self.assertIsNone(row['rate'])
        self.assertIsNone(row['quantity'])
        self.assertIsNone(row['issuer'])
        self.assertIsNone(row['rate_type'])

    def test_holding_institution_overrides_connector(self):
        self.assertEqual(normalize({**RAW, 'institution': {'name': 'BTG'}}, 'Corretora')['institution'], 'BTG')
        self.assertEqual(normalize({**RAW, 'institution': {'name': ''}}, 'Corretora')['institution'], 'Corretora')
        self.assertEqual(normalize({**RAW, 'institution': None}, 'Corretora')['institution'], 'Corretora')

    def test_transactions_are_opt_in(self):
        request = api([RAW])
        rows = collect('id', 'secret', ['item'], request)
        self.assertNotIn('transactions', rows[0])
        self.assertFalse(any('transactions' in c for c in request.calls))

    def test_transactions_collected_and_slimmed(self):
        txs = {'a': [{'tradeDate': '2026-03-01T00:00:00.000Z', 'date': '2026-03-02', 'type': 'BUY', 'amount': 100,
                      'expenses': {'other': 1}, 'description': 'private text'}]}
        rows = collect('id', 'secret', ['item'], api([RAW], txs), with_transactions=True)
        self.assertEqual(rows[0]['transactions'], [{'date': '2026-03-01T00:00:00.000Z', 'type': 'BUY', 'amount': 100}])
        report_model.investments_list(rows)

    def test_no_transactions_is_empty_list_but_failure_is_unknown_and_non_fatal(self):
        second = {**RAW, 'id': 'b', 'name': 'B'}
        warnings = []
        rows = collect('id', 'secret', ['item'], api([RAW, second], fail_transactions_for={'b'}),
                       with_transactions=True, warnings=warnings)
        by_id = {r['id']: r for r in rows}
        self.assertEqual(by_id['a']['transactions'], [])
        self.assertIsNone(by_id['b']['transactions'])
        self.assertEqual(warnings, ['b'])

    def test_malformed_transaction_marks_unknown(self):
        rows = collect('id', 'secret', ['item'], api([RAW], {'a': [{'type': 'BUY', 'amount': 1}]}), with_transactions=True)
        self.assertIsNone(rows[0]['transactions'])

    def test_transactions_paginate(self):
        pages = {1: {'totalPages': 2, 'results': [{'date': '2026-01-01', 'type': 'BUY', 'amount': 1}]},
                 2: {'totalPages': 2, 'results': [{'date': '2026-01-02', 'type': 'SELL', 'amount': 2}]}}
        def request(endpoint, api_key=None, payload=None):
            return pages[int(endpoint.split('page=')[1].split('&')[0])]
        self.assertEqual(len(ci.list_transactions(request, 'k', 'a')), 2)

    def test_validation_rejects_bad_transactions(self):
        for bad in ({'transactions': 'x'}, {'transactions': [{'date': 1, 'type': 'BUY', 'amount': 1}]},
                    {'transactions': [{'date': 'd', 'type': 'BUY', 'amount': 'x'}]}):
            with self.assertRaises(ValueError):
                report_model.investments_list([{'value': 1, **bad}])

    def test_cli_flag_and_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'o.json'
            def fake_collect(*args, with_transactions=False, warnings=None, **kw):
                self.assertTrue(with_transactions)
                warnings.append('x')
                return []
            with patch.dict(os.environ, {'PLUGGY_CLIENT_ID': 'i', 'PLUGGY_CLIENT_SECRET': 's'}), \
                    patch.object(sys, 'argv', ['c', str(out), '--with-transactions']), \
                    patch('collect_investments.collect', fake_collect), patch('sys.stderr') as err:
                self.assertEqual(ci.main(), 0)
            self.assertTrue(out.exists())
            self.assertIn('estimated', ''.join(str(c) for c in err.write.call_args_list))


class ModelCoverageTests(unittest.TestCase):
    ROWS = [{'value': 1100, 'amount': 1000}, {'value': 500, 'amount': None}, {'value': 300, 'amount': 400, 'return_amount': -100}]

    def test_partial_coverage(self):
        cov = report_model.coverage(self.ROWS)
        self.assertEqual((cov['known_count'], cov['count'], cov['complete']), (2, 3, False))
        self.assertEqual(cov['invested'], 1400)
        self.assertEqual(cov['return_amount'], 0)
        self.assertAlmostEqual(cov['value_pct'], 1400 / 1900 * 100)
        self.assertIsNone(report_model.aggregate(self.ROWS)['return_amount'])  # total stays unknown

    def test_empty_and_unknown(self):
        self.assertTrue(report_model.coverage([])['complete'])
        none = report_model.coverage([{'value': 5}])
        self.assertEqual(none['known_count'], 0)
        self.assertIsNone(none['return_rate'])

    def test_summary_shows_partial_result_and_json(self):
        text = summary(self.ROWS)
        self.assertIn('não informado', text)
        self.assertIn('Rendimento parcial', text)
        self.assertIn('2 de 3 ativos', text)
        data = summary_data(self.ROWS)
        self.assertEqual(data['coverage']['known_count'], 2)
        json.dumps(data, allow_nan=False)

    def test_recommendation_wording_has_no_double_negative(self):
        analysis = report_model.build_allocation_analysis({'ETF': 8, 'Renda Fixa': 92}, {'ETF': 15, 'Renda Fixa': 85}, 100)
        self.assertIn('↑ Comprar ETF (7% abaixo da meta)', analysis['recommendations'])
        self.assertIn('↓ Reduzir Renda Fixa (7% acima da meta)', analysis['recommendations'])

    def test_tolerance_is_configurable(self):
        args = ({'A': 53, 'B': 47}, {'A': 50, 'B': 50}, 100)
        self.assertEqual(report_model.build_allocation_analysis(*args, tolerance=5)['recommendations'], [])
        self.assertEqual(len(report_model.build_allocation_analysis(*args, tolerance=2)['recommendations']), 2)


class ReportHtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.object(snapshot_diff, 'SNAPSHOT_DIR', self.root / 'snapshots')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = self.root / 'r.html'

    def html(self, invs, **kw):
        generate_report.generate_html(invs, str(self.out), **kw)
        return self.out.read_text()

    def snap(self, minutes_ago, value):
        moment = datetime.now().astimezone() - timedelta(minutes=minutes_ago)
        path = snapshot_diff.SNAPSHOT_DIR / (moment.strftime('%Y-%m-%d_%H%M%S_%f') + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'timestamp': moment.isoformat(), 'totals': {'current': value}, 'investments': []}))
        return moment.isoformat()

    def test_cost_return_columns_and_signed_sort_keys(self):
        invs = [{'id': 'a', 'name': 'Loss', 'type': 'EQUITY', 'value': 90, 'amount': 100, 'maturity_date': '2027-02-01T00:00:00Z'},
                {'id': 'b', 'name': 'NoCost', 'type': 'EQUITY', 'value': 50, 'maturity_date': '2026-12-31T00:00:00Z'}]
        diff = {'first_run': False, 'previous_timestamp': '2026-01-01T00:00:00', 'totals': {'current': {'delta': -10}},
                'assets': {'changed': [{'id': 'a', 'value_delta': -10}], 'new': [], 'removed': []}}
        html = self.html(invs, diff=diff)
        self.assertIn('Custo ↕', html)
        self.assertIn('Rendimento ↕', html)
        self.assertIn('data-sort="-10"', html)          # a loss sorts below zero
        self.assertIn('data-sort="2027-02-01"', html)   # ISO date sorts chronologically, not by day
        self.assertIn('data-sort=""', html)             # unknown cost sorts as unknown
        self.assertIn('não informado', html)
        self.assertIn('-R$ 10,00', html)
        self.assertNotIn('replace(\'.\', \'\')', html)

    def test_summary_cards_show_partial_coverage(self):
        invs = [{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 110, 'amount': 100},
                {'id': 'b', 'name': 'B', 'type': 'ETF', 'value': 50}]
        html = self.html(invs)
        self.assertIn('Total Investido', html)
        self.assertIn('1 de 2 ativos com custo informado', html)
        self.assertIn('R$ 10,00 (10,00%)', html)

    def test_line_chart_uses_real_time_axis(self):
        self.snap(120, 100)
        html = self.html([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}])
        self.assertIn("type: 'linear'", html)
        self.assertIn('"x": ', html)

    def test_history_hides_only_the_snapshot_of_the_current_run(self):
        older, current = self.snap(120, 100), self.snap(1, 110)
        with_diff = self.html([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}], diff={'first_run': False, 'current_timestamp': current})
        self.assertIn(older, with_diff)
        self.assertEqual(with_diff.count(f'"timestamp": "{current}"'), 1)  # only in the chart series, not the history list
        without_diff = self.html([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}])
        self.assertEqual(without_diff.count(f'"timestamp": "{current}"'), 2)  # newest snapshot is no longer dropped silently

    def test_performance_and_rebalance_panels(self):
        perf = {'period': {'from': '2026-08-01T10:00:00+00:00', 'to': '2026-10-01T10:00:00+00:00', 'days': 61.0},
                'portfolio': {'rate': 2.5, 'annualized_rate': 15.9, 'profit': 250.0, 'net_flow': 100.0, 'pct_of_cdi': 110.0, 'real_rate': 1.0},
                'benchmarks': {'cdi_pct': 2.2, 'ipca_pct': 1.5}, 'caveats': ['<script>alert(1)</script>'],
                'by_category': [{'name': 'Renda Fixa', 'v1': 1000.0, 'profit': 25.0, 'rate': 2.5}]}
        reb = {'plan': {'actions': [{'category': 'ETF', 'action': 'comprar', 'amount': 300.0}], 'allow_sell': False,
                        'aporte': 300.0, 'min_aporte_no_sell': 120.5, 'notes': []},
               'indexers': [{'indexer': 'CDI', 'value': 900.0, 'pct': 90.0}],
               'maturities': {'overdue': [], 'next_30': [{'name': 'CDB <b>', 'institution': 'X', 'date': '2026-10-20', 'value': 10.0}], 'next_90': []},
               'alerts': [{'kind': 'fgc', 'severity': 'atenção', 'message': 'Banco X <i>'}]}
        html = self.html([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}], performance=perf, rebalance=reb)
        for needle in ('Rentabilidade no período', '% do CDI', 'Movimentações sugeridas', 'R$ 300,00', 'Aporte mínimo',
                       'Calendário de vencimentos', '20/10/2026', 'sev-atencao', 'recomendação de investimento'):
            self.assertIn(needle, html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('CDB <b>', html)

    def test_panels_absent_without_data_and_error_perf_is_ignored(self):
        html = self.html([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}], performance={'error': 'x', 'period': None})
        self.assertNotIn('Rentabilidade no período', html)
        self.assertNotIn('Rebalanceamento e alertas', html)

    def test_cli_accepts_extra_sections_and_survives_bad_files(self):
        source = self.root / 'in.json'
        source.write_text(json.dumps([{'id': 'a', 'name': 'A', 'type': 'ETF', 'value': 1}]))
        bad = self.root / 'bad.json'
        bad.write_text('{nope')
        with patch.object(sys, 'argv', ['g', str(source), str(self.out), '--performance', str(bad), '--rebalance', str(self.root / 'missing.json')]), \
                patch.object(generate_report, 'TARGETS_PATH', str(self.root / 'none.json')), \
                patch('builtins.print'), patch('sys.stderr'), \
                patch.dict('sys.modules'):
            import runpy
            runpy.run_path(str(Path(generate_report.__file__)), run_name='__main__')
        self.assertTrue(self.out.exists())


if __name__ == '__main__':
    unittest.main()
