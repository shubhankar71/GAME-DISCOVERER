import hashlib
import json
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
EMBEDDINGS_META_PATH = DATA_DIR / "embeddings_meta.json"
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
enabled = False

try:
    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer(MODEL_NAME)
    enabled = True
except Exception:
    # covers ImportError (package not installed) and any runtime failure
    # loading/downloading the model (e.g. no internet on first run)
    _model = None
    enabled = False


def _corpus_hash(corpus: list[str]) -> str:
    joined = "\u241f".join(corpus)
    return hashlib.sha256(joined.encode()).hexdigest()


def get_corpus_embeddings(corpus: list[str]) -> np.ndarray | None:
    """Returns an (N, dim) array of embeddings for the given corpus, using a
    cached copy on disk if it matches the current corpus, else computing
    and caching a fresh one. Returns None if the model isn't available."""
    if not enabled:
        return None

    current_hash = _corpus_hash(corpus)

    if EMBEDDINGS_PATH.exists() and EMBEDDINGS_META_PATH.exists():
        try:
            meta = json.loads(EMBEDDINGS_META_PATH.read_text())
            if meta.get("hash") == current_hash and meta.get("model") == MODEL_NAME:
                return np.load(EMBEDDINGS_PATH)
        except (json.JSONDecodeError, OSError, ValueError):
            pass  # fall through and recompute

    embeddings = _model.encode(corpus, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.asarray(embeddings, dtype=np.float32)

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        np.save(EMBEDDINGS_PATH, embeddings)
        EMBEDDINGS_META_PATH.write_text(
            json.dumps({"hash": current_hash, "model": MODEL_NAME, "count": len(corpus)})
        )
    except OSError:
        pass  # caching is best-effort; still return the embeddings we just computed

    return embeddings


def embed_query(text: str) -> np.ndarray | None:
    if not enabled:
        return None
    vec = _model.encode([text], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)[0]


def cosine_scores(query_vec: np.ndarray, corpus_vecs: np.ndarray) -> np.ndarray:
    """Both inputs are already L2-normalized (normalize_embeddings=True), so
    cosine similarity is just the dot product."""
    return corpus_vecs @ query_vec
