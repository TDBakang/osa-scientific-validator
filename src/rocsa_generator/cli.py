import typer

from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    no_args_is_help=True,
    help="ROCSA Scientific Compiler",
)

console = Console()


@app.command()
def version():
    """
    Display ROCSA version.
    """

    console.print(
        Panel.fit(
            "[bold cyan]ROCSA Generator[/bold cyan]\nVersion 0.1.0",
            title="ROCSA",
        )
    )


@app.command()
def init():
    """
    Initialize ROCSA workspace.
    """

    console.print("[green]Workspace initialized.[/green]")


@app.command()
def validate():
    """
    Validate CSA definitions.
    """

    console.print("[yellow]Validation engine coming soon.[/yellow]")


@app.command()
def build():
    """
    Generate ROCSA SDK.
    """

    console.print("[cyan]Build engine coming soon.[/cyan]")


@app.command()
def registry():
    """
    Generate registry.
    """

    console.print("[cyan]Registry generation coming soon.[/cyan]")


def main():
    app()


if __name__ == "__main__":
    main()
