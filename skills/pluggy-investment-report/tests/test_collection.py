import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from collect_investments import collect, normalize, ApiError
from report_model import aggregate, private_json, investments_list, validate_targets
from generate_report import generate_html
from summary import summary
import snapshot_diff


class CollectionTests(unittest.TestCase):
    def test_complete_pagination_and_normalization(self):
        requests = []
        def request(endpoint, api_key=None, payload=None):
            requests.append(endpoint)
            if endpoint == '/auth':
                self.assertEqual(payload, {'clientId': 'id', 'clientSecret': 'secret'})
                return {'apiKey': 'private'}
            self.assertEqual(api_key, 'private')
            if endpoint.startswith('/v2/items'):
                second = '?' in endpoint
                return {'results': [{'id': 'b' if second else 'a', 'status': 'UPDATED', 'connector': {'name': 'Bank'}}], 'next': None if second else '?after=cursor%2Bvalue'}
            params = parse_qs(urlsplit(endpoint).query)
            page = int(params['page'][0])
            return {'total': 2, 'results': [{'id': params['itemId'][0] + str(page), 'balance': 1100, 'amount': 1200, 'amountOriginal': 1000, 'amountProfit': 100, 'type': 'FIXED_INCOME', 'subtype': 'TREASURY'}]}
        rows = collect('id', 'secret', request=request)
        self.assertEqual(len(rows), 4)
        self.assertIn('/v2/items?after=cursor%2Bvalue', requests)
        self.assertEqual(rows[0]['amount'], 1000)  # Gross amount is not the original cost.
        self.assertEqual(rows[0]['return_rate'], 10)
        self.assertEqual(rows[0]['type'], 'TREASURY')
        self.assertEqual(aggregate(rows)['return_amount'], 400)

    def test_explicit_items_do_not_require_opt_in_listing(self):
        def request(endpoint, **kwargs):
            if endpoint == '/auth': return {'apiKey': 'key'}
            if endpoint == '/items/known': return {'id': 'known', 'status': 'UPDATED'}
            if endpoint.startswith('/investments?'): return {'results': [], 'total': 0}
            self.fail(endpoint)
        self.assertEqual(collect('id', 'secret', ['known'], request), [])

    def test_missing_cost_is_unknown_and_zero_profit_is_preserved(self):
        row = normalize({'id': 'a', 'balance': 1000, 'amount': 1000, 'amountProfit': 0}, 'Bank')
        self.assertIsNone(row['amount'])
        self.assertEqual(row['return_amount'], 0)
        self.assertIsNone(aggregate([row])['invested'])
        self.assertIn('não informado', summary([row]))

    def test_non_brl_and_missing_balances_are_rejected(self):
        for raw in [{'id': 'a', 'balance': 100, 'currencyCode': 'USD'}, {'id': 'a', 'amount': 100}]:
            with self.assertRaises(ValueError): normalize(raw, 'Bank')

    def test_partial_and_repeated_pages_fail(self):
        for response in [{'results': [], 'total': 1}, {'results': [{'id': 'a', 'balance': 10}], 'total': 2}]:
            def request(endpoint, **kwargs):
                if endpoint == '/auth': return {'apiKey': 'key'}
                if endpoint == '/items/item': return {'id': 'item', 'status': 'UPDATED'}
                return response
            with self.assertRaises(ApiError): collect('id', 'secret', ['item'], request)

    def test_repeated_cursor_and_outdated_connection_fail(self):
        for status in ['UPDATED', 'UPDATING']:
            def request(endpoint, **kwargs):
                if endpoint == '/auth': return {'apiKey': 'key'}
                if endpoint.startswith('/v2/items'): return {'results': [{'id': endpoint, 'status': status}], 'next': '?after=same'}
                return {'results': [], 'total': 0}
            with self.assertRaises(ApiError): collect('id', 'secret', request=request)

    def test_http_errors_do_not_disclose_body_or_credentials(self):
        from urllib.error import HTTPError
        from io import BytesIO
        from collect_investments import request_json
        with patch('collect_investments.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://api.pluggy.ai/auth', 403, 'secret', {}, BytesIO(b'secret-body'))
            with self.assertRaises(ApiError) as failure:
                request_json('/auth', payload={'clientSecret': 'secret'})
            self.assertNotIn('secret', str(failure.exception))
            self.assertIn('403', str(failure.exception))

    def test_collection_failure_preserves_previous_output(self):
        from collect_investments import main
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'out.json'
            output.write_text('previous')
            with patch.dict(os.environ, {'PLUGGY_CLIENT_ID':'id', 'PLUGGY_CLIENT_SECRET':'secret'}), patch.object(sys, 'argv', ['collect', str(output)]), patch('collect_investments.collect', side_effect=ApiError('incomplete page')), patch('sys.stderr'):
                self.assertEqual(main(), 2)
            self.assertEqual(output.read_text(), 'previous')


class ModelTests(unittest.TestCase):
    def test_rejects_bad_shapes_and_non_finite_money(self):
        for data in [None, {}, [1], [{'value': '100'}], [{'value': float('nan')}]]:
            with self.assertRaises(ValueError): investments_list(data)
        for targets in [[], {'ETF': 10}, {'ETF': -10, 'Ações': 110}, {'ETF': float('nan')}]:
            with self.assertRaises(ValueError): validate_targets(targets)

    def test_private_atomic_outputs_and_consistent_zero_negative_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'id': 'a', 'name': 'Debt', 'value': -20, 'amount': 0}, {'id': 'b', 'name': 'Zero', 'value': 0, 'amount': 10}]
            source, diff, html = root / 'in.json', root / 'diff.json', root / 'out.html'
            private_json(source, rows)
            with patch.object(snapshot_diff, 'SNAPSHOT_DIR', root / 'snapshots'):
                self.assertEqual(snapshot_diff.main(['diff', str(source), str(diff)]), 0)
                snapshot_diff.main(['diff', str(source), str(diff)])
                snapshots = list((root / 'snapshots').glob('*.json'))
                self.assertEqual(len(snapshots), 2)
            generate_html(rows, str(html))
            self.assertIn('Debt', html.read_text())
            self.assertIn('Zero', html.read_text())
            self.assertIn('-R$ 20,00', summary(rows))
            self.assertEqual(json.loads(diff.read_text())['totals']['current']['curr'], -20)
            if os.name == 'posix':
                for file in [source, diff, html, *snapshots]: self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_unknown_totals_have_no_fabricated_delta(self):
        totals = snapshot_diff.diff_totals({'invested': None}, {'invested': 100})
        self.assertIsNone(totals['invested']['delta'])
