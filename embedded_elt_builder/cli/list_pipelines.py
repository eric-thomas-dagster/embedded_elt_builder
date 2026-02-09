"""List command to show all pipelines."""

import click
from pathlib import Path
import yaml


@click.command()
@click.option("--repo-path", default=".", help="Path to the ELT pipelines repository")
def list_pipelines(repo_path: str):
    """List all ELT pipelines in the repository.

    \b
    Example:
        elt list
        elt list --repo-path ~/my-pipelines
    """
    repo_path_obj = Path(repo_path).resolve()
    pipelines_dir = repo_path_obj / "pipelines"

    if not pipelines_dir.exists():
        click.echo("No pipelines directory found.")
        click.echo(f"Expected at: {pipelines_dir}")
        return

    click.echo(f"\n📋 ELT Pipelines in {repo_path_obj}\n")

    # List dlt pipelines
    dlt_dir = pipelines_dir / "dlt"
    if dlt_dir.exists():
        dlt_pipelines = [d for d in dlt_dir.iterdir() if d.is_dir()]
        if dlt_pipelines:
            click.echo("🔹 dlt Pipelines:")
            for pipeline in sorted(dlt_pipelines, key=lambda x: x.name):
                _print_pipeline_info(pipeline, "dlt")
            click.echo()

    # List Sling replications
    sling_dir = pipelines_dir / "sling"
    if sling_dir.exists():
        sling_pipelines = [d for d in sling_dir.iterdir() if d.is_dir()]
        if sling_pipelines:
            click.echo("🔹 Sling Replications:")
            for pipeline in sorted(sling_pipelines, key=lambda x: x.name):
                _print_pipeline_info(pipeline, "sling")
            click.echo()


def _print_pipeline_info(pipeline_dir: Path, tool_type: str):
    """Print information about a pipeline."""
    dagster_yaml = pipeline_dir / "dagster.yaml"
    config_yaml = pipeline_dir / "config.yaml"

    # Read config
    description = "No description"
    enabled = True
    source = "unknown"

    if dagster_yaml.exists():
        try:
            with open(dagster_yaml) as f:
                config = yaml.safe_load(f)
                description = config.get("description", description)
                enabled = config.get("enabled", enabled)
        except:
            pass

    if config_yaml.exists():
        try:
            with open(config_yaml) as f:
                config = yaml.safe_load(f)
                source = config.get("source_type", source)
        except:
            pass

    status = "✓" if enabled else "✗"
    click.echo(f"  {status} {pipeline_dir.name}")
    click.echo(f"     Source: {source} | {description}")
