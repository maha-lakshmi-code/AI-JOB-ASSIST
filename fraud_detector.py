"""
fraud_detector.py — Rule-based fraud detection for job postings.

CLASSIFICATION: This is entirely RULE-BASED logic.
No machine learning or AI models are used here.
All decisions are based on hand-crafted heuristic rules.

Python 3.9 compatible (uses Optional[] instead of X | None union syntax).
"""

import re
import urllib.parse
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration Constants
# ──────────────────────────────────────────────

# Personal / free email providers → suspicious
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.in", "hotmail.com", "outlook.com",
    "rediffmail.com", "live.com", "icloud.com", "aol.com", "protonmail.com",
    "ymail.com", "mail.com", "inbox.com", "zoho.com", "gmx.com",
}

# Known legitimate corporate domains → bonus trust points
TRUSTED_CORPORATE_DOMAINS = {
    "tcs.com", "infosys.com", "wipro.com", "hcl.com", "accenture.com",
    "ibm.com", "microsoft.com", "google.com", "amazon.com", "flipkart.com",
    "cognizant.com", "capgemini.com", "deloitte.com", "pwc.com", "ey.com",
    "kpmg.com", "oracle.com", "sap.com", "salesforce.com", "adobe.com",
}

# Scam / fraud trigger keywords and their individual score contributions
FRAUD_KEYWORDS = {
    "registration fee":         25,
    "payment required":         25,
    "pay to apply":             25,
    "deposit required":         25,
    "processing fee":           20,
    "earn money fast":          20,
    "make money fast":          20,
    "work from home no experience": 18,
    "earn from home":           18,
    "unlimited income":         18,
    "guaranteed income":        15,
    "urgent hiring":            12,
    "immediate joining":        10,
    "limited slots":            12,
    "limited seats":            12,
    "hurry apply now":          12,
    "no experience needed":     10,
    "no experience required":   10,
    "no qualification":         10,
    "100% job guarantee":       15,
    "job guarantee":            12,
    "part time earn":           10,
    "daily payment":            12,
    "weekly payment":            8,
    "work from mobile":         12,
    "work from phone":          12,
    "free training":             8,
    "be your own boss":         10,
    "passive income":           10,
    "refer and earn":           10,
    "multi level":              12,
    "mlm":                      15,
    "direct selling":            8,
    "easy money":               15,
    "home based job":            8,
    "fresher earn":              8,
}

# Jobs typically associated with inflated salary scams
# Maps keyword → (reasonable_max_monthly_inr, job_label)
LOW_SKILL_JOB_SALARY_CAPS = {
    "data entry":   (25_000,  "Data Entry"),
    "typing job":   (20_000,  "Typing Job"),
    "form filling": (15_000,  "Form Filling"),
    "copy paste":   (15_000,  "Copy-Paste Job"),
    "simple task":  (20_000,  "Simple Task"),
    "easy job":     (20_000,  "Easy Job"),
    "home based":   (25_000,  "Home Based"),
    "part time":    (30_000,  "Part-Time"),
    "delivery":     (30_000,  "Delivery"),
    "packing":      (20_000,  "Packing Job"),
    "survey":       (20_000,  "Survey Job"),
    "telecaller":   (30_000,  "Telecaller"),
    "receptionist": (35_000,  "Receptionist"),
}

# Score thresholds
THRESHOLD_SAFE       = 30
THRESHOLD_SUSPICIOUS = 60


# ──────────────────────────────────────────────
# Helper Utilities
# ──────────────────────────────────────────────

