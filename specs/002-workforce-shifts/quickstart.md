# Quickstart: M1 Workforce

A runnable proof that the milestone works. Run every command from the repository root.
This guide validates the contract in `contracts/api.md`; it does not repeat the field
rules, which live there.

## Prerequisites

- Docker and Docker Compose
- `uv` installed
- Port 8000 free for the API, port 27017 free for MongoDB
- M0 already applied: the database holds an admin account, or step 3 creates one

## 1. Start MongoDB

```bash
docker compose up -d mongo
docker compose ps mongo
```

Expected: the `mongo` service is `healthy`. The healthcheck initiates the single-node
replica set, which the shift transactions require.

## 2. Install dependencies and migrate

```bash
uv sync
uv run python src/manage.py migrate
```

Expected: no error, and a new `workforce` migration is applied. The `workforce` app has an
empty `models.py` today, so this is the first migration in that app.

## 3. Create the first admin

```bash
uv run python src/manage.py create_admin --email admin@example.com --password 'change-this-now'
```

Expected: one account with role `ADMIN`. Running the command again refuses, because an
active admin exists.

## 4. Run the test suite

```bash
uv run pytest
```

Expected: the M0 suites plus the M1 suites pass. The M1 files are `tests/test_shifts.py`,
`tests/test_shift_scope.py`, and `tests/test_shift_cache.py`. The suite needs MongoDB up;
Django creates and drops a `test_` database.

Lint gate:

```bash
uv run ruff check . && uv run ruff format --check .
```

Expected: no findings. The `M1` scope is one new app, one new migration, three new test
files, and one change in `tests/test_accounts.py`.

## 5. Run the server

```bash
uv run python src/manage.py runserver 0.0.0.0:8000
```

Leave it running. The remaining steps use a second terminal.

## 6. Walk the rota

Use a cookie jar so sessions survive between calls, and one helper for reads.

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

The `csrf` helper prints the token the unsafe calls need in `X-CSRFToken`.

### 6.1 As admin, create two stores and three accounts

```bash
login "$ADMIN_JAR" admin@example.com 'change-this-now'
A=$(csrf "$ADMIN_JAR")

STORE_A=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Downtown"}' "$BASE/stores/" | id_of)
STORE_B=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d '{"name":"Riverside"}' "$BASE/stores/" | id_of)

MANAGER=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"mgr@example.com\",\"password\":\"test-password-123\",\"role\":\"MANAGER\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" | id_of)
BARISTA=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"bar@example.com\",\"password\":\"test-password-123\",\"role\":\"BARISTA\",\"store_ids\":[\"$STORE_A\"]}" \
  "$BASE/accounts/" | id_of)
FOREIGN=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"riv@example.com\",\"password\":\"test-password-123\",\"role\":\"BARISTA\",\"store_ids\":[\"$STORE_B\"]}" \
  "$BASE/accounts/" | id_of)
```

Expected: two stores and three accounts exist. `Riverside` now sits in every regional
manager's assignments, per the M0 propagation rule.

### 6.2 Create employee profiles

A shift references an employee profile, not an account.

```bash
EMP=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$BARISTA\",\"hire_date\":\"2026-11-01\"}" "$BASE/employees/" | id_of)
```

Expected: a 201 and an employee id.

### 6.3 As the manager, fill the rota

```bash
login "$MANAGER_JAR" mgr@example.com 'test-password-123'
M=$(csrf "$MANAGER_JAR")

SHIFT=$(curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-11-30T08:00:00Z\",\"ends_at\":\"2026-11-30T16:00:00Z\"}" \
  "$BASE/shifts/" | id_of)
echo "$SHIFT"
```

Expected: a 201 and a shift id.

### 6.4 As the barista, read the schedule

```bash
login "$BARISTA_JAR" bar@example.com 'test-password-123'
curl -s -b "$BARISTA_JAR" "$BASE/shifts/" | python3 -m json.tool
```

