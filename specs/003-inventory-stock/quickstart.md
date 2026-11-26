# Quickstart: M2 Inventory

A runnable proof that the milestone works. Run every command from the repository root. This
guide validates the contract in `contracts/api.md`; it does not repeat the field rules, which
live there.

## Prerequisites

- Docker and Docker Compose
- `uv` installed
- Port 8000 free for the API, port 27017 free for MongoDB
- M1 already applied: the database has the identity, stores, workforce, and catalog migrations
- The mongo service runs with an open-file limit of 64000. `docker-compose.yml` sets it, because
  the default soft limit of 1024 is low enough that mongod panics under a burst of connections.
  Confirm with `docker exec coffeeshopmanagement-mongo-1 sh -c 'ulimit -Sn'`, which prints 64000.

## 1. Start MongoDB

```bash
docker compose up -d mongo
docker compose ps mongo
```

Expected: the `mongo` service is `healthy`. The healthcheck initiates the single-node replica
set, which the stock transactions require.

## 2. Apply the new migrations

```bash
uv sync
uv run python src/manage.py migrate
```

Expected: `inventory 0001_initial` and `catalog 0002_item_shape` are applied. The catalog
migration alters two fields and adds two, and the database holds no product rows, so there is
no data step.

## 3. Create the first admin

Skip this when an admin already exists.

```bash
uv run python src/manage.py create_admin --email admin@example.com --password 'change-this-now'
```

Expected: one account with role `ADMIN`.

## 4. Run the test suite and the lint gate

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Expected: the M0 and M1 suites still pass, plus the six new files: `test_stock_movements.py`,
`test_stock_pools.py`, `test_stock_counts.py`, `test_stock_scope.py`, `test_stock_low.py`, and
`test_stock_concurrency.py`. No lint findings.

The concurrency file asserts that 3 simultaneous writers all succeed, and prints the accepted
count at its higher level of 20, where a refused write is an expected outcome. Record a new
number in `research.md` R19 if it moves. Do not raise either level without reading R20 first:
the container's open-file limit is part of what makes these numbers hold.

## 5. Run the server

```bash
uv run python src/manage.py runserver 0.0.0.0:8000
```

Leave it running. The remaining steps use a second terminal.

## 6. Walk the ledger

```bash
BASE=http://127.0.0.1:8000/api
ADMIN_JAR=/tmp/coffee-admin.txt
MANAGER_JAR=/tmp/coffee-manager.txt
BARISTA_JAR=/tmp/coffee-barista.txt
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

### 6.1 As admin, create stores, products, and staff

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
BAG=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Coffee bag XYZ","unit":"pcs","price":"12.50"}' "$BASE/products/" | id_of)

MANAGER=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"mgr@example.com\",\"password\":\"test-password-123\",\"role\":\"MANAGER\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" | id_of)
BARISTA=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"bar@example.com\",\"password\":\"test-password-123\",\"role\":\"BARISTA\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" | id_of)
```

Expected: two stores, two products, two accounts. Milk carries `unit: "L"` and a threshold of
5. The coffee bag carries a price of `"12.50"`, which is the field that used to be text.

Confirm the product detail route now answers, which it could not before this feature:

```bash
curl -s -b "$ADMIN_JAR" "$BASE/products/$MILK/" | python3 -m json.tool
```

Expected: 200 with the product, including `low_stock_threshold: "5"`.

### 6.2 A manager records a delivery into their store

```bash
login "$MANAGER_JAR" mgr@example.com 'test-password-123'
M=$(csrf "$MANAGER_JAR")

curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"12.5\",\"at\":\"2026-11-26T08:00:00Z\"}" \
  "$BASE/stock/movements/" | python3 -m json.tool
```

Expected: 201 with `stock.current_stock: "12.5"` and an event whose `kind` is `MOVEMENT`, `type`
is `RECEIVED`, `by_name` names the manager, and `store_id` is store A. Read it back:

```bash
curl -s -b "$MANAGER_JAR" "$BASE/stock/" | python3 -m json.tool
```

