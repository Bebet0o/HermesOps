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
- Frontière [`AgentRuntime`](AGENT_RUNTIME.md) entre le plan de contrôle et
  l'exécution IA ; `HermesRuntime` est l'adapter transitionnel actuel.
- Frontière [`ModelProvider`](MODEL_PROVIDER.md) sous un futur runtime natif ;
  elle normalise uniquement une génération modèle et son backend concret.
- Événements d'exécution typés et liés à la request (`STARTED`, `HEARTBEAT`) ;
  ils transportent des faits runtime, jamais une décision lifecycle ou métier.
- Projection d'erreur commune pour le journal durable, sans déplacer la
  persistance, Git, review ou Recovery dans le runtime.
- Adoption et cleanup des conteneurs fail-closed : labels d'ownership,
  identité cohérente et binding durable sont requis ; un nom ressemblant à
  HermesOps n'est jamais une preuve de propriété.
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
