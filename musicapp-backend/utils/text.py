def slug(s: str) -> str:
    return "-".join((s or "").strip().lower().split())
