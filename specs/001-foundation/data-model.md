# Data Model: M0 Foundation

Three collections change or appear in this milestone. `catalog` keeps its current shape and is not store owned.

## User, collection `identity_user`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key, `ObjectIdAutoField` |
| `email` | string | Unique, indexed, stored lowercase with no surrounding spaces. Login identifier (`USERNAME_FIELD`). |
| `password` | string | Django password hash. Never serialized. |
| `role` | string | One of `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`, `BARISTA`. Required. |
| `store_ids` | array of ObjectId | Default empty list. Every id must reference an existing store. Multikey index. |
| `is_active` | boolean | Default true. False blocks sign in and every authenticated request. |
| `is_staff` | boolean | True only for `ADMIN`. Grants Django admin site access, not business permission. |
| `is_superuser` | boolean | True only for `ADMIN`. Django admin needs it to manage accounts. |
| `first_name`, `last_name` | string | Optional, inherited from `AbstractUser`. |
| `date_joined`, `last_login` | datetime | Inherited. |

`username` is removed. `USERNAME_FIELD = "email"` and `REQUIRED_FIELDS = []`.

### Indexes

- Unique index on `email`.
- Multikey index on `store_ids`, used by `contains` and `overlap`.
- Compound index on `(role, is_active)` for the account list filters.

### Validation rules

- Role must be one of the five values. Anything else is a 400 and nothing is stored.
- Email must be unique after lowercasing and trimming.
- Every id in `store_ids` must reference an existing store.
- A manager may only assign stores the manager already has.
- A manager and a regional manager may not create or change an `ADMIN` or `REGIONAL_MANAGER` account.
- The last active `ADMIN` may not be deactivated or demoted.
- Passwords are validated by Django's password validators and only stored as a hash.

## Employee, collection `identity_employee`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key |
| `user` | one-to-one reference to `User` | Required, unique, cascade on user delete |
| `hire_date` | date | Required |

### Indexes

- Unique index on `user`, created by the one-to-one relation.

An employee profile carries no credentials, no role, and no store field. Scope comes from the linked user's `store_ids`.

## Store, collection `stores_store`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key |
| `name` | string | Required, max 40 |
| `address` | string | Max 100 |
| `postal_code` | string | Max 10 |

No `manager` field. Manager access comes from `role` plus `store_ids`, per macro decision 23.

### Indexes

- Index on `name` for the store list ordering.

## Access rules

One helper module, `src/apps/identity/permissions.py`, is the only place a role value decides an outcome.

```python
ACTIONS = {
    "store.create", "store.change", "store.delete",
    "account.create", "account.change", "account.deactivate",
    "employee.read", "employee.create", "employee.change",
    "shift.schedule",
}

def can(actor: User, action: str, store_id: ObjectId | None = None) -> bool: ...
def scope_stores(queryset, actor: User, field: str = "store_id"): ...
def require_store_access(actor: User, store_id: ObjectId) -> None: ...
```

Rules:

- `can()` returns true for `ADMIN` on every action and every store.
- `REGIONAL_MANAGER` passes the store check through `store_ids__contains=[store_id]`, exactly like every other role. There is no second bypass.
- `reshape` is not a concept here. Scope is a filter on `store_ids`.
- `require_store_access()` raises DRF `PermissionDenied` with `{"detail": "This record is outside your store access."}`.
- Catalog endpoints never call the helper's store check, because a catalog item has no store.
- A user with an empty `store_ids` gets an empty queryset, never an error.

## State transitions

### Account lifecycle

1. Created active by an admin, regional manager, or manager within their authority.
2. Role or `store_ids` changed by an allowed actor. Applies on the next request, because every request reloads the user.
3. Deactivated. Sign in is refused, and the next authenticated request is refused.
4. Reactivated by an allowed actor.

Guards: the last active `ADMIN` cannot be deactivated or demoted. A manager cannot escalate to `ADMIN` or grant a store outside their own.

### Store lifecycle

1. Created by `ADMIN` or `REGIONAL_MANAGER`. If the creator is a regional manager, the new id is added to their assignments.
2. Every existing `REGIONAL_MANAGER` gets the new id appended to `store_ids`.
3. Renamed by `ADMIN` or `REGIONAL_MANAGER`.
4. Deleted by `ADMIN` only. Deletion removes the id from every user's `store_ids` through `identity.services.remove_store_from_all_users(store_id)`.

### Employee profile lifecycle

1. Created for an existing account, by `ADMIN`, `REGIONAL_MANAGER`, or `MANAGER` inside their stores.
2. Hire date changed by the same actors.
3. Never a login. No password, no role.

## Invariants checked in this milestone

| Invariant | Where it is enforced |
|---|---|
| I1, store scoped access | `permissions.scope_stores` on every store-owned queryset, plus a two-store leakage test |
| I3, one item identity | Catalog stays global and unfiltered; no copy of item data outside `catalog` |
| Role authority | `permissions.can`, plus tests for manager and regional manager escalation attempts |
| Last admin guard | Account service, plus a test that deactivation and demotion both fail |
| Regional manager coverage | Store service propagation, plus a test that a store created after the account is visible |
