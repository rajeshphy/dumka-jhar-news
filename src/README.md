# `src` breakdown for Dumka/Jharkhand Brief

This `src` folder splits the original single `main.py` into smaller files while keeping the same workflow purpose.

## Files

- `main.py` — command-line entry point and orchestration.
- `common.py` — constants, paths, `NewsItem`, YAML/env helpers.
- `directlink.py` — opens indirect/RSS links and stores only the final landed URL from `response.geturl()`.
- `fetch.py` — downloads RSS/Atom feeds, parses items, resolves direct links, and collects selected news.
- `filter.py` — freshness, relevance, deduplication, grouping, scoring, source validation.
- `ai.py` — Gemini prompt, quota handling, Gemini summary, fallback summary.
- `markdown.py` — Jekyll post generation and source-chip rendering.

## Direct-link policy

The source links in generated posts are not RSS fallback links. For each RSS entry:

1. `fetch.py` reads the feed link.
2. `directlink.py` opens that indirect link with a browser-like GET request.
3. The final URL reached by the HTTP response is returned.
4. If the final URL cannot be resolved, the item is skipped.
5. `markdown.py` prints only the saved direct URL.

This avoids guessed links such as favicon/image URLs and avoids using RSS redirect URLs as source links.
