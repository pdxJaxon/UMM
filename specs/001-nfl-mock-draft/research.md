# Research: NFL Mock Draft Experience

## Decision

The platform will use a three-layer web architecture consistent with the project constitution:

- FastAPI backend services for domain logic, data persistence, and REST API contracts.
- Flask as the lightweight server/gateway for UI-facing routing or server-side compatibility, while Angular handles the browser UI.
- PostgreSQL as the relational persistence layer for users, teams, players, boards, draft runs, picks, and rating signals.

The default team board will be calculated from a weighted composite score called `UMM_Ranking`. Each source signal is kept in the database, while the derived ranking is recalculated from those inputs. The system will allow exactly one controlled team per draft run; all other teams are simulated automatically using ranked board logic and deterministic draft rules.

## Rationale

This design matches the product goals and the project constitution:

- The product is a mock-draft engine driven by ranking logic and draft simulation, so a backend service layer is the cleanest way to own drafting rules and security checks.
- A structured relational database supports board versions, player records, signals, pick history, and audit events without introducing schema drift.
- Keeping raw signals alongside the derived score supports auditing, recalculation, and future weighting changes without losing original evidence.
- The single-team-controlled-draft model simplifies ownership, authorization, and the user experience while still enabling full-simulation draft runs.
- AI guidance can act as an advisory recommendation layer without changing the core rule model: the user chooses when their team is on the clock, while the rest of the league is still simulated.

## Alternatives considered

### 1. Multi-team controlled draft in one session

Rejected because it adds ambiguity to draft ownership, authorization boundaries, and user expectation. The clarified design is simpler, more testable, and easier to explain to users.

### 2. No derived UMM_Ranking

Rejected because the product requirements explicitly require a weighted composite that is auditable and recalculable. Keeping only a single final score would lose the source signals that later weighting adjustments depend on.

### 3. Pure client-side draft logic

Rejected because it weakens security, auditability, and multi-user isolation. Draft state and player availability must live in the backend service boundary.

### 4. AI-only picks for all teams

Rejected because the product requirement is a realistic mock-draft engine with user-controlled team picks and board-driven automation. AI should be an assistive recommendation component, not the only valid decision engine.

## Key decisions for design

### Ranking model

A player's `UMM_Ranking` is computed using a weighted average of these sources:

- PFF ranking
- NFL.com ranking
- SPARQ score
- school affinity score
- team connection score
- other future signals, if explicitly added with a documented weight

Each source value is stored as a normalized numeric rating signal and associated with the source name, player, and effective date window.

### Draft engine behavior

- The user chooses one team at the start of a draft run.
- That team's picks are interactive, user-driven.
- All other teams are simulated by the engine using the configured board logic.
- The engine tracks picks, pick count, team order, player availability, and board rank.

### Security model

- Authentication is required for all draft and board actions.
- Authorization checks verify user ownership of drafts and personal boards.
- Audit events capture sign-in failures, access denials, board saves, and draft deletions.
- Secrets are never hardcoded and are stored through environment configuration or a secure secret manager.

### AI guidance model

- AI can compare a player's composite score to team needs and historical fit signals.
- AI output should be advisory and reviewable, not authoritative unless explicitly required by the product owner.
- The model can produce a recommended pick for the controlled team, but the user still authorizes the final selection.

## Open issues to resolve during implementation

- Exact weight values for PFF, NFL.com, SPARQ, school affinity, and team connection signals.
- Standardization of normalization for ranking inputs so different scales can be combined safely.
- LLM provider and fallback behavior if AI service is unavailable or returns invalid output.
- Team-specific historical connection logic, including coach/college affiliation and family relationships.
- Audit retention and user-visible history of recommendation events.

These items are deferred to implementation planning and task breakdown, not to the feature specification.
