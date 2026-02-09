"""Delete command to remove pipelines."""

import click
from pathlib import Path
import shutil
from git import Repo


@click.command()
@click.argument("name")
@click.option("--repo-path", default=".", help="Path to the ELT pipelines repository")
@click.option("--git-commit/--no-git-commit", default=True, help="Auto-commit to git")
def delete(name: str, repo_path: str, git_commit: bool):
    """Delete an ELT pipeline by name.

    \b
    Example:
        elt delete my_pipeline
        elt delete my_pipeline --no-git-commit
    """
    repo_path_obj = Path(repo_path).resolve()
    pipelines_dir = repo_path_obj / "pipelines"

    # Search for pipeline in both dlt and sling directories
    found = None
    for tool in ["dlt", "sling"]:
        pipeline_dir = pipelines_dir / tool / name
        if pipeline_dir.exists():
            found = (pipeline_dir, tool)
            break

    if not found:
        click.echo(f"❌ Pipeline '{name}' not found")
        click.echo(f"\nSearched in:")
        click.echo(f"  - {pipelines_dir}/dlt/{name}")
        click.echo(f"  - {pipelines_dir}/sling/{name}")
        return

    pipeline_dir, tool = found

    # Confirm deletion
    if not click.confirm(f"\n⚠️  Delete {tool} pipeline '{name}'?", abort=True):
        return

    # Delete directory
    shutil.rmtree(pipeline_dir)
    click.echo(f"✅ Deleted: {pipeline_dir.relative_to(repo_path_obj)}")

    # Git operations
    if git_commit:
        try:
            if (repo_path_obj / ".git").exists():
                repo = Repo(repo_path_obj)
                relative_path = pipeline_dir.relative_to(repo_path_obj)

                # Git rm
                repo.index.remove([str(relative_path)], r=True, working_tree=True)

                # Commit
                repo.index.commit(f"Delete {tool} pipeline: {name}")
                click.echo(f"✅ Committed deletion")

                # Push if remote exists
                if repo.remotes:
                    try:
                        origin = repo.remotes.origin
                        origin.push()
                        click.echo("✅ Pushed to remote")
                    except Exception as e:
                        click.echo(f"⚠️  Could not push: {e}")
        except Exception as e:
            click.echo(f"⚠️  Git operation failed: {e}")
            click.echo("   You can commit manually later.")
