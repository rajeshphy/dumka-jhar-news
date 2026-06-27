from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone

try:
    from .common import IST, NewsItem, clean_text, config_bool
except ImportError:
    from common import IST, NewsItem, clean_text, config_bool


def configured_keywords(settings: dict, key: str, default: str) -> list[str]:
    raw = settings.get(key, default)
    return [clean_text(keyword).lower() for keyword in str(raw).split(",") if clean_text(keyword)]


def section_keywords(section: str, settings: dict) -> list[str]:
    default_local = (
        "dumka,दुमका,basukinath,बासुकीनाथ,santhal,संथाल,deoghar,देवघर,"
        "jamtara,जामताड़ा,godda,गोड्डा,pakur,पाकुड़,sahebganj,sahibganj,साहिबगंज,"
        "muri,मुरी,मूरी,silli,सिल्ली,sonahatu,सोनाहातू,rahe,राहे"
    )
    default_state = (
        "jharkhand,झारखंड,ranchi,रांची,jamshedpur,जमशेदपुर,dhanbad,धनबाद,"
        "bokaro,बोकारो,palamu,पलामू,hazaribagh,हजारीबाग,giridih,गिरिडीह,chaibasa,चाईबासा"
    )
    return configured_keywords(settings, f"{section}_keywords", default_local if section == "local" else default_state)


def filter_fresh_items(items: list[NewsItem], settings: dict) -> list[NewsItem]:
    require_today = config_bool(settings.get("require_ist_today"), True)
    allow_unknown_dates = config_bool(settings.get("allow_unknown_dates"), False)
    max_age_hours = int(settings.get("max_age_hours", 30))
    now_ist = datetime.now(IST)
    fresh: list[NewsItem] = []
    for item in items:
        if not item.published_at:
            if allow_unknown_dates:
                fresh.append(item)
            continue
        published_ist = item.published_at.astimezone(IST)
        if require_today:
            if published_ist.date() == now_ist.date():
                fresh.append(item)
            continue
        if now_ist - published_ist <= timedelta(hours=max_age_hours):
            fresh.append(item)
    return sorted(fresh, key=item_sort_key, reverse=True)


def filter_relevant_items(section: str, items: list[NewsItem], settings: dict) -> list[NewsItem]:
    keywords = section_keywords(section, settings)
    if not keywords:
        return items
    relevant = []
    for item in items:
        haystack = f"{item.title} {item.source}".lower()
        if any(keyword in haystack for keyword in keywords):
            relevant.append(item)
    return relevant


def filter_excluded_items(items: list[NewsItem], settings: dict) -> list[NewsItem]:
    excluded = configured_keywords(
        settings,
        "exclude_keywords",
        "horoscope,astrology,photo gallery,photos,web story,viral video,recipe,lottery,result live,cricket score,match preview",
    )
    useful = []
    for item in items:
        haystack = f"{item.title} {item.source}".lower()
        if not any(keyword in haystack for keyword in excluded):
            useful.append(item)
    return useful


def item_sort_key(item: NewsItem) -> tuple[int, float]:
    if not item.published_at:
        return (0, 0.0)
    return (1, item.published_at.timestamp())


def assign_ids(section: str, items: list[NewsItem]) -> list[NewsItem]:
    prefix = "L" if section == "local" else "J"
    for index, item in enumerate(items, 1):
        item.item_id = f"{prefix}{index}"
    return items


def normalized_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_match_text(text: str) -> str:
    text = clean_text(text).lower()
    replacements = {
        r"\bhc\b": "high court",
        r"\bcm\b": "chief minister",
        r"\bgovt\b": "government",
        r"\bfir\b": "first information report",
        r"\bmcc\b": "model code conduct",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def keyword_set(text: str) -> set[str]:
    normalized = normalize_match_text(text)
    words = re.findall(r"[\w-]{4,}", normalized, flags=re.UNICODE)
    stopwords = {
        "about", "after", "from", "have", "into", "that", "their", "this", "with",
        "dumka", "jharkhand", "news", "latest", "today", "google", "india", "court", "high",
        "case", "cases", "legal", "order", "orders", "updates", "story", "stories", "live",
    }
    return {word for word in words if word not in stopwords}


def title_fingerprint(title: str) -> str:
    words = keyword_set(title)
    return " ".join(sorted(words))


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    result: list[NewsItem] = []
    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    for item in items:
        url_key = normalized_url(item.url)
        title_key = title_fingerprint(item.title)
        if url_key in seen_urls or title_key in seen_keys:
            continue
        seen_urls.add(url_key)
        seen_keys.add(title_key)
        result.append(item)
    return result


def related_titles(a: str, b: str) -> bool:
    left = keyword_set(a)
    right = keyword_set(b)
    if not left or not right:
        return False
    overlap = len(left & right)
    return overlap >= 3 and overlap / min(len(left), len(right)) >= 0.55


def group_related_items(items: list[NewsItem]) -> list[list[NewsItem]]:
    groups: list[list[NewsItem]] = []
    for item in items:
        matched_group = None
        for group in groups:
            if any(related_titles(item.title, existing.title) for existing in group):
                matched_group = group
                break
        if matched_group is None:
            groups.append([item])
        else:
            matched_group.append(item)
    return groups


def keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)


def unique_sources(group: list[NewsItem]) -> set[str]:
    return {clean_text(item.source).lower() for item in group if clean_text(item.source)}


def primary_local_keywords(settings: dict) -> list[str]:
    return configured_keywords(
        settings,
        "primary_local_keywords",
        str(settings.get("local_primary_keywords", "dumka,दुमका,basukinath,बासुकीनाथ,jama,जामा,jarmundi,जरमुंडी")),
    )


