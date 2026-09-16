<!--
Sync Impact Report:
- Version change: scaffold -> 1.0.0
- Modified principles: placeholder principles replaced with five project principles
- Added sections: Technology Constraints, Quality and Delivery Gates
- Removed sections: none
- Follow-up TODOs: confirm the original ratification date
-->
# UMM Constitution

## Core Principles

### I. Microservice Boundaries
Each business capability MUST be implemented as an independently deployable microservice with
an explicit API contract, isolated ownership of its data, and a documented health and failure
model. Services MUST communicate through versioned contracts and MUST NOT access another service's
database directly. This preserves deployability, fault isolation, and clear ownership.

### II. Python Service Stack
All backend microservices MUST use Python and FastAPI. The presentation boundary MUST use Python
Flask where a server-side web or gateway layer is required, and Angular MUST provide the browser
application. Technology choices MAY be extended only when a design record documents the reason,
the operational impact, and the replacement or integration boundary.

### III. Documented and Testable Code
All production code MUST include complete docstring-style documentation for public modules,
classes, functions, endpoints, and non-obvious behavior. Every production change MUST include
unit tests for its behavior, error paths, and security-sensitive branches. Automated coverage MUST
be at least 80% of executable code paths for the affected service or application, and coverage
gates MUST fail below that threshold unless an explicitly reviewed exclusion is documented.

### IV. Responsive User Experience
Angular interfaces and Flask-rendered pages MUST support mobile and desktop viewport sizes without
loss of core functionality. Responsive behavior MUST be verified for representative mobile and
desktop viewports, including navigation, forms, tables, loading states, and error states. Layout
decisions MUST use accessible semantic structure and keyboard-operable controls.

### V. Secure by Default
Security MUST be considered during design, implementation, testing, deployment, and review. Services
MUST validate inputs, enforce authentication and authorization at the owning boundary, protect
secrets through configuration or a secret manager, use secure transport where applicable, and
avoid logging credentials or sensitive personal data. Security-relevant actions MUST be auditable,
and dependency, threat, and vulnerability checks MUST be part of the delivery pipeline.

## Technology Constraints

FastAPI is the required framework for backend services. Flask is the required Python framework for
server-side UI or gateway responsibilities, and Angular is the required browser UI framework.
Shared schemas, API contracts, configuration, and service runbooks MUST be versioned with the
owning service. New cross-service infrastructure MUST document ownership, availability expectations,
observability, and data-protection requirements.

## Quality and Delivery Gates

Before merge, changes MUST pass formatting and static analysis checks, unit tests, the applicable
80% coverage gate, API or contract tests for changed boundaries, and security checks. UI changes
MUST include responsive verification for mobile and desktop breakpoints. A pull request MUST
identify changed services, migrations, security implications, operational considerations, and any
intentional test exclusions. Failing gates require correction or an approved, documented exception.

## Governance
<!-- Example: Constitution supersedes all other practices; Amendments require documentation, approval, migration plan -->

This constitution supersedes conflicting project practices. Every feature specification, plan, code
review, and release MUST verify compliance with these principles. Amendments require a documented
rationale, an updated Sync Impact Report, and a semantic version change. Versioning follows
semantic versioning: MAJOR for incompatible governance changes, MINOR for new or materially expanded
principles, and PATCH for clarifications that do not change obligations. Compliance MUST be reviewed
at each pull request and release; exceptions MUST name an owner, scope, rationale, compensating
control, and expiration or review date.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): confirm original adoption date | **Last Amended**: 2026-09-15