def _clean(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", str(text).lower().strip())


def _extract_salary_number(salary_str: str) -> Optional[float]:
    """
    Extract the first numeric value from a salary string.
    Handles formats: "50000", "50,000", "50k", "1.5 lakh", "50000/month"
    Returns value in raw units (not normalised yet).
    """
    s = _clean(salary_str)

    # Handle "lakh" / "lac" — convert to absolute
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", s)
    if lakh_match:
        return float(lakh_match.group(1)) * 100_000

    # Handle "k" shorthand
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", s)
    if k_match:
        return float(k_match.group(1)) * 1_000

    # Handle plain numbers (strip commas)
    plain = re.sub(r"[,_]", "", s)
    num_match = re.search(r"\d+(?:\.\d+)?", plain)
    if num_match:
        return float(num_match.group())

    return None


def _is_annual_salary(salary_str: str) -> bool:
    """Detect if the salary string mentions per-year / annual / CTC."""
    s = _clean(salary_str)
    return bool(re.search(r"\b(per year|per annum|p\.?a\.?|annual|ctc|yearly)\b", s))


def _get_email_domain(email: str) -> Optional[str]:
    """Return the domain part of an email, or None if invalid."""
    email = _clean(email)
    match = re.match(r"^[\w.+\-]+@([\w.\-]+\.[a-z]{2,})$", email)
    return match.group(1) if match else None


def _build_google_link(company: str) -> str:
    """Build a Google search URL for the company name."""
    query = urllib.parse.quote_plus(f"{company} company India official site")
    return f"https://www.google.com/search?q={query}"


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


# ──────────────────────────────────────────────
# FraudDetector Class
# ──────────────────────────────────────────────

class FraudDetector:
    """
    Rule-based fraud detection for job postings.

    CLASSIFICATION: Rule-based only. NOT AI / ML.

    Usage:
        detector = FraudDetector()
        result   = detector.analyze(company, salary, email, description)
    """

    def analyze(
        self,
        company:     str,
        salary:      str,
        email:       str,
        description: str,
    ) -> dict:
        """
        Run all detection checks and return a structured result dict.

        Returns:
        {
            "score":        int  (0–100),
            "status":       str  ("SAFE" | "SUSPICIOUS" | "FRAUD"),
            "safe_points":  list[str],
            "fraud_points": list[str],
            "google_link":  str,
            "google_label": str,
        }
        """
        score        = 0
        safe_points: List[str]  = []
        fraud_points: List[str] = []

        # Sanitise inputs
        company     = str(company     or "").strip()
        salary      = str(salary      or "").strip()
        email       = str(email       or "").strip()
        description = str(description or "").strip()

        # ── Run each check ──
        s, sp, fp = self._check_company(company)
        score += s; safe_points += sp; fraud_points += fp

        s, sp, fp = self._check_email(email)
        score += s; safe_points += sp; fraud_points += fp

        s, sp, fp = self._check_salary(salary, description)
        score += s; safe_points += sp; fraud_points += fp

        s, sp, fp = self._check_keywords(description)
        score += s; safe_points += sp; fraud_points += fp

        s, sp, fp = self._check_description_quality(description)
        score += s; safe_points += sp; fraud_points += fp

        # ── Final score + status ──
        score  = _clamp(score)
        status = self._score_to_status(score)

        # ── Google search link ──
        if company:
            google_link  = _build_google_link(company)
            google_label = f'Search "{company}" on Google'
        else:
            google_link  = "https://www.google.com/search?q=verify+company+India"
            google_label = "Company name missing — verify manually"

        logger.info(
            f"[FraudDetector] score={score} status={status} "
            f"safe={len(safe_points)} fraud={len(fraud_points)}"
        )

        return {
            "score":        score,
            "status":       status,
            "safe_points":  safe_points,
            "fraud_points": fraud_points,
            "google_link":  google_link,
            "google_label": google_label,
        }

    # ──────────────────────────────────────────
    # Check 1 — Company Name
    # ──────────────────────────────────────────
    def _check_company(self, company: str) -> Tuple[int, List[str], List[str]]:
        score = 0
        safe: List[str]  = []
        fraud: List[str] = []

        if not company:
            score += 20
            fraud.append("Company name is missing — a major red flag")
            return score, safe, fraud

        cl = _clean(company)

        if len(company) < 3:
            score += 15
            fraud.append(f'Company name "{company}" is suspiciously short or incomplete')
            return score, safe, fraud

        vowels = sum(1 for c in cl if c in "aeiou")
        if len(cl) > 5 and vowels == 0:
            score += 15
            fraud.append(f'Company name "{company}" appears fake or randomly generated')
        else:
            safe.append(f'Company name "{company}" appears plausible')

        scam_name_patterns = [
            r"\beasy\s*(job|earn|money)\b",
            r"\bwork\s*from\s*home\s*pvt\b",
            r"\bhome\s*based\s*(pvt|llc|inc)\b",
            r"\bonline\s*earn\b",
            r"\bfreelance\s*pvt\b",
        ]
        for pat in scam_name_patterns:
            if re.search(pat, cl):
                score += 12
                fraud.append(f'Company name "{company}" matches common scam naming patterns')
                break

        return score, safe, fraud

    # ──────────────────────────────────────────
    # Check 2 — Email Address
    # ──────────────────────────────────────────
    def _check_email(self, email: str) -> Tuple[int, List[str], List[str]]:
        score = 0
        safe: List[str]  = []
        fraud: List[str] = []

        if not email:
            score += 15
            fraud.append("No contact email provided — legitimate companies always share official contact")
            return score, safe, fraud

        domain = _get_email_domain(email)

        if domain is None:
            score += 15
            fraud.append(f'"{email}" is not a valid email address format')
            return score, safe, fraud

        if domain in TRUSTED_CORPORATE_DOMAINS:
            score -= 5
            safe.append(f'Email domain "@{domain}" is a verified corporate domain ✔')

        elif domain in PERSONAL_EMAIL_DOMAINS:
            score += 20
            fraud.append(
                f'"{email}" uses a free personal email (@{domain}) — '
                "legitimate companies use official domain emails"
            )

        else:
            safe.append(
                f'Email uses a custom domain "@{domain}" — '
                "verify that this matches the company website"
            )

        return score, safe, fraud

    # ──────────────────────────────────────────
    # Check 3 — Salary Analysis
    # ──────────────────────────────────────────
    def _check_salary(self, salary: str, description: str) -> Tuple[int, List[str], List[str]]:
        score = 0
        safe: List[str]  = []
        fraud: List[str] = []

        if not salary:
            score += 8
            fraud.append("No salary information provided — reputable postings disclose compensation")
            return score, safe, fraud

        amount = _extract_salary_number(salary)

        if amount is None:
            score += 5
            fraud.append(f'Salary "{salary}" is vague or unreadable — unclear compensation is a warning sign')
            return score, safe, fraud

        is_annual = _is_annual_salary(salary)
        monthly   = (amount / 12) if is_annual else amount

        desc_lower = _clean(description)

        flagged = False
        for keyword, (cap, label) in LOW_SKILL_JOB_SALARY_CAPS.items():
            if keyword in desc_lower or keyword in _clean(salary):
                if monthly > cap:
                    ratio = monthly / cap
                    if ratio >= 5:
                        pts   = 30
                        level = "extremely"
                    elif ratio >= 3:
                        pts   = 22
                        level = "very"
                    elif ratio >= 2:
                        pts   = 15
                        level = "unusually"
                    else:
                        pts   = 8
                        level = "slightly"

                    score += pts
                    fraud.append(
                        f"Salary ₹{int(monthly):,}/month is {level} high "
                        f"for a {label} role (typical max ≈ ₹{cap:,}/month)"
                    )
                    flagged = True
                else:
                    safe.append(
                        f"Salary appears realistic for a {label} role "
                        f"(≈ ₹{int(monthly):,}/month)"
                    )
                    flagged = True
                break

        if not flagged:
            if monthly > 500_000:
                score += 25
                fraud.append(
                    f"Salary ₹{int(monthly):,}/month (₹{int(monthly * 12):,}/year) "
                    "is unrealistically high — verify carefully"
                )
            elif monthly > 200_000:
                score += 10
                fraud.append(
                    f"Salary ₹{int(monthly):,}/month is on the high end — "
                    "confirm role seniority before applying"
                )
            elif 15_000 <= monthly <= 150_000:
                safe.append(
                    f"Salary ₹{int(monthly):,}/month is within a realistic market range"
                )
            elif monthly < 5_000:
                score += 10
                fraud.append(
                    f"Salary ₹{int(monthly):,}/month is extremely low — "
                    "possible unpaid or exploitative role"
                )

        return score, safe, fraud

    # ──────────────────────────────────────────
    # Check 4 — Keyword Scanning
    # ──────────────────────────────────────────
    def _check_keywords(self, description: str) -> Tuple[int, List[str], List[str]]:
        score = 0
        safe: List[str]  = []
        fraud: List[str] = []

        if not description:
            return score, safe, fraud

        dl    = _clean(description)
        found = {}

        for kw, pts in FRAUD_KEYWORDS.items():
            if kw in dl:
                found[kw] = pts

        if not found:
            safe.append("No scam or urgency keywords detected in the job description")
        else:
            for kw, pts in found.items():
                capped = min(pts, 20)
                score += capped
                fraud.append(f'Scam keyword detected: "{kw}"')

        return score, safe, fraud

    # ──────────────────────────────────────────
    # Check 5 — Description Quality
    # ──────────────────────────────────────────
    def _check_description_quality(self, description: str) -> Tuple[int, List[str], List[str]]:
        score = 0
        safe: List[str]  = []
        fraud: List[str] = []

        if not description:
            score += 20
            fraud.append("Job description is completely missing — all legitimate postings describe the role")
            return score, safe, fraud

        word_count = len(description.split())
        dl         = _clean(description)

        if word_count < 15:
            score += 18
            fraud.append(
                f"Description is extremely short ({word_count} words) — "
                "legitimate postings clearly describe responsibilities and requirements"
            )
        elif word_count < 40:
            score += 10
            fraud.append(
                f"Description is very brief ({word_count} words) — "
                "a real job posting should detail role, skills, and expectations"
            )
        elif word_count >= 80:
            safe.append(
                f"Description is detailed ({word_count} words) — "
                "well-written descriptions indicate a more credible posting"
            )
        else:
            safe.append(f"Description has adequate length ({word_count} words)")

        role_signals = [
            "responsibilities", "requirements", "qualification", "experience",
            "skills", "role", "duties", "position", "candidate", "team",
            "reporting", "manage", "develop", "analyse", "communicate",
            "coordinate", "support", "deliver", "degree", "graduate",
        ]
        found_signals = [w for w in role_signals if w in dl]

        if len(found_signals) >= 4:
            safe.append(
                f"Description mentions professional role indicators "
                f"({', '.join(found_signals[:4])}…) — adds credibility"
            )
        elif len(found_signals) == 0 and word_count >= 15:
            score += 12
            fraud.append(
                "Description lacks any professional role indicators "
                "(responsibilities, skills, qualifications, etc.)"
            )
        elif len(found_signals) < 2 and word_count >= 15:
            score += 6
            fraud.append(
                "Description has very little role clarity — "
                "no mention of responsibilities or requirements"
            )

        upper_words = sum(1 for w in description.split() if w.isupper() and len(w) > 2)
        if upper_words > 5:
            score += 8
            fraud.append(
                f"Description contains {upper_words} ALL-CAPS words — "
                "a common pattern in scam postings"
            )

        exclamations = description.count("!")
        if exclamations >= 4:
            score += 6
            fraud.append(
                f"Description uses {exclamations} exclamation marks — "
                "over-hyped language is typical of scam postings"
            )

        return score, safe, fraud

    # ──────────────────────────────────────────
    # Status Label
    # ──────────────────────────────────────────
    @staticmethod
    def _score_to_status(score: int) -> str:
        if score <= THRESHOLD_SAFE:
            return "SAFE"
        elif score <= THRESHOLD_SUSPICIOUS:
            return "SUSPICIOUS"
        else:
            return "FRAUD"


# ──────────────────────────────────────────────
# Quick CLI test
# ──────────────────────────────────────────────
if __name__ == "__main__":
    detector = FraudDetector()

    tests = [
        {
            "label":       "LEGITIMATE JOB",
            "company":     "Infosys Limited",
            "salary":      "60000 per month",
            "email":       "hr@infosys.com",
            "description": (
                "We are looking for a Python developer with 2+ years of experience. "
                "Responsibilities include developing REST APIs, writing unit tests, "
                "collaborating with cross-functional teams, and delivering features on time. "
                "Requirements: strong Python skills, knowledge of Flask or Django, "
                "good communication skills. B.Tech/MCA preferred."
            ),
        },
        {
            "label":       "SCAM JOB",
            "company":     "Easy Earn Pvt Ltd",
            "salary":      "75000/month",
            "email":       "hr@gmail.com",
            "description": (
                "URGENT HIRING!!! Earn money fast from home!!! "
                "No experience needed. Limited slots available. "
                "Registration fee of ₹500 required. Daily payment."
            ),
        },
    ]

    for t in tests:
        print(f"\n{'=' * 60}")
        print(f"  TEST: {t['label']}")
        print(f"{'=' * 60}")
        result = detector.analyze(t["company"], t["salary"], t["email"], t["description"])
        print(f"  Score  : {result['score']}")
        print(f"  Status : {result['status']}")
        print(f"  Safe   : {result['safe_points']}")
        print(f"  Fraud  : {result['fraud_points']}")
