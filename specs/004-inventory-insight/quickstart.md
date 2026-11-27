# Quickstart: M3 Inventory Insight

A runnable proof that the milestone works. Run every command from the repository root. This
guide validates the contract in `contracts/api.md`; it does not repeat the field rules, which
live there.

M3 adds no migration, so step 2 should report nothing to apply. That is itself a check: this
milestone changes no model.

## Prerequisites

- Docker and Docker Compose
- `uv` installed
- Port 8000 free for the API, port 27017 free for MongoDB
- M2 already applied: `Stock` and `StockEvent` exist and the stock routes answer

## 1. Start MongoDB

```bash
docker compose up -d mongo
docker compose ps mongo
```

Expected: the `mongo` service is `healthy`.

## 2. Apply migrations and confirm there are none new

```bash
uv sync
uv run python src/manage.py migrate
```

Expected: every migration is already applied. No new migration name appears. If a new one
appears, a model changed, which this feature must not do.

## 3. Create the first admin

Skip this when an admin already exists.

```bash
uv run python src/manage.py create_admin --email admin@example.com --password 'change-this-now'
```

Expected: one account with role `ADMIN`.

## 4. Run the suite and the lint gate

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Expected: the M0, M1, and M2 suites still pass, plus 57 new tests in
`test_waste_report.py`, `test_activity_feed.py`, and `test_insight_scope.py`. No lint findings.

The report timing test seeds 10,000 events, times one request, and prints the elapsed time.
Record the number if it moves materially between machines.

## 5. Run the server

```bash
uv run python src/manage.py runserver 0.0.0.0:8000
```

Leave it running. The remaining steps use a second terminal.

## 6. Set up the shell helpers

```bash
BASE=http://127.0.0.1:8000/api
ADMIN_JAR=/tmp/m3-admin.txt
MANAGER_JAR=/tmp/m3-manager.txt
BARISTA_JAR=/tmp/m3-barista.txt
REGIONAL_JAR=/tmp/m3-regional.txt
id_of() { python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }
login() {
  curl -s -c "$1" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$2\",\"password\":\"$3\"}" "$BASE/auth/login/" >/dev/null
}
csrf() { python3 - "$1" <<'PY'
import sys
from http.cookiejar import MozillaCookieJar
jar = MozillaCookieJar(sys.argv[1]); jar.load(ignore_discard=True)
print(next(c.value for c in jar if c.name == "csrftoken"))
PY
}
```

## 7. Seed stores, products, and accounts

```bash
login "$ADMIN_JAR" admin@example.com 'change-this-now'
A=$(csrf "$ADMIN_JAR")

STORE_A=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Downtown"}' "$BASE/stores/" | id_of)
STORE_B=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Riverside"}' "$BASE/stores/" | id_of)

MILK=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Milk","description":"Semi skimmed","unit":"L","low_stock_threshold":"5"}' \
  "$BASE/products/" | id_of)
COFFEE=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Coffee bag XYZ","unit":"pcs","price":"12.50"}' "$BASE/products/" | id_of)

curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"mgr@example.com\",\"password\":\"test-password-123\",\"role\":\"MANAGER\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" >/dev/null
curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"bar@example.com\",\"password\":\"test-password-123\",\"role\":\"BARISTA\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" >/dev/null
curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"reg@example.com\",\"password\":\"test-password-123\",\"role\":\"REGIONAL_MANAGER\",\"store_ids\":[\"$STORE_A\",\"$STORE_B\"]}" \
  "$BASE/accounts/" >/dev/null
```

Expected: two stores, two products, and three staff accounts. The manager and the barista reach
store A only. The regional manager reaches both stores.

## 8. Record the events

Day one is 2026-11-24, day two is 2026-11-25. All times are UTC, written with `Z`.

```bash
login "$MANAGER_JAR" mgr@example.com 'test-password-123'
M=$(csrf "$MANAGER_JAR")

# 1. a delivery of milk
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"12.5\",\"at\":\"2026-11-24T08:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null

# 2. a delivery of coffee bags, so the coffee waste has stock to remove
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$COFFEE\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"6\",\"at\":\"2026-11-24T07:30:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null

# 3. two litres of milk binned
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"2\",\"note\":\"expired on Tuesday\",\"at\":\"2026-11-24T09:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null

# 4. one coffee bag binned
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$COFFEE\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"1\",\"note\":\"dropped the bag\",\"at\":\"2026-11-24T09:30:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null

# 5. a quarter litre of milk spilled
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"0.25\",\"note\":\"spilled\",\"at\":\"2026-11-24T10:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null

# 6. a count, which is not waste and must not appear in the report
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"counted\":\"9\",\"note\":\"counted the shelf\",\"at\":\"2026-11-24T12:00:00Z\"}" \
  "$BASE/stock/counts/" >/dev/null

# 7. three litres of milk binned the next day
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"3\",\"note\":\"expired again\",\"at\":\"2026-11-25T11:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null
```

Now the online pool, as admin, so the feed has a sale and the report proves it excludes one:

