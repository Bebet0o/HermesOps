# État du projet

## Jalon validé

`1D — Hermes WebUI séparée`

## Hermes Agent

- version : `0.18.2`
- fournisseur : `openai-codex`
- modèle : `gpt-5.6-sol`
- API : `127.0.0.1:8642`
- backend terminal : daemon Docker dédié par socket Unix

## Hermes WebUI

- version source : `ghcr.io/nesquena/hermes-webui:0.52.41`
- image verrouillée : `ghcr.io/nesquena/hermes-webui@sha256:10eaa2d43efbdd01833e7ff64aaaa5557beb15e2a34d32a489af4fd4ed5fbff5`
- conteneur : `hermesops-webui`
- URL locale : `http://127.0.0.1:8787`
- authentification WebUI : active
- backend de conversation : `gateway`
- accès au socket sandbox : aucun
- workspace monté dans WebUI : lecture seule
- source Agent dans WebUI : lecture seule
- connexion WebUI → Gateway : validée

## Approbations

La Runs API d'approbation n'est pas encore activée. Voir
`docs/BLOCKERS.md`.

## Projet métier importé

Aucun.

## Prochaine étape

`2A — registre déclaratif des projets et schéma de politique`
