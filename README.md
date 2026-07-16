# HermesOps

HermesOps est une couche d'orchestration et d'exploitation autour de Hermes
Agent et Hermes WebUI.

Objectif :

- gérer plusieurs projets de manière transactionnelle ;
- séparer orchestrateurs, workers, reviewers et recovery managers ;
- reprendre proprement après une panne ;
- appliquer des politiques Git strictes ;
- produire des sauvegardes, journaux et preuves vérifiables ;
- offrir une interface WebUI et des notifications distantes.

HermesOps n'est pas un fork de Hermes Agent.

## Principes

1. Aucun worker ne travaille directement sur `main`.
2. Aucun `git push` automatique.
3. Snapshot avant toute tâche d'écriture.
4. Tests et revue indépendante avant validation.
5. Une seule transaction d'écriture par projet au départ.
6. Reprise uniquement lorsqu'elle est prouvée sûre.
7. Sinon, passage explicite à `BLOCK_HUMAN`.
8. Les secrets ne sont jamais suivis par Git.
9. Les watchdogs critiques restent extérieurs à Hermes.
10. Toutes les actions importantes sont journalisées.
