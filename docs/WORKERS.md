# Controlled worker lifecycle

1. Controller creates a standalone Git clone.
2. Controller starts and audits a DIND sandbox.
3. Controller labels it with the Hermes task/profile reuse identity.
4. Hermes attaches to the existing sandbox.
5. Worker commits in the standalone clone.
6. Controller verifies/imports the commit.
7. Controller removes the sandbox in `finally`.
