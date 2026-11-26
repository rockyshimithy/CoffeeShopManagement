# API Contract: M1 Workforce

Base path: `/api/`. Body and response format: JSON. Identifiers are 24 character ObjectId
hex strings. This contract adds one resource, `shifts`, and changes no M0 endpoint.

## Common rules

- Every endpoint here requires an authenticated session. Missing or invalid session
  returns 401.
- Unsafe methods (POST, PATCH, DELETE) require the `X-CSRFToken` header after sign in.
- A shift outside the actor's stores returns 403 with:
  `{"detail": "This record is outside your store access."}` and no field of the shift.
- A role that may not write shifts returns 403 with:
  `{"detail": "Your role may not perform this action."}`
- Validation errors return 400 with a field map, for example
  `{"ends_at": ["The end must be later than the start."]}`.
- Lists are paginated with `?page=` and `?page_size=` (default 20, maximum 100). List
  responses are `{"count": n, "next": url|null, "previous": url|null, "results": [...]}`.
- A missing or malformed id in the path returns 404, before any scope check.

## Objects

### Shift

```json
{
  "id": "65f1c0a2b3d4e5f6a7b8c9d3",
  "employee_id": "65f1c0a2b3d4e5f6a7b8c9d2",
  "employee_name": "Ana Silva",
  "store_id": "65f1c0a2b3d4e5f6a7b8c9d1",
  "store_name": "Downtown",
  "starts_at": "2026-11-30T08:00:00Z",
  "ends_at": "2026-11-30T16:00:00Z"
}
```

`employee_name` is `"{first_name} {last_name}"` from the linked account, with the whole
name trimmed. When both names are empty the account email is used instead.
`store_name` is the store's `name`.

Times are ISO 8601. A UTC instant renders with the `Z` designator. Input accepts any ISO
8601 string with an offset; input without an offset is read as UTC.

## Permissions

| Method | Path | ADMIN | REGIONAL_MANAGER | MANAGER, SUPERVISOR | BARISTA |
|---|---|---|---|---|---|
| GET | `/api/shifts/` | all | all reachable | own stores | own stores |
| POST | `/api/shifts/` | yes | yes | own stores | 403 |
| GET | `/api/shifts/{id}/` | all | all reachable | own stores | own stores |
| PATCH | `/api/shifts/{id}/` | yes | yes | own stores | 403 |
| DELETE | `/api/shifts/{id}/` | yes | yes | own stores | 403 |

"All reachable" is every store, because creating a store appends it to every regional
manager's assignments (M0 decision 27). A regional manager reaches a store through
`store_ids`, not through an exemption.

## GET /api/shifts/

The schedule. Returns the shifts of the actor's stores inside a window, ordered by start
ascending, then employee name, then id.

Filters:

| Query parameter | Required | Rules |
|---|---|---|
| `store` | no | ObjectId of one store. Must be inside the actor's stores, otherwise 403. Narrows the response to that store. |
| `from` | no | ISO 8601 instant. Inclusive lower bound. |
| `to` | no | ISO 8601 instant. Exclusive upper bound. |

Window rules:

- Neither bound given: `from` is Monday 00:00 of the current week in the project time zone
  (UTC), `to` is the following Monday 00:00.
- Only `from` given: `to` is `from` plus 7 days.
- Only `to` given: `from` is `to` minus 7 days.
- `to` not after `from`, or a span over 31 days: 400 with
  `{"detail": "The window must start before it ends and span at most 31 days."}`

Selection is by start: a shift appears when `from <= starts_at < to`. This is exact because
a shift never crosses midnight, so no shift can begin before the window and end inside it.

Caching: a repeated read of an unchanged window is answered from a stored copy of the page.
Any shift write that touches a store in scope makes the next read recompute. The client
sees only the new data; there is no cache header to honour.

Responses:

- 200 with a paginated list of Shift objects.
- 400 for a malformed date, a `store` id that is not a valid ObjectId, or an invalid window.
- 403 when `store` is outside the actor's stores.
- 401 when not signed in.

