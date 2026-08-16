import sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "app.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS likes (
            session_id TEXT NOT NULL,
            game_id INTEGER NOT NULL,
            PRIMARY KEY (session_id, game_id)
        )"""
    )
    conn.commit()
    conn.close()


def add_like(session_id: str, game_id: int):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO likes (session_id, game_id) VALUES (?, ?)",
        (session_id, game_id),
    )
    conn.commit()
    conn.close()


def remove_like(session_id: str, game_id: int):
    conn = get_conn()
    conn.execute(
        "DELETE FROM likes WHERE session_id = ? AND game_id = ?",
        (session_id, game_id),
    )
    conn.commit()
    conn.close()


def get_liked_ids(session_id: str) -> list[int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT game_id FROM likes WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return [r["game_id"] for r in rows]


def get_profile_weights(session_id: str, games_by_id: dict) -> tuple[dict, dict]:
    liked_ids = get_liked_ids(session_id)
    genre_counter: Counter = Counter()
    tag_counter: Counter = Counter()

    for gid in liked_ids:
        game = games_by_id.get(gid)
        if not game:
            continue
        genre_counter.update(game["genres"])
        tag_counter.update(game["tags"])

    return dict(genre_counter), dict(tag_counter)
