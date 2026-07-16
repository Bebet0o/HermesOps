# État du projet

## Jalon validé

`1B — moteur de sandbox dédié`

## Hermes Agent

- version : `0.18.2`
- conteneur : `hermesops-agent`
- API : `127.0.0.1:8642`
- authentification : active
- backend terminal : `docker`

## Plan d'exécution

- moteur : `hermesops-sandbox-engine`
- image moteur : `docker@sha256:66d292e5c26bd33a6f6f61cacb880de2186339a524ecba1ce098dbbaceed6515`
- image sandbox : `python@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93`
- socket Docker hôte transmis à Agent : non
- publication réseau du moteur : aucune
- persistance sandbox : validée
- séparation des daemons : validée

## Fournisseur et modèle

Non configurés.

## Projet métier importé

Aucun.

## Prochaine étape

`1C — fournisseur IA, modèle et premier appel contrôlé sans outil`