## POST /api/shifts/

Request fields:

| Field | Required | Rules |
|---|---|---|
| `employee_id` | yes | Must be an existing employee profile. |
| `store_id` | yes | Must be an existing store inside the actor's stores. |
| `starts_at` | yes | ISO 8601 instant. |
| `ends_at` | yes | ISO 8601 instant, later than `starts_at`, same UTC day, span at most 12 hours. |

The employee must already be assigned to `store_id`. The combination of employee and store
is refused when it is not.

Responses:

- 201 with the Shift object.
- 400 with a field map for: `ends_at` not later than `starts_at`, a span crossing midnight,
  a span over 12 hours, an unknown employee, an unknown store, an employee not assigned to
  that store, or an overlap with another shift of that employee in any store.
- 403 when the actor's role may not create shifts, or `store_id` is outside their stores.
- 401 when not signed in.

Two concurrent requests for overlapping shifts of the same employee result in exactly one
stored shift. The loser answers 400 with the overlap message.

## GET /api/shifts/{id}/

Responses: 200 with the Shift object. 403 when outside the actor's stores. 404 for a missing
or malformed id. 401 when not signed in.

## PATCH /api/shifts/{id}/

Accepted fields: `starts_at`, `ends_at`. Partial update.

Sending `employee_id` or `store_id` returns 400 with
`{"employee_id": ["A shift's employee cannot change. Delete the shift and create a new one."]}`
and the same shape for `store_id`.

The rules are the same as creation, evaluated against the edited values with the shift
itself excluded from the overlap check.

Responses:

- 200 with the updated Shift object.
- 400 for any rule in creation, or for a forbidden field.
- 403 for the role or the store scope.
- 404 for a missing or malformed id.
- 401 when not signed in.

## DELETE /api/shifts/{id}/

Responses: 204. 403 for the role or the store scope. 404 for a missing or malformed id.
401 when not signed in.

After a successful delete the shift's detail answers 404 and the schedule no longer
contains it.

## Account deletion (new in this feature)

`DELETE /api/accounts/{id}/` is the only new identity route, and it is what makes FR-025
reachable.

| Rule | Value |
|---|---|
| Allowed roles | ADMIN only. Everyone else gets 403 with `{"detail": "Your role may not perform this action."}` |
| Success | 204 with an empty body, matching `DELETE /api/stores/{id}/` |
| Effect | The account, its employee profile, and that profile's shifts are removed in one operation, and the affected stores' cache token moves, so the next schedule read no longer lists them |
| Last active admin | 403 with `{"detail": "The last active admin cannot be deactivated or demoted."}` and nothing is removed. The guard also holds under concurrent requests, see below |
| Missing or malformed id | 404 |
| Not signed in | 401 |

An account with no employee profile is deleted alone. An admin may delete their own account
unless they are the last active admin. There is no bulk delete and no undo.

Concurrency: the last-admin guard is serialized on one shared document, so two admins
deleting each other at the same instant cannot both succeed. One request answers 204 and the
other answers 403. The same guarantee applies to `PATCH /api/accounts/{id}/` with
`{"is_active": false}` or a role change away from `ADMIN`.

## Side effects owned by other contexts

| Event | Effect on shifts |
|---|---|
| `DELETE /api/stores/{id}/` (ADMIN only) | That store's shifts are removed in the same operation. |
| `DELETE /api/accounts/{id}/` (ADMIN only) | That account's employee profile and the profile's shifts are removed in the same operation. |

## Status code summary

| Code | When |
|---|---|
| 200 | Schedule read, detail read, successful edit |
| 201 | Successful creation |
| 204 | Successful delete of a shift, a store, or an account |
| 400 | Validation failure, bad window, forbidden field, unknown or unassigned employee, overlap |
| 401 | No session, expired session, deactivated account |
| 403 | Role not allowed, store out of scope, last active admin |
| 404 | Shift does not exist, or the id is malformed |
