# FairToy — Agent Instructions

## Project Overview

FairToy is a supply-chain traceability application
for identifying potential child-labor exposure
in toy manufacturing.

## Source of Truth

Before making changes, read the relevant documents:

- specs/specs.md
- specs/data-model.md
- specs/implementation.md

## Development Rules

1. Implement only the assigned phase or task.
2. Do not introduce features outside the specifications.
3. Do not silently change business rules or the database schema.
4. Report ambiguities and contradictions before implementation.
5. Prefer simple, maintainable solutions.
6. Keep domain logic separate from transport and UI logic.
7. Write tests for important business rules.
8. Run relevant tests after modifications.
9. Do not modify specifications to justify existing code.
10. Do not commit or push changes unless explicitly instructed.

## Before Implementation

Provide:

- Your understanding of the assigned scope.
- Files you expect to create or modify.
- Important technical decisions.
- Any ambiguities or blockers.

Wait for approval before implementation.

## After Implementation

Provide:

- Summary of changes.
- Tests executed and their results.
- Acceptance criteria satisfied.
- Remaining limitations.
- Any deviations from the specifications.

## Review Principles

- Correctness before optimization.
- Remove unnecessary abstractions.
- Avoid unrelated refactoring.
- Prefer explicit behavior over hidden assumptions.
- Do not claim tests passed unless they were executed.