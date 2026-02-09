# Converting HackerNews to REST API Configuration

This guide shows how to convert the custom HackerNews pipeline to use the REST API generic source.

## Current Custom Pipeline

The HackerNews pipeline has two resources:
- **top_stories**: Fetches top 50 stories
- **best_stories**: Fetches best 30 stories

Each resource:
1. Fetches story IDs from an endpoint
2. Fetches full story data for each ID

## REST API Configuration (Advanced Mode)

To replicate this with the REST API source, use **Advanced Mode** with the following JSON configuration:

### Configuration for Top Stories

```json
{
  "client": {
    "base_url": "https://hacker-news.firebaseio.com/v0"
  },
  "resources": [
    {
      "name": "top_stories",
      "endpoint": {
        "path": "topstories.json",
        "data_selector": "$",
        "paginator": null
      },
      "processing_steps": [
        {
          "filter": {"limit": 50}
        }
      ],
      "resolve": [
        {
          "endpoint": {
            "path": "item/{story_id}.json",
            "params": {
              "story_id": {
                "type": "resolve",
                "field": "$",
                "resolve_config": {
                  "field_path": "$"
                }
              }
            }
          },
          "data_selector": "$"
        }
      ]
    }
  ]
}
```

### Configuration for Best Stories

```json
{
  "client": {
    "base_url": "https://hacker-news.firebaseio.com/v0"
  },
  "resources": [
    {
      "name": "best_stories",
      "endpoint": {
        "path": "beststories.json",
        "data_selector": "$",
        "paginator": null
      },
      "processing_steps": [
        {
          "filter": {"limit": 30}
        }
      ],
      "resolve": [
        {
          "endpoint": {
            "path": "item/{story_id}.json",
            "params": {
              "story_id": {
                "type": "resolve",
                "field": "$",
                "resolve_config": {
                  "field_path": "$"
                }
              }
            }
          },
          "data_selector": "$"
        }
      ]
    }
  ]
}
```

## Simplified Alternative

For a simpler approach that doesn't require resolvers, you could use the HackerNews Search API:

```json
{
  "client": {
    "base_url": "https://hn.algolia.com/api/v1"
  },
  "resources": [
    {
      "name": "top_stories",
      "endpoint": {
        "path": "search",
        "params": {
          "tags": "front_page",
          "hitsPerPage": 50
        }
      },
      "data_selector": "hits"
    }
  ]
}
```

This uses the Algolia-powered HackerNews search API which returns full story data in a single request.

## Steps to Convert via UI

1. **Create New Pipeline**:
   - Tool: DLT
   - Source: `rest_api`
   - Destination: `duckdb` (or your preferred destination)
   - Name: `hackernews_rest`

2. **Configure REST API Source**:
   - Base URL: `https://hacker-news.firebaseio.com/v0` or `https://hn.algolia.com/api/v1`
   - Resource Name: `top_stories`
   - Enable **Advanced Mode** toggle
   - Paste the appropriate JSON configuration above

3. **Configure Write Disposition**:
   - Select "Replace" for full refresh (matches current behavior)

4. **Save and Test**:
   - The new pipeline will be created alongside the existing custom one
   - You can compare results before removing the old pipeline

## Notes

- The custom pipeline gives you more control and is easier to maintain
- REST API configuration is more declarative but can handle most use cases
- For complex multi-step APIs like HackerNews, custom Python may be preferable
- You can keep both and compare performance/ease of maintenance
