# État du projet

## Jalon validé

`2A — registre déclaratif et état transactionnel`

## Infrastructure

- Hermes Agent : sain
- moteur sandbox : sain
- OpenAI Codex : authentifié
- modèle : GPT-5.6 Sol
- Hermes WebUI : saine
- backend WebUI : Gateway
- Controller SQLite : initialisé
- registre déclaratif : initialisé
- projets actifs : aucun

## Plan de contrôle

- configuration globale : `config/controller.toml`
- politique par défaut : `config/policies/default.toml`
- registre actif : `config/projects.d/*.toml`
- base : `state/controller/hermesops.db`
- migration courante : `001`
- journal SQLite : WAL

## Projet métier importé

Aucun.

## Prochaine étape

`2B — profils Orchestrator, Worker, Reviewer et Recovery`
