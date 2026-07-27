# Sécurité HermesOps

## Plan d'exécution

Hermes Agent n'accède jamais au socket Docker du daemon hôte.

Les outils Hermes utilisent un daemon Docker dédié :

- conteneur : `hermesops-sandbox-engine`
- socket : `/run/hermes-docker/docker.sock`
- transport TCP : désactivé
- port publié sur l'hôte : aucun
- réseau partagé entre Agent et moteur : aucun
- état moteur : `/opt/docker/hermesops/state/sandbox-engine`

Le socket dédié est partagé uniquement entre Hermes Agent et le moteur
sandbox. Il donne le contrôle du moteur sandbox, mais pas celui du daemon
Docker hôte.

## Sandboxes

- backend Hermes : `docker`
- image verrouillée : `python@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93`
- capacités supprimées par défaut ;
- `no-new-privileges` activé ;
- montage automatique du répertoire courant désactivé ;
- secrets non transmis par défaut ;
- persistance validée ;
- daemon hôte et daemon sandbox séparés.

## Console foundation security boundary

The milestone 2P Console is a static, loopback-only, unprivileged service. It
uses an exact route and asset allowlist, a no-network Content Security Policy,
bounded request concurrency, no browser storage, no external dependency, no
API credential, and no direct access to Controller state. The legacy Hermes
WebUI and Hermes Agent are not trusted as Console data sources.
