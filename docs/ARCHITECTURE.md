# Architecture HermesOps

## Plan de contrôle

- Hermes WebUI : interface utilisateur uniquement.
- Hermes Agent : Gateway et API interne.
- HermesOps Controller : machine d'état et attribution des tâches.
- Recovery Manager : reprise, rollback ou blocage humain.
- Watchdog systemd : surveillance extérieure aux conteneurs Hermes.

## Plan d'exécution

- Orchestrateur par projet.
- Workers spécialisés.
- Reviewer indépendant.
- Worktrees Git isolés.
- Une transaction d'écriture active par projet.

## Stockage

- `state/hermes-home` : état partagé exigé par Hermes.
- `state/controller` : état transactionnel HermesOps.
- `workspaces` : dépôts et worktrees des projets.
- `project-data` : données non Git propres aux projets.
- `backups` : bundles, patches et snapshots.
- `secrets` : identifiants hors Git.
- `logs` : journaux d'exploitation.
- `runtime` : verrous, PID et état éphémère.
