import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import images, semantic

DATA_PATH = Path(__file__).parent / "data" / "games.json"

SEMANTIC_WEIGHT = 0.55
TFIDF_WEIGHT_WITH_SEMANTIC = 0.30
TFIDF_WEIGHT_ONLY = 1.0
TAG_BOOST = 0.12
GENRE_BOOST = 0.20
PROFILE_GENRE_BOOST = 0.05
PROFILE_TAG_BOOST = 0.03


def _game_text(game: dict) -> str:
    parts = [
        game["title"],
        " ".join(game["genres"]),
        " ".join(game["tags"]),
        game["description"],
    ]
    return " ".join(parts)


class GameRecommender:
    def __init__(self):
        with open(DATA_PATH) as f:
            self.games = json.load(f)

        self.corpus = [_game_text(g) for g in self.games]
        self.id_to_index = {g["id"]: i for i, g in enumerate(self.games)}

        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(self.corpus)

        self.semantic_enabled = semantic.enabled
        self.corpus_embeddings = semantic.get_corpus_embeddings(self.corpus) if semantic.enabled else None
        if self.corpus_embeddings is None:
            self.semantic_enabled = False

        cover_map = images.resolve_cover_images(self.games)
        for g in self.games:
            g["cover_image"] = cover_map.get(g["id"])

    def _component_scores(self, query: str) -> tuple[np.ndarray, np.ndarray | None]:
        query_vec = self.vectorizer.transform([query])
        tfidf_scores = cosine_similarity(query_vec, self.matrix)[0]

        semantic_scores = None
        if self.semantic_enabled:
            q_emb = semantic.embed_query(query)
            if q_emb is not None:
                semantic_scores = semantic.cosine_scores(q_emb, self.corpus_embeddings)
                semantic_scores = np.clip(semantic_scores, 0.0, 1.0)

        return tfidf_scores, semantic_scores

    def _hybrid_base_score(self, i: int, tfidf_scores: np.ndarray, semantic_scores) -> tuple[float, float]:
        tfidf_s = float(tfidf_scores[i])
        semantic_s = float(semantic_scores[i]) if semantic_scores is not None else 0.0

        if semantic_scores is not None:
            base = SEMANTIC_WEIGHT * semantic_s + TFIDF_WEIGHT_WITH_SEMANTIC * tfidf_s
        else:
            base = TFIDF_WEIGHT_ONLY * tfidf_s

        return base, semantic_s

    def search(self, query: str, boost_tags: list[str] | None = None,
               boost_genres: list[str] | None = None, top_k: int = 10) -> list[dict]:
        tfidf_scores, semantic_scores = self._component_scores(query)

        boost_tags = set(t.lower() for t in (boost_tags or []))
        boost_genres = set(g.lower() for g in (boost_genres or []))

        results = []
        for i, game in enumerate(self.games):
            base, _ = self._hybrid_base_score(i, tfidf_scores, semantic_scores)

            game_tags = set(t.lower() for t in game["tags"])
            game_genres = set(g.lower() for g in game["genres"])

            tag_overlap = len(boost_tags & game_tags)
            genre_overlap = len(boost_genres & game_genres)
            score = base + tag_overlap * TAG_BOOST + genre_overlap * GENRE_BOOST

            if score > 0.01:
                results.append((score, game))

        results.sort(key=lambda x: x[0], reverse=True)
        return [{**g, "match_score": round(s, 3)} for s, g in results[:top_k]]
                   
    def match(self, query: str, intent: dict, liked_genres: dict[str, int],
              liked_tags: dict[str, int], top_k: int = 8) -> list[dict]:
        tfidf_scores, semantic_scores = self._component_scores(query)

        boost_tags = set(t.lower() for t in (intent.get("tags") or []))
        boost_genres = set(g.lower() for g in (intent.get("genres") or []))
        mood = (intent.get("mood") or "").lower().strip()
        multiplayer_pref = intent.get("multiplayer")
        playtime = intent.get("playtime_minutes")
        difficulty = (intent.get("difficulty") or "").lower().strip()

        scored = []
        for i, game in enumerate(self.games):
            base, semantic_s = self._hybrid_base_score(i, tfidf_scores, semantic_scores)

            game_tags = set(t.lower() for t in game["tags"])
            game_genres = set(g.lower() for g in game["genres"])
            game_text = game["description"].lower()

            tag_overlap = boost_tags & game_tags
            genre_overlap = boost_genres & game_genres
            score = base + len(tag_overlap) * TAG_BOOST + len(genre_overlap) * GENRE_BOOST

            mood_hit = bool(mood) and (mood in game_tags or mood in game_text)
            if mood_hit:
                score += 0.15

            multiplayer_hit = False
            if multiplayer_pref is True and "multiplayer" in game_tags:
                multiplayer_hit = True
                score += 0.1
            elif multiplayer_pref is False and "single-player" in game_tags:
                multiplayer_hit = True
                score += 0.1

            playtime_hit = False
            if playtime is not None and playtime <= 45 and ("short" in game_tags or "casual" in game_tags):
                playtime_hit = True
                score += 0.08

            difficulty_hit = False
            if difficulty:
                if difficulty in ("hard", "difficult", "hardcore") and (
                    "difficult" in game_tags or "hardcore" in game_tags or "souls-like" in game_genres
                ):
                    difficulty_hit = True
                    score += 0.08
                elif difficulty in ("easy", "casual", "relaxed") and (
                    "casual" in game_tags or "family-friendly" in game_tags
                ):
                    difficulty_hit = True
                    score += 0.08

            profile_boost = 0.0
            for g in game["genres"]:
                profile_boost += liked_genres.get(g, 0) * PROFILE_GENRE_BOOST
            for t in game["tags"]:
                profile_boost += liked_tags.get(t, 0) * PROFILE_TAG_BOOST
            score += profile_boost

            scored.append({
                "game": game,
                "score": score,
                "semantic_s": semantic_s,
                "tag_overlap": tag_overlap,
                "genre_overlap": genre_overlap,
                "mood_hit": mood_hit,
                "multiplayer_hit": multiplayer_hit,
                "playtime_hit": playtime_hit,
                "difficulty_hit": difficulty_hit,
                "profile_hit": profile_boost > 0,
            })

        scored.sort(key=lambda r: r["score"], reverse=True)

        output = []
        for r in scored[:top_k]:
            if r["score"] <= 0.01:
                continue
            percentage = max(1, min(99, round(min(r["score"], 1.0) * 100)))
            output.append({
                **r["game"],
                "match_score": round(r["score"], 3),
                "match_percentage": percentage,
                "why": self._build_reasons(r, mood, difficulty),
            })
        return output

    @staticmethod
    def _build_reasons(r: dict, mood: str, difficulty: str) -> list[str]:
        reasons = []
        if r["mood_hit"]:
            reasons.append(f"Matches your preference for {mood} gameplay")
        if r["playtime_hit"]:
            reasons.append("Suitable for shorter gaming sessions")
        if r["genre_overlap"]:
            reasons.append(f"Genre match: {', '.join(sorted(r['genre_overlap']))}")
        if r["tag_overlap"]:
            reasons.append(f"Matches what you described: {', '.join(sorted(r['tag_overlap'])[:3])}")
        if r["multiplayer_hit"]:
            reasons.append("Fits the multiplayer/single-player style you asked for")
        if r["difficulty_hit"]:
            reasons.append(f"Difficulty matches your '{difficulty}' preference")
        if r["profile_hit"]:
            reasons.append("Similar to genres you've liked before")
        if r["semantic_s"] > 0.35:
            reasons.append("Strong semantic match with your description")
        if not reasons:
            reasons.append("Broadly relevant based on your description")
        return reasons[:5]
        
    def rerank_for_profile(self, results: list[dict], liked_genres: dict[str, int],
                            liked_tags: dict[str, int]) -> list[dict]:
        if not liked_genres and not liked_tags:
            return results

        for r in results:
            profile_boost = 0.0
            for genre in r["genres"]:
                profile_boost += liked_genres.get(genre, 0) * PROFILE_GENRE_BOOST
            for tag in r["tags"]:
                profile_boost += liked_tags.get(tag, 0) * PROFILE_TAG_BOOST
            r["match_score"] = round(r["match_score"] + profile_boost, 3)

        results.sort(key=lambda r: r["match_score"], reverse=True)
        return results

    def get_by_id(self, game_id: int) -> dict | None:
        idx = self.id_to_index.get(game_id)
        return self.games[idx] if idx is not None else None


recommender = GameRecommender()
