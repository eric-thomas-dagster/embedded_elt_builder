"""Main CLI entry point for ELT pipeline management."""

import click

from .scaffold import scaffold
from .list_pipelines import list_pipelines
from .delete import delete
from .ui import ui


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """ELT Pipeline Manager - Manage dlt and Sling pipelines for Dagster.

    \b
    Examples:
        elt scaffold create github_snowflake --source github --destination snowflake
        elt scaffold create postgres_bigquery --source postgres --destination bigquery
        elt list
        elt delete my_pipeline
        elt ui
    """
    pass


cli.add_command(scaffold)
cli.add_command(list_pipelines, name="list")
cli.add_command(delete)
cli.add_command(ui)


if __name__ == "__main__":
    cli()