```bash
A=$(csrf "$ADMIN_JAR")
curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"ONLINE\",\"type\":\"RECEIVED\",\"quantity\":\"5\",\"at\":\"2026-11-24T13:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null
curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"ONLINE\",\"type\":\"SOLD\",\"quantity\":\"1\",\"at\":\"2026-11-24T14:00:00Z\"}" \
  "$BASE/stock/movements/" >/dev/null
```

Expected: nine events in total. Seven in store A: coffee delivery 07:30, milk delivery 08:00,
waste 09:00, waste 09:30, waste 10:00, count 12:00, waste next day 11:00. Two in the online
pool: delivery 13:00 and sale 14:00.

## 9. Read the waste report for day one

```bash
START=2026-11-24T00:00:00.000Z
END=2026-11-24T23:59:59.999Z

curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END" | python3 -m json.tool
```

Expected:

- `count` is 3.
- `results` has three rows, newest first: 0.25 Milk at 10:00, 1 Coffee at 09:30, 2 Milk at
  09:00.
- `totals` has two rows, ordered by total descending: Milk `"2.25"` with 2 events, then Coffee
  `"1"` with 1 event.
- `grand_total` is `"3.25"`.
- The 12.5 delivery at 08:00, the count at 12:00, the online delivery, and the online sale do
  not appear.

Confirm the envelope cannot contradict its totals:

```bash
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("count", d["count"])
print("sum of events", sum(t["events"] for t in d["totals"]))
print("sum of totals", sum(float(t["total"]) for t in d["totals"]))
print("grand", d["grand_total"])
'
```

Expected: `count` 3 equals the sum of `events` 3, and the sum of `totals` 3.25 equals
`grand_total` 3.25.

## 10. Prove both bounds are inclusive

The 09:00 waste is exactly on the bound in each case.

```bash
# start equals the instant
curl -s -b "$MANAGER_JAR" \
  "$BASE/stock/waste/?start=2026-11-24T09:00:00Z&end=2026-11-24T09:00:00Z" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["count"], [r["at"] for r in d["results"]])'

# one millisecond after the instant, up to one millisecond before the next waste
curl -s -b "$MANAGER_JAR" \
  "$BASE/stock/waste/?start=2026-11-24T09:00:00.001Z&end=2026-11-24T09:29:59.999Z" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["count"])'

# the next waste sits exactly on the upper bound
curl -s -b "$MANAGER_JAR" \
  "$BASE/stock/waste/?start=2026-11-24T09:29:59.999Z&end=2026-11-24T09:30:00Z" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["count"])'
```

Expected: the first answers `1` with the 09:00 instant, because a window whose start equals its
end includes that instant. The second answers `0`, because nothing sits strictly between the
09:00 and 09:30 waste events. The third answers `1`, the 09:30 event, because the upper bound is
included. Together they prove both ends are inclusive, and that an instant outside the window is
excluded.

## 11. Prove the totals cover the range, not the page

```bash
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END&page_size=2" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("count",d["count"],"rows",len(d["results"]),"totals",len(d["totals"]),"grand",d["grand_total"])'

curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END&page_size=2&page=2" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("count",d["count"],"rows",len(d["results"]),"totals",len(d["totals"]),"grand",d["grand_total"])'
```

Expected: page 1 has 2 rows, page 2 has 1 row, and both carry `count` 3, the same two totals,
and `grand_total` `"3.25"`. The totals are not paginated.

## 12. Prove the item and store filters

```bash
# item filter: totals shrink with the rows
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END&product=$MILK" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("rows",len(d["results"]),"totals",[(t["total"],t["events"]) for t in d["totals"]],"grand",d["grand_total"])'

# a valid item with no events is an empty report, not an error
curl -s -o /dev/null -w '%{http_code}\n' -b "$MANAGER_JAR" \
  "$BASE/stock/waste/?start=$START&end=$END&product=000000000000000000000000"

# store filter, as the regional manager, for an empty store
login "$REGIONAL_JAR" reg@example.com 'test-password-123'
curl -s -b "$REGIONAL_JAR" "$BASE/stock/waste/?start=$START&end=$END&store=$STORE_B" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("count",d["count"],"totals",d["totals"],"grand",d["grand_total"])'
```

Expected: the item filter answers 2 rows, one total for Milk `"2.25"` with 2 events, and
`grand_total` `"2.25"`. The unknown item answers 200 with an empty report. Store B answers
`count` 0, an empty `totals`, and `"0"`.

## 13. Prove the date and scope refusals

```bash
# missing end
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START"

# start later than end
curl -s -b "$MANAGER_JAR" \
  "$BASE/stock/waste/?start=2026-11-25T00:00:00Z&end=2026-11-24T00:00:00Z"

# a manager naming a store outside their assignments
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END&store=$STORE_B"

# a malformed instant
curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=yesterday&end=$END"
```

Expected: four 400 or 403 answers, in order: `{"end": ["This field is required."]}`,
`{"end": ["The end must not be earlier than the start."]}`,
`{"detail": "This record is outside your store access."}` with no field of any row, and a
datetime format error on `start`.

## 14. Read the activity feed

