# API Contract: M2 Inventory

Base path: `/api/`. Body and response format: JSON. Identifiers are 24 character ObjectId hex
strings. This contract adds five routes under `stock` and changes the existing `products`
routes. Every M0 and M1 route keeps its behaviour.

## Common rules

- Every endpoint here requires an authenticated session. Missing or invalid session returns 401.
- Unsafe methods (POST, PATCH, DELETE) require the `X-CSRFToken` header after sign in.
- A stock record outside the actor's stores returns 403 with
  `{"detail": "This record is outside your store access."}` and no field of the record.
- A role that may not record stock returns 403 with
  `{"detail": "Your role may not perform this action."}`
- The online pool is reachable only by an actor whose assignments cover every store. Everyone
  else receives 403 with the store access message, because the pool has no store they can see.
- Validation errors return 400 with a field map, for example
  `{"quantity": ["The quantity must be greater than zero."]}`
- Lists are paginated with `?page=` and `?page_size=` (default 20, maximum 100). List responses
  are `{"count": n, "next": url|null, "previous": url|null, "results": [...]}`.
- A missing or malformed id in the path returns 404, before any scope check.
- A quantity, a counted number, and a threshold travel as decimal strings with no trailing
  zeros (`"12.5"`, `"0"`, `"2.75"`). A price travels with two decimal places (`"12.50"`).
- A stock write that loses three write conflicts in a row answers 409 with
  `Retry-After: 1`. Nothing from that request is stored, so resending the identical body is
  safe and is the intended answer to that status. The server stops after three rounds and the
  client supplies the next one. One second is the header's smallest unit, not a measurement of
  how long the conflict lasts: it clears in milliseconds, and resending sooner is also safe.
  Resend on 409 only. A timeout or a dropped connection says nothing about whether the write
  landed, and a movement is not idempotent.

## Objects

### Stock

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d4",
  "product_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "product_name": "Milk",
  "unit": "L",
  "pool": "BRANCH",
  "store_id": "65f1c0a2b3d4e5f6a7b8c9d1",
  "store_name": "Downtown",
  "current_stock": "6",
  "last_count": "10",
  "last_event_at": "2026-11-26T14:31:00Z",
  "is_low": true
}
```

`store_id` and `store_name` are null when `pool` is `ONLINE`. `last_event_at` is null on a row
that has no events, which cannot happen through this API, because a row is only created by a
write that also stores its event. `is_low` is true exactly when the product has a threshold
and `current_stock` is strictly below it (FR-041, FR-042).

### StockEvent

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d5",
  "stock_id": "65f1c0a2b3d4e5f6a7b8c9d4",
  "product_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "pool": "BRANCH",
  "store_id": "65f1c0a2b3d4e5f6a7b8c9d1",
  "kind": "MOVEMENT",
  "type": "WASTE",
  "quantity": "2",
  "counted": null,
  "by_id": "65f1c0a2b3d4e5f6a7b8c9d0",
  "by_name": "Ana Silva",
  "at": "2026-11-26T14:31:00Z",
  "note": "expired on Tuesday"
}
```

`type` and `quantity` are null on a `COUNT`, and `counted` is null on a movement. `by_name` is
the display name captured when the event was written, so a later name change or account
deletion does not rewrite history.

