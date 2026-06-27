from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import IST, POSTS, NewsItem, clean_text
    from .filter import extract_source_ids, infer_source_ids, validate_source_ids
except ImportError:
    from common import IST, POSTS, NewsItem, clean_text
    from filter import extract_source_ids, infer_source_ids, validate_source_ids


def plain_text(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"[*_`#>~]+", "", text)
    text = re.sub(r"\[[A-Z]\d+\]", "", text)
    return clean_text(text)


def readable_title(text: str) -> str:
    text = clean_text(text)
    letters = [char for char in text if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) > 0.82:
        small_words = {"a", "an", "and", "as", "at", "for", "from", "in", "of", "on", "or", "the", "to"}
        words = text.lower().split()
        titled = []
        for index, word in enumerate(words):
            titled.append(word if index > 0 and word in small_words else word[:1].upper() + word[1:])
        return " ".join(titled)
    return text


def clean_title(value: str) -> str:
    title = plain_text(value).strip(" .,:;-")
    return title[:80].rstrip(" ,;:") if title else "Dumka Brief"


def clean_summary(value: str) -> str:
    summary = plain_text(value).strip(" .,:;-")
    return summary[:157].rstrip() + "..." if len(summary) > 160 else summary


def split_digest_header(summary: str) -> tuple[str, str, str]:
    lines = summary.splitlines()
    remaining: list[str] = []
    title = ""
    teaser = ""
    for line in lines:
        match = re.match(r"^TITLE\s*:\s*(.+)$", line.strip(), flags=re.I)
        if match and not title:
            title = clean_title(match.group(1))
            continue
        summary_match = re.match(r"^SUMMARY\s*:\s*(.+)$", line.strip(), flags=re.I)
        if summary_match and not teaser:
            teaser = clean_summary(summary_match.group(1))
            continue
        remaining.append(line)
    return title or "Dumka and Jharkhand News Brief", teaser, "\n".join(remaining).strip()


def split_digest_title(summary: str) -> tuple[str, str]:
    title, _, body = split_digest_header(summary)
    return title, body


def generic_title(title: str) -> bool:
    normalized = clean_text(title).lower()
    return normalized in {
        "dumka brief",
        "dumka and jharkhand news brief",
        "daily dumka and jharkhand news brief",
        "dumka and jharkhand brief",
    }


def yaml_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def item_map(items: list[NewsItem]) -> dict[str, NewsItem]:
    return {item.item_id: item for item in items}


def source_chips_html(source_ids: list[str], lookup: dict[str, NewsItem]) -> str:
    links: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        source_id = source_id.upper()
        if source_id in seen or source_id not in lookup:
            continue
        seen.add(source_id)
        item = lookup[source_id]
        label = html.escape(source_id)
        url = html.escape(item.url, quote=True)
        links.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
    return f'<span class="source-chips">{" ".join(links)}</span>' if links else ""


def inline_markdown_to_html(text: str) -> str:
    placeholders: list[str] = []

    def link_replacer(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        placeholders.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
        return f"@@LINK{len(placeholders) - 1}@@"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacer, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for index, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"@@LINK{index}@@", replacement)
    return escaped


def summary_to_html(summary: str, items: list[NewsItem], points_per_section: int = 5) -> str:
    _, body = split_digest_title(summary)
    lookup = item_map(items)
    current_section = ""
    section_counts = {"local": 0, "state": 0}
    max_points = min(5, points_per_section)
    html_lines: list[str] = []
    in_list = False

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section_match = re.match(r"^SECTION\s*:\s*(.+)$", line, flags=re.I)
        if section_match:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            heading = clean_title(section_match.group(1))
            current_section = "local" if "dumka" in heading.lower() else "state"
            section_counts[current_section] = 0
            html_lines.append(f"\n## {html.escape(heading)}\n")
            html_lines.append('<ul class="digest-points">')
            in_list = True
            continue

        if line.startswith(("- ", "* ")):
            if current_section and section_counts[current_section] >= max_points:
                continue
            if not in_list:
                html_lines.append('<ul class="digest-points">')
                in_list = True
            bullet_text, source_ids = extract_source_ids(line[2:].strip())
            if current_section:
                source_ids = validate_source_ids(bullet_text, source_ids, lookup, current_section)
                if not source_ids:
                    source_ids = infer_source_ids(bullet_text, items, current_section)
            chips = source_chips_html(source_ids, lookup)
            html_lines.append(f"  <li>{inline_markdown_to_html(bullet_text)}{chips}</li>")
            if current_section:
                section_counts[current_section] += 1
            continue

        if in_list:
            html_lines.append("</ul>")
            in_list = False
        html_lines.append(f"<p>{inline_markdown_to_html(line)}</p>")

    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines).strip()


def sources_to_html(items: list[NewsItem]) -> str:
    lines = ['<ul class="source-list">']
    for item in items[:12]:
        label = html.escape(item.item_id)
        title = html.escape(readable_title(item.title))
        url = html.escape(item.url, quote=True)
        source = html.escape(readable_title(item.source)) if item.source else "Source"
        lines.append(f'  <li><a href="{url}" target="_blank" rel="noopener noreferrer">{label}: {title}</a> <span class="source-name">{source}</span></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def build_post(summary: str, items: list[NewsItem], used_ai: bool, points_per_section: int = 5) -> Path:
    POSTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    now_ist = now.astimezone(IST)
    post_path = POSTS / f"{now.date().isoformat()}-dumka-brief.md"

    try:
        run_time = now_ist.strftime("%-I:%M%p")
    except ValueError:
        run_time = now_ist.strftime("%I:%M%p").lstrip("0")

    extracted_title, teaser, _ = split_digest_header(summary)
    if not teaser:
        teaser = clean_summary(plain_text(summary)) or "Daily Dumka and Jharkhand news updates"
    title = extracted_title if not generic_title(extracted_title) else "Dumka and Jharkhand News Brief"
    ai_note = f"Gemini Summary: {run_time}" if used_ai else f"Headline Digest: {run_time}"
    source_list = sources_to_html(items)

    content = f"""---
layout: default
title: {yaml_escape(title)}
date: {now.isoformat()}
summary: {yaml_escape(teaser)}
run_time_ist: {yaml_escape(run_time)}
---

<article class="digest-post">
  <a class="back-link" href="{{{{ '/' | relative_url }}}}">Dumka Brief</a>
  <p class="post-meta">{html.escape(ai_note)}</p>

{summary_to_html(summary, items, points_per_section)}

<section class="source-note">
  <h2>Source</h2>
  <p>Generated from configured local and Jharkhand RSS/news sources.</p>
</section>

<details class="tp-sources">
<summary>Headlines considered</summary>

{source_list}

</details>
</article>
"""
    post_path.write_text(content, encoding="utf-8")
    return post_path
