# Tasks: M0 Foundation: Identity, Roles, and Store Scoped Access

**Input**: Design documents from `/specs/001-foundation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Included, because the constitution requires unit tests before a feature is complete and the spec's success criteria are test outcomes.

**Organization**: Tasks are grouped by user story so each story can be implemented, tested, and demonstrated on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2, US3, US4, matching the spec
- Every task names an exact file path

## Path Conventions

Single Django project. The project root for Python is `src/`, and `manage.py` sits in `src/`. Tests live in `tests/` at the repository root. MongoDB specific migrations live in `src/mongo_migrations/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Replace the relational stack with the document stack and prepare the project skeleton.

- [X] T001 Update `pyproject.toml`: set `django==6.1.3`, add `django-mongodb-backend==6.1.0`, raise `djangorestframework>=3.18`, `django-filter>=26.2`, `django-cors-headers>=4.9`, `django-environ>=0.14`; remove `psycopg[binary]`
- [X] T002 Add `[tool.pytest.ini_options]` to `pyproject.toml` with `DJANGO_SETTINGS_MODULE = "core.settings"`, `pythonpath = ["src"]`, `testpaths = ["tests"]`, and `addopts = "-q"`
- [X] T003 Replace the `db` service with a `mongo` service in `docker-compose.yml`: image `mongo:8.0`, `--replSet rs0 --bind_ip_all`, named volume `mongo_data`, healthcheck that runs `rs.initiate()` when the set is not yet initiated, and `MONGO_URI=mongodb://mongo:27017/?directConnection=true` plus `MONGO_DB=coffeeshop` on `web`
- [X] T004 Create `src/core/apps.py` with `MongoAdminConfig`, `MongoAuthConfig`, `MongoContentTypesConfig`, each setting `default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"`
- [X] T005 Update `src/core/settings.py`: use the three app configs from T004, `DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"`, `DATABASES` with `ENGINE: django_mongodb_backend` and `HOST`/`NAME` from `MONGO_URI`/`MONGO_DB`, `MIGRATION_MODULES` for `admin`, `auth`, `contenttypes` under `mongo_migrations.*`, `AUTH_USER_MODEL = "identity.User"`, and `INSTALLED_APPS` with `apps.identity`, `apps.catalog`, `apps.stores`, and `apps.workforce`
- [X] T006 Create the `src/apps/identity/` package skeleton: `__init__.py`, `apps.py` with `IdentityConfig`, and empty `models.py`, `managers.py`, `permissions.py`, `services.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `migrations/__init__.py`
- [X] T007 Update `src/core/settings.py` to drop every Postgres reference: search `psycopg`, `postgres://`, `DATABASE_URL`, and `employee_db`, and leave no match

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, the single permission helper, routing, and the test harness. No user story can start before this phase passes.

**CRITICAL**: Complete this phase before any user story work.

