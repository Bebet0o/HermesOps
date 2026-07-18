# Projets HermesOps

Ce répertoire mélange volontairement deux catégories :

- les fixtures publiques de fondation, versionnées et toujours désactivées ;
- les projets réels propres à l'installation, ignorés par Git.

Les seuls fichiers `*.toml` autorisés dans l'index public sont :

```text
transaction-fixture.toml
transaction-fixture-b.toml
```

Pour ajouter un projet local :

```bash
cp ../examples/project.example.toml ./mon-projet.toml
```

Adapter ensuite les chemins, puis exécuter :

```bash
/opt/docker/hermesops/repo/scripts/hermesops-registry.py validate
/opt/docker/hermesops/repo/scripts/hermesops-registry.py sync
```

Les configurations de projets réels ne doivent pas être publiées. Les deux
fixtures doivent rester avec `enabled = false`.
