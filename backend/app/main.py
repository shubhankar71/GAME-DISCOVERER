from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import database, nlp
from .recommend import recommender

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="AI Game Discovery")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

database.init_db()
games_by_id = {g["id"]: g for g in recommender.games}


class SearchRequest(BaseModel):
    query: str
    session_id: str = "anonymous"
    explain: bool = False


class LikeRequest(BaseModel):
    session_id: str
    game_id: int


class MatchmakerRequest(BaseModel):
    query: str
    session_id: str = "anonymous"


@app.post("/api/search")
def search(req: SearchRequest):
    intent = nlp.extract_intent(req.query)

    results = recommender.search(
        query=intent.get("search_text") or req.query,
        boost_tags=intent.get("tags"),
        boost_genres=intent.get("genres"),
        top_k=12,
    )

    liked_genres, liked_tags = database.get_profile_weights(req.session_id, games_by_id)
    results = recommender.rerank_for_profile(results, liked_genres, liked_tags)

    liked_ids = set(database.get_liked_ids(req.session_id))
    for r in results:
        r["liked"] = r["id"] in liked_ids
        if req.explain:
            r["why"] = nlp.explain_pick(req.query, r)

    return {"query": req.query, "detected_intent": intent, "results": results}


@app.post("/api/matchmaker")
def matchmaker(req: MatchmakerRequest):
    intent = nlp.extract_matchmaker_intent(req.query)

    liked_genres, liked_tags = database.get_profile_weights(req.session_id, games_by_id)
    results = recommender.match(req.query, intent, liked_genres, liked_tags, top_k=8)

    liked_ids = set(database.get_liked_ids(req.session_id))
    for r in results:
        r["liked"] = r["id"] in liked_ids

    return {
        "query": req.query,
        "detected_intent": intent,
        "semantic_search_enabled": recommender.semantic_enabled,
        "results": results,
    }


@app.post("/api/like")
def like(req: LikeRequest):
    database.add_like(req.session_id, req.game_id)
    return {"status": "ok"}


@app.delete("/api/like")
def unlike(req: LikeRequest):
    database.remove_like(req.session_id, req.game_id)
    return {"status": "ok"}


@app.get("/api/profile/{session_id}")
def profile(session_id: str):
    liked_genres, liked_tags = database.get_profile_weights(session_id, games_by_id)
    liked_ids = database.get_liked_ids(session_id)
    return {
        "liked_games": [games_by_id[i] for i in liked_ids if i in games_by_id],
        "top_genres": sorted(liked_genres.items(), key=lambda x: -x[1])[:5],
        "top_tags": sorted(liked_tags.items(), key=lambda x: -x[1])[:5],
    }


@app.get("/api/games/{game_id}")
def get_game(game_id: int):
    return recommender.get_by_id(game_id)


@app.get("/health")
def health():
    return {"status": "ok", "games_loaded": len(recommender.games)}
