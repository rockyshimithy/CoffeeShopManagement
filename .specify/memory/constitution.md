# CoffeeShopManagement Constitution

<!-- Sync Impact Report:
Version change: 0.1.1 → 0.1.2
Modified principles: none
Modified invariants:
  - I3. One Item Identity renamed to One Product Identity, so the invariant matches the
    model name `Product` in src/apps/catalog. The rule itself is unchanged.
Other changes:
  - Data Layer, Query rules: the stock event index on (item_id, at) becomes (product_id, at).
Added sections: none
Removed sections: none
Templates requiring updates: none
TODOs: None
-->

## Core Principles

### 1. Modular Monolith Architecture
- The application is a Modular Monolith built with Python 3.12+ and Django.
- Every business domain must reside in its own isolated module under `src/apps/` (e.g., `src/apps/catalog`, `src/apps/stores`, `src/apps/workforce`). The Django app label stays the short name (`apps.catalog`), because `manage.py` lives in `src/`.
- **Domain Boundary Rule:** Direct imports of models or private code from another module are strictly forbidden. Inter-module communication must occur exclusively via explicit public service interfaces or internal domain events.

### 2. Ponytail Philosophy (Pragmatic Simplicity)
- **Zero YAGNI / Anti-Overengineering:** Write only the code required to fulfill the current specification.
- Do not introduce design patterns (Repositories, Factories, CQRS, etc.) unless there is proven repetition across at least 3 distinct domains.
- Stick to idiomatic Django and Django REST Framework constructs.

### 3. Strict Spec-Driven Development (SDD) Workflow
- No production code shall be written without an approved specification chain in `.specify/`.
- The mandatory lifecycle for any feature is:
  1. `Spec` (What to build & Acceptance criteria)
  2. `Plan` (Architecture & Data model strategy)
  3. `Tasks` (Implementation steps)
  4. `Code` (Implementation execution)

### 4. Code Quality & Tooling Standards
- Dependency management is handled natively by `uv`.
- Local execution and environment consistency are enforced via Docker Compose.
- All code must include basic type hints and unit tests covering core domain logic before completion.

## Domain Invariants

These hold for every feature and are checked in review. A violation is a defect even when
the tests pass.

### I1. Store Scoped Access
- Every endpoint that reads or writes store data derives its queryset from the requesting user's `store_ids`.
- `ADMIN` is the only role that bypasses the filter.
- An endpoint with an unscoped queryset is a defect, regardless of its tests.

### I2. Pool Isolation
- A single operation changes stock in at most one pool. A pool is one store, or the single online pool.
- No stock transfer operation exists. No code path writes stock for two pools in one operation.

### I3. One Product Identity
- A product exists once in the catalog. Stock references that document by id.
- Stock never copies a product's name or price.
- Order lines do copy `unit_price`, because an order records what was charged at that moment.

### I4. Stock Is Never Read Then Saved
- Stock is never loaded, modified in Python, and saved back.
- Every change goes through the single stock service function, which issues a targeted update inside a transaction.
- There is no other legal write path to stock or stock events, including Django admin.

## Data Layer

### Engine
- The database is MongoDB, reached through `django-mongodb-backend`.
- The backend version must match the installed Django major and minor version.
- Every model uses `ObjectIdAutoField`. Contrib apps need their own `AppConfig` subclasses and MongoDB specific migrations under `mongo_migrations/`.

### Django idioms that do not work here
- `prefetch_related()` is unsupported. Related data on a list endpoint loads by manual batch, after pagination: collect the ids, one `filter(id__in=...)`, one dict, attach in Python.
- `django.db.transaction.atomic()` is a documented no-op. Use `django_mongodb_backend.transaction.atomic`.
- `select_for_update()` is a no-op. Concurrency safety comes from targeted atomic updates inside a transaction, never from row locks.

### Query rules
- No list endpoint returns an unbounded result set. Pagination is mandatory.
- Shifts are indexed on `(store_id, starts_at)`.
- Stock events are indexed on `(store_id, at)`, `(product_id, at)`, and `(stock_id, at)`.
- The schedule endpoint is cached. A read that repeats for every user in a store does not need to reach the database.

## Development Constraints

- **Complexity Justification:** Any pull request introducing new abstractions or third-party dependencies outside `uv` must justify why a simpler, idiomatic Django solution is insufficient.

## Governance

- **Supremacy:** This Constitution supersedes all informal architectural decisions or ad-hoc code practices.
- **Amendments:** Changes to this Constitution require documentation and clear architectural justification, followed by a formal review and approval process.
- **Versioning Policy:** The Constitution version adheres to semantic versioning: MAJOR for backward-incompatible changes, MINOR for additions or significant expansions, and PATCH for clarifications or minor refinements.
- **Compliance Review:** All code contributions and architectural decisions MUST be reviewed for compliance with these principles before integration.

**Version**: 0.1.2 | **Ratified**: 2026-09-10 | **Last Amended**: 2026-11-26
