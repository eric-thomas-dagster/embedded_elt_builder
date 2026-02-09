"""UI command to launch the web interface."""

import click
import json
from pathlib import Path


def load_last_repo_path() -> str:
    """Load the last used repository path from config."""
    config_dir = Path.home() / ".elt-builder"
    config_file = config_dir / "config.json"

    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return config.get("last_repo_path", ".")
        except Exception:
            pass

    return "."


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--repo-path", default=None, help="Path to the ELT pipelines repository")
def ui(host: str, port: int, repo_path: str):
    """Launch the web UI for managing ELT pipelines.

    \b
    Example:
        elt ui
        elt ui --port 8080
        elt ui --repo-path /path/to/pipelines
    """
    import uvicorn

    from ..web.app_enhanced import create_app

    # Use last repo path if not specified
    if repo_path is None:
        repo_path = load_last_repo_path()

    click.echo(f"Starting ELT Builder Web UI on http://{host}:{port}")
    click.echo(f"Repository path: {repo_path}")
    click.echo("💡 You can change the repository path from the UI settings")
    click.echo("\nPress Ctrl+C to stop the server")

    app = create_app(repo_path)
    uvicorn.run(app, host=host, port=port)
