# Politiques initiales

## États de recovery autorisés

- `RESUME_SAFE`
- `ROLLBACK_SAFE`
- `BLOCK_HUMAN`

## Verdicts de revue

- `PASS`
- `PASS_WITH_DEBT`
- `FIX`
- `SECURITY`
- `PERFORMANCE`
- `ARCHITECTURE`
- `HUMAN`

## Git

- branche principale protégée par convention et contrôles ;
- aucune modification directe par un worker ;
- commit obligatoire avant finalisation ;
- worktree propre obligatoire après finalisation ;
- aucun push automatique ;
- sauvegarde avant chaque transaction.

## Sécurité

- API Gateway non publiée sur Internet ;
- secrets avec permissions restrictives ;
- WebUI non considérée comme environnement d'exécution ;
- aucune commande destructive sans politique explicite ;
- journaux et sauvegardes conservés hors du dépôt Git.
