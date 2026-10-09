

import re
from typing import Any


def normalize_query(query: str) -> str:
    """Normalize a search query."""
    return re.sub(
        r"\s+",
        " ",
        (query or "").strip().lower()
    )


def tokenize(text: str) -> list[str]:
    """Extract searchable words from text."""
    return re.findall(
        r"[^\W_]+",
        normalize_query(text),
        flags=re.UNICODE
    )


def rank_search_results(
    query: str,
    rows: list[dict[str, Any]],
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    Rank indexed pages by relevance to a query.

    Expected fields include:
    title, description, content, domain and url.
    """

    query = normalize_query(query)

    if not query or not rows:
        return []

    query_words = set(tokenize(query))

    if not query_words:
        return []

    ranked = []

    for row in rows:
        page = dict(row)

        title = normalize_query(
            str(page.get("title") or "")
        )
        description = normalize_query(
            str(page.get("description") or "")
        )
        content = normalize_query(
            str(page.get("content") or "")
        )
        domain = normalize_query(
            str(page.get("domain") or "")
        )
        url = normalize_query(
            str(page.get("url") or "")
        )

        score = 0.0

        if query in title:
            score += 12

        if query in description:
            score += 6

        if query in content:
            score += 3

        if query in domain or query in url:
            score += 2

        title_words = set(tokenize(title))
        description_words = set(tokenize(description))
        content_words = set(tokenize(content))
        domain_words = set(tokenize(domain))

        score += len(
            query_words & title_words
        ) * 5

        score += len(
            query_words & description_words
        ) * 2

        score += len(
            query_words & content_words
        )

        score += len(
            query_words & domain_words
        )

        if score > 0:
            page["relevance_score"] = round(
                score,
                3
            )
            ranked.append(page)

    ranked.sort(
        key=lambda item: item["relevance_score"],
        reverse=True
    )

    limit = max(1, min(int(limit), 100))

    return ranked[:limit]
