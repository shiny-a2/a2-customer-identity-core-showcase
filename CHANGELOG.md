# Changelog

## [Unreleased]

No changes yet.

## [0.3.0] - 2026-08-05

### Added

- Added the reviewed domain model for one-time code verification and send limits, covered by adversarial tests for expiry, replay, cross-device use, stale parallel claims, and atomic quota ceilings.
- Added deadlines to every held verification, so a worker that stops mid-flight releases its claim instead of locking a customer out of their own sign-in until the code expires.
- Added a recovery path out of the state between a correct code and an issued session, which previously had no exit and so kept holding what it was protecting.
- Added scheduled dependency review, so an advisory published after the last change is reported rather than waiting for the next one.

### Changed

- Validated audit records as a whole rather than field by field, refusing entries whose parts are each valid but jointly impossible.
- Narrowed operational detail in audit records from free text to a closed vocabulary, since a free-form field eventually receives something that identifies a person.
- Recovery never returns a spent verification attempt, so an induced stall cannot be traded for extra guesses.

### Security

- Kept the runtime deliberately disabled: no schema applied, no customer data processed, and no staging or Production behavior changed.
- Reworked two verification guards after testing the guards themselves rather than the code they cover. A scanning scope proved to be exempting a whole file instead of a known-safe pattern within it, and a pipeline-integrity check compared a digest before evaluating its structural rules, so its bypass cases never reached a rule. Both are now proven by tests that fail unless a planted problem is actually reported.

## [0.2.0] - 2026-07-17

### Added

- Released the first privately reviewed implementation foundation for centralized customer identity.
- Added testable validation, fail-closed service boundaries, repeatable packaging, and automated quality and privacy checks.
- Documented the remaining approval gates for migration, pilot validation, and deployment.

### Changed

- Advanced the public milestone from architecture-only to an implemented but deliberately non-operational foundation.

### Safety note

- No database schema was applied.
- No customer data was processed.
- No staging deployment or Production behavior changed.
- This showcase contains no production source, credentials, customer information, infrastructure identifiers, or sensitive implementation details.

## [0.1.0] - 2026-07-14

### Added

- Published the design milestone for a centralized verified-customer identity boundary.
- Documented transaction-safe OTP, session-bound authorization, duplicate-safe resolution, encrypted additive storage, and privacy-safe audit goals.
- Added staged delivery, security testing, performance protection, and secure rollback expectations.

### Safety note

- This release is a public architecture showcase only. It contains no production code, credentials, customer data, sensitive infrastructure, or deployment claim.
