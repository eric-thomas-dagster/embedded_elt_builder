"""FastAPI application for the ELT Builder Web UI."""

import os
import json
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml
from git import Repo
import shutil

from ..pipeline_generator import (
    PipelineRequest,
    create_pipeline,
    choose_tool,
)
from .credentials_config import (
    get_required_credentials,
    get_source_configuration,
    SOURCE_CREDENTIALS,
    DESTINATION_CREDENTIALS,
)


def get_config_dir() -> Path:
    """Get the config directory for ELT Builder."""
    config_dir = Path.home() / ".elt-builder"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def load_config() -> dict:
    """Load configuration from file."""
    config_file = get_config_dir() / "config.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config: dict):
    """Save configuration to file."""
    config_file = get_config_dir() / "config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)


def validate_repo_path(path: Path) -> dict:
    """Validate if a path is a valid ELT repository."""
    if not path.exists():
        return {"valid": False, "error": "Path does not exist"}

    if not path.is_dir():
        return {"valid": False, "error": "Path is not a directory"}

    # Check for pipelines directory
    pipelines_dir = path / "pipelines"
    if not pipelines_dir.exists():
        return {
            "valid": True,
            "warning": "No pipelines directory found. This will create one when you add pipelines.",
            "pipeline_count": 0
        }

    # Count pipelines
    dlt_pipelines = list((pipelines_dir / "dlt").glob("*/")) if (pipelines_dir / "dlt").exists() else []
    sling_pipelines = list((pipelines_dir / "sling").glob("*/")) if (pipelines_dir / "sling").exists() else []
    pipeline_count = len(dlt_pipelines) + len(sling_pipelines)

    return {
        "valid": True,
        "pipeline_count": pipeline_count,
        "has_git": (path / ".git").exists()
    }


def ensure_env_vars_exist(repo_path: Path, pipeline_name: str, source_type: str, destination_type: str):
    """Ensure required environment variables exist in .env file for a pipeline."""
    env_file = repo_path / ".env"
    env_metadata = repo_path / ".env.metadata.json"

    # Get required credentials
    creds = get_required_credentials(source_type, destination_type)
    required_keys = []

    for cred in creds.get("source", []):
        required_keys.append(cred["key"])
    for cred in creds.get("destination", []):
        required_keys.append(cred["key"])

    if not required_keys:
        return

    # Read existing .env file
    existing_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key] = value

    # Add missing keys with blank values and comments
    new_lines = []
    if env_file.exists():
        with open(env_file, 'r') as f:
            new_lines = f.readlines()

    # Add new keys at the end with a comment
    added_keys = []
    for key in required_keys:
        if key not in existing_vars:
            if not new_lines or new_lines[-1].strip() != "":
                new_lines.append("\n")
            new_lines.append(f"# Required by pipeline: {pipeline_name}\n")
            new_lines.append(f"{key}=\n")
            added_keys.append(key)

    if added_keys:
        with open(env_file, 'w') as f:
            f.writelines(new_lines)

    # Update metadata to track which pipeline needs which vars
    import json
    metadata = {}
    if env_metadata.exists():
        with open(env_metadata, 'r') as f:
            metadata = json.load(f)

    if "pipeline_vars" not in metadata:
        metadata["pipeline_vars"] = {}

    metadata["pipeline_vars"][pipeline_name] = required_keys

    with open(env_metadata, 'w') as f:
        json.dump(metadata, f, indent=2)


