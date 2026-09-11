# CoffeeShopManagement Constitution

<!-- Sync Impact Report:
Version change: 0.0.1 → 0.0.2
Modified principles:
  - 1. Modular Monolith Architecture
  - 2. Ponytail Philosophy (Pragmatic Simplicity)
  - 3. Strict Spec-Driven Development (SDD) Workflow
  - 4. Code Quality & Tooling Standards
Added sections:
  - Development Constraints
  - Governance (separate from combined section)
Removed sections:
  - (The combined 'Development Constraints & Governance' section is replaced by two distinct sections)
TODOs: None
-->

## Core Principles

### 1. Modular Monolith Architecture
- The application is a Modular Monolith built with Python 3.12+ and Django.
- Every business domain must reside in its own isolated module under `apps/` (e.g., `apps/catalog`, `apps/stores`, `apps/workforce`).
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

## Development Constraints

- **Complexity Justification:** Any pull request introducing new abstractions or third-party dependencies outside `uv` must justify why a simpler, idiomatic Django solution is insufficient.

## Governance

- **Supremacy:** This Constitution supersedes all informal architectural decisions or ad-hoc code practices.
- **Amendments:** Changes to this Constitution require documentation and clear architectural justification, followed by a formal review and approval process.
- **Versioning Policy:** The Constitution version adheres to semantic versioning: MAJOR for backward-incompatible changes, MINOR for additions or significant expansions, and PATCH for clarifications or minor refinements.
- **Compliance Review:** All code contributions and architectural decisions MUST be reviewed for compliance with these principles before integration.

**Version**: 0.0.2 | **Ratified**: 2026-09-10 | **Last Amended**: 2026-09-10
