# Dependency Management Strategy

## The Problem

When users create pipelines through the UI:
1. They select sources/destinations (e.g., Snowflake, Postgres)
2. DLT requires extras: `dlt[snowflake]`, `dlt[postgres]`
3. These dependencies aren't automatically installed
4. Pipeline execution fails with import errors

**Additional complexity**: When Dagster clones the repo, it needs these dependencies too.

## Recommended Solution: Multi-Layer Approach

### Layer 1: Auto-Install on Pipeline Creation (Development)

When a pipeline is created via the web UI, automatically install required dependencies.

**Implementation**:
```python
def install_pipeline_dependencies(source_type: str, destination_type: str):
    """Install DLT extras for source and destination."""
    import subprocess
    import sys

    extras = set()

    # Map source/destination types to DLT extras
    EXTRA_MAPPING = {
        'snowflake': 'snowflake',
        'bigquery': 'bigquery',
        'postgres': 'postgres',
        'redshift': 'redshift',
        'duckdb': 'duckdb',
        'motherduck': 'motherduck',
        'mysql': 'mysql',
        'mssql': 'mssql',
        'clickhouse': 'clickhouse',
        'athena': 'athena',
        'databricks': 'databricks',
        # Add more mappings as needed
    }

    if source_type in EXTRA_MAPPING:
        extras.add(EXTRA_MAPPING[source_type])
    if destination_type in EXTRA_MAPPING:
        extras.add(EXTRA_MAPPING[destination_type])

    if extras:
        extras_str = ','.join(extras)
        package = f"dlt[{extras_str}]"

        print(f"Installing dependencies: {package}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            check=True,
            capture_output=True
        )
```

### Layer 2: requirements.txt Generation

Automatically update `requirements.txt` in the repo with used dependencies.

**Implementation**:
```python
def update_requirements_txt(repo_path: Path):
    """Update requirements.txt with all used pipeline dependencies."""
    pipelines_dir = repo_path / "pipelines"

    # Scan all pipeline configs to find used sources/destinations
    used_sources = set()
    used_destinations = set()

    for tool_dir in pipelines_dir.glob("*"):
        for pipeline_dir in tool_dir.glob("*"):
            config_file = pipeline_dir / "dagster.yaml"
            if config_file.exists():
                # Parse and extract source/destination
                # (would need to add this to pipeline metadata)
                pass

    # Build requirements
    requirements = [
        "dlt>=0.4.0",
        "dagster>=1.6.0",
        "dagster-webserver>=1.6.0",
        # Add extras for each used source/destination
    ]

    for source in used_sources:
        if source in EXTRA_MAPPING:
            requirements.append(f"dlt[{EXTRA_MAPPING[source]}]")

    # Write to requirements.txt
    req_file = repo_path / "requirements.txt"
    with open(req_file, "w") as f:
        f.write("\n".join(sorted(set(requirements))))
```

### Layer 3: Dagster Component Graceful Handling

Make the Dagster component handle missing dependencies gracefully.

**Implementation**:
```python
def _build_dlt_asset(self, pipeline_info: DltPipelineInfo, repo_path: str):
    """Build asset with dependency checking."""

    @asset(...)
    def dlt_pipeline_asset(context: AssetExecutionContext):
        try:
            # Try to import the pipeline module
            module = importlib.import_module(...)
            result = module.run()
            return Output(...)

        except ImportError as e:
            # Check if it's a missing DLT extra
            if "dlt" in str(e).lower():
                error_msg = (
                    f"Missing DLT dependency for pipeline '{pipeline_info.name}'. "
                    f"Install with: pip install dlt[source] or dlt[destination]\\n"
                    f"Original error: {e}"
                )
                context.log.error(error_msg)
                raise ImportError(error_msg)
            raise
```

### Layer 4: Pre-install Common Dependencies (Recommended)

Create a comprehensive `requirements.txt` with all common DLT extras.

**File**: `requirements.txt`
```txt
# Core dependencies
dlt>=0.4.0
dagster>=1.6.0
dagster-webserver>=1.6.0
pydantic>=2.0.0
fastapi>=0.100.0
uvicorn>=0.23.0

# DLT with common database extras
dlt[snowflake]>=0.4.0
dlt[bigquery]>=0.4.0
dlt[postgres]>=0.4.0
dlt[redshift]>=0.4.0
dlt[duckdb]>=0.4.0
dlt[motherduck]>=0.4.0
dlt[databricks]>=0.4.0

# Additional common sources
requests>=2.31.0
pyyaml>=6.0
gitpython>=3.1.0
```

