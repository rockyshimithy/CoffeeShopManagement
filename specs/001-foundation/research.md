# Research: M0 Foundation

Phase 0 decisions. Each entry states the decision, why it wins here, and what was rejected.

## D1. Django 6.1 with django-mongodb-backend 6.1.0

**Decision**: Pin Django to 6.1.x and `django-mongodb-backend` to 6.1.0. Use Django 6.1.3, the current patch.

**Rationale**: The backend states that its version must match the Django major and minor version. 6.1.0 is the stable release for the Django 6.1 line and requires Python 3.12 or newer, which the project already requires. Django 6.1.3 is the current patch release.

**Alternatives considered**: Django 5.2 with backend 5.2.4 (one line behind, no benefit here) and Django 6.0 with backend 6.0.4 (also supported, but adds nothing over 6.1). The Kyaor chose 6.1.

**Source**: https://django-mongodb-backend.readthedocs.io/en/latest/intro/install/

## D2. MongoDB 8.0 as a single-node replica set

**Decision**: Use the `mongo:8.0` image in Docker Compose, started with `--replSet rs0`, and initiate the set through the container healthcheck.

**Rationale**: The backend's transaction API requires a replica set, and the constitution names transactions for every stock write from M2 onward. A standalone node would force a compose change in M2 and would fail any test that uses `django_mongodb_backend.transaction.atomic`. A single-node replica set is enough for development and tests.

**Alternatives considered**: Standalone `mongod` (simpler now, breaks in M2), and Atlas (external dependency, no offline development).

**Source**: https://www.mongodb.com/docs/languages/python/django-mongodb/current/interact-data/transactions/

## D3. Session authentication, not JWT

**Decision**: Sign in with a Django session cookie. DRF uses `SessionAuthentication` plus `IsAuthenticated`. Login and logout are explicit endpoints. CSRF is enforced on unsafe methods.

**Rationale**: Sessions, password hashing, and CSRF are all built into Django. Adding JWT means a new dependency, token storage decisions in the browser, refresh handling, and revoking a token when an account is deactivated. The spec requires deactivation to take effect on the next request, which a database-backed session gives for free. The management frontend arrives later, in the same repository, and can be served from the same site.

**Alternatives considered**: `djangorestframework-simplejwt` (more moving parts, revocation is extra work) and token-in-header custom auth (reinvents both). Revisit only if the frontend is deployed on a separate domain.

**Source**: https://docs.djangoproject.com/en/6.1/topics/auth/default/

## D4. Custom user is an `AbstractUser` subclass with email login

**Decision**: `identity.User` subclasses `AbstractUser`, sets `username = None`, `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`, and uses a custom manager with `create_user` and `create_superuser` that normalize the email. The email field is unique and indexed.

**Rationale**: `AbstractUser` keeps Django admin, permissions, password hashing, and the session auth backend working with no extra code. Only the identifier changes. A hand-rolled `AbstractBaseUser` would force reimplementing admin compatibility and `PermissionsMixin` wiring for no gain.

**Alternatives considered**: `AbstractBaseUser` plus `PermissionsMixin` (more code, same result) and keeping `username` (the spec says email is the identifier).

**Source**: https://docs.djangoproject.com/en/6.1/topics/auth/customizing/

## D5. Store assignments are an `ArrayField` of ObjectIds

**Decision**: `User.store_ids = ArrayField(ObjectIdField(), default=list)`. Scope checks use `store_ids__contains=[store_id]`. List filters use `store_ids__overlap=[...]`.

**Rationale**: The backend ships `ArrayField` and registers `contains` and `overlap` lookups. `ArrayField` rejects only relational base fields, so an ObjectId base field is allowed. This matches macro decision 23, where one person can work at several stores and the assignment list is the only source of scope.

**Alternatives considered**: a separate `StoreAssignment` collection (a join table in a document store, two reads per check, no benefit at this size) and `JSONField` (loses the ObjectId type and the array lookups).

**Source**: https://django-mongodb-backend.readthedocs.io/en/latest/ref/models/fields/

## D6. Employee is a separate collection with a one-to-one reference

**Decision**: `identity.Employee` with `user = OneToOneField(User, on_delete=CASCADE)` and `hire_date`. No credentials, no role, no store field.

**Rationale**: Macro decision 22 keeps `User` and `Employee` as two collections so a future customer is a user with no employment record. A one-to-one reference is the idiomatic Django way to express that and keeps admin usable. Store scope for an employee is the linked user's `store_ids`, so no duplicate store field is needed.

**Alternatives considered**: a bare `user_id = ObjectIdField()` (works, but loses the relation in the admin and in query helpers) and one combined collection (contradicts decision 22).

**Source**: https://django-mongodb-backend.readthedocs.io/en/latest/ref/models/fields/

## D7. Regenerate migrations, do not translate them

**Decision**: Delete the three existing `0001_initial.py` files and regenerate app migrations with `makemigrations`. Generate the contrib migrations into `src/mongo_migrations/` and point `MIGRATION_MODULES` at them. Set `DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"`.