Expected: the shift appears with `employee_name`, `store_name`, and both instants ending in
`Z`. If the current week is not the week of 2026-11-30, pass the window explicitly:

```bash
curl -s -b "$BARISTA_JAR" "$BASE/shifts/?from=2026-11-30T00:00:00Z&to=2026-12-07T00:00:00Z"
```

### 6.5 Prove the four refusals

```bash
post_shift() {
  curl -s -o /tmp/shift-body.json -w '%{http_code}\n' -b "$MANAGER_JAR" \
    -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
    -d "$1" "$BASE/shifts/"
  cat /tmp/shift-body.json; echo
}
```

Overlap, same employee, same day:

```bash
post_shift "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-11-30T15:00:00Z\",\"ends_at\":\"2026-11-30T20:00:00Z\"}"
```

Expected: `400` and an overlap message naming `starts_at` or `ends_at`.

Touching endpoints are allowed, and this is the proof:

```bash
post_shift "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-11-30T16:00:00Z\",\"ends_at\":\"2026-11-30T20:00:00Z\"}"
```

Expected: `201`.

Crossing midnight:

```bash
post_shift "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-12-01T19:00:00Z\",\"ends_at\":\"2026-12-02T07:00:00Z\"}"
```

Expected: `400`.

More than 12 hours:

```bash
post_shift "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-12-01T07:00:00Z\",\"ends_at\":\"2026-12-01T20:00:00Z\"}"
```

Expected: `400`. A 12 hour shift, 08:00 to 20:00, returns `201`.

An employee from another store:

```bash
post_shift "{\"employee_id\":\"$FOREIGN\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-12-02T08:00:00Z\",\"ends_at\":\"2026-12-02T16:00:00Z\"}"
```

Expected: `400`, because that account is not assigned to `Downtown`.

### 6.6 Prove scope, edit, and delete

A manager of `Downtown` asking for a `Riverside` shift is refused:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -b "$MANAGER_JAR" \
  "$BASE/shifts/?store=$STORE_B"
```

Expected: `403`.

Edit the shift's start, then delete it:

```bash
curl -s -X PATCH -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d '{"starts_at":"2026-11-30T09:00:00Z"}' "$BASE/shifts/$SHIFT/"
```

Expected: `200`. Edit the start and not the end here, because step 6.5 already stored a
16:00 to 20:00 shift for the same employee, so moving the end to 17:00 is a correct `400`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE -b "$MANAGER_JAR" \
  -H "X-CSRFToken: $M" "$BASE/shifts/$SHIFT/"

curl -s -o /dev/null -w '%{http_code}\n' -b "$MANAGER_JAR" "$BASE/shifts/$SHIFT/"
```

Expected: `204`, then `404`.

Changing the employee is a `400`:

```bash
curl -s -X PATCH -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"employee_id\":\"$FOREIGN\"}" "$BASE/shifts/$SHIFT/"
```

Expected: `400` with a message under `employee_id`.

### 6.7 Prove the cache

Read the same window twice, then write, then read again.

```bash
WINDOW="from=2026-12-07T00:00:00Z&to=2026-12-14T00:00:00Z"
curl -s -b "$BARISTA_JAR" "$BASE/shifts/?$WINDOW" | python3 -c 'import json,sys; print(json.load(sys.stdin)["count"])'

curl -s -b "$MANAGER_JAR" -H "X-CSRFToken: $M" -H 'Content-Type: application/json' \
  -d "{\"employee_id\":\"$EMP\",\"store_id\":\"$STORE_A\",\"starts_at\":\"2026-12-07T08:00:00Z\",\"ends_at\":\"2026-12-07T16:00:00Z\"}" \
  "$BASE/shifts/" >/dev/null

curl -s -b "$BARISTA_JAR" "$BASE/shifts/?$WINDOW" | python3 -c 'import json,sys; print(json.load(sys.stdin)["count"])'
```

