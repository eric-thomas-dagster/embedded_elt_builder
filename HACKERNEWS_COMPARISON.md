# HackerNews Pipeline Comparison

This document compares the three HackerNews pipeline implementations in this repository.

## Overview

| Pipeline | Location | Type | API | Complexity |
|----------|----------|------|-----|------------|
| **Original** | `pipelines/dlt/hackernews/` | Custom Python | Firebase | Medium |
| **REST API** | `pipelines/dlt/hackernews_rest/` | Generic REST API | Algolia | Low |
| **Advanced REST** | _(create via UI)_ | Generic REST API | Firebase | High |

## Detailed Comparison

### 1. Original Custom Pipeline

**File**: `pipelines/dlt/hackernews/pipeline.py`

```python
@dlt.resource(name="top_stories", write_disposition="replace")
def get_top_stories(max_items: int = 50):
    # Custom Python code with requests library
    response = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json")
    story_ids = response.json()[:max_items]

    for story_id in story_ids:
        story_response = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        story = story_response.json()
        yield story
```

**Pros**:
- ✅ Full control over logic
- ✅ Official HackerNews API
- ✅ Easy to customize and debug
- ✅ Can add complex transformations

**Cons**:
- ❌ Requires custom Python code
- ❌ Cannot be created through UI
- ❌ Maintenance requires code changes
- ❌ Multiple API calls (slower)

**Best for**:
- Complex ETL logic
- Custom transformations
- Learning DLT resource patterns
- When you need full control

---

### 2. REST API Pipeline (Simplified - Algolia)

**File**: `pipelines/dlt/hackernews_rest/pipeline.py`

```python
source = rest_api_source({
    "client": {
        "base_url": "https://hn.algolia.com/api/v1",
    },
    "resources": [{
        "name": "top_stories",
        "endpoint": {
            "path": "search",
            "params": {"tags": "front_page", "hitsPerPage": 50},
        },
        "data_selector": "hits",
    }]
})
```

**Pros**:
- ✅ Simple configuration
- ✅ Single API call per resource
- ✅ Fast execution
- ✅ Can be created via UI
- ✅ Built-in search/filtering
- ✅ Easy to maintain

**Cons**:
- ❌ Third-party API (not official)
- ❌ Data schema differs slightly from Firebase

**Best for**:
- Quick setup and deployment
- When UI configuration is preferred
- Production pipelines (fast + reliable)
- Teams without Python expertise
- When Algolia's features are valuable

---

### 3. REST API Pipeline (Advanced - Firebase)

**Created via UI with Advanced Mode**

```json
{
  "client": {"base_url": "https://hacker-news.firebaseio.com/v0"},
  "resources": [{
    "name": "top_stories",
    "endpoint": {"path": "topstories.json"},
    "child_resources": [{
      "name": "story_details",
      "endpoint": {
        "path": "item/{item_id}.json",
        "params": {"item_id": {"type": "resolve", "field": "items"}}
      }
    }]
  }]
}
```

**Pros**:
- ✅ Official HackerNews API
- ✅ Declarative configuration
- ✅ No custom Python code
- ✅ Can be created via UI

**Cons**:
- ❌ Complex JSON configuration
- ❌ Harder to debug
- ❌ Multiple API calls (slower)
- ❌ Requires understanding resolvers

**Best for**:
- Demonstrating REST API capabilities
- When official API is required
- Infrastructure-as-code approach
- Learning advanced DLT features

---

## Performance Comparison

Assuming 50 top stories:

| Pipeline | API Calls | Avg Time | Network |
|----------|-----------|----------|---------|
| **Original** | 51 (1 + 50) | ~15-20s | High |
| **REST API (Algolia)** | 1 | ~1-2s | Low |
| **REST API (Firebase)** | 51 (1 + 50) | ~15-20s | High |

---

## Data Schema Comparison

### Firebase API Response (Original & Advanced REST)
```json
{
  "id": 39281234,
  "type": "story",
  "by": "username",
  "time": 1704067200,
  "title": "Example Story",
  "url": "https://example.com",
  "score": 123,
  "descendants": 45
}
```

### Algolia API Response (REST API)
```json
{
  "objectID": "39281234",
  "title": "Example Story",
  "url": "https://example.com",
  "author": "username",
  "points": 123,
  "created_at_i": 1704067200,
  "num_comments": 45,
  "_tags": ["story", "front_page"]
}
```

**Field Mapping**:
- `id` → `objectID`
- `by` → `author`
- `time` → `created_at_i`
- `score` → `points`
- `descendants` → `num_comments`

---

## Recommendation Matrix

Choose your implementation based on your needs:

| Need | Recommended Pipeline |
|------|---------------------|
| **Quick setup** | REST API (Algolia) |
| **Best performance** | REST API (Algolia) |
| **Official API required** | Original or Advanced REST |
| **Complex transformations** | Original (Custom) |
| **No Python knowledge** | REST API (either) |
| **Learning DLT** | Original (Custom) |
| **Production deployment** | REST API (Algolia) |
| **UI-based workflow** | REST API (either) |

---

## How to Try Each Approach

### Try Original (Already exists)
```bash
cd elt_pipelines_example
python pipelines/dlt/hackernews/pipeline.py
```

### Try REST API (Algolia)
```bash
cd elt_pipelines_example
python pipelines/dlt/hackernews_rest/pipeline.py
```

### Create Advanced REST (Firebase) via UI
1. Open web UI: `python -m embedded_elt_builder.web.app_enhanced`
2. Click "Create Pipeline"
3. Configure:
   - Source: `rest_api`
   - Destination: `duckdb`
   - Name: `hackernews_firebase`
4. Enable **Advanced Mode** toggle
5. Paste Firebase configuration from `ADVANCED_CONFIG.md`
6. Save and test

---

## Conclusion

**For most users**: Use **REST API (Algolia)** - it's simple, fast, and can be fully configured through the UI.

**For learning**: Keep **Original** - it shows how to build custom DLT resources.

**For advanced users**: Try **Advanced REST (Firebase)** - demonstrates complex REST API configurations with resolvers.

All three approaches are valid and have their place. The best choice depends on your specific requirements and constraints.