- [X] T008 [P] Create the `User` model in `src/apps/identity/models.py`: subclass `AbstractUser`, set `username = None`, `email = EmailField(unique=True)`, `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`; add `role` with the five choices `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`, `BARISTA`; add `store_ids = ArrayField(ObjectIdField(), default=list)`; add indexes: unique `email`, multikey `store_ids`, compound `(role, is_active)`
- [X] T009 [P] Create the `Employee` model in `src/apps/identity/models.py`: `user = OneToOneField(User, on_delete=CASCADE)` and `hire_date = DateField()`; no credentials, no role, no store field; unique index on `user`
- [X] T010 Implement `UserManager` in `src/apps/identity/managers.py`: normalize email to lowercase and trimmed, `create_user(email, password, **extra)`, `create_superuser(email, password, **extra)` with `is_staff` and `is_superuser` true; set `objects = UserManager()` on the model
- [X] T011 Update `src/apps/stores/models.py`: add an index on `name`, remove the `manager` comment, keep `name` (max 40), `address` (max 100), `postal_code` (max 10)
- [X] T012 Remove the legacy employee model and endpoints: delete the `Employee` model from `src/apps/workforce/models.py`, empty `src/apps/workforce/views.py`, `serializers.py`, `urls.py`, keep the app folder and registration for M1, and remove the workforce include from `src/core/urls.py`
- [X] T013 Remove the three legacy SQL migrations with `git rm src/apps/catalog/migrations/0001_initial.py src/apps/stores/migrations/0001_initial.py src/apps/workforce/migrations/0001_initial.py`, then regenerate app migrations with `uv run python src/manage.py makemigrations catalog stores identity`
- [X] T014 Generate MongoDB migrations for contrib apps: `uv run python src/manage.py makemigrations admin auth contenttypes` into `src/mongo_migrations/`, and confirm `src/mongo_migrations/{admin,auth,contenttypes}/` exist
- [X] T015 Create `src/apps/identity/permissions.py` with `ACTIONS`, `can(actor, action, store_id=None)`, `scope_stores(queryset, actor, field="store_id")`, and `require_store_access(actor, store_id)`; `ADMIN` bypasses the store filter, `REGIONAL_MANAGER` uses `store_ids__contains`, every other role does the same, and `require_store_access` raises DRF `PermissionDenied` with `{"detail": "This record is outside your store access."}`
- [X] T016 Create `src/apps/identity/services.py` with `add_store_to_regional_managers(store_id)`, `remove_store_from_all_users(store_id)`, `assign_all_stores_to_regional_manager(user)`, and `ensure_not_last_active_admin(user, new_role, new_is_active)`; all use targeted `QuerySet.update()` calls, never read then save
- [X] T017 Configure DRF in `src/core/settings.py`: `DEFAULT_AUTHENTICATION_CLASSES = ["core.authentication.SessionAuthentication"]` (a DRF subclass whose `authenticate_header` returns `"Session"`, so an anonymous request answers 401 as the contract requires), `DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]`, `DEFAULT_PAGINATION_CLASS = "core.pagination.StandardPagination"`, `PAGE_SIZE = 20`, and a page size limit of 100 via a small `src/core/pagination.py`
- [X] T018 Create `src/core/urls.py` routing: keep `admin/`, mount `apps.identity.urls`, `apps.stores.urls`, and `apps.catalog.urls` under `api/`, and remove the workforce include
- [X] T019 Create `src/apps/identity/admin.py` registering `User` with `list_display = ("email", "role", "is_active")` and `Employee` with `list_display = ("user", "hire_date")`
- [X] T020 Create `src/apps/identity/management/commands/create_admin.py`: accepts `--email` and `--password`, refuses when an active `ADMIN` already exists, creates an active admin with `is_staff` and `is_superuser` true
- [X] T021 Create `tests/conftest.py` with helpers that build stores, users per role, and authenticated API clients, and a `pytest.mark.django_db` baseline; no network calls
- [X] T022 Run `uv run python src/manage.py check` and `uv run python src/manage.py migrate`, then confirm `pytest` collects zero tests without error

**Checkpoint**: The database is MongoDB, migrations apply, the helper exists, and the test harness runs.

---

## Phase 3: User Story 1 - A staff member signs in and sees their access (Priority: P1) MVP

**Goal**: A person signs in with email and password, stays signed in, reads their own profile, and signs out. Deactivation and wrong credentials are refused identically.

**Independent Test**: Create one user directly through the model manager with role `MANAGER` and one store, sign in, read `/api/auth/me/`, and sign out. No account API is needed.

### Tests for User Story 1

- [X] T023 [P] [US1] Write `tests/test_auth.py` covering: successful login sets a session; wrong password and unknown email both return 401 with `{"detail": "Invalid email or password."}`; a deactivated user returns 401; `GET /api/auth/me/` returns email, role, and `store_ids`; `PATCH /api/auth/me/` rejects `role`, `store_ids`, and `is_active` with 400; logout returns 204 and the next `me` call returns 401
- [X] T024 [US1] Run the T023 tests and confirm they fail for the expected reason before implementing

### Implementation for User Story 1

