# Changelog

## [Unreleased]

### Added

- installateur Debian 12 idempotent et reprenable ;
- préflight, validation et désinstallation non destructive ;
- contrôle anti-secrets local et en CI ;
- exemples Agent, WebUI et Telegram ;
- export et chargement vérifié de l'image worker.

### Changed

- isolation des fixtures sous `tests/fixtures/projects/` ;
- une installation publique neuve commence avec zéro projet enregistré ;
- l'initialisation des fixtures nécessite une action de test explicite ;
- version publique `0.1.0-alpha` ;
- configuration locale TradingBot retirée du suivi Git ;
- les deux fixtures de fondation sont versionnées uniquement sous `tests/fixtures/projects/` ;
- la configuration locale TradingBot est remplacée dans le dépôt public par un exemple désactivé.

### Fixed

- le préflight Debian minimal ne considère plus `rsync`, `sqlite3` ou
  `python3-yaml` comme des prérequis déjà installés ;
- le `PATH` inclut désormais `/usr/sbin` et `/sbin`, ce qui permet de détecter
  correctement `runuser` ;
- `util-linux` est une dépendance explicite de l’installateur.
- les exceptions `.gitignore` qui republiaient les fixtures locales ont été supprimées.
- le test du contrat `.gitignore` fonctionne désormais depuis une archive source sans métadonnées `.git`.

### Security

- couverture explicite de `auth.json` et des répertoires `secrets/` ;
- sauvegarde avant mise à niveau divergente ;
- aucun secret généré dans le dépôt.
