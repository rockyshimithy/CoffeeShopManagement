# API Contract: M3 Inventory Insight

Base path: `/api/`. Body and response format: JSON. Identifiers are 24 character ObjectId hex
strings. This contract adds two read routes under `stock` and changes no existing route's
response.

## Common rules

- Both routes require an authenticated session. A missing or invalid session returns 401.
- Both routes are `GET` only. Any other method on either path returns 405.
- The actor must hold `stock.read`. Every role does, so this refusal exists for a future role
  that does not. A refusal returns 403 with
  `{"detail": "Your role may not perform this action."}`
- Every query is filtered by the actor's store assignments. A named store outside those
  assignments returns 403 with `{"detail": "This record is outside your store access."}` and no
  field of any row.
- The online pool is reachable only when no store is named and the actor's assignments cover
  every store. A named store excludes it for every role, including ADMIN.
- Instants travel and render as ISO 8601 with an explicit offset. The project is `UTC`, so they
  render with `Z`, for example `2026-11-26T14:31:00Z`.
- Quantities, counted numbers, totals, and grand totals travel as decimal strings with no
  trailing zeros: `"12.5"`, `"0"`, `"2.75"`. A zero grand total renders `"0"`.
- A quantity has at most three decimal places, as in M2.

## Objects

### Event row

Returned by both routes. The feed and the waste list use the same object.

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d5",
  "stock_id": "65f1c0a2b3d4e5f6a7b8c9d4",
  "product_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "product_name": "Milk",
  "unit": "L",
  "pool": "BRANCH",
  "store_id": "65f1c0a2b3d4e5f6a7b8c9d1",
  "store_name": "Downtown",
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

- `kind` is `MOVEMENT` or `COUNT`. `type` and `quantity` are null on a count, and `counted` is
  null on a movement.
- `pool` is `BRANCH` or `ONLINE`. `store_id` and `store_name` are null exactly when the pool is
  `ONLINE`.
- `product_name` and `unit` are read from the catalog at request time, so a renamed item reads
  under its current name. If the label cannot be resolved, `product_name` and `unit` are empty
  strings and the page still answers.
- `by_name` is the display name stored when the event was written. It survives a rename and an
  account deletion.
- `stock_id` lets a client open that record's history at
  `GET /api/stock/{stock_id}/events/`.

### Waste total

Present only in the waste report.

```json
{
  "product_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "product_name": "Milk",
  "unit": "L",
  "total": "6.75",
  "events": 3
}
```

One row per item with at least one waste event in the filtered range, ordered by `total`
descending and then `product_id` ascending. `total` is the exact sum of the listed quantities,
and `events` is the count of waste events. There is no sort parameter.

## GET /api/stock/waste/

Every waste event in a date range, newest first, with per item totals and a grand total.

### Parameters

| Name | Required | Type | Rules |
|---|---|---|---|
| `start` | yes | ISO 8601 instant | Included in the window. Missing or malformed is 400. |
| `end` | yes | ISO 8601 instant | Included in the window. Missing or malformed is 400. Earlier than `start` is 400 on `end`. |
| `store` | no | ObjectId | Must be in the actor's assignments. Out of scope is 403. |
| `product` | no | ObjectId | Need not exist. A valid id with no events answers an empty report. Malformed is 400. |
| `page` | no | integer | 1 or greater. Past the last page is 404. |
| `page_size` | no | integer | Default 20, maximum 100. Above 100 is capped. |

Both bounds are inclusive. `start` equal to `end` is legal and answers the events at that one
instant. Any window length is legal.

The client sends the first and last instant of the day it means, for example
`00:00:00.000Z` and `23:59:59.999Z`. The server performs no day arithmetic, which is why the
window is inclusive rather than half open.

### Response, 200

```json
{
  "count": 34,
  "next": "http://127.0.0.1:8000/api/stock/waste/?page=2&start=2026-11-24T00%3A00%3A00Z&end=2026-11-24T23%3A59%3A59.999Z&store=65f1c0a2b3d4e5f6a7b8c9d1",
  "previous": null,
  "results": [ { "...": "Event row" } ],
  "totals": [ { "...": "Waste total" } ],
  "grand_total": "8.25"
}
```

- `count` is the number of waste events in the range. It equals the sum of `totals[].events`.
- `results` is one page of event rows, ordered by `at` descending then `id` descending.
- `totals` covers the whole filtered range, not the current page, and is identical on every
  page of the same query. It is not paginated.