- [X] T025 [US1] Add `LoginSerializer` and `AccountProfileSerializer` to `src/apps/identity/serializers.py`; the profile serializer returns `id`, `email`, `role`, `store_ids`, `is_active`, `first_name`, `last_name`, `date_joined`, and never `password`
- [X] T026 [US1] Implement `LoginView`, `LogoutView`, and `MeView` in `src/apps/identity/views.py`: login uses `django.contrib.auth.authenticate` and `login`, logout calls `logout`, `MeView` allows `GET` and `PATCH` with only `email`, `password`, `first_name`, `last_name` writable
- [X] T027 [US1] Create `src/apps/identity/urls.py` with `auth/login/`, `auth/logout/`, and `auth/me/`, and include it from `src/core/urls.py` under `api/`
- [X] T028 [US1] Set session rules in `src/core/settings.py`: `SESSION_COOKIE_AGE = 28800`, `SESSION_SAVE_EVERY_REQUEST = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`
- [X] T029 [US1] Run `uv run pytest tests/test_auth.py` and confirm every scenario passes, including the deactivated-account case

**Checkpoint**: US1 works alone. A signed-in user can read and update their own profile.

---

## Phase 4: User Story 2 - An admin onboards staff (Priority: P2)

**Goal**: An admin, a regional manager, or a manager creates and changes staff accounts within their authority. The last active admin cannot be removed.

**Independent Test**: As an admin, create a manager for one store, list accounts, change the role, deactivate the account, and confirm the deactivated user is refused on their next request.

### Tests for User Story 2

- [ ] T030 [P] [US2] Write `tests/test_accounts.py` covering: admin creates each of the five roles; duplicate email returns 400; manager creates a `BARISTA` in an own store; manager creating `ADMIN` returns 403; manager assigning a store outside their own returns 403; regional manager creates a `SUPERVISOR` in any store; manager listing accounts sees only own-store BARISTA and SUPERVISOR plus self; regional manager listing sees all; last active admin cannot be deactivated or demoted; deactivation takes effect on the next request; pagination caps at 100 and defaults to 20
- [ ] T031 [US2] Run the T030 tests and confirm they fail before implementing

### Implementation for User Story 2

- [ ] T032 [US2] Add `AccountReadSerializer` and `AccountWriteSerializer` to `src/apps/identity/serializers.py`; `AccountWriteSerializer` validates `email` uniqueness case-insensitively, `role` in the five values, and every `store_ids` entry against an existing store, and never returns `password`
- [ ] T033 [US2] Add actor-aware validation to `src/apps/identity/serializers.py`: a manager may only submit roles `BARISTA` and `SUPERVISOR` and only stores in the actor's `store_ids`; a regional manager may submit any store but only those two roles; only `ADMIN` may submit `ADMIN` or `REGIONAL_MANAGER`
- [ ] T034 [US2] Implement `create_account(actor, data)` and `update_account(actor, user, data)` in `src/apps/identity/services.py`, including the last-active-admin guard from T016 and `assign_all_stores_to_regional_manager` when the new role is `REGIONAL_MANAGER`
- [ ] T035 [US2] Implement `AccountListCreateView` and `AccountDetailView` in `src/apps/identity/views.py`: list filters `role`, `is_active`, and `store`; manager querysets are limited with `store_ids__overlap` plus the actor's own id; detail reads and updates go through `require_store_access`
- [ ] T036 [US2] Add `accounts/` and `accounts/<id>/` routes to `src/apps/identity/urls.py`
- [ ] T037 [US2] Run `uv run pytest tests/test_accounts.py tests/test_auth.py` and confirm both suites pass

**Checkpoint**: US1 and US2 work. Account administration respects the matrix.

---

## Phase 5: User Story 3 - Store scoped access is enforced everywhere (Priority: P3)

**Goal**: Every store-owned endpoint filters by the actor's stores. Cross-store requests return 403. ADMIN is the only bypass. Regional managers cover every store through assignments, including stores created later.

**Independent Test**: Create two stores, one manager assigned to the first, and one admin. List stores as the manager and see one. Request the second store by id and get 403. Create a third store as a regional manager and see it on the next request.

### Tests for User Story 3

