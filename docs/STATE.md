# HermesOps state after milestone 3E

Base before this milestone: `2350dc9049258bc880bbc467a1b8bfbbb925b6a8`.

Milestone 3E adds migration 007 and the deterministic Recovery Manager. Tests
simulate an abandoned worker, an interrupted review, a missing worktree, a
power loss after Git fast-forward but before SQLite finalization, a divergent
default branch, and a corrupted snapshot. The resulting decisions cover
`RESUME_SAFE`, `ROLLBACK_SAFE`, and `BLOCK_HUMAN`, including resource cleanup,
approval creation, idempotent terminal handling, and safe fixture restoration.


3E v2 fixes the only failure observed during the first real milestone run.
All recovery decisions and scenarios passed, but deleting the abandoned
worker clone left an empty project parent directory. The inherited 3B worker
foundation correctly rejected that residue. The Recovery Manager now prunes
empty clone parents after per-run cleanup and after global orphan cleanup.
