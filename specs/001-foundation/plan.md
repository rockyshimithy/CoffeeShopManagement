# Implementation Plan: M0 Foundation: Identity, Roles, and Store Scoped Access

**Branch**: `001-foundation` | **Date**: 2026-11-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-foundation/spec.md`

## Summary

Deliver the identity slice that every later milestone depends on: a custom user model with email login, one role per account, store assignments, a single permission helper, an employee profile, account administration for admins, regional managers and managers, store CRUD with the agreed matrix, and every store-owned endpoint filtered by the actor's stores.

The storage layer changes in this milestone. The current PostgreSQL and SQLite setup is replaced by MongoDB through `django-mongodb-backend` 6.1.0 on Django 6.1, every model uses `ObjectIdAutoField`, and the three existing SQL migrations are regenerated for MongoDB. There is no production data, so nothing is preserved.

The app split adds `src/apps/identity` for `User`, `Employee`, the role matrix, the permission helper, and its endpoints. `workforce` keeps its folder for M1 but loses the legacy `Employee` model. `stores` gains the matrix rules, the store creation propagation rule, and the store deletion cleanup rule. `catalog` stays as it is in M0, global read data, and is renamed to `Item` in M2 when inventory needs it.

## Technical Context

**Language/Version**: Python 3.12 or newer

**Primary Dependencies**: Django 6.1.3, django-mongodb-backend 6.1.0, djangorestframework 3.18.x, django-filter 26.2, django-cors-headers 4.9.x, django-environ 0.14.x

**Storage**: MongoDB 8.0, run as a single-node replica set so the transaction API works from M2 onward

**Testing**: pytest 8 with pytest-django 4.14, running against the Docker Compose MongoDB. Django creates and drops a `test_` database per run.

**Target Platform**: Linux containers through Docker Compose, development on Ubuntu 24.04

**Project Type**: Web service, one backend now, separate frontend folders later in the same repository

**Performance Goals**: store-owned list endpoints answer within 200 ms at the 95th percentile with 10,000 accounts and 50 stores. This is a target, not a release gate.

**Constraints**: `prefetch_related()`, `select_for_update()`, and `django.db.transaction` are unusable. ObjectId primary keys everywhere. Pagination is mandatory on every list. No unbounded result set.

**Scale/Scope**: five roles, one new app, three existing apps touched, 5 endpoint groups, 17 endpoints, 1 bootstrap command

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Modular monolith, module under `src/apps/` | PASS | `src/apps/identity` added. `stores` calls one public identity service for propagation and imports no identity model. |
| Domain boundary rule | PASS | No cross-app model imports. The only cross-context call is `identity.services.add_store_to_regional_managers(store_id)`. |
| Ponytail, no unneeded patterns | PASS | `AbstractUser` subclass, Django session auth, function based permission helper, no repository, no JWT, no event bus. |
| Strict SDD | PASS | Spec approved, plan here, tasks next, then code. |
| Code quality, type hints, tests | PASS | Ruff and pytest wired in M0. Store scoping, role authority, and propagation each get tests. |
| I1 store scoped access | PASS | One permission helper. Every store-owned queryset goes through it. A two-store test proves zero leakage. ADMIN is the only bypass. |
| I2 pool isolation | N/A | No stock exists in M0. |
| I3 one item identity | PASS | Catalog stays global and is never store filtered. No copy of item data anywhere. |
| I4 stock is never read then saved | N/A | No stock writes in M0. |
| Data layer, engine version match | PASS | Django 6.1 with backend 6.1.0, exactly the documented pairing. |
| Data layer, ObjectId and contrib setup | PASS | `DEFAULT_AUTO_FIELD` plus `AppConfig` subclasses and `MIGRATION_MODULES` for admin, auth, and contenttypes. |
| Data layer, query rules | PASS | Pagination on lists. Indexes on `User.email`, `User.store_ids`, and `Employee.user_id`. No `prefetch_related`. No `django.db.transaction`. |

No violations, so complexity tracking is empty.

**Post-design re-check**: PASS. The design in `data-model.md` and `contracts/api.md` keeps the helper as the only authorization path, keeps regional manager scope as data rather than a bypass, and uses only supported backend features.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 decisions and rationale
├── data-model.md        # Phase 1 collections, fields, indexes
├── quickstart.md        # Phase 1 end to end validation guide
├── contracts/
│   └── api.md           # Phase 1 HTTP contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output, created by /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── manage.py
├── mongo_migrations/            # generated for admin, auth, contenttypes
│   ├── admin/
│   ├── auth/
│   └── contenttypes/
├── core/
│   ├── settings.py              # Mongo engine, AUTH_USER_MODEL, app configs
│   ├── urls.py                  # includes apps.identity.urls
│   └── apps.py                  # MongoAdminConfig, MongoAuthConfig, MongoContentTypesConfig
└── apps/
    ├── identity/                # NEW
    │   ├── models.py            # User, Employee
    │   ├── managers.py          # UserManager with create_user / create_superuser
    │   ├── permissions.py       # the only role and store scope helper
    │   ├── services.py          # add_store_to_regional_managers, create_account, bootstrap_admin
    │   ├── serializers.py
    │   ├── views.py
    │   ├── urls.py
    │   ├── admin.py
    │   ├── apps.py
    │   ├── migrations/
    │   └── tests/
    ├── stores/                  # gains matrix rules and propagation call
    ├── catalog/                 # unchanged in M0, global read
    └── workforce/               # Employee model removed, folder kept for M1

tests/
└── conftest.py                  # shared factories and API clients
```

**Structure Decision**: Single Django project under `src/`, with one module per bounded context under `src/apps/`. The MongoDB specific migrations for contrib apps live in `src/mongo_migrations/` because `manage.py` sits in `src/`. Frontend folders arrive in M4 and M5.

## Phase Plan

### Phase 0, research

All unknowns are resolved in `research.md`: version pairing, replica set need, auth mechanism, custom user shape, array field for store assignments, cross-context propagation, migration regeneration, and test strategy.

### Phase 1, design

`data-model.md` defines the three collections and their indexes. `contracts/api.md` defines the HTTP surface and every error code. `quickstart.md` gives the runnable proof that the milestone is done.

### Phase 2, tasks

`/speckit.tasks` turns this plan into ordered tasks. Expected order: dependency and settings swap, migrations, identity models and helper, account endpoints, store endpoints, propagation, employee profile, tests, bootstrap command, quickstart run.

## Complexity Tracking

No constitution violations, so no justification table.