- [ ] T038 [P] [US3] Write `tests/test_store_scope.py` covering: manager sees exactly one store; admin sees all; cross-store `GET` returns 403 with `{"detail": "This record is outside your store access."}` and no store field; a user with empty `store_ids` gets an empty list and not an error; barista cannot create or change a store; manager cannot create a store; regional manager can create and rename a store; delete is admin only; catalog list stays global for every signed-in role
- [ ] T039 [P] [US3] Write `tests/test_propagation.py` covering: creating a store appends its id to every regional manager; creating a regional manager assigns every existing store; deleting a store removes its id from every user; a regional manager created before any store exists sees the first store created afterwards
- [ ] T040 [US3] Run the T038 and T039 tests and confirm they fail before implementing

### Implementation for User Story 3

- [ ] T041 [US3] Add `StoreSerializer` to `src/apps/stores/serializers.py` with `name` (max 40), `address` (max 100), and `postal_code` (max 10)
- [ ] T042 [US3] Create `src/apps/stores/services.py`: `create_store(actor, data)` calls `identity.services.add_store_to_regional_managers(store_id)` and appends the store to the actor when the actor is a regional manager; `delete_store(actor, store)` calls `identity.services.remove_store_from_all_users(store_id)`; both use `django_mongodb_backend.transaction.atomic` when two collections change, and retry the whole operation on a `DatabaseError` write conflict, because MongoDB aborts one of two conflicting writes
- [ ] T043 [US3] Rewrite `src/apps/stores/views.py`: list and detail querysets pass through `scope_stores`; create and change check `can(actor, "store.create" / "store.change")`; delete checks `can(actor, "store.delete")`; list is paginated and ordered by `name`
- [ ] T044 [US3] Update `src/apps/stores/urls.py` to the `api/stores/` prefix expected by `src/core/urls.py`
- [ ] T045 [US3] Update `src/apps/catalog/views.py`: require authentication, paginate the list, and do not apply any store filter; leave the model unchanged
- [ ] T046 [US3] Replace any hand-written `store_ids__overlap` filter in `src/apps/identity/views.py` with `permissions.scope_stores`, so the account list has one scoping path, and confirm the manager overlap rule from T035 still holds
- [ ] T047 [US3] Run `uv run pytest tests/test_store_scope.py tests/test_propagation.py tests/test_accounts.py` and confirm all pass

**Checkpoint**: Store scoping is proven on stores, accounts, and catalog.

---

## Phase 6: User Story 4 - An employee profile is attached to a staff account (Priority: P4)

**Goal**: An account may carry an employment record with a hire date. The record is never a login and is scoped through the linked account's stores.

**Independent Test**: Create an account, attach an employee profile with a hire date, read it as an admin and as the manager of the assigned store, and confirm a barista sees the name but not the email.

### Tests for User Story 4

- [ ] T048 [P] [US4] Write `tests/test_employees.py` covering: create a profile for an existing user; a second profile for the same user returns 400; a missing user returns 400; a profile outside the manager's stores returns 403; a barista list omits `user_email` and keeps `user_name`; `PATCH` changes `hire_date`; an account without a profile still signs in and works
- [ ] T049 [US4] Run the T048 tests and confirm they fail before implementing

### Implementation for User Story 4

- [ ] T050 [US4] Add `EmployeeSerializer` to `src/apps/identity/serializers.py` with `id`, `user_id`, `user_email`, `user_name`, and `hire_date`; drop `user_email` when the requesting role is `BARISTA`
- [ ] T051 [US4] Add `create_employee(actor, data)` and `update_employee(actor, employee, data)` to `src/apps/identity/services.py`, validating that the user exists, has no profile yet, and is inside the actor's stores
- [ ] T052 [US4] Implement `EmployeeListCreateView` and `EmployeeDetailView` in `src/apps/identity/views.py`, scoped through the linked user's `store_ids`, paginated, ordered by `hire_date` descending
- [ ] T053 [US4] Add `employees/` and `employees/<id>/` routes to `src/apps/identity/urls.py`
- [ ] T054 [US4] Run `uv run pytest tests/test_employees.py` and confirm every scenario passes

**Checkpoint**: All four user stories work independently and together.

---

## Phase 7: Polish and Cross-Cutting Concerns

**Purpose**: Finish the milestone with clean tooling and a proven quickstart.

