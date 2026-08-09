"""Interface en ligne de commande (CLI) complète pour rocsa_generator."""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rocsa_generator import (
    RocsaEngine,
    RocsaGeneratorError,
    RocsaRegistry,
    RocsaValidator,
    __version__,
    configure_logging,
    get_logger,
    settings,
)

app = typer.Typer(
    help="ROCSA Compiler - Scientific Atomic Controls Generator",
    no_args_is_help=True,
)

console = Console()
logger = get_logger("cli")


@app.callback()
def main(
    debug: bool = typer.Option(
        False, "--debug", "-d", help="Activer le mode debug et l'affichage détaillé des logs"
    ),
):
    """Configuration globale de l'application CLI ROCSA."""
    log_level = (
        logging.DEBUG
        if (debug or settings.debug)
        else getattr(logging, settings.log_level.upper(), logging.INFO)
    )
    configure_logging(level=log_level)


@app.command()
def version():
    """Afficher la version de ROCSA et l'environnement actif."""
    console.print(
        Panel.fit(
            f"[bold cyan]ROCSA Generator[/bold cyan]\n"
            f"Version : [bold white]{__version__}[/bold white]\n"
            f"Environnement : [yellow]{settings.environment}[/yellow]",
            title="Informations ROCSA",
        )
    )


@app.command()
def init(
    target_dir: Path = typer.Option(
        Path.cwd() / "rocsa_workspace",
        "--dir",
        "-d",
        help="Dossier racine de l'espace de travail à initialiser",
    )
):
    """Initialiser la structure d'un espace de travail ROCSA."""
    folders = [
        target_dir,
        target_dir / "core",
        target_dir / "crypto",
        target_dir / "schemas",
        target_dir / "templates",
    ]

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Espace de travail initialisé dans {target_dir}")
    console.print(f"[green]✓ Espace de travail ROCSA créé dans :[/green] [bold]{target_dir}[/bold]")


@app.command()
def validate(
    file: Path = typer.Argument(..., help="Fichier de définition YAML/JSON à valider"),
    strict: bool = typer.Option(
        False, "--strict", "-s", help="Traiter les avertissements comme des erreurs bloquantes"
    ),
):
    """Valider la conformité d'une définition ROCSA."""
    validator = RocsaValidator(strict=strict)
    report = validator.validate_file(file)

    if report.is_valid:
        console.print(f"[bold green]✓ Fichier valide :[/bold green] {file}")
    else:
        console.print(f"[bold red]✗ Fichier invalide :[/bold red] {file}")

    if report.issues:
        table = Table(title=f"Rapport de validation ({file.name})")
        table.add_column("Niveau", style="bold")
        table.add_column("Champ")
        table.add_column("Message")

        for issue in report.issues:
            color = "red" if issue.level == "ERROR" else "yellow"
            table.add_row(f"[{color}]{issue.level}[/{color}]", issue.field or "-", issue.message)

        console.print(table)


@app.command()
def build(
    file: Path = typer.Option(..., "--file", "-f", help="Fichier de définition YAML source"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Dossier de sortie personnalisé"),
):
    """Générer les SDKs et artefacts à partir d'une définition."""
    engine = RocsaEngine(output_dir=output)
    try:
        raw_data = engine.load_definition(file)
        request = engine.validate_definition(raw_data)
        result = engine.build_sdk(request)
        console.print(f"[bold green]✓ Artefact généré avec succès :[/bold green] {result.output_path}")
    except RocsaGeneratorError as err:
        console.print(f"[bold red]Erreur lors de la génération :[/bold red] {err}")


@app.command()
def registry(
    directory: Path = typer.Option(Path.cwd(), "--dir", "-d", help="Dossier workspace à scanner"),
    output: Path = typer.Option(
        Path("./output/registry.json"), "--output", "-o", help="Fichier JSON de destination"
    ),
):
    """Scanner le workspace, construire et exporter le registre central ROCSA."""
    reg = RocsaRegistry(workspace_path=directory)
    try:
        index = reg.scan_workspace()
        reg.export(output)

        table = Table(title=f"Registre ROCSA ({index.total_entries} entrées)")
        table.add_column("ID / Nom", style="bold cyan")
        table.add_column("Fichier Source")
        table.add_column("Statut Validation")

        for entry_id, entry in index.entries.items():
            status = "[green]✓ Valide[/green]" if entry.is_valid else "[red]✗ Invalide[/red]"
            table.add_row(entry_id, entry.file_path, status)

        console.print(table)
        console.print(f"\n[bold green]✓ Registre exporté vers :[/bold green] {output}")
    except RocsaGeneratorError as err:
        console.print(f"[bold red]Erreur de registre :[/bold red] {err}")


if __name__ == "__main__":
    app()