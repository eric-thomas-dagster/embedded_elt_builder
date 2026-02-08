# github_to_duckdb

Load github data to duckdb

## Source
- **Type**: github

### Configuration
- **repos**: dagster-io/dagster
- **resources**: ['issues', 'pull_requests', 'workflows']

## Destination
- **Type**: duckdb

## Run Locally

```bash
python -m pipelines.dlt.github_to_duckdb.pipeline
```

## Environment Variables

See your .env file for required credentials.
