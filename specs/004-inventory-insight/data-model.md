# Data Model: M3 Inventory Insight

M3 adds **no collection, no field, no index, and no migration**. It reads `inventory_stockevent`
through two new endpoints and derives every number at read time. Anything in this document
that looks like a model is a response shape, not storage.

The one structural addition is a permission call: every read view now consults `stock.read`
before it applies scope (R11). No model or permission table entry changes.

## Source collection, `inventory_stockevent`

Defined in `src/apps/inventory/models.py` by M2. M3 reads these fields and none of the stock
row's numbers.

| Field | Type | Read by M3 | Note |
|---|---|---|---|
| `id` | ObjectId | yes | Row identity, and the sort tiebreak |
| `stock_id` | ObjectId | yes | Lets a client open that record's history |
| `product_id` | ObjectId | yes | Group key for the totals |
| `pool_type` | `BRANCH` or `ONLINE` | yes | Rendered as `pool` |
| `store_id` | ObjectId, null | yes | Null exactly for the online pool |
| `kind` | `MOVEMENT` or `COUNT` | yes | The report selects `MOVEMENT` only |
| `type` | `RECEIVED`, `SOLD`, `WASTE`, null | yes | The report selects `WASTE` only |
| `quantity` | decimal, 3 places, null | yes | Summed for the totals |
| `counted` | decimal, 3 places, null | yes | Present on feed entries, null on movements |
| `by_id` | ObjectId | yes | The actor |
| `by_name` | string, 120 | yes | The name snapshot, never re-resolved |
| `at` | datetime | yes | Range filter and sort key |
| `note` | string, 200, blank | yes | Required by M2 for waste, optional otherwise |

Nothing is written. `derived_discrepancy` is not called (R12).

## Resolved at read time

| Value | Source | Why not stored | Requirement |
|---|---|---|---|
| `product_name` | `catalog.services.product_labels` | I3 forbids copying a product name into stock or events | FR-011 |
| `unit` | same batch | same | FR-011 |
| `store_name` | `stores.services.store_names` | A store can be renamed, and the event names a store by id | FR-005, FR-014 |
| `by_name` | the event | **not** resolved live: the account may no longer exist | FR-011, FR-024 |

The split is deliberate. The item label follows the catalog because a rename should read
correctly today. The actor label is the snapshot because history must not change when an
account is deleted.

## Response shapes

### Event row, used by both reads

One serializer, `EventReadSerializer`, subclassing `StockEventSerializer` and adding three
method fields. The waste list and the feed return the identical object, because FR-005 and
FR-014 describe almost the same row.

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

The waste report returns rows where `kind` is `MOVEMENT` and `type` is `WASTE`, so those two
fields are constant there. They stay in the object so both reads share one shape, and so a feed
entry says what it is without a second field.

### Waste total row

```json
{
  "product_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "product_name": "Milk",
  "unit": "L",
  "total": "6.75",
  "events": 3
}
```

One row per product with at least one waste event in the filtered range. `total` is the exact
sum of `quantity`, and `events` is the count of waste events. Both come from one aggregation
(R2). `product_name` and `unit` arrive in the same batch as the page rows (R9).

The rows are ordered by `total` descending, then `product_id` ascending, so two products with
the same total never swap between requests. No sort parameter exists (D2).

### Waste report envelope

```json
{
  "count": 34,
  "next": "http://127.0.0.1:8000/api/stock/waste/?page=2&start=...&end=...",
  "previous": null,
  "results": [ { "...": "Event row" } ],
  "totals": [ { "...": "Waste total row" } ],
  "grand_total": "8.25"
}
```