def create_app(repo_path: str) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="ELT Builder", version="0.1.0")

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store repo path in app state
    app.state.repo_path = Path(repo_path).resolve()

    # Templates
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Serve the main UI."""
        return templates.TemplateResponse("index_enhanced.html", {"request": request})

    @app.get("/api/pipelines")
    async def list_pipelines():
        """List all pipelines in the repository."""
        pipelines_dir = app.state.repo_path / "pipelines"

        if not pipelines_dir.exists():
            return {"dlt": [], "sling": []}

        result = {"dlt": [], "sling": []}

        # List dlt pipelines
        dlt_dir = pipelines_dir / "dlt"
        if dlt_dir.exists():
            for pipeline_dir in dlt_dir.iterdir():
                if pipeline_dir.is_dir():
                    info = _get_pipeline_info(pipeline_dir, "dlt")
                    result["dlt"].append(info)

        # List Sling pipelines
        sling_dir = pipelines_dir / "sling"
        if sling_dir.exists():
            for pipeline_dir in sling_dir.iterdir():
                if pipeline_dir.is_dir():
                    info = _get_pipeline_info(pipeline_dir, "sling")
                    result["sling"].append(info)

        return result

    @app.post("/api/pipelines")
    async def create_new_pipeline(request: PipelineRequest):
        """Create a new pipeline."""
        try:
            # Choose tool
            tool = choose_tool(request.source_type, request.destination_type)

            # Build pipeline directory path
            pipeline_dir = app.state.repo_path / "pipelines" / tool / request.name

            if pipeline_dir.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Pipeline '{request.name}' already exists"
                )

            # Create pipeline
            create_pipeline(pipeline_dir, request, tool)

            # Ensure required env vars exist in .env
            ensure_env_vars_exist(
                app.state.repo_path,
                request.name,
                request.source_type,
                request.destination_type
            )

            # Don't auto-commit - let user review changes and commit manually

            return {
                "success": True,
                "message": f"Created {tool} pipeline: {request.name}",
                "tool": tool,
                "path": str(pipeline_dir.relative_to(app.state.repo_path))
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/pipelines/{tool}/{name}")
    async def update_pipeline(tool: str, name: str, request: PipelineRequest):
        """Update an existing pipeline."""
        try:
            pipeline_dir = app.state.repo_path / "pipelines" / tool / name

            if not pipeline_dir.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{name}' not found"
                )

            # Recreate pipeline with new configuration
            create_pipeline(pipeline_dir, request, tool)

            # Ensure required env vars exist in .env
            ensure_env_vars_exist(
                app.state.repo_path,
                request.name,
                request.source_type,
                request.destination_type
            )

            # Don't auto-commit - let user review changes and commit manually

            return {
                "success": True,
                "message": f"Updated {tool} pipeline: {request.name}",
                "tool": tool,
                "path": str(pipeline_dir.relative_to(app.state.repo_path))
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/pipelines/{tool}/{name}")
    async def delete_pipeline(tool: str, name: str):
        """Delete a pipeline."""
        try:
            pipeline_dir = app.state.repo_path / "pipelines" / tool / name

            if not pipeline_dir.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{name}' not found"
                )

            # Delete directory
            shutil.rmtree(pipeline_dir)

            # Don't auto-commit - let user review changes and commit manually

            return {
                "success": True,
                "message": f"Deleted pipeline: {name}"
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.patch("/api/pipelines/{tool}/{name}/toggle")
    async def toggle_pipeline(tool: str, name: str, data: dict):
        """Toggle pipeline enabled status."""
        try:
            pipeline_dir = app.state.repo_path / "pipelines" / tool / name
            dagster_yaml_path = pipeline_dir / "dagster.yaml"

            if not dagster_yaml_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{name}' dagster.yaml not found"
                )

            # Read current dagster.yaml
            with open(dagster_yaml_path) as f:
                config = yaml.safe_load(f) or {}

            # Toggle enabled status
            enabled = data.get("enabled", True)
            config["enabled"] = enabled

            # Write back to file
            with open(dagster_yaml_path, "w") as f:
                yaml.dump(config, f, sort_keys=False, default_flow_style=False)

            # Don't auto-commit toggle changes - let user review and commit manually
            # This allows batching multiple toggles before committing

            return {
                "success": True,
                "message": f"Pipeline {'enabled' if enabled else 'disabled'}",
                "enabled": enabled
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/pipelines/{tool}/{name}/metadata")
    async def get_pipeline_metadata(tool: str, name: str):
        """Get metadata from dagster.yaml for a pipeline."""
        try:
            pipeline_dir = app.state.repo_path / "pipelines" / tool / name
            dagster_yaml_path = pipeline_dir / "dagster.yaml"

            if not dagster_yaml_path.exists():
                # Return default metadata if file doesn't exist
                return {
                    "enabled": True,
                    "description": None,
                    "group_name": "default",
                    "owners": [],
                    "tags": {},
                    "kinds": [],
                    "retries": 2,
                    "retry_delay": 30,
                    "retry_backoff": "LINEAR",
                    "retry_jitter": None
                }

            # Read dagster.yaml
            with open(dagster_yaml_path) as f:
                config = yaml.safe_load(f) or {}

            # Extract retry policy
            retry_policy = config.get("retry_policy", {})
            retries = retry_policy.get("max_retries", config.get("retries", 2))
            retry_delay = retry_policy.get("delay", config.get("retry_delay", 30))
            retry_backoff = retry_policy.get("backoff", "LINEAR")
            retry_jitter = retry_policy.get("jitter")

            return {
                "enabled": config.get("enabled", True),
                "description": config.get("description"),
                "group_name": config.get("group", "default"),
                "owners": config.get("owners", []),
                "tags": config.get("tags", {}),
                "kinds": config.get("kinds", []),
                "retries": retries,
                "retry_delay": retry_delay,
                "retry_backoff": retry_backoff,
                "retry_jitter": retry_jitter
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/pipelines/{tool}/{name}/metadata")
    async def update_pipeline_metadata(tool: str, name: str, metadata: dict):
        """Update metadata in dagster.yaml for a pipeline."""
        try:
            pipeline_dir = app.state.repo_path / "pipelines" / tool / name
            dagster_yaml_path = pipeline_dir / "dagster.yaml"

            if not pipeline_dir.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{name}' not found"
                )

            # Read current config or create new
            if dagster_yaml_path.exists():
                with open(dagster_yaml_path) as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            # Update metadata fields
            config["enabled"] = metadata.get("enabled", True)

            if metadata.get("description"):
                config["description"] = metadata["description"]
            elif "description" in config:
                del config["description"]

            config["group"] = metadata.get("group_name", "default")

            if metadata.get("owners"):
                config["owners"] = metadata["owners"]
            elif "owners" in config:
                del config["owners"]

            if metadata.get("tags"):
                config["tags"] = metadata["tags"]
            elif "tags" in config:
                del config["tags"]

            if metadata.get("kinds"):
                config["kinds"] = metadata["kinds"]
            elif "kinds" in config:
                del config["kinds"]

            # Update retry policy
            retry_policy = {
                "max_retries": metadata.get("retries", 2),
                "delay": metadata.get("retry_delay", 30)
            }

            retry_backoff = metadata.get("retry_backoff", "LINEAR")
            if retry_backoff != "LINEAR":
                retry_policy["backoff"] = retry_backoff

            retry_jitter = metadata.get("retry_jitter")
            if retry_jitter:
                retry_policy["jitter"] = retry_jitter

            config["retry_policy"] = retry_policy

            # Write back to file
            with open(dagster_yaml_path, "w") as f:
                yaml.dump(config, f, sort_keys=False, default_flow_style=False)

            return {
                "success": True,
                "message": f"Updated metadata for pipeline: {name}"
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/sources")
    async def get_sources():
        """Get available source types."""
        sources = list(SOURCE_CREDENTIALS.keys())
        return sorted(sources)

    @app.get("/api/destinations")
    async def get_destinations():
        """Get available destination types."""
        destinations = list(DESTINATION_CREDENTIALS.keys())
        return sorted(destinations)

    @app.get("/api/sources/consolidated")
    async def get_sources_consolidated():
        """Get available sources with tool support information."""
        # API/SaaS sources - DLT only
        api_sources = {
            "github", "stripe", "shopify", "hubspot", "salesforce",
            "google_analytics", "facebook_ads", "google_ads", "slack", "notion",
            "airtable", "asana", "jira", "zendesk", "intercom", "mixpanel",
            "segment", "rest_api"
        }

        # Database sources - primarily Sling, but some supported by DLT too
        db_sources = {
            "postgres", "mysql", "mongodb", "mssql", "oracle", "snowflake",
            "bigquery", "redshift", "databricks", "trino", "clickhouse"
        }

        # Storage sources - DLT only
        storage_sources = {"s3", "gcs", "azure_blob", "csv", "json", "parquet"}

        sources = []
        for source_name in sorted(SOURCE_CREDENTIALS.keys()):
            tools = []

            if source_name in api_sources or source_name in storage_sources:
                tools.append("dlt")

            if source_name in db_sources:
                # Most databases support both
                if source_name in {"postgres", "mysql", "mssql", "oracle"}:
                    tools.extend(["dlt", "sling"])
                else:
                    tools.append("dlt")

            # If not categorized, default to dlt
            if not tools:
                tools.append("dlt")

            sources.append({
                "name": source_name,
                "display_name": source_name.replace("_", " ").title(),
                "tools": tools
            })

        return sources

    @app.get("/api/destinations/consolidated")
    async def get_destinations_consolidated():
        """Get available destinations with tool support information."""
        # File-based destinations - DLT only
        file_based = {
            "filesystem", "duckdb", "motherduck", "s3", "gcs", "azure_blob"
        }

        # Database/warehouse destinations - support both tools
        db_destinations = {
            "postgres", "mysql", "snowflake", "bigquery", "redshift",
            "databricks", "mssql", "clickhouse", "trino"
        }

        # Analytics/search destinations - DLT only
        analytics = {"elasticsearch", "druid", "pinot"}

        destinations = []
        for dest_name in sorted(DESTINATION_CREDENTIALS.keys()):
            tools = []

            if dest_name in file_based or dest_name in analytics:
                tools.append("dlt")

            if dest_name in db_destinations:
                # Most databases support both
                if dest_name in {"postgres", "mysql", "snowflake", "bigquery",
                                  "redshift", "databricks", "mssql"}:
                    tools.extend(["dlt", "sling"])
                else:
                    tools.append("dlt")

            # If not categorized, default to dlt
            if not tools:
                tools.append("dlt")

            destinations.append({
                "name": dest_name,
                "display_name": dest_name.replace("_", " ").title(),
                "tools": tools
            })

        return destinations

    @app.get("/api/credentials/{source_or_destination}")
    async def get_credentials_for_type(source_or_destination: str):
        """Get required credentials for a source or destination."""
        # Check both sources and destinations
        if source_or_destination in SOURCE_CREDENTIALS:
            return SOURCE_CREDENTIALS[source_or_destination]
        elif source_or_destination in DESTINATION_CREDENTIALS:
            return DESTINATION_CREDENTIALS[source_or_destination]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown type: {source_or_destination}"
            )

    @app.get("/api/source-configuration/{source_type}")
    async def get_source_config(source_type: str):
        """Get source configuration fields."""
        config_fields = get_source_configuration(source_type)
        return config_fields

    @app.post("/api/tool-recommendation")
    async def recommend_tool(data: dict):
        """Recommend a tool based on source and destination."""
        source_type = data.get("source_type")
        destination_type = data.get("destination_type")

        if not source_type or not destination_type:
            raise HTTPException(
                status_code=400,
                detail="Both source_type and destination_type required"
            )

        tool = choose_tool(source_type, destination_type)
        return {"tool": tool}

    @app.get("/api/git/status")
    async def git_status():
        """Get git repository status."""
        if not (app.state.repo_path / ".git").exists():
            return {"is_repo": False}

        try:
            repo = Repo(app.state.repo_path)

            return {
                "is_repo": True,
                "branch": repo.active_branch.name,
                "is_dirty": repo.is_dirty(),
                "untracked_files": repo.untracked_files,
                "has_remote": bool(repo.remotes)
            }
        except Exception as e:
            return {"is_repo": False, "error": str(e)}

    @app.post("/api/git/commit")
    async def git_commit(data: dict):
        """Commit changes to git."""
        message = data.get("message", "Update pipelines")

        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)
            repo.git.add(A=True)
            repo.index.commit(message)

            return {
                "success": True,
                "message": "Changes committed"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/git/push")
    async def git_push():
        """Push changes to remote."""
        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)

            if not repo.remotes:
                raise HTTPException(status_code=400, detail="No remote configured")

            origin = repo.remotes.origin
            origin.push()

            return {
                "success": True,
                "message": "Pushed to remote"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/git/diff")
    async def git_diff():
        """Get git diff of uncommitted changes."""
        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)

            # Get diff of unstaged changes
            unstaged_diff = repo.git.diff()

            # Get diff of staged changes
            staged_diff = repo.git.diff('--cached')

            # Get list of untracked files
            untracked = repo.untracked_files

            return {
                "unstaged": unstaged_diff,
                "staged": staged_diff,
                "untracked": untracked
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/git/log")
    async def git_log(limit: int = 20):
        """Get git commit history."""
        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)

            commits = []
            for commit in list(repo.iter_commits(max_count=limit)):
                commits.append({
                    "sha": commit.hexsha[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "full_sha": commit.hexsha
                })

            return {"commits": commits}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/git/revert")
    async def git_revert():
        """Revert uncommitted changes."""
        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)

            # Reset all changes
            repo.git.reset('--hard', 'HEAD')

            # Clean untracked files
            repo.git.clean('-fd')

            return {
                "success": True,
                "message": "All uncommitted changes reverted"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/git/init")
    async def git_init():
        """Initialize a new git repository."""
        if (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Already a git repository")

        try:
            repo = Repo.init(app.state.repo_path)

            # Create initial commit
            repo.git.add(A=True)
            repo.index.commit("Initial commit: ELT pipelines repository")

            return {
                "success": True,
                "message": "Git repository initialized"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/git/add-remote")
    async def git_add_remote(data: dict):
        """Add a remote to existing git repository."""
        remote_url = data.get("remote_url")
        remote_name = data.get("remote_name", "origin")

        if not remote_url:
            raise HTTPException(status_code=400, detail="remote_url is required")

        if not (app.state.repo_path / ".git").exists():
            raise HTTPException(status_code=400, detail="Not a git repository")

        try:
            repo = Repo(app.state.repo_path)

            # Check if remote already exists
            if remote_name in [r.name for r in repo.remotes]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Remote '{remote_name}' already exists"
                )

            # Add the remote
            repo.create_remote(remote_name, remote_url)

            return {
                "success": True,
                "message": f"Remote '{remote_name}' added successfully"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/git/clone")
    async def git_clone(data: dict):
        """Clone a repository (replaces current repo directory)."""
        repo_url = data.get("repo_url")

        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required")

        try:
            # Backup existing directory if it exists and has content
            if app.state.repo_path.exists():
                files = list(app.state.repo_path.iterdir())
                if files:
                    # Only allow clone if directory is empty or user explicitly wants to replace
                    raise HTTPException(
                        status_code=400,
                        detail="Directory not empty. Please use a different path or delete existing content."
                    )

            # Clone the repository
            repo = Repo.clone_from(repo_url, app.state.repo_path)

            return {
                "success": True,
                "message": f"Repository cloned successfully",
                "branch": repo.active_branch.name
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/git/status")
    async def git_status():
        """Check if local repo is behind remote."""
        try:
            repo_path = app.state.repo_path

            if not (repo_path / ".git").exists():
                return {"has_git": False}

            repo = Repo(repo_path)

            # Check if we have a remote
            if not repo.remotes:
                return {
                    "has_git": True,
                    "has_remote": False
                }

            origin = repo.remotes.origin
            current_branch = repo.active_branch.name

            # Fetch latest from remote
            origin.fetch()

            # Get commits behind/ahead
            local_commit = repo.head.commit
            try:
                remote_commit = origin.refs[current_branch].commit
                commits_behind = list(repo.iter_commits(f'{local_commit}..{remote_commit}'))
                commits_ahead = list(repo.iter_commits(f'{remote_commit}..{local_commit}'))

                return {
                    "has_git": True,
                    "has_remote": True,
                    "current_branch": current_branch,
                    "is_behind": len(commits_behind) > 0,
                    "commits_behind": len(commits_behind),
                    "commits_ahead": len(commits_ahead),
                    "can_pull": len(commits_behind) > 0 and len(commits_ahead) == 0
                }
            except Exception:
                return {
                    "has_git": True,
                    "has_remote": True,
                    "current_branch": current_branch,
                    "error": "Could not compare with remote"
                }

        except Exception as e:
            return {"has_git": True, "error": str(e)}

    @app.post("/api/git/pull")
    async def git_pull():
        """Pull latest changes from remote."""
        try:
            repo_path = app.state.repo_path

            if not (repo_path / ".git").exists():
                raise HTTPException(status_code=400, detail="Not a git repository")

            repo = Repo(repo_path)

            if not repo.remotes:
                raise HTTPException(status_code=400, detail="No remote configured")

            origin = repo.remotes.origin
            current_branch = repo.active_branch.name

            # Pull changes
            pull_info = origin.pull(current_branch)

            return {
                "success": True,
                "message": f"Pulled latest changes from {current_branch}",
                "changes": len(pull_info)
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Environment Variables Management
    @app.get("/api/env")
    async def list_env_vars():
        """List all environment variables from .env file with pipeline dependencies."""
        env_file = app.state.repo_path / ".env"
        env_metadata = app.state.repo_path / ".env.metadata.json"

        if not env_file.exists():
            return {"variables": {}, "pipeline_vars": {}}

        try:
            import json

            variables = {}
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Mask sensitive values
                        if any(sensitive in key.upper() for sensitive in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
                            variables[key] = '********' if value else ''
                        else:
                            variables[key] = value if value else ''

            # Read metadata to get pipeline dependencies
            pipeline_vars = {}
            if env_metadata.exists():
                with open(env_metadata, 'r') as f:
                    metadata = json.load(f)
                    pipeline_vars = metadata.get("pipeline_vars", {})

            # Invert to get var -> pipelines mapping
            var_pipelines = {}
            for pipeline, vars in pipeline_vars.items():
                for var in vars:
                    if var not in var_pipelines:
                        var_pipelines[var] = []
                    var_pipelines[var].append(pipeline)

            return {
                "variables": variables,
                "var_pipelines": var_pipelines
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/env")
    async def set_env_var(data: dict):
        """Set or update an environment variable in .env file."""
        key = data.get("key")
        value = data.get("value")

        if not key:
            raise HTTPException(status_code=400, detail="key is required")

        env_file = app.state.repo_path / ".env"

        try:
            # Read existing env vars
            existing_lines = []
            key_found = False

            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.strip().startswith(f"{key}="):
                            if value:  # Update
                                existing_lines.append(f"{key}={value}\n")
                                key_found = True
                            # If value is None, skip the line (delete)
                        else:
                            existing_lines.append(line)

            # Add new key if not found and value is provided
            if not key_found and value:
                existing_lines.append(f"{key}={value}\n")

            # Write back to file
            with open(env_file, 'w') as f:
                f.writelines(existing_lines)

            return {
                "success": True,
                "message": f"Environment variable '{key}' {'updated' if key_found else 'added'}"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/env/{key}")
    async def delete_env_var(key: str):
        """Delete an environment variable from .env file."""
        env_file = app.state.repo_path / ".env"

        if not env_file.exists():
            raise HTTPException(status_code=404, detail=".env file not found")

        try:
            # Read and filter out the key
            existing_lines = []
            found = False

            with open(env_file, 'r') as f:
                for line in f:
                    if not line.strip().startswith(f"{key}="):
                        existing_lines.append(line)
                    else:
                        found = True

            if not found:
                raise HTTPException(status_code=404, detail=f"Key '{key}' not found")

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(existing_lines)

            return {
                "success": True,
                "message": f"Environment variable '{key}' deleted"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/env/sync-dagster-plus-with-values")
    async def sync_to_dagster_plus_with_values(data: dict):
        """Sync environment variables to Dagster+ with specific values for each scope."""
        configs = data.get("configs", [])  # List of {key, value, scope, code_location}

        if not configs:
            raise HTTPException(status_code=400, detail="configs list is required")

        try:
            import subprocess

            results = []
            for config in configs:
                key = config.get("key")
                value = config.get("value")
                scope = config.get("scope")  # "full" or "branch"
                code_location = config.get("code_location")

                if not key or not value:
                    results.append({
                        "key": key,
                        "scope": scope,
                        "success": False,
                        "error": "Missing key or value"
                    })
                    continue

                # Build dg command
                cmd = ["dg", "plus", "create", "env", key, "--value", value]

                # Add scope flag
                if scope == "full":
                    cmd.append("--full-deployment")
                elif scope == "branch":
                    cmd.append("--branch-deployments")

                # Add code location scope if specified
                if code_location:
                    cmd.extend(["--code-location", code_location])

                # Run command
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=app.state.repo_path
                )

                results.append({
                    "key": key,
                    "scope": scope,
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr
                })

            return {
                "success": all(r["success"] for r in results),
                "results": results
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ============================================================================
    # Repository Configuration Endpoints
    # ============================================================================

    @app.get("/api/config/repo-path")
    async def get_repo_path():
        """Get the current repository path."""
        repo_path = app.state.repo_path
        validation = validate_repo_path(repo_path)
        return {
            "path": str(repo_path),
            "validation": validation
        }

    @app.post("/api/config/repo-path")
    async def set_repo_path(data: dict):
        """Set a new repository path."""
        new_path = data.get("path")
        if not new_path:
            raise HTTPException(status_code=400, detail="path is required")

        new_path = Path(new_path).expanduser().resolve()

        # Validate the path
        validation = validate_repo_path(new_path)
        if not validation.get("valid"):
            raise HTTPException(status_code=400, detail=validation.get("error", "Invalid path"))

        # Update app state
        app.state.repo_path = new_path

        # Save to config
        config = load_config()
        config["last_repo_path"] = str(new_path)
        save_config(config)

        return {
            "success": True,
            "path": str(new_path),
            "validation": validation
        }

    @app.get("/api/config/browse")
    async def browse_directories(path: Optional[str] = None):
        """Browse directories for repository selection."""
        if path:
            current_path = Path(path).expanduser().resolve()
        else:
            current_path = Path.home()

        if not current_path.exists() or not current_path.is_dir():
            current_path = Path.home()

        try:
            # Get parent directory
            parent = current_path.parent if current_path != current_path.parent else None

            # Get subdirectories
            subdirs = []
            try:
                for item in sorted(current_path.iterdir()):
                    if item.is_dir() and not item.name.startswith('.'):
                        # Check if it's an ELT repo
                        validation = validate_repo_path(item)
                        subdirs.append({
                            "name": item.name,
                            "path": str(item),
                            "is_elt_repo": validation.get("valid") and validation.get("pipeline_count", 0) > 0,
                            "pipeline_count": validation.get("pipeline_count", 0)
                        })
            except PermissionError:
                pass

            return {
                "current": str(current_path),
                "parent": str(parent) if parent else None,
                "directories": subdirs
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/config/validate")
    async def validate_path(path: str):
        """Validate a repository path."""
        path_obj = Path(path).expanduser().resolve()
        validation = validate_repo_path(path_obj)
        return validation

    return app


def _get_pipeline_info(pipeline_dir: Path, tool_type: str) -> dict:
    """Get information about a pipeline."""
    dagster_yaml = pipeline_dir / "dagster.yaml"
    config_yaml = pipeline_dir / "config.yaml"

    info = {
        "name": pipeline_dir.name,
        "tool": tool_type,
        "description": "No description",
        "enabled": True,
        "source": "unknown",
        "destination": "unknown"
    }

    # Read dagster.yaml
    if dagster_yaml.exists():
        try:
            with open(dagster_yaml) as f:
                config = yaml.safe_load(f)
                if config:
                    info["description"] = config.get("description", info["description"])
                    info["enabled"] = config.get("enabled", info["enabled"])
        except Exception:
            pass

    # Read config.yaml
    if config_yaml.exists():
        try:
            with open(config_yaml) as f:
                config = yaml.safe_load(f)
                if config:
                    info["source"] = config.get("source_type", info["source"])
                    info["destination"] = config.get("destination_type", info["destination"])
                    info["config"] = config.get("configuration", {})
        except Exception:
            pass

    # Also read group, schedule, and metadata from dagster.yaml
    if dagster_yaml.exists():
        try:
            with open(dagster_yaml) as f:
                dagster_config = yaml.safe_load(f)
                if dagster_config:
                    info["group"] = dagster_config.get("group", dagster_config.get("group_name", ""))
                    if "schedule" in dagster_config:
                        info["schedule"] = dagster_config["schedule"]
                    info["owners"] = dagster_config.get("owners", [])
                    info["tags"] = dagster_config.get("tags", {})
                    info["kinds"] = dagster_config.get("kinds", [])

                    # Handle retry policy (new format) or legacy format
                    if "retry_policy" in dagster_config:
                        retry_policy = dagster_config["retry_policy"]
                        info["retries"] = retry_policy.get("max_retries", 2)
                        info["retry_delay"] = retry_policy.get("delay", 30)
                        info["retry_backoff"] = retry_policy.get("backoff", "LINEAR")
                        info["retry_jitter"] = retry_policy.get("jitter")
                    else:
                        # Legacy format
                        info["retries"] = dagster_config.get("retries", 2)
                        info["retry_delay"] = dagster_config.get("retry_delay", 30)
                        info["retry_backoff"] = "LINEAR"
                        info["retry_jitter"] = None
        except Exception:
            pass

    return info
