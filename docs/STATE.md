# État du projet

## Jalon validé

`1C — OpenAI Codex et premier appel contrôlé`

## Hermes Agent

- version : `0.18.2`
- conteneur : `hermesops-agent`
- API : `127.0.0.1:8642`
- backend terminal : `docker`
- moteur sandbox : socket Unix uniquement

## Fournisseur IA

- fournisseur : `openai-codex`
- modèle : `gpt-5.6-sol`
- authentification : OAuth ChatGPT / device code
- fichier secret : `/opt/docker/hermesops/state/hermes-home/auth.json`
- identifiants suivis par Git : non
- appel CLI réel : validé
- appel Gateway API réel : validé

## Raisonnement

Aucun niveau global imposé pendant le jalon 1C. Les futurs profils
orchestrateur, worker et reviewer recevront leurs propres politiques.

## Projet métier importé

Aucun.

## Prochaine étape

`1D — Hermes WebUI séparée, verrouillée et connectée au Gateway`
