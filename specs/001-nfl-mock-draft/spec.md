# Feature Specification: NFL Mock Draft Experience

**Feature Branch**: `001-nfl-mock-draft`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "Develop UMockMe.com, an NFL MOCK Draft Site where registered users can run Mock Drafts that will attempt to predict what players each team will pick in the upcoming draft. Users will have the ability to modify the default Big Board for each team. The big board is the list of players each team wants to pick in sequential order based on team needs, player strength, team drafting tendencies, etc."

## Clarifications

### Session 2026-09-15

- Q: How should the system combine PFF rankings, NFL.com rankings, SPARQ, school affinity, and team-connection signals when building each team's default big board? → A: UMM_Ranking uses a weighted average of the combined metrics, and each individual rating score is saved in the database for auditability and recalculation.
- Q: When a user starts a mock draft, should they choose a single team to control for the entire draft, or can they control multiple teams across different draft runs? → A: Each draft run has one controlled team chosen at the start; the user can start a new draft to control a different team.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a Mock Draft (Priority: P1)

As a registered user, I want to run a mock draft so that I can predict the players selected by each NFL team in the upcoming draft.

**Why this priority**: Running a draft is the core value of the product and must work independently as the minimum viable experience.

**Independent Test**: A signed-in user can start a draft, make or accept a selection for each pick, complete the draft, and view the resulting selections.

**Acceptance Scenarios**:

1. **Given** a registered user is on the draft start screen, **When** the user starts a new mock draft and selects a team to control, **Then** the system creates a draft with the current team order, available player pool, and that team designated as the user's controlled team.
2. **Given** it is the user's controlled team's turn, **When** the user selects an available player, **Then** the selection is recorded for that team and the draft advances to the next pick.
3. **Given** it is another team's turn, **When** the draft engine reaches that pick, **Then** the system makes the selection automatically according to the configured team board logic and continues the draft.
4. **Given** a player has already been selected, **When** the user attempts to select that player again, **Then** the system rejects the selection and clearly identifies that the player is unavailable.
5. **Given** all configured draft picks are complete, **When** the user finishes the final pick, **Then** the system marks the draft complete and displays the full results in pick order.

---

### User Story 2 - Customize Team Big Boards (Priority: P1)

As a registered user, I want to modify each team's default big board so that my mock draft reflects my evaluation of team needs, player strength, and team tendencies.

**Why this priority**: Personalizing team preferences is the feature that differentiates UMockMe.com from a static draft list.

**Independent Test**: A signed-in user can open a team's default board, reorder players, add an eligible player, remove a player, save the changes, and verify that the updated order is used in a new mock draft.

**Acceptance Scenarios**:

1. **Given** a user views a team's default big board, **When** the user reorders players and saves, **Then** the system preserves the new sequential ranking for that user and team.
2. **Given** a user is editing a team board, **When** the user adds an eligible player who is not currently listed, **Then** the player appears at the chosen ranking position.
3. **Given** a user is editing a team board, **When** the user removes a player, **Then** that player is excluded from the user's board but remains available in the shared player pool unless selected in the draft.
4. **Given** a user has customized a board, **When** the user starts a new mock draft, **Then** the draft uses the user's saved board for that team rather than silently replacing it with the default board.
5. **Given** a user has unsaved board edits, **When** the user attempts to leave the editor, **Then** the system warns that changes will be lost and offers the choice to save or discard them.

---

### User Story 3 - Review and Manage Drafts (Priority: P2)

As a registered user, I want to save and review my mock drafts so that I can compare predictions and revisit my decisions.

**Why this priority**: Draft history gives users continuity and makes their predictions useful beyond a single session.

**Independent Test**: A signed-in user can view a list of their drafts, open a completed draft, and delete a draft from the list.

**Acceptance Scenarios**:

1. **Given** a user has saved drafts, **When** the user opens draft history, **Then** the system shows each draft's status, creation date, and completion state.
2. **Given** a user opens a saved draft, **When** the draft details load, **Then** the system shows the selections in pick order and identifies the team and player for every pick.
3. **Given** a user requests deletion of one of their drafts, **When** the user confirms the action, **Then** the system removes the draft from their history and does not expose it in later searches.
4. **Given** a user requests a draft belonging to another user, **When** the request is processed, **Then** the system denies access without disclosing the draft's contents.

### Edge Cases

