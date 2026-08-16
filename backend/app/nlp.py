import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"

_client = None
if os.getenv("ANTHROPIC_API_KEY"):
    _client = Anthropic()

SYSTEM_PROMPT = """You turn a player's natural language game request into structured search hints.
Respond with ONLY a JSON object, no other text, in this exact shape:
{"genres": ["..."], "tags": ["..."], "search_text": "..."}

- genres: likely genre words (e.g. FPS, Puzzle, RPG, Roguelike, Racing, Horror, Platformer, Strategy, Sports, Fighting, Simulation, MOBA, Sandbox, Survival, Party)
- tags: relevant descriptive tags (e.g. multiplayer, single-player, co-op, competitive, relaxing, difficult, increasing difficulty, 2D, open-world, futuristic, colorful)
- search_text: a short cleaned-up version of the query for text search

Keep lists short (max 4 items each)."""


def extract_intent(query: str) -> dict:
    if _client is None:
        return {"genres": [], "tags": [], "search_text": query}

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        text = response.content[0].text.strip()
        return json.loads(text)
    except Exception:
        return {"genres": [], "tags": [], "search_text": query}


MATCHMAKER_SYSTEM_PROMPT = """You turn a player's natural language description into structured \
matchmaking preferences for a game recommender. Respond with ONLY a JSON object, no other text, \
in this exact shape:
{
  "mood": "..." or null,
  "genres": ["..."],
  "gameplay_style": "..." or null,
  "multiplayer": true, false, or null,
  "num_players": integer or null,
  "playtime_minutes": integer or null,
  "difficulty": "..." or null,
  "tags": ["..."],
  "search_text": "..."
}

- mood: one short word/phrase, e.g. "relaxing", "intense", "funny", "cozy" - null if not implied
- genres: likely genre words (e.g. FPS, Puzzle, RPG, Strategy, Racing, Horror, Platformer, Party, Simulation)
- gameplay_style: short phrase describing how it plays, e.g. "co-op with friends", "solo exploration"
- multiplayer: true if they want multiplayer/friends/co-op, false if explicitly solo, null if unclear
- num_players: a number if they mention a specific group size, else null
- playtime_minutes: estimated minutes if they mention a session length ("an hour" -> 60, "quick" -> 20), else null
- difficulty: "easy", "medium", "hard", or a phrase like "not too competitive" - null if not implied
- tags: relevant descriptive tags (e.g. multiplayer, single-player, co-op, competitive, relaxing, funny, casual, difficult, increasing difficulty)
- search_text: a short cleaned-up version of the query for text search

Keep lists short (max 4 items each)."""

_MOOD_WORDS = ["relaxing", "chill", "calm", "cozy", "intense", "funny", "hilarious",
               "scary", "creepy", "peaceful", "exciting", "competitive"]
_GENRE_WORDS = ["fps", "shooter", "puzzle", "rpg", "strategy", "racing", "horror",
                "platformer", "party", "simulation", "sports", "fighting", "roguelike",
                "survival", "sandbox", "battle royale", "moba", "card game", "board game"]
_DIFFICULTY_WORDS = {"easy": "easy", "casual": "easy", "beginner": "easy",
                      "hard": "hard", "difficult": "hard", "challenging": "hard", "hardcore": "hard"}


def _fallback_matchmaker_intent(query: str) -> dict:
    q = query.lower()

    mood = next((w for w in _MOOD_WORDS if w in q), None)
    genres = [w.upper() if w == "fps" else w for w in _GENRE_WORDS if w in q][:4]

    multiplayer = None
    if any(w in q for w in ["multiplayer", "with my friends", "with friends", "co-op", "coop", "together"]):
        multiplayer = True
    elif any(w in q for w in ["single player", "single-player", "solo", "by myself", "alone"]):
        multiplayer = False

    num_players = None
    players_match = re.search(r"(\d+)\s*(players?|friends|people)", q)
    if players_match:
        num_players = int(players_match.group(1))

    playtime_minutes = None
    hour_match = re.search(r"(\d+)\s*hour", q)
    min_match = re.search(r"(\d+)\s*min", q)
    if hour_match:
        playtime_minutes = int(hour_match.group(1)) * 60
    elif min_match:
        playtime_minutes = int(min_match.group(1))
    elif "an hour" in q:
        playtime_minutes = 60
    elif any(w in q for w in ["quick", "short", "a few minutes"]):
        playtime_minutes = 20

    difficulty = next((v for k, v in _DIFFICULTY_WORDS.items() if k in q), None)
    if difficulty is None and "not too competitive" in q:
        difficulty = "easy"

    tags = []
    if multiplayer is True:
        tags.append("multiplayer")
    if multiplayer is False:
        tags.append("single-player")
    if mood:
        tags.append(mood)
    if "funny" in q or "hilarious" in q or "comedy" in q:
        tags.append("comedy")

    return {
        "mood": mood,
        "genres": genres,
        "gameplay_style": None,
        "multiplayer": multiplayer,
        "num_players": num_players,
        "playtime_minutes": playtime_minutes,
        "difficulty": difficulty,
        "tags": tags[:4],
        "search_text": query,
    }


def extract_matchmaker_intent(query: str) -> dict:
    """Richer intent extraction for the AI Game Matchmaker. Falls back to
    regex/keyword matching if no API key is configured or the call fails,
    so the matchmaker always returns a usable, correctly-shaped result."""
    fallback = _fallback_matchmaker_intent(query)

    if _client is None:
        return fallback

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=350,
            system=MATCHMAKER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        text = response.content[0].text.strip()
        parsed = json.loads(text)
        for key, value in fallback.items():
            parsed.setdefault(key, value)
        return parsed
    except Exception:
        return fallback


def explain_pick(query: str, game: dict) -> str:
    if _client is None:
        return f"Matches your search based on genre and tags: {', '.join(game['genres'])}."

    try:
        prompt = (
            f"User asked for: \"{query}\"\n"
            f"Game: {game['title']} — genres: {', '.join(game['genres'])}, "
            f"tags: {', '.join(game['tags'])}\n"
            "In one short friendly sentence, explain why this game fits what they asked for."
        )
        response = _client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return f"Matches your search based on genre and tags: {', '.join(game['genres'])}."
