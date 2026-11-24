# API Contract: M0 Foundation

Base path: `/api/`. Body and response format: JSON. Identifiers are 24 character ObjectId hex strings.

## Common rules

- Every endpoint except `POST /api/auth/login/` requires an authenticated session. Missing or invalid session returns 401.
- Unsafe methods (POST, PATCH, DELETE) require the `X-CSRFToken` header after sign in.
- A store-owned record outside the actor's assignments returns 403 with:
  `{"detail": "This record is outside your store access."}`
- A role that may not perform the action returns 403 with:
  `{"detail": "Your role may not perform this action."}`
- Validation errors return 400 with a field map, for example `{"email": ["An account with this email already exists."]}`.
- Lists are paginated with `?page=` and `?page_size=` (default 20, maximum 100). List responses are `{"count": n, "next": url|null, "previous": url|null, "results": [...]}`.
- No response ever contains a password.

## Objects

### Account

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d0",
  "email": "ana@example.com",
  "role": "MANAGER",
  "store_ids": ["65f1c0a2b3d4e5f6a7b8c9d1"],
  "is_active": true,
  "first_name": "Ana",
  "last_name": "Silva",
  "date_joined": "2026-11-24T12:00:00Z"
}
```

### Employee

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "user_id": "65f1c0a2b3d4e5f6a7b8c9d0",
  "user_email": "ana@example.com",
  "user_name": "Ana Silva",
  "hire_date": "2026-11-01"
}
```

### Store

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d1",
  "name": "Downtown",
  "address": "12 Main Street",
  "postal_code": "12345"
}
```

## Authentication

### POST /api/auth/login/

Request: `{"email": "ana@example.com", "password": "..."}`

Responses:

- 200 with the Account object and a `sessionid` cookie.
- 400 when a field is missing.
- 401 with `{"detail": "Invalid email or password."}` for both unknown email and wrong password.

### POST /api/auth/logout/

Responses: 204. The session is destroyed.

### GET /api/auth/me/

Responses: 200 with the caller's Account object. 401 when not signed in.

### PATCH /api/auth/me/

Accepted fields: `email`, `password`, `first_name`, `last_name`. `role`, `store_ids`, and `is_active` are read only here and return 400 if sent.

Responses: 200 with the updated Account object. 400 on validation failure.

## Accounts

Permission source: the matrix in `spec.md`, rows for staff accounts.

| Method | Path | ADMIN | REGIONAL_MANAGER | MANAGER | Others |
|---|---|---|---|---|---|
| GET | `/api/accounts/` | all | all | own stores, BARISTA and SUPERVISOR, plus self | 403 |
| POST | `/api/accounts/` | any role | BARISTA, SUPERVISOR | BARISTA, SUPERVISOR in own stores | 403 |
| GET | `/api/accounts/{id}/` | all | all | in scope, plus self | 403 or 403 cross-store |
| PATCH | `/api/accounts/{id}/` | all | BARISTA, SUPERVISOR | BARISTA, SUPERVISOR in own stores | 403 |

### GET /api/accounts/

Filters: `role`, `is_active`, `store` (store id). Ordering: email ascending. Manager results are limited to accounts whose `store_ids` overlap the manager's stores, plus the manager's own account.

### POST /api/accounts/

Request fields:

| Field | Required | Rules |
|---|---|---|
| `email` | yes | Unique after lowercasing and trimming |
| `password` | yes | Django password validators |
| `role` | yes | One of the five roles, limited by the actor's authority |
| `store_ids` | no | Default empty. Each id must exist. Manager may only use own stores |
| `first_name`, `last_name` | no | Free text |

Responses: 201 with the Account object. 400 on validation failure. 403 when the actor may not grant that role or store.

### GET /api/accounts/{id}/

Responses: 200 with the Account object. 403 for a cross-store target. 404 for a missing id.

### PATCH /api/accounts/{id}/

Accepted fields: `email`, `password`, `role`, `store_ids`, `is_active`, `first_name`, `last_name`. Partial update.

Responses: 200 with the Account object. 400 for a duplicate email, an unknown role, or an unknown store. 403 for role or store escalation, and for deactivating or demoting the last active admin.

Deactivation is `PATCH` with `{"is_active": false}`. There is no DELETE on accounts.

## Stores

Permission source: the matrix in `spec.md`, rows for stores.

| Method | Path | ADMIN | REGIONAL_MANAGER | MANAGER, SUPERVISOR, BARISTA |
|---|---|---|---|---|
| GET | `/api/stores/` | all | all assigned (every store) | own stores |
| POST | `/api/stores/` | yes | yes | 403 |
| GET | `/api/stores/{id}/` | all | all assigned | own stores |
| PATCH | `/api/stores/{id}/` | yes | yes | 403 |
| DELETE | `/api/stores/{id}/` | yes | 403 | 403 |

### GET /api/stores/

Ordering: name ascending. A regional manager sees every store because every store id is in `store_ids`, not because of an exemption.

### POST /api/stores/

Request: `{"name": "...", "address": "...", "postal_code": "..."}`. Name is required.

Side effects: the new id is appended to every regional manager's `store_ids`, and to the creator's assignments when the creator is a regional manager.

Responses: 201 with the Store object. The next request from every regional manager includes it.

### PATCH /api/stores/{id}/

Accepted fields: `name`, `address`, `postal_code`. Renaming is allowed for ADMIN and REGIONAL_MANAGER.

Responses: 200 with the Store object. 403 for a store outside the actor's access.

### DELETE /api/stores/{id}/

ADMIN only.

Side effects: the id is removed from every user's `store_ids`.

Responses: 204. 403 for non-admin.

## Employees

| Method | Path | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|---|
| GET | `/api/employees/` | all | all | own stores | own stores | own stores, names only |
| POST | `/api/employees/` | yes | yes | own stores | 403 | 403 |
| GET | `/api/employees/{id}/` | all | all | own stores | own stores | own stores, names only |
| PATCH | `/api/employees/{id}/` | yes | yes | own stores | 403 | 403 |

### GET /api/employees/

Filters: `store` (store id). Ordering: `hire_date` descending. For a BARISTA the response keeps `id`, `user_id`, `user_name`, and `hire_date` and omits `user_email`. This is the "names only" rule in the matrix.

### POST /api/employees/

Request: `{"user_id": "...", "hire_date": "YYYY-MM-DD"}`. The user must exist and must not already have an employee profile.

Responses: 201 with the Employee object. 400 for a missing user or a duplicate profile. 403 when the target user is outside the actor's stores.

### GET /api/employees/{id}/

Responses: 200 with the Employee object. 403 cross-store. 404 missing.

### PATCH /api/employees/{id}/

Accepted field: `hire_date`.

Responses: 200 with the Employee object. 403 when outside the actor's stores.

## Status code summary

| Code | When |
|---|---|
| 200 | Successful read or update |
| 201 | Successful creation |
| 204 | Successful logout or store deletion |
| 400 | Validation failure, duplicate email, unknown role, unknown store, read-only field sent |
| 401 | No session, expired session, invalid credentials, deactivated account |
| 403 | Role not allowed, store out of scope, last admin guard |
| 404 | Record does not exist |