- If current draft order, team, or player data is unavailable, the system MUST prevent a new draft from starting and explain what data is missing.
- If a board contains a player who becomes ineligible or unavailable before a draft begins, the system MUST identify the affected entry and require the user to resolve it before starting.
- If a user loses connectivity during a selection, the system MUST avoid creating duplicate picks and show whether the selection was saved after reconnection.
- If two draft actions compete for the same player, only one action may claim the player; the other action MUST receive an availability error.
- If a user has no saved board changes, the system MUST use the current default board.
- If a draft is abandoned, the system MUST preserve its incomplete status and allow the user to resume or discard it.
- If a user submits invalid reorder data, the system MUST reject the update without partially changing the saved board.
- The interface MUST remain usable at representative mobile and desktop viewport sizes, including board editing, draft selection, and history review.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a person to register, sign in, sign out, and recover access to their account.
- **FR-002**: System MUST require authentication before a user can create drafts, customize boards, or access draft history.
- **FR-003**: System MUST maintain the current upcoming draft order, participating teams, eligible players, and available pick count used by a new draft.
- **FR-004**: System MUST allow an authenticated user to start a new mock draft from the current draft data and choose exactly one team to control for that draft run.
- **FR-005**: System MUST present the active pick, team, available players, and enough player information for the user to make an informed selection when it is the controlled team's turn.
- **FR-006**: System MUST record each valid selection with its pick number, team, player, and timestamp.
- **FR-007**: System MUST prevent a player from being selected more than once within the same draft.
- **FR-008**: System MUST support saving, resuming, completing, and discarding an in-progress draft.
- **FR-008A**: System MUST automatically make selections for all non-controlled teams during the draft based on their configured board logic and the current draft state.
- **FR-009**: System MUST provide a default sequential big board for every participating team.
- **FR-010**: System MUST allow an authenticated user to reorder, add, and remove eligible players on a team-specific personal big board.
- **FR-011**: System MUST validate that a personal big board contains only eligible players and a valid, non-duplicated sequence before saving.
- **FR-012**: System MUST preserve personal board changes independently for each user and team.
- **FR-013**: System MUST use the user's saved team board when determining the default recommendation or available ranking for a new mock draft.
- **FR-014**: System MUST allow a user to restore a personal team board to the current default board.
- **FR-015**: System MUST provide a user's draft history with status, created date, updated date, and completion state.
- **FR-016**: System MUST allow a user to view the complete pick sequence for drafts they own.
- **FR-017**: System MUST allow a user to delete drafts they own after an explicit confirmation.
- **FR-018**: System MUST deny access to another user's drafts and personal boards.
- **FR-019**: System MUST protect account credentials and session data and MUST NOT expose credentials or sensitive account data in logs or user-visible errors.
- **FR-020**: System MUST record security-relevant events, including sign-in failures, access denials, board changes, and draft deletions.
- **FR-021**: System MUST provide clear validation, loading, empty, conflict, and error states for registration, draft actions, board editing, and draft history.
- **FR-022**: System MUST support keyboard navigation and readable semantic labels for core draft and board-editing actions.
- **FR-023**: System MUST support the core workflows on mobile and desktop viewport sizes without requiring horizontal scrolling for primary actions.
- **FR-024**: System MUST expose documented service boundaries and versioned contracts for account, draft, player/team data, and board capabilities.
- **FR-025**: System MUST compute a composite UMM_Ranking for each player using a weighted average of the available individual rating signals, including PFF ranking, NFL.com ranking, SPARQ score, school affinity, and team-connection factors.
- **FR-026**: System MUST persist the underlying individual rating values in the database alongside the derived UMM_Ranking so they can be audited, reweighted, and recalculated without losing original signal data.

### Key Entities

- **User**: A registered person who owns drafts and personal team boards; includes account status and audit timestamps.
- **Team**: An NFL team participating in the upcoming draft; includes identity, draft position, and default board.
- **Player**: An eligible draft prospect; includes identity, position, evaluation information, and eligibility status.
- **Player Rating Signal**: A source-specific score such as PFF rank, NFL.com rank, SPARQ score, school affinity value, or team-connection value, including the source name and numeric value.
- **UMM_Ranking**: A derived composite ranking value for a player produced from the weighted average of the stored rating signals.
- **Big Board**: An ordered list of players for one team, with a distinction between the shared default version and a user's personal version.
- **Big Board Entry**: A player's position in a board and the information needed to validate its order and eligibility.
- **Mock Draft**: A user-owned draft session with status, draft context, timestamps, and a sequence of selections.
- **Draft Pick**: One selection in a mock draft, associating a pick number, team, player, and selection time.
- **Audit Event**: A security or ownership-sensitive action recorded with actor, action, outcome, and timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of authenticated users can start a new mock draft and reach the first pick without assistance.
- **SC-002**: At least 90% of valid draft selections appear in the user's draft within 2 seconds under normal operating conditions.
- **SC-003**: At least 90% of users can reorder and save a team board in under 3 minutes during usability evaluation.
- **SC-004**: The system prevents 100% of duplicate-player selections in acceptance and concurrency tests.
- **SC-005**: At least 95% of authorized draft-history requests return the requested content within 2 seconds under normal operating conditions.
- **SC-006**: Unauthorized attempts to access another user's draft or board are denied in 100% of security acceptance tests.
- **SC-007**: Core workflows achieve a minimum 80% automated test coverage threshold for changed executable paths.
- **SC-008**: Users can complete the primary draft, board-editing, and history workflows at both representative mobile and desktop viewport sizes without loss of core functionality.
- **SC-009**: Every player record exposes the underlying rating signals and the composite UMM_Ranking, and the derived score is consistent with the stored signal set during acceptance tests.

## Assumptions

- The first release targets the upcoming NFL draft and uses one authoritative current draft order and player data set at a time.
- A user may maintain one active personal board per team for the current draft context; later releases may support version history.
- Draft recommendations are ranked from board order; automated expert projections or probabilistic simulation are outside this feature unless separately specified.
- Draft history is private by default; public sharing, leaderboards, social comparison, and invitations are outside this feature.
- Account verification and password recovery use the product's approved identity and email capabilities.
- Current NFL team and player data is supplied by an approved internal or external data source and has an identifiable refresh time.
- The initial draft experience uses the configured draft order and pick count; trades and compensatory picks must be represented by the current authoritative draft data before a draft starts.
- The product will be delivered as independently owned service capabilities with documented contracts, while this specification remains focused on user-visible behavior.