Expected: the first count, then the same count plus one. The second read must not serve the
earlier stored copy. To confirm the cache is really in use rather than never hit, check that
`workforce_schedulesnapshot` has one row for the window after the first read:

```bash
docker compose exec mongo mongosh coffeeshop --quiet \
  --eval 'db.workforce_schedulesnapshot.countDocuments({})'
```

Expected: a number of at least 1, because the second read of an unchanged window lands on a
stored copy.

### 6.8 Prove the account cascade

FR-026 is the only new identity route. Prove the guard first, then the cascade.

```bash
SELF=$(curl -s -b "$ADMIN_JAR" "$BASE/auth/me/" | id_of)

curl -s -o /tmp/self.json -w '%{http_code}\n' -X DELETE -b "$ADMIN_JAR" \
  -H "X-CSRFToken: $A" "$BASE/accounts/$SELF/"
cat /tmp/self.json; echo
```

Expected: `403` and the last active admin message. Nothing is removed.

Now an account that has a profile and a shift in Riverside, which the admin may reach and
the Downtown manager may not:

```bash
GONE=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"email\":\"gone@example.com\",\"password\":\"test-password-123\",\"role\":\"BARISTA\",\"store_ids\":[\"$STORE_B\"]}" \
  "$BASE/accounts/" | id_of)
GONE_EMP=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$GONE\",\"hire_date\":\"2026-11-01\"}" "$BASE/employees/" | id_of)
GONE_SHIFT=$(curl -s -b "$ADMIN_JAR" -H "X-CSRFToken: $A" -H 'Content-Type: application/json' \
  -d "{\"employee_id\":\"$GONE_EMP\",\"store_id\":\"$STORE_B\",\"starts_at\":\"2026-12-03T08:00:00Z\",\"ends_at\":\"2026-12-03T16:00:00Z\"}" \
  "$BASE/shifts/" | id_of)

curl -s -o /dev/null -w '%{http_code}\n' -X DELETE -b "$ADMIN_JAR" \
  -H "X-CSRFToken: $A" "$BASE/accounts/$GONE/"

curl -s -o /dev/null -w '%{http_code}\n' -b "$ADMIN_JAR" "$BASE/shifts/$GONE_SHIFT/"
curl -s -o /dev/null -w '%{http_code}\n' -b "$ADMIN_JAR" "$BASE/accounts/$GONE/"
```

Expected: `204`, then `404`, then `404`. The account, the profile, and the shift left
together. The concurrent case, two admins deleting each other at the same instant, cannot be
driven from curl; `tests/test_accounts.py` proves it and asserts exactly one active admin
survives.

### 6.9 Prove the store cascade

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE -b "$ADMIN_JAR" \
  -H "X-CSRFToken: $A" "$BASE/stores/$STORE_A/"

curl -s -b "$BARISTA_JAR" "$BASE/shifts/?from=2026-11-01T00:00:00Z&to=2026-12-01T00:00:00Z" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["count"])'
```

Expected: `204`, then `0`. Deleting the store removed its shifts in the same operation.

## 7. What this proves

| Step | Requirement |
|---|---|
| 6.3, 6.4 | FR-001, FR-016, FR-021, SC-001 |
| 6.5 overlap, touching, midnight, 12 hours, foreign employee | FR-003 to FR-008, SC-003 |
| 6.6 scope, edit in time only, delete | FR-010, FR-014, FR-023 |
| 6.7 cache | FR-022, SC-005 |
| 6.8 account cascade and last admin guard | FR-025, FR-026, FR-027, FR-028, SC-007 |
| 6.9 store cascade | FR-024 |
| the concurrent admin test in `tests/test_accounts.py` | FR-027, SC-008 |
| the concurrent overlap test in `tests/test_shifts.py` | FR-009, SC-004 |

FR-025 also holds when nothing deletes the account through the API, because it is a model
level cascade. The suite proves that separate path directly in `tests/test_accounts.py`,
next to the last admin guard that already lives there.
