from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str, filename: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load {filename}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


ORCHESTRATOR = load_script(
    "lifecycle_stabilization_orchestrator",
    "hermesops-orchestrator.py",
)
OBJECTIVES = load_script(
    "lifecycle_stabilization_objectives",
    "hermesops-objectives.py",
)
INTEGRATOR = load_script(
    "lifecycle_stabilization_integrator",
    "hermesops-integrator.py",
)


NOW = "2026-08-16T10:00:00.000Z"
PROJECT_ID = "lifecycle-project"
OWNER = "orchestrator:test-instance:pipeline"


class LifecycleStabilizationRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "hermesops.db"
        self.runtime = self.root / "runtime"
        self._apply_migrations()
        self._seed_roles_and_project()

        for module in (ORCHESTRATOR, OBJECTIVES, INTEGRATOR):
            module.DATABASE = self.database
        ORCHESTRATOR.RUNTIME = self.runtime / "orchestrator"
        ORCHESTRATOR.OBJECTIVE_RUNTIME = self.runtime / "objectives"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _apply_migrations(self) -> None:
        with sqlite3.connect(self.database) as connection:
            for migration in sorted((REPOSITORY / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
                connection.executescript(migration.read_text(encoding="utf-8"))

    def _seed_roles_and_project(self) -> None:
        with contextlib.closing(self.connect()) as connection:
            for role_id, role_kind, workspace_mode in (
                ("orchestrator", "orchestrator", "controller_only"),
                ("worker", "worker", "write"),
                ("reviewer", "reviewer", "read_only"),
            ):
                connection.execute(
                    """
                    INSERT INTO roles (
                        role_id, profile_name, role_kind, description,
                        reasoning_effort, max_turns, toolsets_json, skills_json,
                        workspace_mode, may_commit, may_push, network_enabled,
                        cpu_limit, memory_mb, enabled, config_source, config_hash,
                        registered_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'medium', 10, '[]', '[]', ?, 0, 0, 0,
                              1, 512, 1, ?, ?, ?, ?)
                    """,
                    (
                        role_id,
                        f"test-{role_id}",
                        role_kind,
                        f"Test {role_kind}",
                        workspace_mode,
                        str(self.root / "roles.toml"),
                        role_id * 8,
                        NOW,
                        NOW,
                    ),
                )
            connection.execute(
                """
                INSERT INTO projects (
                    project_id, display_name, repo_path, data_path, policy_id,
                    enabled, config_source, config_hash, registered_at, updated_at
                ) VALUES (?, 'Lifecycle project', ?, ?, 'default', 1, ?, ?, ?, ?)
                """,
                (
                    PROJECT_ID,
                    str(self.root / "repository"),
                    str(self.root / "data"),
                    str(self.root / "project.toml"),
                    "a" * 64,
                    NOW,
                    NOW,
                ),
            )
            connection.execute(
                """
                INSERT INTO orchestrator_instances (
                    instance_id, hostname, pid, owner, version, status,
                    started_at, heartbeat_at
                ) VALUES ('test-instance', 'localhost', 1, 'test',
                          'orchestrator-v2', 'RUNNING', ?, ?)
                """,
                (NOW, NOW),
            )
            connection.commit()

    @staticmethod
    def _plan(*tasks: dict[str, Any], objective: str = "Lifecycle regression") -> dict[str, Any]:
        return {
            "schema_version": 1,
            "objective": objective,
            "max_parallel_tasks": 2,
            "tasks": list(tasks),
        }

    @staticmethod
    def _task(
        key: str,
        *,
        kind: str = "NOOP",
        project_id: str | None = None,
        role_id: str | None = None,
        dependencies: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "kind": kind,
            "project_id": project_id,
            "role_id": role_id,
            "priority": 100,
            "instruction": f"Execute {key}",
            "acceptance_criteria": [f"{key} completed"],
            "marker": f"{key.upper()}_DONE" if kind == "PIPELINE" else None,
            "max_attempts": 1,
            "dependencies": dependencies or [],
        }

    def _insert_objective(
        self,
        *,
        source: str,
        plan_id: str | None = None,
    ) -> str:
        return OBJECTIVES.insert_objective(
            objective="Lifecycle stabilization objective",
            source=source,
            priority=10,
            not_before=NOW,
            project_ids=[PROJECT_ID],
            max_parallel_tasks=1,
            planning_max_attempts=3,
            plan_id=plan_id,
        )

    def _command(self, function: Any, objective_id: str) -> None:
        original_payload = OBJECTIVES.objective_payload
        OBJECTIVES.objective_payload = lambda _: {}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                function(argparse.Namespace(objective=objective_id))
        finally:
            OBJECTIVES.objective_payload = original_payload

    def _row(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row:
        with contextlib.closing(self.connect()) as connection:
            row = connection.execute(sql, parameters).fetchone()
        self.assertIsNotNone(row)
        return row

    def _create_running_plan(self) -> tuple[str, str, str, sqlite3.Row]:
        plan_id = ORCHESTRATOR.insert_plan(
            self._plan(
                self._task(
                    "pipeline",
                    kind="PIPELINE",
                    project_id=PROJECT_ID,
                    role_id="worker",
                ),
                self._task("after_cancel"),
            ),
            source="TEST",
            initial_status="READY",
        )
        objective_id = self._insert_objective(source="TEST", plan_id=plan_id)
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE objective_queue SET status='RUNNING' WHERE objective_id=?",
                (objective_id,),
            )
            connection.commit()
        ORCHESTRATOR.refresh_plan_states(plan_id)
        task_id = str(
            self._row(
                "SELECT orchestration_task_id FROM orchestration_tasks "
                "WHERE plan_id=? AND task_key='pipeline'",
                (plan_id,),
            )[0]
        )
        attempt_id, _, task = ORCHESTRATOR.reserve_attempt(
            task_id,
            instance_id="test-instance",
        )
        return objective_id, plan_id, attempt_id, task

    def _insert_run(self, run_id: str, *, status: str = "RUNNING") -> None:
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, project_id, status, base_commit, result_commit,
                    worktree_path, metadata_json, created_at, started_at,
                    heartbeat_at, branch_name, transaction_owner
                ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    PROJECT_ID,
                    status,
                    "a" * 40,
                    "b" * 40,
                    str(self.root / "worktree"),
                    NOW,
                    NOW,
                    NOW,
                    "hermesops/test-run",
                    OWNER,
                ),
            )
            connection.execute(
                """
                INSERT INTO project_locks (
                    project_id, run_id, holder, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (PROJECT_ID, run_id, OWNER, NOW, NOW),
            )
            connection.commit()

    def test_ai_objective_resume_continues_with_its_existing_plan(self) -> None:
        objective_id = self._insert_objective(source="AI")
        reserved = ORCHESTRATOR.reserve_ai_objective(
            objective_id,
            instance_id="test-instance",
            config={"global_parallel_objectives": 2},
        )
        self.assertIsNotNone(reserved)
        _, objective_attempt_id = reserved

        plan_id = ORCHESTRATOR.insert_plan(
            self._plan(self._task("planned_work"), objective="Planned AI work"),
            source="AI",
            initial_status="DRAFT",
        )
        execution_id = "orchestrator-execution-planning"
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO orchestrator_executions (
                    execution_id, plan_id, role_id, source_profile,
                    outer_container_name, prompt_path, output_path, marker,
                    exit_code, result_json, created_at, started_at, finished_at
                ) VALUES (?, ?, 'orchestrator', 'test-orchestrator',
                          'planning-container', ?, ?, 'PLANNED', 0, '{}', ?, ?, ?)
                """,
                (
                    execution_id,
                    plan_id,
                    str(self.root / "planner.prompt"),
                    str(self.root / "planner.output"),
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            connection.commit()

        self._command(OBJECTIVES.command_pause, objective_id)
        ORCHESTRATOR.finish_objective_planning_success(
            objective_id,
            objective_attempt_id,
            {"plan_id": plan_id, "execution_id": execution_id},
        )
        self.assertEqual(
            tuple(
                self._row(
                    "SELECT status, plan_id FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                )
            ),
            ("PAUSED", plan_id),
        )

        self._command(OBJECTIVES.command_resume, objective_id)
        queued = ORCHESTRATOR.next_queued_objective()
        self.assertEqual(queued["objective_id"], objective_id)

        resumed_plan_id = ORCHESTRATOR.promote_planned_objective(objective_id)
        self.assertEqual(resumed_plan_id, plan_id)
        ORCHESTRATOR.refresh_plan_states(resumed_plan_id)
        self.assertEqual(
            tuple(
                self._row(
                    "SELECT status, plan_id, planning_attempt_count "
                    "FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                )
            ),
            ("RUNNING", plan_id, 1),
            "resume must reuse the existing plan without a second planning attempt",
        )

        task_count = int(
            self._row(
                "SELECT COUNT(*) FROM orchestration_tasks WHERE plan_id=?",
                (plan_id,),
            )[0]
        )
        self._command(OBJECTIVES.command_pause, objective_id)
        self._command(OBJECTIVES.command_resume, objective_id)
        self.assertEqual(
            ORCHESTRATOR.promote_planned_objective(objective_id),
            plan_id,
        )
        ORCHESTRATOR.refresh_plan_states(plan_id)
        self.assertEqual(
            tuple(
                self._row(
                    "SELECT status, plan_id, planning_attempt_count "
                    "FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                )
            ),
            ("RUNNING", plan_id, 1),
        )
        self.assertEqual(
            int(
                self._row(
                    "SELECT COUNT(*) FROM orchestration_tasks WHERE plan_id=?",
                    (plan_id,),
                )[0]
            ),
            task_count,
        )

    def test_non_ai_planned_objective_promotion_is_unchanged(self) -> None:
        plan_id = ORCHESTRATOR.insert_plan(
            self._plan(self._task("declarative_work")),
            source="TEST",
            initial_status="DRAFT",
        )
        objective_id = self._insert_objective(source="TEST", plan_id=plan_id)

        self.assertEqual(
            ORCHESTRATOR.promote_planned_objective(objective_id),
            plan_id,
        )
        self.assertEqual(
            tuple(
                self._row(
                    "SELECT status, plan_id, planning_attempt_count "
                    "FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                )
            ),
            ("RUNNING", plan_id, 0),
        )
        self.assertEqual(
            self._row(
                "SELECT status FROM orchestration_plans WHERE plan_id=?",
                (plan_id,),
            )[0],
            "READY",
        )

    def test_cancelled_objective_cannot_reserve_new_tasks_or_attempts(self) -> None:
        objective_id, plan_id, _, _ = self._create_running_plan()
        attempts_before = int(
            self._row("SELECT COUNT(*) FROM orchestration_attempts")[0]
        )

        self._command(OBJECTIVES.command_cancel, objective_id)

        self.assertEqual(ORCHESTRATOR.runnable_tasks(set(), capacity=4), [])
        self.assertEqual(
            int(self._row("SELECT COUNT(*) FROM orchestration_attempts")[0]),
            attempts_before,
        )
        self.assertEqual(
            self._row(
                "SELECT status FROM orchestration_tasks "
                "WHERE plan_id=? AND task_key='after_cancel'",
                (plan_id,),
            )[0],
            "READY",
            "the queued task remains READY but must be excluded by objective state",
        )

    def test_cancelled_objective_converges_after_active_attempt_finishes(self) -> None:
        objective_id, plan_id, attempt_id, task = self._create_running_plan()
        self._insert_run("run-cancellation")
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE orchestration_attempts SET run_id=? WHERE attempt_id=?",
                ("run-cancellation", attempt_id),
            )
            connection.commit()

        self._command(OBJECTIVES.command_cancel, objective_id)
        ORCHESTRATOR.finish_task_success(task, attempt_id, {"kind": "PIPELINE"})
        ORCHESTRATOR.synchronize_objective_states()

        self.assertEqual(
            tuple(
                self._row(
                    "SELECT status, finished_at IS NOT NULL FROM objective_queue "
                    "WHERE objective_id=?",
                    (objective_id,),
                )
            ),
            ("CANCELLED", 1),
        )
        self.assertEqual(
            self._row(
                "SELECT status FROM orchestration_plans WHERE plan_id=?",
                (plan_id,),
            )[0],
            "CANCELLED",
        )

    def test_cancel_is_rejected_after_integration_point_of_no_return(self) -> None:
        objective_id, _, attempt_id, _ = self._create_running_plan()
        run_id = "run-integration-committing"
        self._insert_run(run_id, status="COMMITTING")
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE orchestration_attempts SET run_id=? WHERE attempt_id=?",
                (run_id, attempt_id),
            )
            connection.commit()

        with self.assertRaisesRegex(
            OBJECTIVES.ObjectiveError,
            "integration point of no return",
        ):
            self._command(OBJECTIVES.command_cancel, objective_id)

        self.assertEqual(
            self._row(
                "SELECT status FROM objective_queue WHERE objective_id=?",
                (objective_id,),
            )[0],
            "RUNNING",
            "cancel must not claim acceptance after integration is COMMITTING",
        )

    def test_cancel_during_post_commit_pre_git_window_is_rejected(self) -> None:
        objective_id, _, attempt_id, _ = self._create_running_plan()
        run_id = "run-cancel-race"
        self._insert_run(run_id, status="REVIEWING")
        self._seed_human_review(run_id)
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE orchestration_attempts SET run_id=? WHERE attempt_id=?",
                (run_id, attempt_id),
            )
            connection.commit()
            run = INTEGRATOR.get_run(connection, run_id)
            review = connection.execute(
                """
                SELECT review.*, execution.execution_id AS review_execution_id
                FROM review_results AS review
                JOIN reviewer_executions AS execution
                  ON execution.review_id=review.review_id
                WHERE review.run_id=?
                """,
                (run_id,),
            ).fetchone()

        git_reached = threading.Event()
        allow_git = threading.Event()
        integration_result: list[dict[str, Any]] = []
        integration_errors: list[BaseException] = []
        original_git = INTEGRATOR.git

        def fake_git(repository: Path, *arguments: str) -> str:
            if arguments[0] == "merge":
                git_reached.set()
                if not allow_git.wait(timeout=5):
                    raise AssertionError("test did not release the Git mutation")
                return ""
            if arguments[:2] == ("rev-parse", "HEAD"):
                return "b" * 40
            if arguments[0] == "status":
                return ""
            raise AssertionError(arguments)

        class Transaction:
            @staticmethod
            def cleanup_worktree(*_: Any) -> None:
                return None

        def integrate() -> None:
            try:
                integration_result.append(
                    INTEGRATOR.integrate_approved(
                        run=run,
                        review=review,
                        owner=OWNER,
                        decision="APPROVE",
                        verdict="PASS",
                        evidence={
                            "repository": str(self.root / "repository"),
                            "worktree": str(self.root / "worktree"),
                            "main_before": "a" * 40,
                        },
                        transaction=Transaction(),
                    )
                )
            except BaseException as error:
                integration_errors.append(error)

        INTEGRATOR.git = fake_git
        worker = threading.Thread(target=integrate)
        try:
            worker.start()
            self.assertTrue(
                git_reached.wait(timeout=5),
                "integrator did not reach the post-COMMIT, pre-Git window",
            )
            self.assertEqual(
                self._row("SELECT status FROM runs WHERE run_id=?", (run_id,))[0],
                "COMMITTING",
            )
            with self.assertRaisesRegex(
                OBJECTIVES.ObjectiveError,
                "integration point of no return",
            ):
                self._command(OBJECTIVES.command_cancel, objective_id)
        finally:
            allow_git.set()
            worker.join(timeout=5)
            INTEGRATOR.git = original_git

        self.assertFalse(worker.is_alive())
        self.assertEqual(integration_errors, [])
        self.assertEqual(len(integration_result), 1)
        self.assertTrue(integration_result[0]["integrated"])
        self.assertEqual(
            self._row(
                "SELECT status FROM objective_queue WHERE objective_id=?",
                (objective_id,),
            )[0],
            "RUNNING",
        )

    def test_cancelled_objective_blocks_post_cancel_integration(self) -> None:
        objective_id, _, attempt_id, task = self._create_running_plan()
        run_id = "run-post-cancel-integration"
        self._insert_run(run_id)
        integration_calls: list[list[str]] = []

        original_run_json = ORCHESTRATOR.run_json
        original_reviewer = ORCHESTRATOR.launch_reviewer_with_transport_retry
        original_rollback = ORCHESTRATOR.rollback_run_best_effort
        rollback_calls: list[str] = []

        def fake_run_json(arguments: list[str], *, timeout: int) -> dict[str, Any]:
            command = Path(arguments[0]).name
            action = arguments[1]
            if command == "hermesops-transaction.py" and action == "begin":
                return {"run_id": run_id}
            if command == "hermesops-worker.py":
                self._command(OBJECTIVES.command_cancel, objective_id)
                return {"execution_id": "worker-after-cancel", "exit_code": 0}
            if command == "hermesops-transaction.py" and action == "submit":
                return {"run_id": run_id, "status": "REVIEWING"}
            if command == "hermesops-integrator.py":
                integration_calls.append(arguments)
                return {
                    "integration_id": "integration-after-cancel",
                    "status": "COMPLETED",
                    "integrated": True,
                }
            raise AssertionError(arguments)

        ORCHESTRATOR.run_json = fake_run_json
        ORCHESTRATOR.launch_reviewer_with_transport_retry = lambda *args, **kwargs: (
            {"execution_id": "review-after-cancel", "decision": "APPROVE"},
            [],
            {},
        )
        ORCHESTRATOR.rollback_run_best_effort = lambda called_run_id, timeout: (
            rollback_calls.append(called_run_id)
        )
        try:
            result = ORCHESTRATOR.execute_pipeline(
                task,
                attempt_id,
                "test-instance",
                {
                    "command_timeout_seconds": 5,
                    "worker_timeout_seconds": 5,
                },
            )
        finally:
            ORCHESTRATOR.run_json = original_run_json
            ORCHESTRATOR.launch_reviewer_with_transport_retry = original_reviewer
            ORCHESTRATOR.rollback_run_best_effort = original_rollback

        self.assertEqual(
            result["integration"],
            {
                "integration_id": None,
                "run_id": run_id,
                "action": "CANCEL",
                "status": "CANCELLED",
                "integrated": False,
                "reason_code": "objective_cancel_requested",
            },
        )
        self.assertEqual(
            integration_calls,
            [],
            "the active pipeline reached integrator.apply after objective cancellation",
        )

        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE runs SET status='REVIEWING' WHERE run_id=?",
                (run_id,),
            )
            connection.commit()
            run = INTEGRATOR.get_run(connection, run_id)
        authoritative_result = INTEGRATOR.integrate_approved(
            run=run,
            review={},
            owner=OWNER,
            decision="APPROVE",
            verdict="PASS",
            evidence={
                "repository": str(self.root / "repository"),
                "worktree": str(self.root / "worktree"),
            },
            transaction=None,
        )
        self.assertEqual(authoritative_result, result["integration"])
        self.assertEqual(rollback_calls, [run_id])
        self.assertEqual(
            int(
                self._row(
                    "SELECT COUNT(*) FROM integration_executions WHERE run_id=?",
                    (run_id,),
                )[0]
            ),
            0,
        )
        self.assertEqual(
            int(
                self._row(
                    "SELECT COUNT(*) FROM orchestration_attempts "
                    "WHERE orchestration_task_id=?",
                    (task["orchestration_task_id"],),
                )[0]
            ),
            1,
            "structured cancellation must not create a retry",
        )
        self.assertIsNone(
            self._row("SELECT recovery_decision FROM runs WHERE run_id=?", (run_id,))[0]
        )
        ORCHESTRATOR.finish_task_success(task, attempt_id, result)
        ORCHESTRATOR.synchronize_objective_states()
        self.assertEqual(
            tuple(
                self._row(
                    "SELECT objective.status, plan.status "
                    "FROM objective_queue AS objective "
                    "JOIN orchestration_plans AS plan "
                    "ON plan.plan_id=objective.plan_id "
                    "WHERE objective.objective_id=?",
                    (objective_id,),
                )
            ),
            ("CANCELLED", "CANCELLED"),
        )
        self.assertEqual(
            self._row(
                "SELECT status FROM orchestration_attempts WHERE attempt_id=?",
                (attempt_id,),
            )[0],
            "COMPLETED",
        )

    def test_ambiguous_objective_linkage_fails_before_integration(self) -> None:
        _, _, first_attempt_id, _ = self._create_running_plan()
        run_id = "run-ambiguous-objectives"
        self._insert_run(run_id, status="REVIEWING")
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE orchestration_attempts SET run_id=? WHERE attempt_id=?",
                (run_id, first_attempt_id),
            )
            connection.commit()

        _, _, second_attempt_id, _ = self._create_running_plan()
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                "UPDATE orchestration_attempts SET run_id=? WHERE attempt_id=?",
                (run_id, second_attempt_id),
            )
            connection.commit()
            run = INTEGRATOR.get_run(connection, run_id)

        with self.assertRaisesRegex(
            INTEGRATOR.IntegrationError,
            "multiple objectives",
        ):
            INTEGRATOR.integrate_approved(
                run=run,
                review={},
                owner=OWNER,
                decision="APPROVE",
                verdict="PASS",
                evidence={
                    "repository": str(self.root / "repository"),
                    "worktree": str(self.root / "worktree"),
                },
                transaction=None,
            )
        self.assertEqual(
            int(self._row("SELECT COUNT(*) FROM integration_executions")[0]),
            0,
        )

    def test_block_human_gate_is_not_automatically_rolled_back(self) -> None:
        _, _, attempt_id, task = self._create_running_plan()
        run_id = "run-block-human"
        self._insert_run(run_id, status="REVIEWING")
        self._seed_human_review(run_id)
        rollback_calls: list[list[str]] = []

        original_run_json = ORCHESTRATOR.run_json
        original_reviewer = ORCHESTRATOR.launch_reviewer_with_transport_retry
        original_run_command = ORCHESTRATOR.run_command

        def fake_run_json(arguments: list[str], *, timeout: int) -> dict[str, Any]:
            command = Path(arguments[0]).name
            action = arguments[1]
            if command == "hermesops-transaction.py" and action == "begin":
                return {"run_id": run_id}
            if command == "hermesops-worker.py":
                return {"execution_id": "worker-block-human", "exit_code": 0}
            if command == "hermesops-transaction.py" and action == "submit":
                return {"run_id": run_id, "status": "REVIEWING"}
            if command == "hermesops-integrator.py":
                with contextlib.closing(self.connect()) as connection:
                    run = INTEGRATOR.get_run(connection, run_id)
                    review = connection.execute(
                        """
                        SELECT review.*, execution.execution_id AS review_execution_id
                        FROM review_results AS review
                        JOIN reviewer_executions AS execution
                          ON execution.review_id=review.review_id
                        WHERE review.run_id=?
                        """,
                        (run_id,),
                    ).fetchone()
                return INTEGRATOR.record_non_integration(
                    run=run,
                    review=review,
                    owner=OWNER,
                    decision="BLOCK_HUMAN",
                    verdict="HUMAN",
                    action="BLOCK_HUMAN",
                    evidence={"main_before": "a" * 40},
                )
            raise AssertionError(arguments)

        def fake_run_command(
            arguments: list[str],
            *,
            timeout: int,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            rollback_calls.append(arguments)
            with contextlib.closing(self.connect()) as connection:
                connection.execute(
                    "UPDATE approvals SET status='CANCELLED', resolved_at=? "
                    "WHERE run_id=? AND status='PENDING'",
                    (NOW, run_id),
                )
                connection.execute(
                    "UPDATE runs SET status='CANCELLED', "
                    "recovery_decision='ROLLBACK_SAFE', finished_at=? WHERE run_id=?",
                    (NOW, run_id),
                )
                connection.commit()
            return subprocess.CompletedProcess(arguments, 0, "", "")

        ORCHESTRATOR.run_json = fake_run_json
        ORCHESTRATOR.launch_reviewer_with_transport_retry = lambda *args, **kwargs: (
            {"execution_id": "reviewer-execution-human", "decision": "BLOCK_HUMAN"},
            [],
            {},
        )
        ORCHESTRATOR.run_command = fake_run_command
        try:
            result = ORCHESTRATOR.execute_pipeline(
                task,
                attempt_id,
                "test-instance",
                {
                    "command_timeout_seconds": 5,
                    "worker_timeout_seconds": 5,
                },
            )
        finally:
            ORCHESTRATOR.run_json = original_run_json
            ORCHESTRATOR.launch_reviewer_with_transport_retry = original_reviewer
            ORCHESTRATOR.run_command = original_run_command

        self.assertEqual(result["integration"]["action"], "BLOCK_HUMAN")
        self.assertFalse(result["integration"]["integrated"])

        state = self._row(
            """
            SELECT run.status, run.recovery_decision, approval.status
            FROM runs AS run
            JOIN approvals AS approval ON approval.run_id=run.run_id
            WHERE run.run_id=?
            """,
            (run_id,),
        )
        self.assertEqual(
            (rollback_calls, state["status"], state["recovery_decision"], state[2]),
            ([], "WAITING_HUMAN", "BLOCK_HUMAN", "PENDING"),
            "BLOCK_HUMAN was treated as pipeline failure and rolled back, losing the pending gate",
        )

        attempts_before = int(
            self._row("SELECT COUNT(*) FROM orchestration_attempts")[0]
        )
        ORCHESTRATOR.finish_task_waiting_human(task, attempt_id, result)
        for _ in range(3):
            ORCHESTRATOR.refresh_plan_states(task["plan_id"])
            ORCHESTRATOR.synchronize_objective_states()

        self.assertEqual(
            ORCHESTRATOR.runnable_tasks(set(), capacity=4),
            [],
            "a stable human gate must freeze every remaining task in the plan",
        )
        self.assertEqual(
            int(self._row("SELECT COUNT(*) FROM orchestration_attempts")[0]),
            attempts_before,
        )
        stable_state = self._row(
            """
            SELECT run.status, run.recovery_decision, approval.status,
                   integration.status
            FROM runs AS run
            JOIN approvals AS approval ON approval.run_id=run.run_id
            JOIN integration_executions AS integration
              ON integration.run_id=run.run_id
            WHERE run.run_id=?
            """,
            (run_id,),
        )
        self.assertEqual(
            tuple(stable_state),
            ("WAITING_HUMAN", "BLOCK_HUMAN", "PENDING", "BLOCKED"),
        )
        self.assertEqual(rollback_calls, [])

    def _seed_human_review(self, run_id: str) -> None:
        with contextlib.closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, run_id, role, status, description, attempt,
                    metadata_json, created_at, started_at, finished_at, heartbeat_at
                ) VALUES ('review-task-human', ?, 'reviewer', 'COMPLETED',
                          'Human gate review', 1, '{}', ?, ?, ?, ?)
                """,
                (run_id, NOW, NOW, NOW, NOW),
            )
            connection.execute(
                """
                INSERT INTO review_results (
                    review_id, run_id, verdict, summary, details_json, created_at
                ) VALUES ('review-human', ?, 'HUMAN', 'Human decision required', '{}', ?)
                """,
                (run_id, NOW),
            )
            connection.execute(
                """
                INSERT INTO reviewer_executions (
                    execution_id, review_id, task_id, run_id, role_id,
                    source_profile, runtime_profile, outer_container_name,
                    prompt_path, output_path, workspace_mode, network_enabled,
                    cpu_limit, memory_mb, mount_verified, isolation_verified,
                    repository_unchanged, decision, verdict, exit_code,
                    result_json, created_at, started_at, finished_at
                ) VALUES (
                    'reviewer-execution-human', 'review-human',
                    'review-task-human', ?, 'reviewer', 'test-reviewer',
                    'runtime-review-human', 'review-container-human', ?, ?,
                    'read_only', 0, 1, 512, 1, 1, 1,
                    'BLOCK_HUMAN', 'HUMAN', 0, '{}', ?, ?, ?
                )
                """,
                (
                    run_id,
                    str(self.root / "review.prompt"),
                    str(self.root / "review.output"),
                    NOW,
                    NOW,
                    NOW,
                ),
            )
            connection.commit()


if __name__ == "__main__":
    unittest.main()