### Product (changed)

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "name": "Milk",
  "description": "Semi skimmed",
  "price": null,
  "unit": "L",
  "low_stock_threshold": "5"
}
```

`price` and `low_stock_threshold` are nullable. `unit` defaults to `"pcs"`. The field list is
additive, so an M0 client that ignores the new fields keeps working.

## Permissions

| Route | Method | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|---|
| `/api/stock/` | GET | all | all | own stores | own stores | own stores |
| `/api/stock/low/` | GET | all | all | own stores | own stores | own stores |
| `/api/stock/{id}/events/` | GET | all | all | own stores | own stores | own stores |
| `/api/stock/movements/` | POST | all | all | own stores | own stores | no |
| `/api/stock/counts/` | POST | all | all | own stores | own stores | no |
| `/api/products/` | GET | yes | yes | yes | yes | yes |
| `/api/products/` | POST | yes | yes | no | no | no |
| `/api/products/{id}/` | GET | yes | yes | yes | yes | yes |
| `/api/products/{id}/` | PATCH, PUT, DELETE | yes | yes | no | no | no |

"All" includes the online pool. A role listed with "own stores" sees and writes only its branch
pools, and the online pool answers 403.

## GET /api/stock/

The stock list for the actor's scope.

Query parameters, all optional: `store` (ObjectId), `pool` (`BRANCH` or `ONLINE`), `product`
(ObjectId), `page`, `page_size`.

- `store` outside the actor's assignments returns 403, not an empty list.
- `pool=ONLINE` for an actor who does not reach every store returns 403, for the same reason.
- Ordering is `product_id`, then `pool`, then `store_id`, ascending with ObjectIds compared as
  strings. That order is served by the unique index (FR-032).

Responses: 200 with a page of Stock objects, 400 on a malformed filter, 403 as above.

## GET /api/stock/low/

Rows whose `current_stock` is strictly below their product's threshold, worst first.

Query parameters: `store` (ObjectId), `page`, `page_size`.

- Ordering is by the shortage, `threshold - current_stock`, descending. Tie broken by
  `product_id` ascending, so the order is total.
- A product with no threshold never appears, at any quantity (FR-042).
- A row exactly at its threshold does not appear (FR-041).
- The page is taken after the ordering, so `count` is the number of low rows, not the number of
  stock rows (FR-043, R9).

Responses: 200 with a page of Stock objects carrying `is_low: true`, 403 as above.

## GET /api/stock/{id}/events/

The history of one stock record, newest first.

Query parameters: `page`, `page_size`.

- Ordering is `at` descending, then `id` descending, so two events at the same instant have a
  stable order.
- A record outside the actor's stores returns 403 with no field leaked (FR-034).
- A malformed id returns 404.

Responses: 200 with a page of StockEvent objects, 403, 404.

## POST /api/stock/movements/

Record a delivery, a sale, or waste. This is the only route that can create a stock row.

Body:

```json
{
  "product": "65f1c0a2b3d4e5f6a7b8c9d2",
  "pool": "BRANCH",
  "store": "65f1c0a2b3d4e5f6a7b8c9d1",
  "type": "RECEIVED",
  "quantity": "12.5",
  "note": "",
  "at": "2026-11-26T14:31:00Z"
}
```

| Field | Rules |
|---|---|
| `product` | Required, must exist |
| `pool` | Required, `BRANCH` or `ONLINE` |
| `store` | Required when `pool` is `BRANCH`, forbidden when `ONLINE` |
| `type` | Required, `RECEIVED`, `SOLD`, or `WASTE` |
| `quantity` | Required, greater than zero, at most 3 decimal places |
| `note` | Required and not blank when `type` is `WASTE`, optional otherwise |
| `at` | Optional, defaults to now. Not in the future, not earlier than the newest count |

Refusals, each a 400 with the field named:

| Case | Message on the field |
|---|---|
| `SOLD` on a branch pool | `"A sale cannot be recorded in a store pool yet."` (FR-013) |
| A subtraction larger than the current quantity | `"There is not enough stock for this movement. Record a count first."` |
| `WASTE` with a blank note | `"Waste needs a note."` |
| Quantity zero, negative, or more precise than 3 places | `"The quantity must be greater than zero with at most 3 decimal places."` |
| `at` earlier than the newest count | `"The instant is earlier than the newest count of this stock."` |
| `at` in the future | `"The instant cannot be in the future."` |
| Pool and store disagree | `"A branch pool needs a store and the online pool forbids one."` |
| Missing product or store | `"No product exists with this id."`, `"No store exists with this id."` |
| A counted number negative or more precise than 3 places | `"The counted number must be zero or greater with at most 3 decimal places."` on `counted` |

Response: 201 with

```json
{"stock": { ... }, "event": { ... }}
```

The stock object is the row after the change, so the client needs no second request.

## POST /api/stock/counts/

Record an observation of the shelf.

Body:

```json
{
  "product": "65f1c0a2b3d4e5f6a7b8c9d2",
  "pool": "BRANCH",
  "store": "65f1c0a2b3d4e5f6a7b8c9d1",
  "counted": "6",
  "note": "after the lunch rush",
  "at": "2026-11-26T15:00:00Z"
}
```

| Field | Rules |
|---|---|
| `counted` | Required, zero or greater, at most 3 decimal places |
| `note` | Optional |
| `type`, `quantity` | Refused if sent at all: `{"type": ["A count has no direction."]}` |
| everything else | As the movement route, except `type` and `quantity` are refused if sent |

A `type` or a `quantity` in this body is a 400, because a count has no direction (FR-011).
`counted: "0"` is accepted: an empty shelf is a real observation.

Response: 201 with `{"stock": { ... }, "event": { ... }}`, where `stock.current_stock` and
`stock.last_count` both equal `counted`, and `is_low` is recomputed.

## Catalog routes

`GET /api/products/` is unchanged apart from the new fields, and it stays global read data
visible to every signed-in account (001 FR-022), so no store filter is applied.

`POST /api/products/`, `PATCH`, `PUT`, and `DELETE /api/products/{id}/` now require the
`product.change` action, which ADMIN and REGIONAL_MANAGER hold. Before this feature any
signed-in account could write the catalog, because the views declared no role check. A MANAGER,
SUPERVISOR, or BARISTA now receives 403 with
`{"detail": "Your role may not perform this action."}`

`PATCH /api/products/{id}/` with `{"low_stock_threshold": null}` clears the level, after which
that product is never reported as low (FR-040, FR-042).

The detail route changes from `products/<int:pk>/` to `products/<str:pk>/`, and the view loads
through `core.shortcuts.object_id_or_404`. Before this feature the integer converter could not
match an ObjectId, so every detail request answered 404.

## Side effects owned by other contexts

| Event | Inventory effect |
|---|---|
| Store deleted | Its stock rows and their events are removed by the cascade, inside the store delete transaction (FR-044). No inventory code runs. |
| Product deleted | Its stock rows and their events are removed by the cascade. M2 adds no product delete route; only the admin could reach it, and the admin is read only for stock. |
| Account deleted | No effect. Events keep `by_id` and `by_name`, and no stock number depends on the actor. |

## Status code summary

| Code | When |
|---|---|
| 200 | A successful read, including an empty page |
| 201 | A movement or a count was recorded, or a product was created |
| 204 | A product was deleted |
| 400 | A rule in the tables above was broken, with the field named |
| 401 | No valid session |
| 403 | Role may not record or write, or the record is outside the actor's stores, or the online pool is out of reach |
| 404 | Missing or malformed id in the path, or an unknown page number |
| 409 | A stock write lost three write conflicts in a row. Nothing was applied, `Retry-After: 1` is set, and the identical body may be resent. `{"detail": "The stock changed while this write was being applied. Nothing was saved. Try again."}` |
