# Pluggy API Reference

Base URL: `https://api.pluggy.ai`

All requests (except `/auth`) require the header:
```
X-API-KEY: {apiKey}
```

---

## 1. Authentication

**POST /auth**

Request:
```json
{
  "clientId": "YOUR_CLIENT_ID",
  "clientSecret": "YOUR_CLIENT_SECRET"
}
```

Response (200):
```json
{
  "apiKey": "abc123..."
}
```

Error (403): invalid credentials.

---

## 2. List Connected Items (Accounts)

**GET /items**

Response (200):
```json
{
  "total": 2,
  "results": [
    {
      "id": "item-uuid-1",
      "status": "UPDATED",
      "connector": {
        "id": 201,
        "name": "Nubank",
        "type": "PERSONAL_BANK"
      },
      "updatedAt": "2026-05-19T10:00:00Z"
    }
  ]
}
```

Collect all `results[].id` values — these are `itemId`s.

---

## 3. Fetch Investments for an Item

**GET /investments?itemId={itemId}**

Response (200):
```json
{
  "total": 3,
  "results": [
    {
      "id": "inv-uuid-1",
      "name": "Tesouro IPCA+ 2029",
      "balance": 5430.50,
      "amount": 5000.00,
      "profits": 430.50,
      "lastTwelveMonthsRate": 8.61,
      "dueDate": "2029-05-15",
      "type": "FIXED_INCOME",
      "subtype": "LFT",
      "issuer": "Tesouro Nacional",
      "currencyCode": "BRL",
      "date": "2023-01-10",
      "quantity": 0.5
    }
  ]
}
```

Repeat for each `itemId`. Concatenate all `results` arrays.

---

## 4. Field Mapping to Report Model

| Pluggy field | Report field | Notes |
|---|---|---|
| `name` | `name` | Asset name |
| `connector.name` (from item) | `institution` | Bank/broker name — carry it when iterating |
| `type` | `type` | FIXED_INCOME, STOCK, FUND, ETF, MUTUAL_FUND, REAL_ESTATE |
| `amount` | `amount` | Original amount invested |
| `balance` | `value` | Current market value |
| `profits` | `return_amount` | Gross return in R$ (balance - amount if missing) |
| `lastTwelveMonthsRate` | `return_rate` | Return % (calculate as profits/amount*100 if missing) |
| `dueDate` | `maturity_date` | May be null for stocks/ETFs |

**Institution lookup:** When iterating items, store a map `{itemId → connector.name}`. Use this when processing each investment.

---

## 5. Sandbox Setup

1. Go to https://pluggy.ai and create a free account
2. In the dashboard, create an **App** — this gives you Client ID and Client Secret
3. In sandbox mode, use the **Pluggy Connect Widget** or the API directly to connect a test account:
   - `POST /connect-token` with your `apiKey` to get a `connectToken`
   - Use the sandbox connector ID `201` (Nubank sandbox) for test data
4. Sandbox investments are pre-populated with realistic fake data

---

## 6. Pagination

Both `/items` and `/investments` support `page` and `pageSize` query params.
Default `pageSize` is 20. Check `total` vs `results.length` — if `total > pageSize`, fetch additional pages:

```
GET /investments?itemId={id}&page=2&pageSize=20
```

For most personal accounts, a single page is sufficient.
