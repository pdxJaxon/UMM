# Implementation Plan: NFL Mock Draft Experience

**Branch**: `001-nfl-mock-draft` | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-nfl-mock-draft/spec.md`

## Summary

This feature delivers an NFL mock-draft platform where a registered user selects one controlled team for a draft run, makes picks when that team is on the clock, and relies on automated board-driven selection logic for all other teams. The default board for each team is derived from weighted player metrics, including PFF ranking, NFL.com ranking, SPARQ, school affinity, and team-connection signals, aggregated into a UMM_Ranking score that is stored alongside its source inputs. The application architecture follows the project constitution: Python FastAPI for backend services, PostgreSQL for persistence, Flask for server-side/UI gateway concerns, Angular for the browser experience, REST APIs for integration boundaries, and security and coverage gates at every step.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, PostgreSQL, SQLAlchemy, Pydantic, Flask, Angular, pytest, pytest-cov, OpenAI-compatible LLM client or similar model SDK, Redis or queue support if async orchestration is needed

**Storage**: PostgreSQL for relational data, including users, teams, players, boards, draft runs, picks, and rating signals; optional cache or queue for LLM orchestration and background tasks

**Testing**: pytest, pytest-cov, integration and contract tests, API tests, UI tests for responsive flows, security tests for authorization and access control

**Target Platform**: Linux-based application servers with web browser clients; responsive desktop and mobile experience

**Project Type**: Web application with multiple service boundaries and a browser UI

**Performance Goals**: Draft selection and board recalculation should respond within a few seconds under normal load; API p95 latency targeted under 500 ms for authenticated reads and under 2 seconds for AI-assisted recommendation generation in steady state

**Constraints**: Must use FastAPI for backend services; must use Flask and Angular for the UI stack; must maintain microservice boundaries; must store raw rating signals and derived UMM_Ranking; must support mobile and desktop layout compliance; must preserve 80% minimum test coverage on relevant code paths; must protect secrets and enforce authorization checks

**Scale/Scope**: MVP targets one active NFL draft cycle, multiple teams, many prospects, and a limited number of authenticated users; architecture must support scaling to more users and additional draft-driven features later

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Pass: Microservice boundaries are explicit and each service owns its data contract.
- Pass: Backend services use Python FastAPI as required.
- Pass: Front-end UI uses Python Flask and Angular as required.
- Pass: All code must be documented with docstrings and tested with 80% minimum coverage.
- Pass: Responsive design is required for mobile and desktop users.
- Pass: Security controls are required for authentication, authorization, secrets, and audit events.
- Pass: The product must maintain separate raw signal data and derived ranking data for auditability.
- No unjustified constitutional violations found.

## Project Structure

### Documentation (this feature)

```text
specs/001-nfl-mock-draft/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
├── spec.md              # Product requirement specification
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── services/
│   ├── schemas/
│   └── workers/
├── tests/
│   ├── contract/
│   ├── integration/
│   └── unit/
├── requirements.txt
├── pyproject.toml
└── Dockerfile

frontend/
├── angular-app/
│   ├── src/
│   ├── e2e/
│   └── package.json
├── flask-gateway/
│   ├── app/
│   ├── templates/
│   └── requirements.txt
└── tests/

shared/
├── contracts/
├── schemas/
└── docs/
```

**Structure Decision**: Use a clear split between an API-focused backend service layer and a UI shell layer. The backend will own domain logic and persistence; the Flask and Angular surfaces will present the UI and call the FastAPI APIs; shared contracts will provide the interface definitions used across services.

## Complexity Tracking

No constitution violations require special justification beyond the planned service split and AI-assisted recommendation layer.
