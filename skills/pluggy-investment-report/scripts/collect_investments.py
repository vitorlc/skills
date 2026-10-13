#!/usr/bin/env python3
"""Collect a complete Pluggy portfolio without printing credentials or raw responses."""
import argparse
import json
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


def normalize(raw, institution):
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
            "return_rate": rate, "maturity_date": raw.get("dueDate")}


def collect(client_id, client_secret, item_ids=None, request=request_json):
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
            result.append(normalize(raw, institution))
    if not seen_items:
        raise ApiError("No connected items. Connect an account before collecting investments")
    return investments_list(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Private JSON output path")
    parser.add_argument("--item-id", action="append", help="Known item ID; repeat for multiple connections")
    args = parser.parse_args()
    client_id, secret = os.environ.get("PLUGGY_CLIENT_ID"), os.environ.get("PLUGGY_CLIENT_SECRET")
    if not client_id or not secret:
        print("Set PLUGGY_CLIENT_ID and PLUGGY_CLIENT_SECRET in the environment", file=sys.stderr)
        return 1
    try:
        result = collect(client_id, secret, args.item_id)
        private_json(args.output, result)
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