- `grand_total` equals the sum of `totals[].total`.
- An empty range answers `count` 0, an empty `results`, an empty `totals`, and
  `grand_total` `"0"` with status 200. No error and no 404.
- Deliveries, sales, and counts never appear, in the rows or in the totals. Count
  discrepancies are not part of this report. The gap a count closes stays derivable from one
  record's history.

### Refusals

| Case | Status | Body |
|---|---|---|
| No session | 401 | `{"detail": "Authentication credentials were not provided."}` |
| Role without `stock.read` | 403 | `{"detail": "Your role may not perform this action."}` |
| `store` outside the assignments | 403 | `{"detail": "This record is outside your store access."}` |
| `start` missing | 400 | `{"start": ["This field is required."]}` |
| `end` missing | 400 | `{"end": ["This field is required."]}` |
| `start` or `end` malformed | 400 | `{"start": ["Datetime has wrong format. ..."]}` |
| `start` later than `end` | 400 | `{"end": ["The end must not be earlier than the start."]}` |
| `store` or `product` not an ObjectId | 400 | `{"store": ["Enter a valid ObjectId."]}` |
| `page` past the end | 404 | `{"detail": "Invalid page."}` |
| `product` well formed, no events | 200 | An empty report |

## GET /api/stock/activity/

The newest stock changes across items in the actor's scope, one timeline, newest first.

### Parameters

| Name | Required | Type | Rules |
|---|---|---|---|
| `store` | no | ObjectId | Must be in the actor's assignments. Out of scope is 403. |
| `product` | no | ObjectId | Need not exist. A valid id with no events answers an empty page. Malformed is 400. |
| `page` | no | integer | 1 or greater. Past the last page is 404. |
| `page_size` | no | integer | Default 20, maximum 100. Above 100 is capped. |

### Response, 200

```json
{
  "count": 137,
  "next": "http://127.0.0.1:8000/api/stock/activity/?page=2",
  "previous": null,
  "results": [ { "...": "Event row" } ]
}
```

- `results` mixes deliveries, sales, waste, and counts in one list.
- Ordering is `at` descending then `id` descending, so two changes at the same instant appear in
  the same order on every read and across a page boundary.
- Page 1 holds the newest `page_size` changes. With fewer changes in scope than the page size,
  every change is returned.
- A change recorded between two page loads can shift one entry across a page boundary, because
  pages are offsets. The order itself never changes.
- No changes in scope answers `count` 0 and an empty `results` with status 200.

### Refusals

| Case | Status | Body |
|---|---|---|
| No session | 401 | `{"detail": "Authentication credentials were not provided."}` |
| Role without `stock.read` | 403 | `{"detail": "Your role may not perform this action."}` |
| `store` outside the assignments | 403 | `{"detail": "This record is outside your store access."}` |
| `store` or `product` not an ObjectId | 400 | `{"product": ["Enter a valid ObjectId."]}` |
| `page` past the end | 404 | `{"detail": "Invalid page."}` |
| `product` well formed, no events | 200 | An empty page |

## Permissions

| Route | Method | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|---|
| `/api/stock/waste/` | GET | all | all | own stores | own stores | own stores |
| `/api/stock/activity/` | GET | all | all | own stores | own stores | own stores |

"All" includes the online pool, but only when no store is named. A row from the online pool
carries `pool: "ONLINE"`, `store_id: null`, and `store_name: null`.

Every role that may read one stock record's history may read both routes. That is FR-023, and
it holds because both routes consult the same `stock.read` action the history route consults.

## Status code summary

| Code | When |
|---|---|
| 200 | A successful read, including an empty page or an empty range |
| 400 | A bound is missing, malformed, or inverted, or an id parameter is malformed |
| 401 | No valid session |
| 403 | The role lacks `stock.read`, or the named store is outside the actor's assignments |
| 404 | The page number is past the last page |
| 405 | Any method other than GET on either route |

## Side effects owned by other contexts

| Event | Effect on these reads |
|---|---|
| Account deleted | None. `by_name` is the stored snapshot, and `by_id` stops resolving but is never joined. |
| Product deleted | Its stock rows and their events are removed by the M2 cascade, so no row can name a missing item. |
| Store deleted | Its stock rows and their events are removed by the cascade, inside the store delete transaction. |
| Stock row deleted | Its events are removed, so no row names a record that no longer exists. |

## What this contract does not add

- No write method, no request body, and no new write path to stock or events.
- No stored total, no gap field, and no discrepancy endpoint.
- No export, no scheduled report, and no chart data.
- No sort parameter. The waste totals are always ordered by total descending.
- No change to any M0, M1, or M2 response.