**Pros**:
- ✅ Everything just works
- ✅ No runtime installation needed
- ✅ Dagster deployment is straightforward

**Cons**:
- ❌ Larger install size (~500MB instead of ~100MB)
- ❌ Some unused dependencies

**Verdict**: This is the **best approach for production** - the install size is acceptable compared to the complexity of dynamic installation.

## Recommended Implementation Plan

### Phase 1: Immediate (Production-Ready)
1. ✅ Create comprehensive `requirements.txt` with all common extras
2. ✅ Document which sources/destinations are supported
3. ✅ Add dependency check in Dagster component with clear error messages

### Phase 2: Enhancement (Optional)
1. Track which sources/destinations are actually used
2. Generate minimal `requirements-min.txt` for users who want smaller installs
3. Add UI warning when selecting source/destination without installed extras

### Phase 3: Advanced (Future)
1. Add `pyproject.toml` with optional extras for modular installation
2. Implement auto-install in web UI with progress indicator
3. Add dependency verification endpoint in web UI

## Example requirements.txt (Comprehensive)

```txt
# ============================================================================
# ELT Builder Dependencies
# ============================================================================
# This file includes all common DLT sources and destinations.
# For a minimal install, see requirements-min.txt
# ============================================================================

# Core Framework
dlt>=0.4.0
dagster>=1.6.0
dagster-webserver>=1.6.0
dagster-duckdb>=0.22.0

# Web UI
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
python-multipart>=0.0.6

# Utilities
pyyaml>=6.0
gitpython>=3.1.0
requests>=2.31.0

# ============================================================================
# Database Destinations (DLT Extras)
# ============================================================================
# These are the most commonly used destinations
# Each adds specific database drivers and adapters

# Cloud Data Warehouses
snowflake-connector-python>=3.6.0  # Snowflake
google-cloud-bigquery>=3.11.0      # BigQuery
databricks-sql-connector>=2.9.0    # Databricks

# Traditional Databases
psycopg2-binary>=2.9.0             # PostgreSQL
pymysql>=1.1.0                     # MySQL
pyodbc>=4.0.0                      # SQL Server / MSSQL

# Modern Databases
duckdb>=0.9.0                      # DuckDB (local analytics)
clickhouse-driver>=0.2.0           # ClickHouse

# ============================================================================
# Data Sources (DLT Verified Sources)
# ============================================================================
# Most DLT sources don't require extras, but some do

# REST API (generic - included in base dlt)
# GitHub, Stripe, etc. (included in base dlt)

# Special sources that need extras:
# google-api-python-client  # For Google Sheets, etc.
# boto3>=1.28.0             # For AWS services

# ============================================================================
# Optional: Development & Testing
# ============================================================================
# Uncomment for development environments:
# pytest>=7.4.0
# black>=23.0.0
# ruff>=0.1.0
```

## Usage Instructions

### For Users
```bash
# Simple: Install everything
pip install -r requirements.txt

# Advanced: Minimal install
pip install -r requirements-min.txt
# Then add specific extras as needed:
pip install dlt[snowflake]
```

### For Dagster Deployment
```bash
# In your Dagster project
pip install -r requirements.txt

# Or in Docker
COPY requirements.txt .
RUN pip install -r requirements.txt
```

### For Web UI Users
The web UI will:
1. Show which sources/destinations are available
2. Warn if dependencies are missing (optional)
3. Auto-install if enabled (optional)

## Trade-offs Summary

| Approach | Install Size | Complexity | Production Ready | User Experience |
|----------|--------------|------------|------------------|-----------------|
| **Comprehensive** | ~500MB | Low | ✅ Yes | ⭐⭐⭐⭐⭐ |
| **Minimal + Auto** | ~100MB | High | ⚠️ Maybe | ⭐⭐⭐ |
| **User Managed** | Variable | Medium | ❌ No | ⭐⭐ |

**Recommendation**: Use the **comprehensive approach** with `requirements.txt` containing all common extras. The ~400MB extra install size is worth the simplified deployment and better user experience.
