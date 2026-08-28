# Installation publique HermesOps 0.2.0 sur Debian 12

## Contrat supporté

HermesOps 0.2.0 cible :

- Debian 12 Bookworm sur `amd64` ;
- un utilisateur de service UID/GID `1000:1000` ;
- la racine fixe `/opt/docker/hermesops` ;
- Docker Engine testé en `29.6.1` ;
- Docker Compose testé en `5.3.0`.

L'installateur peut ajouter le dépôt APT officiel Docker et installer les
versions verrouillées si Docker est absent. Il ne supprime pas automatiquement
les paquets Docker concurrents.

## Installation

```bash
git clone https://github.com/Bebet0o/HermesOps.git
cd HermesOps
./preflight.sh
./install.sh
```

Le snapshot immuable final sera le tag `v0.2.0`, créé après merge de la
finalisation source. Le tag, la GitHub Release et ses assets ne sont donc pas
encore supposés exister sur cette branche.

Si le preflight ajoute l'utilisateur au groupe `docker`, son statut devient
`RELOGIN_REQUIRED` : fermer entièrement la session, se reconnecter et relancer
la même commande. L'installation est idempotente.

Un fichier OpenAI Codex existant peut être fourni sans l'afficher :

```bash
./install.sh --auth-file /secure/path/auth.json
```

Sans ce fichier, l'installation reporte la vérification des profils IA et les
objectifs IA ne sont pas encore utilisables.

## Image worker et installation hors ligne

Le moteur sandbox dédié doit charger l'image
`hermesops-worker-sandbox:0.2` dont l'identifiant exact est verrouillé dans
`config/worker-sandbox.lock.toml`. La release finale doit publier :

- `hermesops-worker-sandbox-0.2.tar.gz` ;
- `hermesops-worker-sandbox-0.2.tar.gz.sha256`.

Avant publication de ces assets, ou pour une installation hors ligne, fournir
l'archive explicitement :

```bash
./install.sh \
  --offline \
  --auth-file /secure/path/auth.json \
  --worker-image-archive /secure/path/hermesops-worker-sandbox-0.2.tar.gz
```

L'archive est chargée dans le moteur Docker isolé. L'installation échoue fermée
si l'identifiant chargé diffère de la lock.

Après merge, produire les deux assets depuis une installation validée avec :

```bash
HERMESOPS_ROOT=/opt/docker/hermesops \
HERMESOPS_EXPORT_DIR=/secure/release-assets \
  /opt/docker/hermesops/repo/scripts/export-worker-image.sh
```

Le script inspecte l'image dans `hermesops-sandbox-engine`, exige l'identifiant
verrouillé, exporte avec `gzip -9`, vérifie l'archive et écrit son SHA-256.

## Services et Console

L'installation active les services utilisateur :

- `hermesops-supervisor.service` ;
- `hermesops-orchestrator.service` ;
- `hermesops-notifier.service` ;
- `hermesops-controller-api.service` sur `127.0.0.1:8765` ;
- `hermesops-console.service` sur `127.0.0.1:8788`.

Hermes Agent utilise également les services locaux `8642` et `8787`. La
Console et les APIs restent loopback-only ; un accès distant nécessite un
tunnel SSH ou reverse proxy TLS géré par l'opérateur.

```bash
systemctl --user status hermesops-console.service
curl --fail http://127.0.0.1:8788/health
```

La Console 0.2.0 fournit authentification, dashboard opérationnel, projets,
Hermesfiles et cycle de vie borné des objectifs.

## Registre initial

Une installation neuve ne crée aucun projet métier. Les fixtures sous
`tests/fixtures/projects/` nécessitent une activation explicite réservée aux
tests :

```bash
HERMESOPS_ENABLE_TEST_FIXTURES=1 \
  /opt/docker/hermesops/repo/scripts/init-test-fixtures.sh
```

## Reprise, sauvegardes et désinstallation

Avant une mise à niveau divergente, l'installateur crée un bundle Git et une
sauvegarde SQLite cohérente lorsqu'elle existe. Secrets, `auth.json`,
workspaces, données projet, backups et configurations locales sont préservés.

```bash
./uninstall.sh --user SERVICE_USER
```

La désinstallation standard désactive les services et retire leurs unités sans
supprimer volumes, secrets, bases, projets ou sauvegardes. La suppression du
repository exige `--remove-repo --confirm REMOVE_REPO`.
