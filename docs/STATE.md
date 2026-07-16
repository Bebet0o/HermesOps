# État du projet

## Jalon validé

`3A — transactions Git et worktrees isolés`

## Infrastructure

- Hermes Agent : sain
- moteur sandbox : sain
- Hermes WebUI : saine
- modèle : GPT-5.6 Sol
- profils spécialisés : six
- Controller SQLite : migration 003

## Transactions

- snapshot Git avant écriture : validé
- bundle vérifié : validé
- worktree isolé : validé
- verrou exclusif par projet : validé
- second writer refusé : validé
- commit obligatoire : validé
- soumission `REVIEWING` : validée
- `ROLLBACK_SAFE` : validé
- branche principale non modifiée : validé

## Projets

- projet métier actif : aucun
- fixture transactionnelle : présente mais désactivée

## Prochaine étape

`3B — lancement contrôlé des workers dans leurs worktrees`
