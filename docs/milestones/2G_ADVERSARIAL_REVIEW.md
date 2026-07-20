# Milestone 2G adversarial review

The review was performed against published commit
`b2999e1d96a9cb8f40ca298403e55a8d1b226cd4`.

Eight defects were reproduced and corrected:

1. Duplicate security-sensitive HTTP headers were accepted. A proxy and the
   Controller could therefore disagree about Cookie, Content-Length,
   Content-Type, Origin, Idempotency-Key or X-CSRF-Token.
2. Duplicate JSON object members were silently resolved with last-value-wins
   semantics.
3. Non-finite numbers, lone Unicode surrogates and excessively nested JSON
   could bypass strict JSON semantics or reach an internal-error path.
4. Semantic validation occurred before an existing idempotency reservation was
   checked, allowing a reused key to return a validation error instead of the
   required conflict.
5. The persisted request digest was an unkeyed SHA-256 verifier, allowing
   offline guesses of low-entropy objective content after database disclosure.
6. Resuming a paused future objective replaced its original `not_before` with
   the current time, making it immediately dispatchable.
7. Pausing a `CANCEL_REQUESTED` objective replaced cancellation with a pause.
8. Unknown persisted objective states were normalized by mutations instead of
   failing closed.

The installed-service command probe now exercises create, pause, resume and
cancel and verifies that the 2099 schedule survives resume before cleanup.
No route or migration is added by this review.
