from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from .common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, IST, QUOTA_FILE, NewsItem, clean_text
    from .filter import group_related_items, score_story_group
    from .markdown import readable_title
except ImportError:
    from common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, IST, QUOTA_FILE, NewsItem, clean_text
    from filter import group_related_items, score_story_group
    from markdown import readable_title


def prompt_story_groups(items: list[NewsItem], settings: dict) -> str:
    lines: list[str] = []
    for section, heading in (("local", "Dumka and Nearby"), ("state", "Jharkhand")):
        lines.append(f"{heading} candidate story groups:")
        section_items = [item for item in items if item.section == section]
        if not section_items:
            lines.append("- No fresh items found for this section.")
            continue
        for group_index, group in enumerate(group_related_items(section_items), 1):
            ids = ", ".join(f"[{item.item_id}]" for item in group)
            dates = ", ".join(sorted({item.published for item in group if item.published}))
            score, reasons = score_story_group(group, settings)
            signals = "; ".join(reasons[:4])
            lines.append(f"- Group {group_index} {ids}; score: {score}; signals: {signals}; dates: {dates}")
            for item in group:
                lines.append(f"  {item.item_id}. {item.title} | {item.source}")
    return "\n".join(lines)


def load_quota() -> dict:
    if not QUOTA_FILE.exists():
        return {"day": "", "count": 0, "last_call": 0.0}
    try:
        return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"day": "", "count": 0, "last_call": 0.0}


def reserve_gemini_call(max_daily_calls: int, min_interval_seconds: int) -> None:
    DATA.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    quota = load_quota()
    if quota.get("day") != today:
        quota = {"day": today, "count": 0, "last_call": 0.0}
    if int(quota.get("count", 0)) >= max_daily_calls:
        raise RuntimeError(f"Daily Gemini call limit reached: {max_daily_calls}")
    elapsed = time.time() - float(quota.get("last_call", 0.0))
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    quota["count"] = int(quota.get("count", 0)) + 1
    quota["last_call"] = time.time()
    QUOTA_FILE.write_text(json.dumps(quota, indent=2), encoding="utf-8")


def gemini_summary(items: list[NewsItem], api_key: str, points_per_section: int, settings: dict) -> str:
    reserve_gemini_call(max_daily_calls=20, min_interval_seconds=12)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    current_date = datetime.now(IST).date().isoformat()
    max_points = min(5, points_per_section)
    prompt_items = prompt_story_groups(items, settings)
    prompt = f"""
Create an English daily news brief for Dumka and Jharkhand.
Current IST date: {current_date}

Rules:
- First line must be: TITLE: concise title for the full brief.
- Second line must be: SUMMARY: one concise homepage line covering the main themes across both sections.
- Then produce exactly two sections: SECTION: Dumka and Nearby and SECTION: Jharkhand.
- Under each section, output 0 to {max_points} significant bullet points.
- Use clear English even when source headlines are Hindi.
- Use only the supplied items; do not invent facts.
- Priority for local news: Dumka and its blocks, Muri-Silli-Sonahatu-Rahe, nearby Santhal Pargana districts.
- Merge repeated headlines into one bullet and cite all relevant source ids.
- Every bullet must end with source ids exactly like: Sources: [L1], [L3] or Sources: [J2]
- Format bullets as: - **Short topic:** one concise synthesized sentence. Sources: [L1]

Candidate story groups:
{prompt_items}
""".strip()
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1100}}
    body = json.dumps(payload).encode("utf-8")
    url = f"{GEMINI_API_ROOT}/{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


def headline_without_source(item: NewsItem) -> str:
    title = clean_text(item.title)
    source = clean_text(item.source)
    if source:
        title = re.sub(rf"\s+-\s*{re.escape(source)}$", "", title, flags=re.I)
    return title


def story_topic(group: list[NewsItem]) -> str:
    text = " ".join(headline_without_source(item) for item in group).lower()
    topic_rules = [
        ("road accidents", ("accident", "हादसा", "टक्कर", "मौत", "death")),
        ("court updates", ("court", "high court", "हाईकोर्ट", "judicial")),
        ("local administration", ("voter", "मतदाता", "administration", "प्रशिक्षण", "review", "बैठक")),
        ("recruitment", ("recruitment", "भर्ती", "walk-in", "interview")),
        ("weather alerts", ("weather", "rain", "alert", "मौसम", "बारिश", "वज्रपात")),
        ("health services", ("health", "hospital", "ambulance", "स्वास्थ्य")),
        ("infrastructure", ("road", "bridge", "railway", "power", "electricity", "सड़क", "रेलवे", "बिजली")),
        ("governance", ("government", "सरकार", "policy", "cm ", "मुख्यमंत्री")),
        ("education", ("school", "college", "exam", "education", "विद्यालय", "परीक्षा")),
    ]
    for label, keywords in topic_rules:
        if any(keyword in text for keyword in keywords):
            return label
    return ""


def join_summary_topics(topics: list[str]) -> str:
    clean_topics = [topic for topic in topics if topic]
    if not clean_topics:
        return "Daily Dumka and Jharkhand news updates"
    if len(clean_topics) == 1:
        return f"{clean_topics[0].capitalize()} from Dumka and Jharkhand"
    if len(clean_topics) == 2:
        return f"{clean_topics[0].capitalize()} and {clean_topics[1]} from Dumka and Jharkhand"
    return f"{', '.join(clean_topics[:-1]).capitalize()}, and {clean_topics[-1]} from Dumka and Jharkhand"


def fallback_home_summary(items: list[NewsItem], points_per_section: int, settings: dict) -> str:
    topics: list[str] = []
    max_points = min(5, points_per_section)
    for section in ("local", "state"):
        section_items = [item for item in items if item.section == section]
        groups = group_related_items(section_items)
        groups.sort(key=lambda group: score_story_group(group, settings)[0], reverse=True)
        for group in groups[:max_points]:
            topic = story_topic(group)
            if topic and topic.lower() not in {existing.lower() for existing in topics}:
                topics.append(topic)
            if len(topics) >= 4:
                return join_summary_topics(topics)
    return join_summary_topics(topics)


def fallback_summary(items: list[NewsItem], points_per_section: int, settings: dict) -> str:
    lines = ["TITLE: Dumka and Jharkhand News Brief", f"SUMMARY: {fallback_home_summary(items, points_per_section, settings)}"]
    max_points = min(5, points_per_section)
    for section, heading in (("local", "Dumka and Nearby"), ("state", "Jharkhand")):
        lines.append(f"SECTION: {heading}")
        section_items = [item for item in items if item.section == section]
        groups = group_related_items(section_items)
        groups.sort(key=lambda group: score_story_group(group, settings)[0], reverse=True)
        for group in groups[:max_points]:
            lead = group[0]
            source_ids = ", ".join(f"[{item.item_id}]" for item in group[:4])
            lines.append(f"- **{readable_title(lead.source)}:** {readable_title(lead.title)} Sources: {source_ids}")
    return "\n".join(lines)
