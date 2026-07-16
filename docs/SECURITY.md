# Sécurité HermesOps

## Plan d'exécution

Hermes Agent n'accède pas au socket Docker de l'hôte.

Les outils Hermes utilisent un daemon Docker dédié :

- conteneur : `hermesops-sandbox-engine`
- image : `docker@sha256:66d292e5c26bd33a6f6f61cacb880de2186339a524ecba1ce098dbbaceed6515`
- port publié sur l'hôte : aucun
- socket Docker hôte monté dans Agent : non
- état : `/opt/docker/hermesops/state/sandbox-engine`

## Sandboxes

- backend Hermes : `docker`
- image de base : `python@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93`
- CPU par défaut : 2
- mémoire par défaut : 4096 Mio
- persistance : active
- secrets transmis : aucun par défaut
- montage automatique du répertoire courant : désactivé

Le moteur sandbox est séparé du daemon qui héberge HermesOps et les autres
services du serveur.
