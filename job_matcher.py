"""
job_matcher.py — AI-powered job matching using Sentence Transformers.

REAL AI components:
  - SentenceTransformer (all-MiniLM-L6-v2): encodes text into 384-dim embeddings
  - cosine_similarity: ranks jobs by semantic relevance to resume/skills

Rule-based fallback (used only if SentenceTransformers unavailable):
  - keyword overlap scoring

Design:
  - Model and dataset embeddings are loaded ONCE at startup (module level)
  - Precomputed embeddings are cached in job_embeddings.pkl for fast startup
  - match_jobs() is the main public API, backward-compatible with existing calls
"""

import os
import json
import pickle
import logging
import re
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE       = os.path.join(_BASE_DIR, "jobs.json")
EMBEDDINGS_FILE = os.path.join(_BASE_DIR, "job_embeddings.pkl")
MODEL_NAME      = "all-MiniLM-L6-v2"

# ── AI Model Loading (once at import time) ─────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity as _cosine_sim

    _model = SentenceTransformer(MODEL_NAME)
    AI_AVAILABLE = True
    logger.info(f"[JobMatcher] ✅ Sentence Transformers model loaded: {MODEL_NAME}")
except Exception as _e:
    _model       = None
    AI_AVAILABLE = False
    logger.warning(f"[JobMatcher] ⚠️  Sentence Transformers unavailable ({_e}). Using keyword fallback.")


# ── Dataset Helpers ────────────────────────────────────────────────────────────
def _load_dataset() -> List[dict]:
    """Load jobs from jobs.json. Returns empty list on failure."""
    try:
        if os.path.exists(JOBS_FILE):
            with open(JOBS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"[JobMatcher] Loaded {len(data)} jobs from {JOBS_FILE}")
            return data
    except Exception as e:
        logger.error(f"[JobMatcher] Failed to load jobs.json: {e}")
    return []


def _job_text(job: dict) -> str:
    """Combine job fields into a single rich text for embedding."""
    parts = [
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", ""),
        job.get("skills", ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _load_or_compute_embeddings(jobs: List[dict]) -> Optional[np.ndarray]:
    """
    Load precomputed embeddings from pickle, or compute + save them.
    Recomputes if the cached count doesn't match the current dataset size.
    """
    if not AI_AVAILABLE or not jobs:
        return None

    # Try loading cached embeddings
    if os.path.exists(EMBEDDINGS_FILE):
        try:
            with open(EMBEDDINGS_FILE, "rb") as f:
                cached: np.ndarray = pickle.load(f)
            if isinstance(cached, np.ndarray) and len(cached) == len(jobs):
                logger.info(f"[JobMatcher] ✅ Loaded {len(cached)} cached embeddings from {EMBEDDINGS_FILE}")
                return cached
            logger.info("[JobMatcher] Cache size mismatch — recomputing embeddings.")
        except Exception as e:
            logger.warning(f"[JobMatcher] Cache load failed: {e} — recomputing.")

    # Compute embeddings
    logger.info(f"[JobMatcher] Computing embeddings for {len(jobs)} dataset jobs…")
    texts      = [_job_text(j) for j in jobs]
    embeddings = _model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )

    # Save for future runs
    try:
        with open(EMBEDDINGS_FILE, "wb") as f:
            pickle.dump(embeddings, f)
        logger.info(f"[JobMatcher] ✅ Embeddings saved → {EMBEDDINGS_FILE}")
    except Exception as e:
        logger.warning(f"[JobMatcher] Could not save embeddings: {e}")

    return embeddings


# ── Startup: Load dataset + precomputed embeddings ─────────────────────────────
DATASET_JOBS       = _load_dataset()
DATASET_EMBEDDINGS = _load_or_compute_embeddings(DATASET_JOBS)


# ── Public API ─────────────────────────────────────────────────────────────────

def match_local_jobs(query_text: str, top_n: int = 5) -> List[dict]:
    """
    ✅ REAL AI: Semantic matching against the precomputed jobs.json dataset.

    Uses SentenceTransformer to encode the query, then ranks all dataset
    jobs by cosine similarity with precomputed embeddings.

    Handles semantic understanding:
      "Worked on APIs"       → Backend Developer
      "Built dashboards"     → Data Analyst
      "Deep learning models" → Machine Learning Engineer

    Args:
        query_text: Resume text or skills string used as the search query.
        top_n:      Number of top matches to return.

    Returns:
        List of job dicts with 'match_score' (float 0–1) added.
    """
    if not DATASET_JOBS:
        logger.warning("[JobMatcher] Dataset is empty.")
        return []

    if not AI_AVAILABLE or DATASET_EMBEDDINGS is None:
        logger.warning("[JobMatcher] AI unavailable — returning first N dataset jobs.")
        return [dict(j, match_score=0.0) for j in DATASET_JOBS[:top_n]]

    query = query_text.strip()
    if not query:
        return [dict(j, match_score=0.0) for j in DATASET_JOBS[:top_n]]

    q_emb  = _model.encode([query], convert_to_numpy=True)
    scores = _cosine_sim(q_emb, DATASET_EMBEDDINGS)[0]

    scored = [
        dict(DATASET_JOBS[i], match_score=round(float(scores[i]), 4))
        for i in range(len(DATASET_JOBS))
    ]
    scored.sort(key=lambda x: x["match_score"], reverse=True)

    logger.info(
        f"[JobMatcher] match_local_jobs: top score={scored[0]['match_score']:.4f}"
        f" job='{scored[0]['title']}'"
    )
    return scored[:top_n]


def match_jobs(
    jobs: List[dict],
    skills: List[str],
    top_n: int = 50,
    resume_text: str = "",
) -> List[dict]:
    """
    ✅ REAL AI: Rank a mixed list of jobs (from APIs or local sources) using
    Sentence Transformers cosine similarity.

    The query is formed from:
      1. resume_text (preferred — full semantic content)
      2. skills list joined as text (fallback)

    Falls back to keyword scoring if Sentence Transformers is unavailable.

    Args:
        jobs:        List of job dicts to rank.
        skills:      User skill keywords (used if resume_text is empty).
        top_n:       Maximum number of results to return.
        resume_text: Full resume text for richer semantic matching.

    Returns:
        Sorted list of job dicts with 'match_score' (float) added.
    """
    if not jobs:
        logger.warning("[JobMatcher] No jobs provided to match_jobs().")
        return []

    # Build the query string
    query = resume_text.strip() if resume_text else " ".join(skills)

    if not query:
        # No query → return jobs with score 0, preserving order
        for job in jobs:
            job["match_score"] = 0.0
        logger.info("[JobMatcher] No query — returning jobs unranked.")
        return jobs[:top_n]

    # ── AI path ───────────────────────────────────────────────────
    if AI_AVAILABLE:
        texts  = [_job_text(j) for j in jobs]
        q_emb  = _model.encode([query], convert_to_numpy=True)
        j_embs = _model.encode(
            texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True
        )
        scores = _cosine_sim(q_emb, j_embs)[0]

        scored = [
            dict(jobs[i], match_score=round(float(scores[i]), 4))
            for i in range(len(jobs))
        ]
        scored.sort(key=lambda x: x["match_score"], reverse=True)

        top_score = scored[0]["match_score"] if scored else 0
        logger.info(
            f"[JobMatcher] AI ranked {len(scored)} jobs. "
            f"Top: '{scored[0]['title']}' ({top_score:.4f})"
        )
        return scored[:top_n]

    # ── Keyword fallback ──────────────────────────────────────────
    logger.info("[JobMatcher] Using keyword fallback scoring.")
    for job in jobs:
        job["match_score"] = _keyword_score(job, skills)
    jobs.sort(key=lambda j: j["match_score"], reverse=True)
    return jobs[:top_n]


# ── Keyword Fallback (rule-based, NOT AI) ─────────────────────────────────────

def _normalize_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower())


