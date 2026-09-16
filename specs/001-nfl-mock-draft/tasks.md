# Tasks: NFL Mock Draft Experience

**Input**: Design documents from `/specs/001-nfl-mock-draft/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create backend, frontend, and shared contract directories per implementation plan
- [ ] T002 Initialize Python FastAPI backend project with dependency management and environment config
- [ ] T003 Initialize Angular frontend workspace and Flask gateway shell
- [ ] T004 [P] Configure linting, formatting, and static analysis tools
- [ ] T005 [P] Configure PostgreSQL database connection and migration tooling
- [ ] T006 [P] Configure pytest, pytest-cov, and baseline test execution for backend and UI validation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**Critical**: No user story work can begin until this phase is complete

- [ ] T007 Create base application configuration, settings, and secret management
- [ ] T008 Create shared database models for users, teams, players, colleges, and audit events
- [ ] T009 Set up authentication and authorization framework with secure sessions and ownership checks
- [ ] T010 Set up REST API routing, middleware, error-handling, and request validation
- [ ] T011 Create base service layer interfaces and dependency injection structure
- [ ] T012 [P] Create logging, telemetry, and health-check endpoints for the backend services
- [ ] T013 [P] Implement seed data loaders for teams, colleges, and players for the draft cycle
- [ ] T014 Validate environment bootstrap using the quickstart workflow

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Run a Mock Draft (Priority: P1) 🎯 MVP

**Goal**: Deliver the core ability to start a draft, control one team, and complete a full simulation.

**Independent Test**: A registered user can start a draft, select the controlled team, complete the picks for that team, and verify all other teams are auto-simulated.

### Tests for User Story 1

- [ ] T015 [P] [US1] Contract test for draft creation in backend/tests/contract/test_draft_create.py
- [ ] T016 [P] [US1] Contract test for draft pick submission in backend/tests/contract/test_draft_pick.py
- [ ] T017 [P] [US1] Integration test for one-team-controlled draft flow in backend/tests/integration/test_mock_draft_flow.py

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create DraftRun model and persistence schema in backend/app/models/draft_run.py
- [ ] T019 [P] [US1] Create DraftPick model and persistence schema in backend/app/models/draft_pick.py
- [ ] T020 [US1] Implement draft service logic for start, control-team assignment, and state transitions in backend/app/services/draft_service.py
- [ ] T021 [US1] Implement automatic selection engine for non-controlled teams in backend/app/services/selection_engine.py
- [ ] T022 [US1] Implement REST endpoints for draft creation, retrieval, and pick submission in backend/app/api/drafts.py
- [ ] T023 [US1] Implement player availability validation, duplicate selection prevention, and round/pick progression logic
- [ ] T024 [US1] Add audit logging for draft start, pick actions, and access denial events
- [ ] T025 [US1] Add UI screen for draft start and controlled-team selection in frontend/angular-app/src/app/draft/
- [ ] T026 [US1] Add UI screen for active draft pick entry in frontend/angular-app/src/app/draft/
- [ ] T027 [US1] Add responsive mobile and desktop layout for the draft experience in Angular components and styles

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Customize Team Big Boards (Priority: P1)

**Goal**: Deliver the ability to view, reorder, save, and restore team boards with user-specific overrides.

**Independent Test**: A signed-in user can open a team board, reorder players, save a version, and then verify the saved board is used in a new draft.

### Tests for User Story 2

- [ ] T028 [P] [US2] Contract test for team board retrieval in backend/tests/contract/test_team_board_read.py
- [ ] T029 [P] [US2] Contract test for team board save in backend/tests/contract/test_team_board_write.py
- [ ] T030 [P] [US2] Integration test for board customization and restore flow in backend/tests/integration/test_team_board_flow.py

### Implementation for User Story 2

- [ ] T031 [P] [US2] Create TeamBoard and TeamBoardEntry models in backend/app/models/team_board.py
- [ ] T032 [P] [US2] Create PlayerRatingSignal and UMM_RankingSnapshot models in backend/app/models/ranking.py
- [ ] T033 [US2] Implement board ranking service and recomputation logic in backend/app/services/board_service.py
- [ ] T034 [US2] Implement weighted UMM_Ranking calculator and source-signal storage in backend/app/services/ranking_service.py
- [ ] T035 [US2] Implement REST endpoints for board read/write/restore in backend/app/api/boards.py
- [ ] T036 [US2] Validate board entries, duplicates, and invalid reorder actions
- [ ] T037 [US2] Add board editor UI and save/discard workflows in frontend/angular-app/src/app/boards/
- [ ] T038 [US2] Add responsive board layout and mobile-friendly ordering controls in frontend styles and templates

**Checkpoint**: At this point, User Stories 1 and 2 should both work independently

---

## Phase 5: User Story 3 - Review and Manage Drafts (Priority: P2)

**Goal**: Deliver draft history, ownership controls, and privacy-safe review of completed and active drafts.

**Independent Test**: A user can access only their own drafts, view the final pick sequence, and delete selected drafts after confirmation.

### Tests for User Story 3

- [ ] T039 [P] [US3] Contract test for draft history retrieval in backend/tests/contract/test_draft_history.py
- [ ] T040 [P] [US3] Contract test for draft deletion in backend/tests/contract/test_draft_delete.py
- [ ] T041 [P] [US3] Integration test for access control and history review in backend/tests/integration/test_draft_history_access.py

### Implementation for User Story 3

- [ ] T042 [P] [US3] Create audit event model and access-control logging in backend/app/models/audit_event.py
- [ ] T043 [US3] Implement draft history service and authorization checks in backend/app/services/history_service.py
- [ ] T044 [US3] Implement REST endpoints for draft list, detail view, and deletion in backend/app/api/history.py
- [ ] T045 [US3] Add draft history view and delete confirmation UI in frontend/angular-app/src/app/history/
- [ ] T046 [US3] Add user-facing empty-state, error state, and loading state handling for draft history screens

**Checkpoint**: All MVP user stories should now be independently functional

---

## Phase 6: User Story 4 - AI-Guided Draft Recommendations (Priority: P2)

**Goal**: Add LLM-assisted recommendations for the user's controlled team while keeping the system auditable and user-controlled.

**Independent Test**: A recommendation can be generated for the controlled team, the response includes rationale and confidence, and the user can accept or ignore it.

### Tests for User Story 4

- [ ] T047 [P] [US4] Contract test for AI recommendation endpoint in backend/tests/contract/test_ai_recommendation.py
- [ ] T048 [P] [US4] Integration test for recommendation workflow in backend/tests/integration/test_ai_guided_pick.py

### Implementation for User Story 4

- [ ] T049 [P] [US4] Create AI recommendation service and provider abstraction in backend/app/services/ai_recommendation_service.py
- [ ] T050 [US4] Add model adapter for external LLM provider and fallback failure handling
- [ ] T051 [US4] Add recommendation endpoint in backend/app/api/recommendations.py
- [ ] T052 [US4] Add UI callout and evaluation panel for AI suggestion in frontend/angular-app/src/app/draft/
- [ ] T053 [US4] Ensure recommendation output is logged with audit context and does not override user decision without explicit confirmation

**Checkpoint**: The draft engine has a user-guided AI assistive mode without breaking ownership rules

---

## Phase 7: Cross-Cutting Polish and Hardening

**Purpose**: Security, performance, documentation, and readiness improvements across all stories

- [ ] T054 [P] Add security regression tests for authentication, authorization, and access denial paths
- [ ] T055 [P] Add database migration and seed validation for all major entities
- [ ] T056 [P] Review and update docstrings for all API, service, and model modules
- [ ] T057 [P] Run full backend and frontend test suites for the feature
- [ ] T058 [P] Validate responsive behavior on representative mobile and desktop breakpoints
- [ ] T059 [P] Run coverage gate to confirm at least 80% of executable code paths are covered for changed code
- [ ] T060 [P] Execute the quickstart guide and confirm the end-to-end user workflow passes
- [ ] T061 Final review of auditability, ranking traceability, and AI recommendation accountability

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup completion - blocks all user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion
- **Polish (Phase 7)**: Depends on all desired stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational phase
- **User Story 2 (P1)**: Can start after Foundational phase and may integrate with US1
- **User Story 3 (P2)**: Can start after Foundational phase and may integrate with US1/US2
- **User Story 4 (P2)**: Can start after US1 and US2 are stable enough to support AI recommendation flows

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel
- User Story tasks within each story can run in parallel where they touch different files
- Stories 1 and 2 can be started in parallel once foundation is complete
- Story 4 can begin after the draft core is valid and stable

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup + Foundational
2. Complete User Story 1
3. Validate independently with contract and integration tests
4. Deploy/demo if the MVP is stable

### Incremental Delivery

1. Add User Story 1: draft simulation and controlled team selection
2. Add User Story 2: custom board logic and ranking data
3. Add User Story 3: history and access control
4. Add User Story 4: AI recommendation support
5. Finish with hardening, coverage, and responsive validation

### Parallel Team Strategy

With multiple developers:

1. Complete Setup + Foundational together
2. Divide by story ownership:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
   - Developer D: User Story 4
3. Consolidate and validate in integration batches

---

## Notes

- [P] tasks = different files and no direct dependency
- User story tasks should remain independently testable
- Contract tests should be written before implementation for each endpoint
- Integration tests should validate the user journey end-to-end
- Coverage and security gates are required before declaration of readiness
- AI recommendation features must remain advisory and auditable
