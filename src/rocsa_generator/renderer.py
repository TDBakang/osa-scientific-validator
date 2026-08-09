"""Moteur de rendu Jinja2 et de génération de code pour ROCSA."""

import re
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from jinja2 import Environment, FileSystemLoader, TemplateError, UndefinedError, select_autoescape

from rocsa_generator.config import settings
from rocsa_generator.exceptions import GenerationError
from rocsa_generator.logger import get_logger

logger = get_logger("renderer")


def _to_snake_case(value: str) -> str:
    """Filtre Jinja2 : convertit une chaîne en snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower().replace("-", "_")


def _to_camel_case(value: str) -> str:
    """Filtre Jinja2 : convertit une chaîne en PascalCase/CamelCase."""
    words = re.split(r"[_\-\s]+", value)
    return "".join(w.capitalize() for w in words if w)


def _to_yaml_filter(value: Any) -> str:
    """Filtre Jinja2 : sérialise un objet en YAML."""
    return yaml.dump(value, sort_keys=False).strip()


class RocsaRenderer:
    """Gestionnaire des templates Jinja2 et du rendu de fichiers source."""

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or (Path(__file__).parent / "templates")

        if not self.templates_dir.exists():
            logger.warning(
                f"Le dossier des templates n'existe pas encore : {self.templates_dir}"
            )
            self.templates_dir.mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(
                enabled_extensions=("html", "xml"),
                default_for_string=False,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Enregistrement des filtres personnalisés
        self._register_filters()

    def _register_filters(self) -> None:
        """Ajoute des filtres de transformation utiles pour la génération de code."""
        self.env.filters["snake_case"] = _to_snake_case
        self.env.filters["camel_case"] = _to_camel_case
        self.env.filters["to_yaml"] = _to_yaml_filter

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Charge un template Jinja2 et le produit sous forme de chaîne de caractères."""
        try:
            template = self.env.get_template(template_name)
            rendered_content = template.render(**context)
            logger.debug(f"Template '{template_name}' rendu avec succès.")
            return rendered_content
        except UndefinedError as e:
            msg = f"Variable indéfinie lors du rendu du template '{template_name}' : {e}"
            logger.error(msg)
            raise GenerationError(msg) from e
        except TemplateError as e:
            msg = f"Erreur de syntaxe Jinja2 dans le template '{template_name}' : {e}"
            logger.error(msg)
            raise GenerationError(msg) from e

    def render_string(self, template_str: str, context: Dict[str, Any]) -> str:
        """Effectue le rendu d'un template directement transmis sous forme de chaîne."""
        try:
            template = self.env.from_string(template_str)
            return template.render(**context)
        except Exception as e:
            raise GenerationError(f"Échec du rendu de la chaîne template : {e}") from e

    def render_to_file(
        self,
        template_name: str,
        context: Dict[str, Any],
        output_path: Path,
    ) -> Path:
        """Génère le contenu d'un template et l'écrit directement dans un fichier cible."""
        content = self.render_template(template_name, context)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            logger.info(f"Fichier généré : {output_path}")
            return output_path
        except Exception as e:
            msg = f"Erreur lors de l'écriture du fichier généré dans '{output_path}' : {e}"
            logger.error(msg)
            raise GenerationError(msg) from e