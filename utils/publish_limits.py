# -*- coding: utf-8 -*-

MAX_TAG_COUNT = 5
KUAISHOU_TAG_COUNT = 4
PLATFORM_TAG_LIMITS = {
    4: KUAISHOU_TAG_COUNT,
}


def get_publish_tag_limit(platform_type):
    try:
        platform_type = int(platform_type)
    except (TypeError, ValueError):
        return MAX_TAG_COUNT
    return PLATFORM_TAG_LIMITS.get(platform_type, MAX_TAG_COUNT)


def normalize_publish_tags(tags, max_count=MAX_TAG_COUNT):
    """Normalize user supplied topic/tag values and enforce a platform cap."""
    if tags is None:
        return []
    if isinstance(tags, str):
        raw_tags = [tags]
    elif isinstance(tags, (list, tuple, set)):
        raw_tags = list(tags)
    else:
        return []

    normalized = []
    seen = set()
    for tag in raw_tags:
        text = str(tag).strip().lstrip("#").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
        if len(normalized) >= max_count:
            break
    return normalized
