"""
generate_embeddings.py — One-time script to precompute and cache job embeddings.

Run this BEFORE starting the Flask app for the first time to avoid a slow
cold start when the model encodes all jobs.json entries on the first request.

Usage:
    python generate_embeddings.py

This creates job_embeddings.pkl in the same directory.
The Flask app will load this file on startup instead of recomputing.
"""

import os
import json
import pickle
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE       = os.path.join(BASE_DIR, "jobs.json")
EMBEDDINGS_FILE = os.path.join(BASE_DIR, "job_embeddings.pkl")
MODEL_NAME      = "all-MiniLM-L6-v2"


def main():
    # Load jobs
    logger.info(f"Loading jobs from {JOBS_FILE}…")
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    logger.info(f"Loaded {len(jobs)} jobs.")

    # Build combined text for each job
    texts = []
    for job in jobs:
        parts = [
            job.get("title", ""),
            job.get("company", ""),
            job.get("description", ""),
            job.get("skills", ""),
        ]
        texts.append(" ".join(p for p in parts if p).strip())

    # Load model
    logger.info(f"Loading Sentence Transformers model: {MODEL_NAME}…")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    # Encode
    logger.info("Computing embeddings (this may take a moment on first run)…")
    import numpy as np
    embeddings: np.ndarray = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    logger.info(f"Embedding shape: {embeddings.shape}")

    # Save
    with open(EMBEDDINGS_FILE, "wb") as f:
        pickle.dump(embeddings, f)
    logger.info(f"✅ Saved embeddings → {EMBEDDINGS_FILE}")


if __name__ == "__main__":
    main()
