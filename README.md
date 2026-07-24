# AI Job Assist — Fixed & Upgraded

A Flask-based job recommendation platform with **real AI** (Sentence Transformers)
for semantic job matching, fraud detection, resume ATS scoring, and resume builder.

---

## What Was Fixed

| Issue | Fix Applied |
|---|---|
| `from xhtml2pdf import pisa` crashing on import | Made optional with `try/except`; app falls back to HTML download |
| `PyPDF2` (deprecated) in `resume_parser.py` | Replaced with `pypdf` |
| `str \| None` union syntax (Python 3.10+ only) in `fraud_detector.py` | Changed to `Optional[str]` (Python 3.9 compatible) |
| Job matching was keyword/rule-based | Replaced with **Sentence Transformers** (`all-MiniLM-L6-v2`) cosine similarity |
| Missing `/ats-gate` route (template existed) | Route added with correct gate logic (score < 70 → gate) |
| `/jobs` and `/fraud-detection` missing `@login_required` | Decorator added |
| `match_jobs()` recomputed embeddings on every request | Dataset embeddings precomputed once at startup, cached in `job_embeddings.pkl` |
| No job dataset for AI matching | `jobs.json` with 40 diverse, richly described jobs created |

---

## AI vs Rule-Based Classification

| Component | Type | Technology |
|---|---|---|
| **Job Matching** | ✅ **Real AI** | Sentence Transformers `all-MiniLM-L6-v2`, cosine similarity |
| Resume ATS Scoring | Rule-based | Keyword/section heuristics |
| Skill Extraction | Rule-based | String matching against skill list |
| Fraud Detection | Rule-based | Pattern matching, salary cap heuristics |
| Resume Builder | Rule-based | Template string generation |

---

## Installation

```bash
# 1. Clone / unzip the project
cd project/

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Install all dependencies
pip install flask pypdf python-docx sentence-transformers scikit-learn numpy pandas requests

# 4. (Optional but recommended) Pre-generate job embeddings for fast startup
python generate_embeddings.py

# 5. Run the app
python app.py
```

The app will be available at: **http://127.0.0.1:5000**

---

## Project Structure

```
project/
├── app.py                   # Main Flask app (fixed)
├── job_matcher.py           # ✅ AI job matching — Sentence Transformers
├── resume_parser.py         # Fixed: pypdf instead of PyPDF2
├── resume_scorer.py         # Rule-based ATS scoring (unchanged)
├── skill_extractor.py       # Rule-based skill extraction (unchanged)
├── fraud_detector.py        # Fixed: Python 3.9 compatible type hints
├── generate_embeddings.py   # One-time embedding precomputation script
├── jobs.json                # 40-job dataset for AI semantic matching
├── job_embeddings.pkl       # Auto-generated on first run (cached embeddings)
├── database.db              # SQLite database (auto-created)
├── requirements.txt         # Updated dependencies
├── static/
│   ├── css/main.css
│   └── uploads/
└── templates/               # All HTML templates (unchanged)
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── upload_resume.html
    ├── ats_result.html
    ├── ats_gate.html
    ├── jobs.html
    ├── fraud.html
    └── ...
```

---

## How AI Job Matching Works

1. **Resume Upload** → text extracted → stored in session
2. **Embeddings** → `all-MiniLM-L6-v2` encodes resume text into a 384-dim vector
3. **Dataset** → `jobs.json` embeddings precomputed once and cached in `job_embeddings.pkl`
4. **Ranking** → cosine similarity between resume embedding and each job embedding
5. **Results** → top 5 semantically relevant jobs returned

**Semantic examples (no keywords needed):**
- *"Worked on APIs and backend systems"* → Python Backend Developer ✓
- *"Built dashboards and reports"* → Data Analyst ✓
- *"Deep learning models for NLP"* → AI/NLP Engineer ✓
- *"Designed user interfaces in Figma"* → UI/UX Designer ✓

---

## Environment Variables (Optional)

```bash
SECRET_KEY=your-secret-key
ADZUNA_APP_ID=your-id
ADZUNA_API_KEY=your-key
SERPAPI_KEY=your-key
JOOBLE_API_KEY=your-key
```
