# Data Model: M1 Workforce

Three collections. `Shift` is the feature. `ScheduleRevision` and `ScheduleSnapshot` are
internal bookkeeping for the write guard and the schedule cache; they are never exposed on
an endpoint.

Everything reuses the M0 engine rules: `ObjectIdAutoField` primary keys, references as
ObjectIds, no `prefetch_related`, and writes inside `django_mongodb_backend.transaction.atomic`.

## Shift, collection `workforce_shift`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key, `ObjectIdAutoField` |
| `employee` | reference to `identity.Employee` | Required. Cascade on employee delete, which also cascades from account delete through the profile. |
| `store` | reference to `stores.Store` | Required. Cascade on store delete. The unit of scope. |
| `starts_at` | datetime | Required. Stored as UTC. |
| `ends_at` | datetime | Required. Stored as UTC. Must be later than `starts_at`. |

No `duration` field, no break fields, no `status`, no soft delete. A shift is a single
interval, per the spec's assumptions.

The model declares the relations with string labels, `"identity.Employee"` and
`"stores.Store"`, so `workforce` imports no other context's model
(see `research.md` R1).

### Indexes

| Index | Serves |
|---|---|
| `(store_id, starts_at)` | The schedule read and its window range. Required by decision 20 and the constitution. |
| `(employee_id, starts_at)` | The overlap check on create and edit. |

### Validation rules

| Rule | Requirement | Where |
|---|---|---|
| `ends_at` strictly later than `starts_at` | FR-003 | `validate_shift_window` |
| `starts_at` and `ends_at` on the same calendar day in the project time zone | FR-004 | `validate_shift_window` |
| Span at most 12 hours, exactly 12 allowed | FR-005 | `validate_shift_window` |
| No overlap with another shift of the same employee, in any store | FR-006, FR-007 | `validate_shift_window`, inside the write transaction |
| The employee already has the shift's store in their `store_ids` | FR-008 | `identity.services.employee_store_ids` |
| Edit changes only `starts_at` and `ends_at` | FR-010 | Serializer fields |

Overlap means `starts_at < other.ends_at AND ends_at > other.starts_at`. Touching
endpoints are allowed. The shift being edited is excluded from its own check.

A validation failure is a 400 with a field map. Nothing is stored and no revision is
bumped, because the transaction aborts.

### Write path

```text
retry_on_conflict(operation)
  operation:
    with atomic():
      stores = employee_store_ids(employee_id)      # 400 when None
      require the shift's store in stores            # 400 when missing
      bump ScheduleRevision for every store in stores  # serializes per employee
      validate_shift_window(..., exclude_pk=None)    # 400 on overlap or bad span
      Shift.objects.create(...)
```

On create the employee and store come from the request. On edit they are the stored ones,
because FR-010 forbids changing them.

## ScheduleRevision, collection `workforce_schedulerevision`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Equal to the store id. Not a foreign key: it is a counter, not a reference. |
| `revision` | integer | Default 0. Incremented by one on every shift write that touches this store. |

Written inside the shift write transaction, once per store the employee is assigned to.
Two jobs in one field:

1. **Write guard.** Any two concurrent writes for the same employee share at least one
   document, so MongoDB aborts one with a write conflict instead of losing the overlap
   check (`research.md` R3).
2. **Cache token.** The schedule cache key includes the revision of every store in scope,
   so a committed write makes every previously cached schedule for that store unreachable
   (`research.md` R8).

Rows are created on first use inside the transaction. A conflicting insert raises
`IntegrityError`, which is a `DatabaseError`, so the outer `retry_on_conflict` replays and
takes the update path.

## AdminGuard, collection `identity_adminguard`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key |
| `key` | string, unique | Fixed value `last-admin`. The unique index is what guarantees exactly one row. |
| `revision` | integer | Default 0. Incremented by one inside every transaction that can remove an active admin. |

