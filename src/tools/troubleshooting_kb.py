"""Tool: query_troubleshooting_kb

Queries the Foundry IQ knowledge base (Azure AI Search) for authoritative
Microsoft documentation about B2B guest user troubleshooting. Returns relevant
passages from indexed Microsoft Learn documents with source citations.

This tool is the agent's grounding mechanism — every diagnostic conclusion
should be backed by a citation from this knowledge base.
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv


# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_INDEX_NAME = os.getenv("SEARCH_INDEX_NAME")

# Azure AI Search REST API version (current stable as of 2026)
API_VERSION = "2024-07-01"


def query_troubleshooting_kb(symptom: str, top_results: int = 3) -> dict:
    """Search authoritative Microsoft documentation for guidance on a B2B guest user issue.

    Use this tool AFTER you have gathered evidence from the other tools and have
    formed a hypothesis about what's wrong. Query with a description of the SYMPTOM
    or DIAGNOSIS, not the user's email. Examples of good queries:

    - "guest user signing in with different email than invited"
    - "MFA registration failure landline phone number"
    - "Google identity provider not configured for B2B"
    - "guest user redeemed invitation but cannot access SharePoint site"

    The tool returns excerpts from official Microsoft Learn documentation that you
    should cite in your final diagnosis. Always include the source filename in your
    response so the IT admin can verify your remediation advice.

    Args:
        symptom: A natural-language description of the problem or failure pattern
            you want guidance on. Be specific.
        top_results: Number of relevant passages to return (default 3, max 5).

    Returns:
        A dict containing:
        - query: the symptom that was searched
        - resultCount: number of passages returned
        - results: list of passages, each with:
            - source: the document filename (e.g., "01-troubleshoot-b2b.pdf")
            - content: the relevant text excerpt
            - score: relevance score (higher = more relevant)
        - error: if the search failed, an error message
    """
    if not all([SEARCH_ENDPOINT, SEARCH_API_KEY, SEARCH_INDEX_NAME]):
        return {
            "error": "Search credentials not configured. Check .env for SEARCH_ENDPOINT, SEARCH_API_KEY, SEARCH_INDEX_NAME."
        }

    top_results = min(max(top_results, 1), 5)

    url = f"{SEARCH_ENDPOINT}/indexes/{SEARCH_INDEX_NAME}/docs/search?api-version={API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": SEARCH_API_KEY,
    }
    body = {
        "search": symptom,
        "top": top_results,
        "queryType": "simple",
        "searchMode": "any",
        # Only retrieve the fields we actually need (excludes the huge vector field)
        "select": "snippet,metadata_storage_path",
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=15)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        return {
            "error": f"Search API returned {response.status_code}: {response.text[:500]}"
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Search request failed: {e}"}

    data = response.json()
    raw_results = data.get("value", [])

    normalized_results = []
    for r in raw_results:
        content = r.get("snippet", "")
        source = r.get("metadata_storage_path", "Unknown source")
        score = r.get("@search.score", 0)

        # Truncate very long content for readability
        if len(content) > 800:
            content = content[:800] + "..."

        normalized_results.append({
            "source": source,
            "content": content,
            "score": round(score, 2),
        })

    return {
        "query": symptom,
        "resultCount": len(normalized_results),
        "results": normalized_results,
    }


if __name__ == "__main__":
    print("Test 1: Query for wrong-identity scenario")
    print(json.dumps(
        query_troubleshooting_kb("guest user signing in with different email than invited"),
        indent=2
    ))

    print("\nTest 2: Query for Google identity scenario")
    print(json.dumps(
        query_troubleshooting_kb("Google identity provider not configured for B2B"),
        indent=2
    ))

    print("\nTest 3: Query for MFA scenario")
    print(json.dumps(
        query_troubleshooting_kb("MFA registration failure phone landline"),
        indent=2
    ))
