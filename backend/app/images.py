import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx

DATA_DIR = Path(__file__).parent / "data"
CACHE_PATH = DATA_DIR / "image_cache.json"

RAWG_BASE_URL = "https://api.rawg.io/api"
REQUEST_TIMEOUT = 4.0

_PALETTES = [
    ("#3a2e5c", "#8b5cf6"),
    ("#1e3a4a", "#22d3ee"),
    ("#4a2318", "#f97316"),
    ("#1a3d2e", "#34d399"),
    ("#4a1e3a", "#ec4899"),
    ("#3a3a1e", "#e3b341"),
    ("#1e2a4a", "#60a5fa"),
    ("#4a1e1e", "#ef4444"),
]


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _placeholder(game: dict) -> str:
    """Deterministic inline SVG poster - always renders, always relevant
    (shows the game's real title), no network required."""
    title = game.get("title", "?")
    initials = "".join(w[0].upper() for w in title.split()[:2]) or "?"
    idx = int(hashlib.md5(str(game.get("id", title)).encode()).hexdigest(), 16) % len(_PALETTES)
    c1, c2 = _PALETTES[idx]

    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='400' height='533' viewBox='0 0 400 533'>
<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
<stop offset='0%' stop-color='{c1}'/><stop offset='100%' stop-color='{c2}'/>
</linearGradient></defs>
<rect width='400' height='533' fill='url(#g)'/>
<text x='200' y='285' font-family='Sora, sans-serif' font-size='120' font-weight='700'
fill='rgba(255,255,255,0.9)' text-anchor='middle' dominant-baseline='middle'>{initials}</text>
<text x='200' y='480' font-family='IBM Plex Mono, monospace' font-size='18'
fill='rgba(255,255,255,0.75)' text-anchor='middle'>{title[:28]}</text>
</svg>"""
    encoded = quote(svg)
    return f"data:image/svg+xml;charset=utf-8,{encoded}"


def _fetch_rawg_cover(title: str, api_key: str) -> str | None:
    try:
        resp = httpx.get(
            f"{RAWG_BASE_URL}/games",
            params={"key": api_key, "search": title, "page_size": 1},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results and results[0].get("background_image"):
            return results[0]["background_image"]
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return None


def resolve_cover_images(games: list[dict]) -> dict[int, str]:
    """Returns {game_id: image_url_or_data_uri} for every game, using the
    dataset's own image field, then RAWG, then a generated placeholder."""
    cache = _load_cache()
    api_key = os.environ.get("RAWG_API_KEY")
    result: dict[int, str] = {}
    cache_dirty = False

    for game in games:
        gid = game["id"]

        if game.get("image"):
            result[gid] = game["image"]
            continue

        cache_key = str(gid)
        if cache_key in cache:
            result[gid] = cache[cache_key]
            continue

        image_url = None
        if api_key:
            image_url = _fetch_rawg_cover(game["title"], api_key)

        image_url = image_url or _placeholder(game)
        result[gid] = image_url
        cache[cache_key] = image_url
        cache_dirty = True

    if cache_dirty:
        _save_cache(cache)

    return result
