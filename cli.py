"""Interface en ligne de commande (CLI) complète pour rocsa_generator avec Menu Interactif."""

import sys
from pathlib import Path

# Injection prioritaire du dossier src dans le PYTHONPATH
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
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
    no_args_is_help=False,
)

console = Console()
logger = get_logger("cli")

CATALOG_DIR = Path("src/rocsa_generator/definitions/catalog")


def execute_engine_build(file_path: Path):
    """Exécute la méthode de build SDK de RocsaEngine."""
    engine = RocsaEngine()
    
    if hasattr(engine, "build_sdk"):
        return engine.build_sdk(file_path)
    elif hasattr(engine, "build"):
        return engine.build(file_path)
    else:
        raise AttributeError(f"Méthode de build introuvable sur RocsaEngine.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    debug: bool = typer.Option(
        False, "--debug", "-d", help="Activer le mode debug et l'affichage détaillé des logs"
    ),
):
    """Configuration globale ou lancement du menu interactif si aucune commande n'est passée."""
    log_level = (
        logging.DEBUG
        if (debug or settings.debug)
        else getattr(logging, settings.log_level.upper(), logging.INFO)
    )
    configure_logging(level=log_level)

    if ctx.invoked_subcommand is None:
        interactive_menu()


def interactive_menu():
    """Affiche un menu interactif dans le terminal."""
    while True:
        console.clear()
        console.print(
            Panel.fit(
                "[bold cyan]ROCSA Compiler & Control Suite[/bold cyan]\n"
                "[dim]Sélectionnez une action ci-dessous[/dim]",
                title="⚙️ Menu Principal",
            )
        )
        
        console.print("1. 🔍 [bold green]Valider le catalogue[/bold green] (validate)")
        console.print("2. 📊 [bold blue]Générer / Afficher le Registre[/bold blue] (registry)")
        console.print("3. 🛠️  [bold yellow]Builder un artefact / SDK[/bold yellow] (build)")
        console.print("4. ℹ️  [bold white]Afficher la Version[/bold white] (version)")
        console.print("0. 🚪 [bold red]Quitter[/bold red]\n")

        choice = Prompt.ask("Choisissez une option", choices=["1", "2", "3", "4", "0"], default="1")

        if choice == "1":
            run_validate_menu()
        elif choice == "2":
            run_registry_menu()
        elif choice == "3":
            run_build_menu()
        elif choice == "4":
            version()
            Prompt.ask("\nAppuyez sur Entrée pour revenir au menu")
        elif choice == "0":
            console.print("[bold yellow]Au revoir ![/bold yellow]")
            break


def run_validate_menu():
    """Menu interactif pour la validation."""
    validator = RocsaValidator()
    files = sorted(list(CATALOG_DIR.glob("*.json")) + list(CATALOG_DIR.glob("*.yaml")))
    
    console.print("\n[bold]Validation des définitions :[/bold]")
    for file in files:
        report = validator.validate_file(file)
        if report.is_valid:
            console.print(f"[green]✓ {file.name}[/green]")
        else:
            console.print(f"[red]✗ {file.name}[/red]")
    Prompt.ask("\nAppuyez sur Entrée pour continuer")


def run_registry_menu():
    """Menu interactif pour le registre."""
    reg = RocsaRegistry(workspace_path=CATALOG_DIR)
    try:
        index = reg.scan_workspace(CATALOG_DIR)
        output = Path("./output/registry.json")
        reg.export(output)
        
        table = Table(title=f"Registre ROCSA ({index.total_entries} contrôles)")
        table.add_column("ID / Nom", style="bold cyan")
        table.add_column("Fichier Source")
        table.add_column("Statut")

        for entry_id, entry in index.entries.items():
            status = "[green]✓ Valide[/green]" if entry.is_valid else "[red]✗ Invalide[/red]"
            table.add_row(entry_id, Path(entry.file_path).name, status)

        console.print(table)
        console.print(f"\n[bold green]✓ Exporté vers :[/bold green] {output}")
    except Exception as err:
        console.print(f"[bold red]Erreur :[/bold red] {err}")
    Prompt.ask("\nAppuyez sur Entrée pour continuer")


def run_build_menu():
    """Menu interactif pour sélectionner un fichier à builder."""
    files = sorted(list(CATALOG_DIR.glob("*.json")) + list(CATALOG_DIR.glob("*.yaml")))
    
    if not files:
        console.print("[red]Aucun fichier catalogue trouvé dans catalog/[/red]")
        Prompt.ask("\nAppuyez sur Entrée pour continuer")
        return

    console.print("\n[bold yellow]Sélectionnez un domaine à builder :[/bold yellow]")
    for i, file in enumerate(files, 1):
        console.print(f"{i}. [cyan]{file.name}[/cyan]")
    console.print("0. Retour")

    choices = [str(i) for i in range(len(files) + 1)]
    idx = int(Prompt.ask("Votre choix", choices=choices, default="1"))

    if idx == 0:
        return

    selected_file = files[idx - 1]
    console.print(f"\n[bold green]Lancement du build SDK pour :[/bold green] {selected_file.name}")
    
    try:
        result = execute_engine_build(selected_file)
        console.print(f"[bold green]✓ Build SDK réussi avec succès ![/bold green]")
        if result:
            console.print(f"[dim]Résultat : {result}[/dim]")
    except Exception as err:
        console.print(f"[bold red]Erreur pendant le build :[/bold red] {err}")

    Prompt.ask("\nAppuyez sur Entrée pour continuer")


@app.command()
def version():
    """Afficher la version de ROCSA."""
    console.print(
        Panel.fit(
            f"[bold cyan]ROCSA Generator[/bold cyan]\n"
            f"Version : [bold white]{__version__}[/bold white]\n"
            f"Environnement : [yellow]{settings.environment}[/yellow]",
            title="Informations ROCSA",
        )
    )


@app.command()
def validate():
    """Validation autonome."""
    run_validate_menu()


@app.command()
def registry():
    """Génération du registre autonome."""
    run_registry_menu()


@app.command()
def build(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Fichier spécifique à builder")
):
    """Build d'un artefact SDK."""
    if file:
        try:
            result = execute_engine_build(file)
            console.print(f"[bold green]✓ Build SDK réussi pour {file.name}[/bold green]")
        except Exception as err:
            console.print(f"[bold red]Erreur :[/bold red] {err}")
    else:
        run_build_menu()


if __name__ == "__main__":
    app()
