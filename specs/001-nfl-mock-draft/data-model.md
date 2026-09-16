# Data Model: NFL Mock Draft Experience

## Overview

The data model supports user-owned draft runs, team boards, player ratings, and auditability for scoring logic. The system stores raw rating signals and derived `UMM_Ranking` values so that rankings can be recomputed without losing the original source information.

## Entities

### User

Represents a registered account.

Fields:
- id: UUID
- email: string
- password_hash: string
- first_name: string
- last_name: string
- created_at: timestamp
- updated_at: timestamp
- is_active: boolean

Relationships:
- one-to-many with DraftRun
- one-to-many with TeamBoard
- one-to-many with AuditEvent

### Team

Represents an NFL franchise.

Fields:
- id: UUID
- name: string
- city: string
- abbreviation: string
- draft_order: integer
- created_at: timestamp

Relationships:
- one-to-many with TeamBoard
- one-to-many with DraftPick
- many-to-one with DraftRun through round and pick sequence

### Player

Represents a draft prospect.

Fields:
- id: UUID
- first_name: string
- last_name: string
- full_name: string
- college_id: UUID
- position: string
- height: string or numeric
- weight: numeric
- draft_year: integer
- eligibility_status: enum
- created_at: timestamp
- updated_at: timestamp

Relationships:
- many-to-one with College
- one-to-many with PlayerRatingSignal
- one-to-many with DraftPick

### College

Represents the school a player attended.

Fields:
- id: UUID
- name: string
- mascot: string
- conference: string
- created_at: timestamp

Relationships:
- one-to-many with Player
- one-to-many with TeamConnectionRule

### PlayerRatingSignal

Stores the raw value for each ranking source.

Fields:
- id: UUID
- player_id: UUID
- source_name: enum (`PFF`, `NFL_COM`, `SPARQ`, `COLLEGE_AFFINITY`, `TEAM_CONNECTION`, `CUSTOM`)
- metric_value: numeric
- normalized_value: numeric
- effective_start: timestamp
- effective_end: timestamp|null
- created_at: timestamp
- updated_at: timestamp

Relationships:
- many-to-one with Player
- supports one-to-many with UMM_RankingSnapshot

### UMM_RankingSnapshot

Stores the derived weighted score.

Fields:
- id: UUID
- player_id: UUID
- value: numeric
- weighting_version: string
- computed_at: timestamp
- created_at: timestamp

Relationships:
- many-to-one with Player
- optional many-to-one with TeamBoard if a team-specific ranking is derived

### TeamBoard

Represents a team's board within a user's draft context.

Fields:
- id: UUID
- user_id: UUID
- team_id: UUID
- board_type: enum (`DEFAULT`, `PERSONAL`)
- name: string
- version: integer
- created_at: timestamp
- updated_at: timestamp

Relationships:
- many-to-one with User
- many-to-one with Team
- one-to-many with TeamBoardEntry

### TeamBoardEntry

Stores an ordered ranking entry for a team board.

Fields:
- id: UUID
- team_board_id: UUID
- player_id: UUID
- rank_position: integer
- is_active: boolean
- created_at: timestamp
- updated_at: timestamp

Relationships:
- many-to-one with TeamBoard
- many-to-one with Player

### DraftRun

Represents a draft simulation session.

Fields:
- id: UUID
- user_id: UUID
- controlled_team_id: UUID
- status: enum (`DRAFTING`, `PAUSED`, `COMPLETED`, `CANCELLED`)
- draft_year: integer
- created_at: timestamp
- updated_at: timestamp
- completed_at: timestamp|null

Relationships:
- many-to-one with User
- many-to-one with Team as controlled team
- one-to-many with DraftPick

### DraftPick

Represents a pick in a draft run.

Fields:
- id: UUID
- draft_run_id: UUID
- pick_number: integer
- round_number: integer
- team_id: UUID
- player_id: UUID
- selection_source: enum (`USER`, `AUTO`, `AI_RECOMMENDATION`)
- selected_at: timestamp

Relationships:
- many-to-one with DraftRun
- many-to-one with Team
- many-to-one with Player

### TeamConnectionRule

Captures historical or relational fit between a player and a team.

Fields:
- id: UUID
- team_id: UUID
- college_id: UUID|null
- coach_affiliation: boolean
- family_connection: boolean
- other_connection_type: string|null
- score_weight: numeric
- created_at: timestamp

Relationships:
- many-to-one with Team
- many-to-one with College

### AuditEvent

Stores high-value security and ownership events.

Fields:
- id: UUID
- user_id: UUID|null
- event_type: enum
- actor_type: string
- target_type: string
- target_id: UUID|null
- outcome: enum (`SUCCESS`, `FAILURE`, `DENIED`)
- details: jsonb
- created_at: timestamp

Relationships:
- many-to-one with User

## Relationships summary

- One User owns many DraftRun records.
- One User owns many TeamBoard records.
- One Team has many TeamBoard records and many DraftPick records.
- One Player can have many PlayerRatingSignal entries and many TeamBoardEntry occurrences.
- One DraftRun contains many DraftPick records.
- One TeamBoard contains many TeamBoardEntry records.
- One DraftRun has exactly one controlled team and many auto-simulated picks for non-controlled teams.

## Validation rules

- A DraftRun must have exactly one controlled_team_id.
- A TeamBoardEntry cannot duplicate a player within the same board version.
- A DraftPick cannot select a player more than once in the same DraftRun.
- `UMM_Ranking` value must be reproducible from the current stored signal set unless a weight version change is explicitly documented.
- AuditEvent must be written for unauthorized access attempts and security-sensitive changes.
- A user can only view or modify their own board and draft data.

## Future extension hooks

- Draft trade simulation
- Multi-round board versioning
- Public leaderboard sharing
- AI recommendation explanation logs
- advanced historical team tendencies