def _keyword_score(job: dict, skills: List[str]) -> float:
    """
    Rule-based fallback: keyword overlap between skills and job title/description.
    NOT AI — used only when Sentence Transformers is unavailable.
    """
    title_tokens = set(_normalize_text(job.get("title", "")).split())
    desc_tokens  = set(_normalize_text(job.get("description", "")).split())
    score        = 0.0

    for skill in skills:
        s = _normalize_text(skill)
        if not s:
            continue
        if s in title_tokens:
            score += 2.0
        if s in desc_tokens:
            score += 1.0

    return round(score, 4)


# ── Quick self-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n── match_local_jobs (AI dataset matching) ──")
    results = match_local_jobs("I worked on REST APIs and backend systems using Python", top_n=5)
    for r in results:
        print(f"  [{r['match_score']:.4f}] {r['title']} @ {r['company']}")

    print("\n── match_local_jobs (semantic: dashboards) ──")
    results2 = match_local_jobs("Built interactive dashboards and reports for business insights", top_n=3)
    for r in results2:
        print(f"  [{r['match_score']:.4f}] {r['title']} @ {r['company']}")

    print("\n── match_jobs (API-style jobs) ──")
    sample_jobs = [
        {
            "title": "Python Developer",
            "company": "StartupX",
            "location": "Bangalore",
            "description": "Build REST APIs using Python and Flask. SQL required.",
            "skills": "",
            "apply_link": "https://www.naukri.com/job/1",
            "source": "Adzuna",
        },
        {
            "title": "Marketing Manager",
            "company": "BizCorp",
            "location": "Mumbai",
            "description": "Manage brand campaigns and social media strategy.",
            "skills": "",
            "apply_link": "https://www.naukri.com/job/2",
            "source": "Indeed",
        },
    ]
    ranked = match_jobs(sample_jobs, ["Python", "Flask", "SQL"])
    for r in ranked:
        print(f"  [{r['match_score']:.4f}] {r['title']}")