**Rationale**: The existing migrations use integer `AutoField`, which MongoDB does not support. There is no production data and no history worth keeping. Regeneration is smaller and clearer than editing SQL migrations into document migrations. Contrib apps need their own `AppConfig` subclasses because `DEFAULT_AUTO_FIELD` does not override an app config that sets `default_auto_field`.

**Alternatives considered**: hand editing the existing migrations (error prone, no benefit) and keeping the SQL database alongside Mongo (violates the constitution).

**Source**: https://django-mongodb-backend.readthedocs.io/en/latest/intro/configure/

## D8. Store propagation crosses contexts through a public service

**Decision**: `stores` calls `apps.identity.services.add_store_to_regional_managers(store_id)` after a store is created. When an account with the regional manager role is created, `identity.services` assigns every existing store id. `stores` imports no identity model.

**Rationale**: The domain boundary rule allows public service interfaces and forbids model imports. The propagation is a two-collection update and belongs to the identity context, because identity owns roles and assignments. The call is synchronous and local, which is simpler than an event bus in a monolith.

**Alternatives considered**: a domain event with a handler (more machinery for one rule) and identity importing the Store model (forbidden).

## D9. Cross-store access returns 403 with a message

**Decision**: A store-owned record outside the actor's assignments returns HTTP 403 with `{"detail": "This record is outside your store access."}`. It does not return 404.

**Rationale**: The Kyaor chose B during clarification: the response may reveal that the record exists, but it must not reveal any field of it. A 403 states the access boundary plainly and is easier to debug than a false 404.

**Alternatives considered**: 404 to hide existence (the earlier recommendation, rejected by the Kyaor).

## D10. Catalog stays unchanged in M0

**Decision**: Keep `catalog.Product` as it is. It is global read data, never store filtered. The rename to `Item` and the price type fix belong to M2.

**Rationale**: M0 is about access, not catalog shape. The spec only requires catalog items to remain global. Changing the catalog model now adds migration churn with no M0 outcome.

**Alternatives considered**: rename to `Item` now (extra work outside the milestone, and the inventory references do not exist yet).

## D11. Tests run against a real MongoDB

**Decision**: Use pytest with pytest-django. Tests need the Compose MongoDB running. Django creates a `test_` database and drops it after the run. Use `--reuse-db` locally when iterating.

**Rationale**: The backend's query behavior, `ArrayField` lookups, and replica set transactions cannot be faithfully faked with SQLite or an in-memory stub. A real server is the only way to prove store scoping with the actual query engine.

**Alternatives considered**: `mongomock` (does not implement the backend's query compilation or transactions) and testing against Atlas (network dependency, credentials in CI).

**Source**: https://docs.djangoproject.com/en/6.1/topics/testing/overview/

## D12. First admin comes from a management command

**Decision**: `python src/manage.py create_admin --email ... --password ...` creates the first active admin when no active admin exists. It refuses when one already exists.

**Rationale**: A fresh install has no account and no way to sign in, so the system would be unusable. A command is explicit, scriptable, and needs no seed fixture.

**Alternatives considered**: a data migration (runs once, hides the password in history), a fixture file (plaintext password in the repo), and open registration (the spec forbids self registration).

## D13. Pagination and filtering

**Decision**: DRF `PageNumberPagination` with a page size of 20 and a maximum of 100. Filters: `role`, `is_active`, and `store` on accounts, by store id. Response ordering is stable.

**Rationale**: The constitution forbids unbounded lists. Twenty rows is enough for the management screens and keeps tests fast.

**Alternatives considered**: cursor pagination (better for huge collections, unnecessary at this scale) and no pagination (forbidden).

## D14. Password hashing and validation

**Decision**: Use Django's default password hashers. Validate passwords with Django's built-in validators. Never return a password field.

**Rationale**: Defaults are audited and require no dependency. The spec forbids returning password data.

**Alternatives considered**: Argon2 (adds a dependency and a settings change, no M0 requirement).

## D15. CORS and CSRF for a future frontend

**Decision**: Keep `django-cors-headers`. Allow all origins only while `DEBUG` is on. In M0 there is no frontend, so no `CSRF_TRUSTED_ORIGINS` entry is added. Add it when the management frontend gets a fixed origin.

**Rationale**: Session cookies need CSRF handling and `credentials: include` on the browser side. Adding origin settings now, with no frontend, would be guesswork.

**Alternatives considered**: opening CORS in all environments (unsafe in production) and switching to token auth to avoid CSRF (rejected in D3).

## D16. Type hints and linting scope

**Decision**: Add type hints to service functions, the permission helper, and model managers. Run Ruff over `src/` and `tests/`. Do not add mypy in M0.

**Rationale**: The constitution asks for basic type hints. A type checker is a separate tool decision with its own configuration cost, and no M0 requirement depends on it.

**Alternatives considered**: mypy or pyright now (extra configuration, no M0 gate).