Expected: one row, `product_name: "Milk"`, `unit: "L"`, `pool: "BRANCH"`,
`current_stock: "12.5"`, `is_low: false`.

### 6.3 Prove pool isolation

```bash
login "$ADMIN_JAR" admin@example.com 'change-this-now'
A=$(csrf "$ADMIN_JAR")

curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"ONLINE\",\"type\":\"RECEIVED\",\"quantity\":\"20\",\"at\":\"2026-11-26T08:05:00Z\"}" \
  "$BASE/stock/movements/" | python3 -m json.tool

curl -s -b "$ADMIN_JAR" "$BASE/stock/?product=$MILK" | python3 -m json.tool
```

Expected: two rows for one product. `ONLINE` reads `"20"`, and store A still reads `"12.5"`.
Neither operation changed the other. This is SC-001 and invariant I2.

### 6.4 Prove waste, the overdraw refusal, and the sale rule

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"2\",\"note\":\"expired on Tuesday\",\"at\":\"2026-11-26T09:00:00Z\"}" \
  "$BASE/stock/movements/" | python3 -m json.tool
```

Expected: 201, store A now reads `"10.5"`.

Three refusals, each a 400:

```bash
# more than is on the shelf
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"999\",\"note\":\"typo\"}" \
  "$BASE/stock/movements/"

# waste with no note
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"WASTE\",\"quantity\":\"1\"}" \
  "$BASE/stock/movements/"

# a sale in a store pool, while no point of sale exists
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"SOLD\",\"quantity\":\"1\"}" \
  "$BASE/stock/movements/"
```

Expected: three 400s naming `quantity`, `note`, and `type`. Read the stock again and confirm it
still reads `"10.5"`, so a refused request changed nothing.

### 6.5 Prove a count reconciles a shelf discrepancy

The shelf really holds 9 litres, but the movements predict 10.5.

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"counted\":\"9\",\"note\":\"counted the shelf\",\"at\":\"2026-11-26T10:00:00Z\"}" \
  "$BASE/stock/counts/" | python3 -m json.tool
```

Expected: 201, and the stock object now reads `current_stock: "9"` and `last_count: "9"`. Now a
delivery applies on top of the count, not on top of the old number:

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"1\",\"at\":\"2026-11-26T11:00:00Z\"}" \
  "$BASE/stock/movements/" | python3 -m json.tool
```

Expected: `current_stock: "10"`.

Prove the discrepancy is derivable and not stored. Read the history:

```bash
curl -s -b "$MANAGER_JAR" "$BASE/stock/?product=$MILK" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["id"])' > /tmp/stock_a.txt
STOCK_A=$(cat /tmp/stock_a.txt)
curl -s -b "$MANAGER_JAR" "$BASE/stock/$STOCK_A/events/" | python3 -m json.tool
```

Expected: four events, newest first: the delivery of 1, the count of 9, the waste of 2, the
delivery of 12.5. No event has a negative quantity, and no event type expresses the gap. The
gap is `predicted - counted`, which is 10.5 minus 9, or 1.5, and it is visible only by reading
the two numbers.

Confirm the newest count now guards the baseline. This is refused, because the instant precedes
the count:

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"1\",\"at\":\"2026-11-26T09:30:00Z\"}" \
  "$BASE/stock/movements/"
```

Expected: 400 naming `at`.

### 6.6 Prove low stock

Milk is at 10 with a threshold of 5, so it is not low. Push it below:

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"counted\":\"4\",\"at\":\"2026-11-26T12:00:00Z\"}" \
  "$BASE/stock/counts/" >/dev/null

curl -s -b "$MANAGER_JAR" "$BASE/stock/low/" | python3 -m json.tool
```

Expected: one row, Milk, `current_stock: "4"`, `is_low: true`.

Now set the shelf exactly at the threshold:

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"counted\":\"5\",\"at\":\"2026-11-26T12:10:00Z\"}" \
  "$BASE/stock/counts/" >/dev/null

curl -s -b "$MANAGER_JAR" "$BASE/stock/low/"
```

Expected: an empty list, because low is strictly below.

