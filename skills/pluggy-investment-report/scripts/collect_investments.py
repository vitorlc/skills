#!/usr/bin/env python3
"""Collect a complete Pluggy portfolio without printing credentials or raw responses."""
import argparse
import json
import math
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from report_model import number, private_json, investments_list

BASE_URL = "https://api.pluggy.ai"


class ApiError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to a redirect target.


def request_json(endpoint, api_key=None, payload=None):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = Request(BASE_URL + endpoint, data=body, headers=headers)
    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            data = json.load(response)
    except HTTPError as exc:
        hint = " Listing items requires opt-in; use --item-id for known connections." if endpoint.startswith('/v2/items') and exc.code == 403 else ""
        raise ApiError(f"Pluggy returned HTTP {exc.code}.{hint}") from None
    except (URLError, TimeoutError, OSError):
        raise ApiError("Pluggy network request failed or timed out") from None
    except (ValueError, UnicodeError):
        raise ApiError("Pluggy returned invalid JSON") from None
    if not isinstance(data, dict):
        raise ApiError("Pluggy response must be an object")
    return data


def list_items(request, api_key):
    endpoint = "/v2/items"
    seen = set()
    while endpoint:
        if endpoint in seen or len(seen) >= 10000:
            raise ApiError("Repeated items cursor; collection aborted")
        seen.add(endpoint)
        data = request(endpoint, api_key=api_key)
        if not isinstance(data.get("results"), list) or "next" not in data:
            raise ApiError("Invalid items page")
        yield from data["results"]
        cursor = data["next"]
        if cursor is not None and (not isinstance(cursor, str) or not cursor.startswith("?")):
            raise ApiError("Invalid items cursor")
        endpoint = "/v2/items" + cursor if cursor else None


def list_investments(request, api_key, item_id):
    seen = set()
    count = 0
    for page in range(1, 10001):
        data = request("/investments?" + urlencode({"itemId": item_id, "page": page, "pageSize": 500}), api_key=api_key)
        rows, total = data.get("results"), data.get("total")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise ApiError("Invalid investments page")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
                raise ApiError("Missing or repeated investment ID; collection aborted")
            seen.add(row["id"])
            yield row
        count += len(rows)
        if count == total:
            return
        if not rows or count > total:
            raise ApiError("Incomplete or inconsistent investments pagination")
    raise ApiError("Investments pagination limit exceeded")


def list_transactions(request, api_key, investment_id):
    """Application/withdrawal history of one investment (paginated)."""
    result = []
    for page in range(1, 1001):
        query = urlencode({"page": page, "pageSize": 500})
        data = request(f"/investments/{quote(investment_id, safe='')}/transactions?{query}", api_key=api_key)
        rows, total_pages = data.get("results"), data.get("totalPages")
        if not isinstance(rows, list):
            raise ApiError("Invalid transactions page")
        for row in rows:
            result.append(normalize_transaction(row))
        if type(total_pages) is not int or page >= total_pages:
            return result
    raise ApiError("Transactions pagination limit exceeded")


def normalize_transaction(raw):
    if not isinstance(raw, dict):
        raise ValueError("Invalid transaction")
    date = raw.get("tradeDate") or raw.get("date")
    kind = raw.get("type")
    if not isinstance(date, str) or not isinstance(kind, str):
        raise ValueError("Transaction without date or type")
    return {"date": date, "type": kind, "amount": number(raw.get("amount"), "transaction amount")}


