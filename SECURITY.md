# Politique de sécurité

Ne publiez jamais de token, clé, `auth.json`, base SQLite, archive d'état ou
journal contenant des secrets.

Signalez les vulnérabilités par le canal privé de sécurité du dépôt GitHub.
À défaut, ouvrez une issue sans détail sensible pour demander un canal privé.

HermesOps conserve les principes suivants : aucun push automatique, aucun
secret dans les sandboxes, reviewer en lecture seule, intégration uniquement
après verdict favorable, snapshots vérifiés, récupération déterministe et
exposition locale sur `127.0.0.1`.