Clear the threshold as admin, and confirm nothing is ever reported as low again:

```bash
curl -s -b "$ADMIN_JAR" -X PATCH -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"low_stock_threshold":null}' "$BASE/products/$MILK/" | python3 -m json.tool

curl -s -b "$MANAGER_JAR" "$BASE/stock/low/"
```

Expected: 200 with `low_stock_threshold: null`, then an empty list.

### 6.7 Prove scope and the online pool

```bash
# a barista reads their own store
login "$BARISTA_JAR" bar@example.com 'test-password-123'
curl -s -b "$BARISTA_JAR" "$BASE/stock/" | python3 -m json.tool

# a barista may not record
B=$(csrf "$BARISTA_JAR")
curl -s -b "$BARISTA_JAR" -H "X-CSRFToken: $B" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_A\",\"type\":\"RECEIVED\",\"quantity\":\"1\"}" \
  "$BASE/stock/movements/"

# a manager may not reach the online pool
curl -s -b "$MANAGER_JAR" "$BASE/stock/?pool=ONLINE"

# a manager may not record into another store
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"product\":\"$MILK\",\"pool\":\"BRANCH\",\"store\":\"$STORE_B\",\"type\":\"RECEIVED\",\"quantity\":\"1\"}" \
  "$BASE/stock/movements/"
```

Expected: the barista sees store A's row and not the online row, which means the online pool is
invisible below regional manager. Then three 403s, each with the message that matches the
reason: the role, the store access, and the store access again. No field of a refused record
appears in any response.

### 6.8 Prove the catalog guard

A manager may not write the catalog:

```bash
curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d '{"name":"Manager tea"}' "$BASE/products/"
```

Expected: 403 with `{"detail": "Your role may not perform this action."}` Before this feature
any signed-in account could create a product.

A regional manager may, because the region buys the stock:

```bash
RM=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"reg@example.com\",\"password\":\"test-password-123\",\"role\":\"REGIONAL_MANAGER\",\"store_ids\":[\"$STORE_A\",\"$STORE_B\"]}" \
  "$BASE/accounts/" | id_of)
RM_JAR=/tmp/coffee-regional.txt
login "$RM_JAR" reg@example.com 'test-password-123'
R=$(csrf "$RM_JAR")

curl -s -b "$RM_JAR" -H "X-CSRFToken: $R" -H 'Content-Type: application/json' \
  -d '{"name":"Oat milk","unit":"L","low_stock_threshold":"3"}' "$BASE/products/" \
  | python3 -m json.tool
```

Expected: 201, and the new product carries a threshold of 3.

## 7. What this proves

| Step | Criterion |
|---|---|
| 6.2, 6.5 | A delivery raises the number and a count reconciles a discrepancy. M2 exit criteria. |
| 6.3 | The online pool and a branch pool move independently, and no operation touches two pools. SC-001, I2. |
| 6.4 | Waste needs a note, an overdraw is refused, and a branch sale is refused while no point of sale exists. FR-009, FR-012, FR-013. |
| 6.5 | The baseline resets at a count, a backdated movement is refused, and the gap is derived rather than stored. FR-016, FR-014, FR-019. |
| 6.6 | Low means strictly below, no threshold means never low, and equality is not low. FR-041, FR-042. |
| 6.7 | Store scope holds, and a suspended role cannot write. SC-005, I1. |
| 6.8 | Catalog writes are ADMIN and REGIONAL_MANAGER only, and the product detail route works. FR-040, R11. |

Two things this walk does not prove, and the test suite does:

- The number and the event commit together under a crash. That needs a transaction test.
- Concurrent writers do not lose an update. That needs threads, and it is `test_stock_concurrency.py`.

## 8. Clean up

The walk leaves rows behind. Empty the application collections before the next session, keep
the migrations:

```bash
uv run python src/manage.py shell -c "
from apps.inventory.models import Stock, StockEvent
from apps.catalog.models import Product
print('events', StockEvent.objects.all().delete())
print('stock', Stock.objects.all().delete())
print('products', Product.objects.all().delete())
"
```
