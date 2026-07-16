# État du projet

## Jalon validé

`1B.1 — transport Unix du moteur sandbox`

## Hermes Agent

- version : `0.18.2`
- conteneur : `hermesops-agent`
- API : `127.0.0.1:8642`
- authentification : active
- backend terminal : `docker`

## Moteur sandbox

- conteneur : `hermesops-sandbox-engine`
- connexion Agent → moteur : socket Unix
- endpoint : `/run/hermes-docker/docker.sock`
- API TCP 2375/2376 : désactivée
- port publié sur l'hôte : aucun
- réseau partagé Agent/moteur : aucun
- socket Docker hôte transmis : non
- smoke test réel : validé

## Fournisseur et modèle

Non configurés.

## Projet métier importé

Aucun.

## Prochaine étape

`1C — fournisseur IA et premier appel contrôlé sans outil`