- `count` is the number of waste events in the range, taken from the sum of `totals[].events`
  (R3's sibling: one calculation, so the envelope cannot contradict the totals).
- `results` is one page of event rows.
- `totals` and `grand_total` are identical on every page of the same query, because they are
  computed from the unsliced queryset on every request (D4). They are not paginated.
- `grand_total` is the sum of `totals[].total`, computed before serialization.

### Activity feed envelope

The project's standard page, with no extra keys:

```json
{
  "count": 137,
  "next": "http://127.0.0.1:8000/api/stock/activity/?page=2",
  "previous": null,
  "results": [ { "...": "Event row" } ]
}
```

`results` mixes deliveries, sales, waste, and counts, ordered by instant descending with the
id tiebreak.

## Filter sets

| Read | Required | Optional | Ignored |
|---|---|---|---|
| Waste report | `start`, `end` | `store`, `product`, `page`, `page_size` | none |
| Activity feed | none | `store`, `product`, `page`, `page_size` | none |

Both reads apply the same scope rule, then the item filter, then the order (R5, R6).

```text
event_scope(actor, store_id, product_id):
    queryset = stock_scope(StockEvent.objects.all(), actor, store_id)
    if product_id is not None:
        queryset = queryset.filter(product_id=product_id)
    return queryset.order_by("-at", "-id")
```

The report adds `kind=MOVEMENT`, `type=WASTE`, and the two range bounds to that queryset.

## Query plans

### Waste report, four queries per page

| Step | Work |
|---|---|
| 1 | Validate `start`, `end`, `store`, `product`, `page`, `page_size`. No query. |
| 2 | `event_scope`. A foreign store raises 403 through `scope_store_ids`. No query. |
| 3 | Totals aggregation over the unsliced filtered queryset, one `$group`. One query. `count` is the sum of its `events`. |
| 4 | Page slice `[offset : offset + page_size]`. One query. |
| 5 | `product_labels` over the page ids plus the totals ids. One query. |
| 6 | `store_names` over the page store ids. One query. |

Step 3 before step 4 means an out of range page costs no event query, and it is what makes
`count` free.

### Activity feed, four queries per page

| Step | Work |
|---|---|
| 1 | Validate `store`, `product`, `page`, `page_size`. No query. |
| 2 | `event_scope`. A foreign store raises 403. No query. |
| 3 | Count from the pager. One query. |
| 4 | Page slice. One query. |
| 5 | `product_labels` over the page ids. One query. |
| 6 | `store_names` over the page store ids. One query. |

The feed has no totals, so its count comes from the standard pager and it is one query more
than the report would be if it also had a totals block. Four either way.

## Indexes used

| Read case | Index | What it serves | What it does not |
|---|---|---|---|
| Report, store named | `(store_id, at)` | Store equality, instant range | The `id` tiebreak, so a blocking sort remains |
| Report, item filter without a store | `(product_id, at)` | Product equality, instant range | The sort, for the same reason |
| Report, scope wide | `(store_id, at)` per branch | Each branch's range | The global sort across branches |
| Feed, store named | `(store_id, at)` | Store equality | The sort, and there is no range to narrow it |
| Feed, scope wide | none directly | n/a | The whole in-scope history is sorted |

`kind` and `type` are applied after the index scan. Waste is a minority of events and the date
range does most of the narrowing.

No index is added (R10). The three costs this creates are carried into `plan.md` as known
limitations.

## Validation

| Rule | Result | Where |
|---|---|---|
| No session | 401 | Global `IsAuthenticated` |
| Role not in `stock.read` | 403, `"Your role may not perform this action."` | `require_action` (R11) |
| `start` missing or malformed | 400 on `start` | `WasteReportQuerySerializer` |
| `end` missing or malformed | 400 on `end` | same |
| `start > end` | 400 on `end`, `"The end must not be earlier than the start."` | same |
| `store` malformed | 400, `"Enter a valid ObjectId."` | `ObjectIdField` |
| `store` outside the actor's assignments | 403, `"This record is outside your store access."` | `scope_store_ids` |
| `product` malformed | 400, `"Enter a valid ObjectId."` | `ObjectIdField` |
| `product` well formed, no events | 200, empty `results` and `totals`, `grand_total` `"0"` | The read itself |
| `page` not an integer, or outside the pages | 404, `"Invalid page."` | `_paged_response` or the DRF pager |
| `page_size` above 100 | Capped at 100 | `StandardPagination.max_page_size` |

`start == end` is legal and answers the events at that one instant. Any window length is
legal, from one millisecond to ten years.

## Access rules

Every read goes through `require_action(actor, "stock.read")` first, then `stock_scope`. The
scope rule is M2's, unchanged (R5).

| Role | `stock.read` | Store scope | Online pool |
|---|---|---|---|
| ADMIN | yes | every store | yes, when no store is named |
| REGIONAL_MANAGER, assignments cover every store | yes | every store | yes, when no store is named |
| REGIONAL_MANAGER, partial assignments | yes | assigned stores | no |
| MANAGER | yes | assigned stores | no |
| SUPERVISOR | yes | assigned stores | no |
| BARISTA | yes | assigned stores | no |

A named store excludes the online pool for every role, including ADMIN, because the filter is
one `store_id`.

An actor with no store assignments gets an empty page, not an error, unless they name a store,
which is a 403.

## Deletion behaviour

| Deleted | Effect on these reads | Requirement |
|---|---|---|
| Account | None. `by_name` is the stored snapshot, and no query joins on `by_id`. | FR-024 |
| Product | Its stock rows and their events are removed by the M2 cascade, so no row can name a missing item. | FR-025 |
| Store | Its stock rows and their events are removed by the cascade, inside the store delete transaction. | FR-025 |
| Stock row | Its events are removed. A read never names a record that no longer exists. | FR-025 |

No M3 code handles a deletion. The cascades already exist and M3 only reads their result.

## What is deliberately not stored

- No per item total on the product or the stock row. It is derived from the events on every
  read (spec Assumptions).
- No grand total anywhere.
- No gap, no discrepancy, and no `SHRINKAGE` type. `derived_discrepancy` stays a read of count
  events, unused by M3 (R12).
- No copy of a product name, unit, or store name on an event. The actor name remains the one
  snapshot, for the reason FR-024 gives.
- No new field, index, or migration.
