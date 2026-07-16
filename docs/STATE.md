# État du projet

## Jalon validé

`2B — flotte de profils HermesOps`

## Infrastructure

- Hermes Agent : sain
- moteur sandbox : sain
- OpenAI Codex : authentifié
- modèle : GPT-5.6 Sol
- Hermes WebUI : saine
- Controller SQLite : migration 002
- projets actifs : aucun
- profils HermesOps : six

## Profils

- orchestrateur : `ops-orchestrator`
- code : `ops-worker-code`
- tests : `ops-worker-tests`
- documentation : `ops-worker-docs`
- reviewer : `ops-reviewer`
- recovery : `ops-recovery`

## Sécurité actuelle

- OAuth partagé sans duplication de jeton ;
- aucun profil autorisé à pousser ;
- orchestrateur privé des outils d'implémentation ;
- reviewer déclaré en lecture seule ;
- recovery déclaré `controller_only`.

Les modes workspace déclarés seront imposés techniquement au jalon 3A.

## Projet métier importé

Aucun.

## Prochaine étape

`3A — transactions Git, snapshots et worktrees isolés`