def soft_number(value):
    """Informational fields must never abort a collection."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def soft_text(value):
    return value if isinstance(value, str) and value else None


def normalize(raw, institution):
    holding = raw.get("institution")
    if isinstance(holding, dict) and isinstance(holding.get("name"), str) and holding["name"]:
        institution = holding["name"]  # e.g. CEI/B3: the broker holding this asset
    if raw.get("currencyCode") not in (None, "BRL"):
        raise ValueError("Non-BRL investment: currency conversion is not supported")
    value = number(raw.get("balance"), "balance")
    amount = number(raw.get("amountOriginal"), "amountOriginal", optional=True)
    profit = number(raw.get("amountProfit"), "amountProfit", optional=True)
    if profit is None and amount is not None:
        profit = value - amount
    rate = profit / amount * 100 if profit is not None and amount else None
    code = raw.get("type") or "OTHER"
    if raw.get("subtype") == "REAL_ESTATE_FUND":
        code = "REAL_ESTATE"
    elif raw.get("subtype") == "TREASURY":
        code = "TREASURY"
    return {"id": raw["id"], "name": raw.get("name") or "-", "institution": institution,
            "type": code, "amount": amount, "value": value, "return_amount": profit,
            "return_rate": rate, "maturity_date": raw.get("dueDate"),
            "subtype": soft_text(raw.get("subtype")), "rate_type": soft_text(raw.get("rateType")),
            "rate": soft_number(raw.get("rate")), "fixed_annual_rate": soft_number(raw.get("fixedAnnualRate")),
            "issuer": soft_text(raw.get("issuer")), "issue_date": soft_text(raw.get("issueDate")),
            "quantity": soft_number(raw.get("quantity")), "as_of": soft_text(raw.get("date")),
            "last_twelve_months_rate": soft_number(raw.get("lastTwelveMonthsRate")),
            "status": soft_text(raw.get("status"))}


def collect(client_id, client_secret, item_ids=None, request=request_json,
            with_transactions=False, warnings=None):
    auth = request("/auth", payload={"clientId": client_id, "clientSecret": client_secret})
    key = auth.get("apiKey")
    if not isinstance(key, str) or not key:
        raise ApiError("Authentication failed: missing API key")
    items = (request("/items/" + quote(item, safe=""), api_key=key) for item in item_ids) if item_ids else list_items(request, key)
    result, seen_items = [], set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ApiError("Invalid item response")
        if item["id"] in seen_items:
            raise ApiError("Repeated item ID; collection aborted")
        seen_items.add(item["id"])
        if item.get("status") != "UPDATED":
            raise ApiError("A connection is not UPDATED; collection aborted to avoid a partial report")
        connector = item.get("connector") or {}
        if not isinstance(connector, dict):
            raise ApiError("Invalid connector response")
        institution = connector.get("name") or "Desconhecida"
        for raw in list_investments(request, key, item["id"]):
            row = normalize(raw, institution)
            if with_transactions:
                # Unknown (None) differs from "no transactions" ([]); failures never abort the run.
                try:
                    row["transactions"] = list_transactions(request, key, raw["id"])
                except (ApiError, ValueError):
                    row["transactions"] = None
                    if warnings is not None:
                        warnings.append(raw["id"])
            result.append(row)
    if not seen_items:
        raise ApiError("No connected items. Connect an account before collecting investments")
    return investments_list(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Private JSON output path")
    parser.add_argument("--item-id", action="append", help="Known item ID; repeat for multiple connections")
    parser.add_argument("--with-transactions", action="store_true",
                        help="Also fetch each investment's transactions (one extra request per investment)")
    args = parser.parse_args()
    client_id, secret = os.environ.get("PLUGGY_CLIENT_ID"), os.environ.get("PLUGGY_CLIENT_SECRET")
    if not client_id or not secret:
        print("Set PLUGGY_CLIENT_ID and PLUGGY_CLIENT_SECRET in the environment", file=sys.stderr)
        return 1
    try:
        warnings = []
        result = collect(client_id, secret, args.item_id, with_transactions=args.with_transactions, warnings=warnings)
        private_json(args.output, result)
        if warnings:
            print(f"Transactions unavailable for {len(warnings)} of {len(result)} investments; "
                  "flows for those will be estimated", file=sys.stderr)
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Collection failed: {exc}", file=sys.stderr)
        return 1
    print(f"Collected {len(result)} investments into {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