```bash
login "$MANAGER_JAR" mgr@example.com 'test-password-123'
M=$(csrf "$MANAGER_JAR")

curl -s -b "$MANAGER_JAR" "$BASE/stock/activity/?page_size=2" | python3 -m json.tool
```

Expected: `count` 7, and two rows. The newest is the 2026-11-25 waste of 3, then the count at
12:00 on day one. Both are in store A.

Page through it:

```bash
for P in 1 2 3 4; do
  curl -s -b "$MANAGER_JAR" "$BASE/stock/activity/?page_size=2&page=$P" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print([(r["at"], r["kind"], r["type"]) for r in d["results"]])'
done
```

Expected: four pages, three of two and a last of one, seven distinct entries across them,
ordered by instant descending.
The kinds are mixed: `MOVEMENT` with `RECEIVED`, `WASTE`, and one `COUNT`. There is no `SOLD`,
because the sale is in the online pool, which the manager cannot see.

Confirm a page past the end is a 404:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -b "$MANAGER_JAR" "$BASE/stock/activity/?page=99"
```

Expected: 404.

## 15. Prove the online pool rule

```bash
# the regional manager reaches both stores and therefore the online pool
curl -s -b "$REGIONAL_JAR" "$BASE/stock/activity/?page_size=100" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("count",d["count"]); [print(r["pool"], r["store_id"], r["store_name"], r["type"] or r["kind"]) for r in d["results"]]'
```

Expected: `count` 9, and two rows with `pool` `ONLINE`, `store_id` null, and `store_name` null:
the sale at 14:00 and the delivery at 13:00. The manager's read above never showed them.

Naming a store excludes the online pool even for the regional manager:

```bash
curl -s -b "$REGIONAL_JAR" "$BASE/stock/activity/?store=$STORE_A&page_size=100" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["count"], {r["pool"] for r in d["results"]})'
```

Expected: `7` and only `{'BRANCH'}`.

## 16. Prove every reading role is allowed

```bash
login "$BARISTA_JAR" bar@example.com 'test-password-123'
curl -s -o /dev/null -w 'report %{http_code}\n' -b "$BARISTA_JAR" \
  "$BASE/stock/waste/?start=$START&end=$END"
curl -s -o /dev/null -w 'feed %{http_code}\n' -b "$BARISTA_JAR" \
  "$BASE/stock/activity/"
```

Expected: `report 200` and `feed 200`. A barista can already read one record's history, so FR-023
says both reads are allowed. The test suite proves the other half: with `stock.read` emptied in
the permission table, both answer 403 with the role message.

## 17. Prove the count gap is not in either read

The gap exists in the data, and neither route reports it.

```bash
STOCK_A=$(curl -s -b "$MANAGER_JAR" "$BASE/stock/?product=$MILK&store=$STORE_A" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])')

curl -s -b "$MANAGER_JAR" "$BASE/stock/$STOCK_A/events/" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("events", d["count"]); print(sorted(d["results"][0].keys()))'

curl -s -b "$MANAGER_JAR" "$BASE/stock/waste/?start=$START&end=$END" \
  | python3 -c 'import json,sys; print("report keys", sorted(json.load(sys.stdin).keys()))'
```

Expected: the history has five events, each with the M2 fields only. There is no `gap`,
`discrepancy`, or `shrinkage` key anywhere, and the report's keys are exactly `count`, `next`,
`previous`, `results`, `totals`, and `grand_total`. `derived_discrepancy` is not called by M3,
and the source scan test in step 4 enforces that.

## 18. What this proves

| Step | Criterion |
|---|---|
| 9, 10 | The report lists every waste event in the range, both bounds inclusive, and nothing outside. SC-001. |
| 9, 11 | Per item totals and the grand total agree exactly, and cover the whole range while the list paginates. FR-007, FR-008, FR-009, SC-002. |
| 12 | The item filter narrows rows and totals together, and an unknown item is empty, not an error. FR-028, FR-029. |
| 13 | Missing, inverted, and malformed bounds are refused, and a foreign store leaks nothing. FR-003, FR-021. |
| 14 | The feed mixes kinds, pages, and keeps the newest first. FR-012 to FR-018, SC-004. |
| 15 | The online pool is visible only in a scope wide read by an actor who reaches every store. FR-019, SC-003. |
| 16 | Every role that reads one record's history reads both routes. FR-022, FR-023. |
| 17 | No count gap is reported, so "total wasted" keeps its meaning. FR-004, FR-030, SC-009. |

Two things this walk does not prove, and the suite does: the stable order for two changes at the
same instant (SC-005), and the 10,000 event time bound (SC-008).

## 19. Clean up

The walk leaves rows behind. Empty the application collections before the next session, keep the
migrations:

```bash
uv run python src/manage.py shell -c "
from apps.inventory.models import Stock, StockEvent
from apps.catalog.models import Product
print('events', StockEvent.objects.all().delete())
print('stock', Stock.objects.all().delete())
print('products', Product.objects.all().delete())
"
```

Stores and accounts can stay; the next walk reuses them, or the seed step creates new ones.