- [ ] T055 [P] Run `uv run ruff format src tests` and commit the formatting result
- [ ] T056 [P] Run `uv run ruff check src tests --fix` and resolve every remaining finding
- [ ] T057 Add type hints to public functions in `src/apps/identity/permissions.py`, `src/apps/identity/services.py`, `src/apps/stores/services.py`, and the model managers
- [ ] T058 Run `uv run pytest` and confirm the full suite passes from a clean test database
- [ ] T059 Walk `specs/001-foundation/quickstart.md` end to end on a fresh `docker compose down -v` then `up`, and fix any command that does not behave as written
- [ ] T060 Search the repository for `psycopg`, `postgres`, `DATABASE_URL`, `employee_db`, and `Product` store filters, and confirm no stale Postgres reference remains
- [ ] T061 Update the `Makefile` with `run`, `test`, `migrate`, and `admin` targets that wrap the `uv run python src/manage.py ...` commands
- [ ] T062 Review `git status` and confirm only intended files changed; leave the commit to the Kyaor

---

## Dependencies and Execution Order

### Phase dependencies

- **Phase 1 Setup**: no dependencies, start immediately
- **Phase 2 Foundational**: depends on Setup, blocks every user story
- **Phase 3 US1**: depends on Foundational
- **Phase 4 US2**: depends on Foundational and reuses US1's session handling
- **Phase 5 US3**: depends on Foundational and reuses US2's account queryset
- **Phase 6 US4**: depends on US2 for accounts and US3 for store scope
- **Phase 7 Polish**: depends on every story that is in scope

### User story dependencies

- **US1 (P1)**: independent after Foundational. It creates its own users through the manager.
- **US2 (P2)**: independent after Foundational. It needs US1 only to sign in during tests, which the fixtures cover.
- **US3 (P3)**: independent after Foundational for store endpoints. The account list scoping step (T046) integrates with US2.
- **US4 (P4)**: needs US2 for accounts. It demonstrates scope through US3.

### Within each story

Tests first (T023, T030, T038, T039, T048), then serializers, then services, then views, then routes, then a green test run.

### Parallel opportunities

- T008 and T009 touch the same file, so run them in order, not in parallel
- T001, T002, T003, T004, T006 touch different files and can run in parallel
- T023, T030, T038, T039, T048 are separate test files and can be written in parallel once Foundational is done
- T041, T050, T032 touch different serializers and can run in parallel
- T055 and T056 are sequential, because lint fixes formatting

---

## Parallel Example: setup and tests

```bash
# Phase 1, different files:
Task: "Update pyproject.toml dependencies and pytest config"
Task: "Replace db with mongo in docker-compose.yml"
Task: "Create src/core/apps.py with Mongo AppConfigs"
Task: "Create the src/apps/identity package skeleton"

# After Foundational, different test files:
Task: "Write tests/test_auth.py"
Task: "Write tests/test_accounts.py"
Task: "Write tests/test_store_scope.py"
Task: "Write tests/test_propagation.py"
Task: "Write tests/test_employees.py"
```

---

## Implementation Strategy

### MVP first, US1 only

1. Phase 1 Setup
2. Phase 2 Foundational
3. Phase 3 US1
4. Stop and validate `tests/test_auth.py`
5. The system can sign in, identify a role, and show the caller's stores

### Incremental delivery

1. Setup plus Foundational: the document stack works and migrations apply
2. US1: sign in and profile, the smallest useful slice
3. US2: account administration and the last-admin guard
4. US3: store scoping and regional manager propagation, the milestone exit criteria
5. US4: employee profiles
6. Polish: lint, type hints, full suite, quickstart

### Verification order

Run the narrow suite after each story, then the full suite at T058. A story is not done until its own test file passes on a clean test database.

---

## Notes

- Every list endpoint must be paginated. An unbounded list is a defect.
- Never use `prefetch_related()`, `select_for_update()`, or `django.db.transaction`. Use `django_mongodb_backend.transaction.atomic` where two collections change.
- The permission helper is the only place a role value decides an outcome. A direct role comparison anywhere else is a defect.
- T013 deletes tracked files. It needs the Kyaor's approval before running, as `git rm`.
- No `spec.md` requirement is dropped: FR-001 to FR-026 map to T023 to T054, and SC-001 to SC-008 are proven by the test files above.
