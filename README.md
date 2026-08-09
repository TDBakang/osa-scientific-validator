Le fichier **`README.md`** 
Complet et structuré, documentant l'ensemble de votre projet `rocsa-generator` (installation, utilisation CLI, API Python, architecture et développement).

---

# ROCSA Generator 🚀

> **ROCSA Compiler - Scientific Atomic Controls Generator**

**ROCSA Generator** est un compilateur et générateur d'outils scientifiques. Il permet de valider des définitions de contrôles atomiques au format YAML/JSON, de les indexer dans un registre centralisé et de générer automatiquement des SDKs, du code Python, des schémas JSON et de la documentation technique via un moteur de rendu Jinja2.

---

## 📋 Table des Matières

* [Fonctionnalités Clés](https://www.google.com/search?q=%23-fonctionnalit%C3%A9s-cl%C3%A9s)
* [Structure du Projet](https://www.google.com/search?q=%23-structure-du-projet)
* [Installation](https://www.google.com/search?q=%23-installation)
* [Utilisation en Ligne de Commande (CLI)](https://www.google.com/search?q=%23-utilisation-en-ligne-de-commande-cli)
* [Utilisation comme Bibliothèque Python](https://www.google.com/search?q=%23-utilisation-comme-biblioth%C3%A8que-python)
* [Configuration](https://www.google.com/search?q=%23-configuration)
* [Développement et Tests](https://www.google.com/search?q=%23-d%C3%A9veloppement-et-tests)

---

## ✨ Fonctionnalités Clés

* **Validation Sémantique & Schéma :** Analyse la conformité des fichiers YAML/JSON avec Pydantic v2 et vérifie les règles métiers ROCSA.
* **Moteur de Rendu Flexible (Jinja2) :** Génère dynamiquement des fichiers source Python, des schémas JSON et des fiches Markdown avec filtres personnalisés (`snake_case`, `camel_case`, `to_yaml`).
* **Registre & Indexation Centralisés :** Scanne récursivement un espace de travail pour construire et exporter un registre JSON global.
* **CLI Moderne & Colorée :** Interface utilisateur en ligne de commande propulsée par `Typer` et `Rich`.
* **Architecture Modulaire :** Structurée selon la convention `src/` layout avec gestion moderne des paramètres via `pydantic-settings`.

---

## 📁 Structure du Projet

```text
.
├── pyproject.toml               # Configuration du projet, dépendances et points d'entrée
├── README.md                    # Documentation principale
└── src/
    └── rocsa_generator/
        ├── __init__.py          # API publique du paquet
        ├── cli.py               # Interface CLI Typer & Rich
        ├── config.py            # Configuration globale (pydantic-settings)
        ├── engine.py            # Orchestrateur d'exécution du compilateur
        ├── exceptions.py        # Hiérarchie d'exceptions personnalisées
        ├── logger.py            # Configuration centralisée du logging
        ├── models.py            # Schémas et structures Pydantic
        ├── registry.py          # Scan et gestion du registre central
        ├── renderer.py          # Moteur de rendu Jinja2 et filtres
        ├── validator.py         # Moteur de validation des contrôles
        └── templates/           # Templates Jinja2
            ├── control.py.j2    # Template de classe Python
            ├── doc.md.j2        # Template de documentation Markdown
            └── schema.json.j2   # Template de schéma JSON

```

---

## ⚙️ Installation

### Prérequis

* Python **3.11** ou supérieur
* `pip` ou `uv`

### Installation en mode développement (editable)

```bash
# Clonez le dépôt
git clone https://github.com/votre-organisation/rocsa-generator.git
cd rocsa-generator

# Créez et activez un environnement virtuel
python3 -m venv .venv
source .venv/bin/activate  # Sur Linux/macOS
# .venv\Scripts\activate   # Sur Windows

# Installez le paquet avec les dépendances de développement
pip install -e ".[dev]"

```

---

## 💻 Utilisation en Ligne de Commande (CLI)

Une fois le paquet installé, la commande globale `rocsa` est disponible dans votre terminal :

### 1. Afficher la version

```bash
rocsa version

```

### 2. Initialiser un espace de travail

Crée l'arborescence de dossiers de travail par défaut (`core`, `crypto`, `schemas`, etc.) :

```bash
rocsa init --dir ./rocsa_workspace

```

### 3. Valider une définition YAML

Vérifie la syntaxe et la conformité d'un fichier de définition :

```bash
rocsa validate definitions/sample_control.yaml

# Mode strict (traite les avertissements comme des erreurs bloquantes)
rocsa validate definitions/sample_control.yaml --strict

```

### 4. Générer des artefacts (Build)

Compile un fichier de définition YAML en artefact :

```bash
rocsa build -f definitions/sample_control.yaml -o ./output

```

### 5. Construire le registre global

Scanne un répertoire et génère l'index `registry.json` :

```bash
rocsa registry -d ./rocsa_workspace -o ./output/registry.json

```

### Option globale `--debug`

Affiche des logs de débogage détaillés pour n'importe quelle commande :

```bash
rocsa --debug build -f definitions/sample_control.yaml

```

---

## 🐍 Utilisation comme Bibliothèque Python

Vous pouvez également importer `rocsa_generator` dans vos propres scripts :

```python
from pathlib import Path
from rocsa_generator import (
    RocsaEngine,
    RocsaValidator,
    RocsaRegistry,
    RocsaRenderer,
    GenerationRequest,
)

# 1. Validation d'un fichier
validator = RocsaValidator()
report = validator.validate_file(Path("definition.yaml"))

if report.is_valid:
    print("Définition valide !")

# 2. Rendu d'un template
renderer = RocsaRenderer()
renderer.render_to_file(
    template_name="control.py.j2",
    context={"name": "AtomicSensor", "parameters": {"threshold": 42}},
    output_path=Path("output/atomic_sensor.py"),
)

# 3. Indexation du registre
registry = RocsaRegistry(workspace_path=Path("./workspace"))
index = registry.scan_workspace()
registry.export(Path("./output/registry.json"))

```

---

## 🔧 Configuration

La configuration globale est gérée par **`pydantic-settings`** dans `config.py`.

Les paramètres peuvent être surchargés par des variables d'environnement (préfixées par `ROCSA_`) ou via un fichier `.env` à la racine :

| Variable d'environnement | Défaut | Description |
| --- | --- | --- |
| `ROCSA_ENVIRONMENT` | `development` | Environnement d'exécution (`development`, `production`) |
| `ROCSA_DEBUG` | `false` | Active le mode debug global |
| `ROCSA_LOG_LEVEL` | `INFO` | Niveau de verbosité (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `ROCSA_OUTPUT_DIR` | `./output` | Dossier par défaut où sont écrits les artefacts |

---

## 🧪 Développement et Tests

### Lancer les tests unitaires

```bash
pytest

```

### Vérifier le style et le formatage du code

```bash
# Linter avec Ruff
ruff check .

# Formater le code avec Black
black --check .

```

---

## 📄 Licence

Propriétaire - **OSA Scientific Committee**. Tous droits réservés.