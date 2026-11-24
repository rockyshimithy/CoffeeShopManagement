# Quickstart: M0 Foundation

A runnable proof that the milestone works. Run every command from the repository root.

## Prerequisites

- Docker and Docker Compose
- `uv` installed
- Port 8000 free for the API, port 27017 free for MongoDB

## 1. Start MongoDB

```bash
docker compose up -d mongo
docker compose ps mongo
```

Expected: the `mongo` service is `healthy`. The healthcheck initiates the single-node replica set.

## 2. Install dependencies and migrate

```bash
uv sync
uv run python src/manage.py migrate
```

Expected: no error, and `src/mongo_migrations/` holds the admin, auth, and contenttypes migrations.

## 3. Create the first admin

```bash
uv run python src/manage.py create_admin --email admin@example.com --password 'change-this-now'
```

Expected: one account with role `ADMIN` and `is_active` true. Running the command again refuses, because an active admin exists.

## 4. Run the server

```bash
uv run python src/manage.py runserver 0.0.0.0:8000
```

Leave it running. The remaining steps use a second terminal.

## 5. Walk the access rules

Use a cookie jar so the session survives between calls.

```bash
BASE=http://127.0.0.1:8000/api
JAR=/tmp/coffee-cookies.txt
```

### 5.1 Sign in as admin and create two stores

```bash
curl -s -c "$JAR" -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"change-this-now"}' \
  "$BASE/auth/login/"

CSRF=$(awk '/csrftoken/ {print $7}' "$JAR")

curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"name":"Downtown","address":"12 Main Street","postal_code":"12345"}' \
  "$BASE/stores/"

curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"name":"Riverside","address":"9 River Road","postal_code":"12346"}' \
  "$BASE/stores/"
```

Note the two store ids from the responses. They are needed below.

### 5.2 Create a manager for Downtown only

```bash
curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"email":"manager@example.com","password":"change-this-now","role":"MANAGER","store_ids":["<DOWNTOWN_ID>"]}' \
  "$BASE/accounts/"
```

Expected: 201, and `store_ids` contains exactly Downtown.

### 5.3 Sign in as the manager and prove scoping

```bash
MJAR=/tmp/coffee-manager-cookies.txt
curl -s -c "$MJAR" -H 'Content-Type: application/json' \
  -d '{"email":"manager@example.com","password":"change-this-now"}' \
  "$BASE/auth/login/"

MCSRF=$(awk '/csrftoken/ {print $7}' "$MJAR")

curl -s -b "$MJAR" "$BASE/stores/"
```

Expected: exactly one store, Downtown.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -b "$MJAR" "$BASE/stores/<RIVERSIDE_ID>/"
```

Expected: `403`. The body is `{"detail": "This record is outside your store access."}`.

### 5.4 Prove a manager cannot escalate

```bash
curl -s -o /dev/null -w '%{http_code}\n' -b "$MJAR" -H "X-CSRFToken: $MCSRF" \
  -H 'Content-Type: application/json' \
  -d '{"role":"ADMIN"}' "$BASE/accounts/<MANAGER_ID>/"
```

Expected: `403`. The manager role is unchanged.

### 5.5 Create a regional manager and a third store

```bash
curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"email":"regional@example.com","password":"change-this-now","role":"REGIONAL_MANAGER","store_ids":[]}' \
  "$BASE/accounts/"
```

Expected: the returned `store_ids` already contains Downtown and Riverside, even though the request sent an empty list.

```bash
curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"name":"Harbor","address":"1 Dock Lane","postal_code":"12347"}' \
  "$BASE/stores/"
```

Sign in as the regional manager and list stores. Expected: all three, including Harbor, with no assignment step.

### 5.6 Add an employee profile

```bash
curl -s -b "$JAR" -H "X-CSRFToken: $CSRF" -H 'Content-Type: application/json' \
  -d '{"user_id":"<MANAGER_ID>","hire_date":"2026-11-01"}' \
  "$BASE/employees/"
```

Expected: 201 with the profile. As the manager, `GET /api/employees/` shows it. As a barista in another store, it does not appear.

## 6. Run the tests

```bash
uv run pytest
```

Expected: all pass. The suite covers:

- sign in, wrong password, deactivated account
- duplicate email
- manager and regional manager account authority
- last active admin guard
- two-store leakage count of exactly zero
- cross-store request returns 403 with no record fields
- manager with no store assignments gets an empty list
- store creation propagation and store deletion cleanup
- barista read-only behavior

## 7. Stop

```bash
docker compose down
```

The database volume is kept for the next run. Add `-v` only when you want a clean database, and know that it deletes all local data.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ServerSelectionTimeoutError` | MongoDB not running or not ready | `docker compose up -d mongo`, then `docker compose ps mongo` |
| `Transaction numbers are only allowed on a replica set` | The healthcheck did not initiate `rs0` | Recreate the container and check `docker compose logs mongo` |
| 403 on every unsafe request | Missing `X-CSRFToken` | Read the `csrftoken` cookie and send it in the header |
| 401 right after login | Cookie jar not reused | Pass `-b "$JAR"` on every call after sign in |