A single row. It is written inside the transaction that deactivates, demotes, or deletes an
account, before the count is taken. Two concurrent removals therefore always write the same
document, MongoDB aborts one with a write conflict, `retry_on_conflict` replays it, and the
replayed count sees the committed change. Without it, both transactions read a count that
still includes the other admin, and both proceed.

`update_account` and `delete_account` both call `_take_admin_slot()` from
`identity.services` inside the transaction. `update_account` gains `atomic()` and
`retry_on_conflict` for this, because M0 ran the check and the save with no transaction at
all.

## ScheduleSnapshot, collection `workforce_schedulesnapshot`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key |
| `key` | string, unique | SHA-256 hex of scope pairs, window, page, page size |
| `body` | JSON | `{"count": n, "results": [...]}`, already serialized |
| `created_at` | datetime | Set on insert. Rows older than one hour are deleted lazily on a miss. |

The scope pairs are `(store_id, revision)` for every store the actor can reach. The window
is the normalized `from` and `to`. The page parameters come from the request.

Rows carry no expiry index, because this backend has no `expireAfterSeconds` support in
`models.Index`. Cleanup is one delete by `created_at__lt`, run on a miss only. It is global
rather than per store on purpose: a store that has been deleted no longer appears in any
actor's scope, so a per store cleanup would never visit its stranded rows.

## Access rules

All role decisions go through `src/apps/identity/permissions.py` (SC-006). Workforce adds
four actions and no role comparison of its own.

| Action | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|
| `shift.read` | yes | yes | own stores | own stores | own stores |
| `shift.create` | yes | yes | own stores | own stores | no |
| `shift.change` | yes | yes | own stores | own stores | no |
| `shift.delete` | yes | yes | own stores | own stores | no |

- List reads use `scope_stores(Shift.objects.all(), actor)`. The default field is
  `store_id`, which is exactly the column a shift carries.
- Detail reads, edits, and deletes load by id, then call `require_store_access`. A shift
  outside the actor's stores is a 403 with the existing
  `"This record is outside your store access."` message and exposes no field.
- An actor with no store assignments gets an empty list, never an error.
- `ADMIN` is the only role that skips the store filter, and that lives in the helper, not
  here.

- The last-admin guard belongs to `identity`, not to this feature: `account.delete` and the
  existing deactivate and demote paths share one serialization document, `AdminGuard`. It
  has no store dimension.

## Deletion and lifecycle

| Deleted | Collected automatically | Requirement |
|---|---|---|
| Shift | nothing | FR-023 |
| Store | its shifts, by the `Shift.store` cascade | FR-024 |
| Account (`User`) | its `Employee` profile, then that profile's shifts, by the two cascades | FR-025 |

The store delete path is the existing `stores.services.delete_store`, already wrapped in
`atomic()` and `retry_on_conflict`. No code changes there: the collector finds the shifts
through the reverse relation declared on `Shift`. The account delete path is new: `identity.services.delete_account` behind
`DELETE /api/accounts/{id}/`, ADMIN only, wrapped in the same `atomic()` and
`retry_on_conflict`. The collector removes the account, then the profile, then that
profile's shifts, and the transaction commits all of it or none of it. Because the cascade
writes no revision, `delete_account` also bumps the revisions of every store where that
profile had shifts, through `workforce.services.bump_store_revisions`, so the next schedule
read cannot serve a page that still lists the deleted person. The cascade is proven by an
end to end test, not only by a direct model delete.

`ScheduleRevision` rows for a deleted store are left behind. They are unreachable: the
scope pairs come from the actor's `store_ids`, and a deleted store is removed from every
account. The same applies to `ScheduleSnapshot` rows for that store, which expire through
the lazy cleanup.

## State transitions

A shift has no lifecycle beyond create, edit times, delete. There is no draft, no
cancellation, no approval. History is not preserved in M1: a deleted shift is gone, and the
cache stops serving it on the next read because the revision moved.