def personal_local_keywords(settings: dict) -> list[str]:
    return configured_keywords(
        settings,
        "personal_local_keywords",
        "muri,मुरी,मूरी,silli,सिल्ली,sonahatu,सोनाहातू,rahe,राहे,hindalco muri,हिंडाल्को मुरी,muri junction,मुरी जंक्शन,silli assembly,सिल्ली विधानसभा",
    )


def regional_local_keywords(settings: dict) -> list[str]:
    return configured_keywords(
        settings,
        "regional_local_keywords",
        str(settings.get("local_nearby_keywords", "santhal,संथाल,santal,संताल,deoghar,देवघर,jamtara,जामताड़ा,godda,गोड्डा,pakur,पाकुड़,sahebganj,sahibganj,साहिबगंज")),
    )


def recency_score(group: list[NewsItem]) -> int:
    newest = max((item.published_at for item in group if item.published_at), default=None)
    if not newest:
        return 0
    age = datetime.now(timezone.utc) - newest.astimezone(timezone.utc)
    if age <= timedelta(hours=6):
        return 2
    if age <= timedelta(hours=12):
        return 1
    return 0


def score_story_group(group: list[NewsItem], settings: dict) -> tuple[int, list[str]]:
    if not group:
        return 0, []
    section = group[0].section
    text = " ".join(f"{item.title} {item.source}" for item in group).lower()
    score = 0
    reasons: list[str] = []
    source_boost = min(4, max((max(0, item.source_weight) for item in group), default=1))
    score += source_boost
    reasons.append(f"source weight +{source_boost}")
    if section == "local":
        primary_hits = keyword_hits(text, primary_local_keywords(settings))
        personal_hits = keyword_hits(text, personal_local_keywords(settings))
        regional_hits = keyword_hits(text, regional_local_keywords(settings))
        if primary_hits:
            score += 6
            reasons.append("primary Dumka +6")
        elif personal_hits:
            score += 5
            reasons.append("Muri-Silli local +5")
        elif regional_hits:
            score += 2
            reasons.append("regional local +2")
        else:
            score -= 3
            reasons.append("weak local match -3")
    else:
        state_hits = keyword_hits(text, section_keywords("state", settings))
        if state_hits:
            score += 3
            reasons.append("state match +3")
    public_hits = keyword_hits(
        text,
        configured_keywords(
            settings,
            "public_interest_keywords",
            "accident,हादसा,death,मौत,court,high court,police,arrest,crime,fire,weather,rain,alert,government,सरकार,recruitment,भर्ती,exam,school,health,hospital,power,electricity,road,bridge,water,farmer,tribal,forest,corruption,probe,जांच",
        ),
    )
    if public_hits:
        boost = min(6, public_hits * 2)
        score += boost
        reasons.append(f"public interest +{boost}")
    if len(group) > 1:
        boost = min(3, len(group) - 1)
        score += boost
        reasons.append(f"related headlines +{boost}")
    if len(unique_sources(group)) > 1:
        score += 2
        reasons.append("multiple sources +2")
    freshness = recency_score(group)
    if freshness:
        score += freshness
        reasons.append(f"freshness +{freshness}")
    return score, reasons


def select_top_story_groups(section: str, items: list[NewsItem], settings: dict) -> list[list[NewsItem]]:
    groups = group_related_items(items)
    scored = []
    for group in groups:
        score, _ = score_story_group(group, settings)
        newest = max((item.published_at.timestamp() for item in group if item.published_at), default=0.0)
        scored.append((score, newest, group))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    max_groups = int(settings.get("max_groups_per_section", 8))
    min_score = int(settings.get("min_group_score", 2))
    selected = [group for score, _, group in scored if score >= min_score][:max_groups]
    if not selected:
        selected = [group for _, _, group in scored[:max_groups]]
    return selected


def source_relevance_score(text: str, item: NewsItem) -> int:
    bullet_words = keyword_set(text)
    title_words = keyword_set(item.title)
    score = len(bullet_words & title_words)
    bullet_text = normalize_match_text(text)
    title_text = normalize_match_text(item.title)
    phrase_pairs = (
        ("basukinath", "basukinath"), ("shravani", "shravani"), ("dumka", "dumka"),
        ("muri", "muri"), ("silli", "silli"), ("accident", "accident"), ("court", "court"),
        ("recruitment", "भर्ती"), ("weather", "मौसम"), ("rain", "बारिश"),
    )
    for bullet_phrase, title_phrase in phrase_pairs:
        if bullet_phrase in bullet_text and title_phrase in title_text:
            score += 2
    return score


def validate_source_ids(text: str, source_ids: list[str], lookup: dict[str, NewsItem], section: str) -> list[str]:
    valid: list[str] = []
    for source_id in source_ids:
        item = lookup.get(source_id)
        if not item or item.section != section:
            continue
        if source_relevance_score(text, item) >= 2:
            valid.append(source_id)
    return valid


def infer_source_ids(text: str, items: list[NewsItem], section: str, limit: int = 2) -> list[str]:
    text_words = keyword_set(text)
    if not text_words:
        return []
    scored = []
    for item in items:
        if item.section != section:
            continue
        overlap = len(text_words & keyword_set(item.title))
        if overlap:
            scored.append((overlap, item.item_id))
    scored.sort(reverse=True)
    return [item_id for _, item_id in scored[:limit]]


def extract_source_ids(text: str) -> tuple[str, list[str]]:
    source_ids = [match.upper() for match in re.findall(r"\[([LJ]\d+)\]", text, flags=re.I)]
    text = re.sub(r"\s*Sources?:\s*(?:\[[LJ]\d+\]\s*,?\s*)+$", "", text, flags=re.I)
    text = re.sub(r"\s*(?:\[[LJ]\d+\]\s*)+$", "", text, flags=re.I)
    return clean_text(text), source_ids
