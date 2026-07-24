"""
app.py — AI Job Assist Flask Application (Fixed & Upgraded)

Changes from original:
  1. xhtml2pdf replaced with conditional import + HTML fallback for download_resume
  2. PyPDF2 → pypdf (handled in resume_parser.py)
  3. Python 3.9 compatible (no str | None union syntax anywhere)
  4. job_matcher upgraded to Sentence Transformers AI (see job_matcher.py)
  5. /jobs route passes resume_text to match_jobs() for semantic AI matching
  6. Added /ats-gate route (template already existed)
  7. Added @login_required to /jobs and /fraud-detection routes
  8. match_local_jobs() called post-resume-upload to show AI top-5 dataset jobs
"""

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, make_response,
)
import sqlite3, os, random, hashlib, datetime, json, smtplib, io, requests, logging, time
from functools import wraps
from typing import Optional

# ── xhtml2pdf: optional — app will NOT crash if not installed ─────────────────
try:
    from xhtml2pdf import pisa as _pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    _pisa = None
    XHTML2PDF_AVAILABLE = False

from resume_parser import parse_resume
from skill_extractor import extract_skills
from resume_scorer import score_resume
from job_matcher import match_jobs, match_local_jobs
from fraud_detector import FraudDetector

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

EMAIL        = "skillbridge19@gmail.com"
APP_PASSWORD = "woclmsqaetnunykv"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ─── DATABASE ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            otp TEXT,
            otp_expiry TEXT,
            otp_attempts INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            login_time TEXT,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            job_title TEXT,
            company TEXT,
            job_type TEXT,
            salary TEXT,
            apply_link TEXT,
            location TEXT DEFAULT '',
            status TEXT DEFAULT 'Applied',
            reason TEXT,
            applied_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            rating INTEGER NOT NULL,
            message TEXT,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS resume_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ats_score INTEGER,
            role TEXT,
            skills TEXT,
            scored_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


init_db()


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def send_otp(receiver_email: str, otp: str) -> bool:
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL, APP_PASSWORD)
        message = (
            f"Subject: SkillBridge OTP Verification\n\n"
            f"Your OTP is: {otp}\n\nValid for 5 minutes.\n\n"
            f"Do not share this OTP with anyone."
        )
        server.sendmail(EMAIL, receiver_email, message)
        server.quit()
        print(f"✅ OTP sent to {receiver_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("❌ Gmail Auth Failed - Check App Password")
        return False
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


def get_motivation(category: str) -> str:
    quotes = {
        "low_ats":     ["Improve your resume 💪", "Keep learning and upgrading 🚀"],
        "high_ats":    ["Great job! 🎯", "You're ready to apply 🔥"],
        "applied":     ["Application submitted 🌟", "Keep applying 💫"],
        "rejected":    ["Don't give up 💪", "Try again stronger 🔥"],
        "shortlisted": ["You're close 🎯", "Prepare for interview ⭐"],
    }
    return random.choice(quotes.get(category, quotes["applied"]))


def get_ai_feedback(status: str) -> str:
    if status == "Rejected":
        return random.choice([
            "Add more relevant technical skills to your resume.",
            "Include quantifiable achievements in your experience section.",
            "Strengthen your project descriptions with impact metrics.",
            "Add relevant certifications to boost your profile.",
        ])
    elif status == "Shortlisted":
        return "Prepare for the interview! Research the company and practice common questions."
    return "Keep applying to more positions to maximize your chances!"


# ─── INDEX ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ─── REGISTER ─────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form["name"].strip()
        contact  = request.form["contact"].strip()
        password = hash_password(request.form["password"])

        conn = get_db()
        if conn.execute("SELECT * FROM users WHERE contact=?", (contact,)).fetchone():
            conn.close()
            flash("User already exists. Please login.", "error")
            return redirect(url_for("register"))

        otp    = generate_otp()
        expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).isoformat()

        conn.execute(
            "INSERT INTO users (name, contact, password, otp, otp_expiry, otp_attempts, verified) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, contact, password, otp, expiry, 0, 0),
        )
        conn.commit()
        conn.close()

        if "@" in contact:
            success = send_otp(contact, otp)
            if not success:
                print(f"⚠️  OTP (email failed, use this): {otp}")
                flash("Email send failed. Check terminal for OTP.", "warning")
            else:
                flash("OTP sent to your email!", "success")
        else:
            print(f"📱 OTP for {contact}: {otp}")
            flash("OTP printed in terminal.", "info")

        session["pending_contact"] = contact
        return redirect(url_for("verify_otp"))

    return render_template("register.html")


# ─── VERIFY OTP ───────────────────────────────────────────────────────────────
@app.route("/verify-otp", methods=["GET", "POST"])
@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    contact = session.get("pending_contact")
    if not contact:
        return redirect(url_for("register"))

    if request.method == "POST":
        otp_input = request.form["otp"].strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE contact=?", (contact,)).fetchone()

        if not user:
            conn.close()
            return redirect(url_for("register"))

        if datetime.datetime.now() > datetime.datetime.fromisoformat(user["otp_expiry"]):
            conn.close()
            flash("OTP expired. Please register again.", "error")
            return redirect(url_for("register"))

        if user["otp_attempts"] >= 3:
            conn.close()
            flash("Too many wrong attempts. Please register again.", "error")
            return redirect(url_for("register"))

        if otp_input != user["otp"]:
            conn.execute(
                "UPDATE users SET otp_attempts = otp_attempts + 1 WHERE contact=?",
                (contact,),
            )
            conn.commit()
            conn.close()
            flash("Wrong OTP. Try again.", "error")
            return render_template("verify_otp.html")

        conn.execute(
            "UPDATE users SET verified=1, otp=NULL, otp_attempts=0 WHERE contact=?",
            (contact,),
        )
        conn.commit()
        conn.close()

        session.pop("pending_contact", None)
        flash("Account verified successfully! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("verify_otp.html")


# ─── LOGIN ────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        contact  = request.form["contact"].strip()
        password = hash_password(request.form["password"])

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE contact=? AND password=?",
            (contact, password),
        ).fetchone()
        conn.close()

        if not user:
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        if not user["verified"]:
            otp    = generate_otp()
            expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).isoformat()

            conn = get_db()
            conn.execute(
                "UPDATE users SET otp=?, otp_expiry=?, otp_attempts=0 WHERE contact=?",
                (otp, expiry, contact),
            )
            conn.commit()
            conn.close()

            if "@" in contact:
                success = send_otp(contact, otp)
                if not success:
                    print(f"⚠️  OTP (email failed): {otp}")
            else:
                print(f"📱 OTP: {otp}")

            session["pending_contact"] = contact
            flash("Account not verified. New OTP sent!", "warning")
            return redirect(url_for("verify_otp"))

        session["user_id"]  = user["id"]
        session["username"] = user["name"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")


# ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        contact = request.form["contact"].strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE contact=?", (contact,)).fetchone()

        if not user:
            conn.close()
            flash("No account found with this email.", "error")
            return redirect(url_for("forgot_password"))

        otp    = generate_otp()
        expiry = (datetime.datetime.now() + datetime.timedelta(minutes=5)).isoformat()

        conn.execute(
            "UPDATE users SET otp=?, otp_expiry=?, otp_attempts=0 WHERE contact=?",
            (otp, expiry, contact),
        )
        conn.commit()
        conn.close()

        if "@" in contact:
            success = send_otp(contact, otp)
            if not success:
                print(f"⚠️  Reset OTP: {otp}")
                flash("Email failed. Check terminal for OTP.", "warning")
            else:
                flash("OTP sent to your email!", "success")
        else:
            print(f"📱 Reset OTP: {otp}")

        session["reset_contact"] = contact
        return redirect(url_for("reset_password"))

    return render_template("forgot_password.html")


# ─── RESET PASSWORD ───────────────────────────────────────────────────────────
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    contact = session.get("reset_contact")
    if not contact:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        otp_input    = request.form["otp"].strip()
        new_password = hash_password(request.form["password"])

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE contact=?", (contact,)).fetchone()

        if not user:
            conn.close()
            flash("Something went wrong. Try again.", "error")
            return redirect(url_for("forgot_password"))

        if datetime.datetime.now() > datetime.datetime.fromisoformat(user["otp_expiry"]):
            conn.close()
            flash("OTP expired. Try again.", "error")
            return redirect(url_for("forgot_password"))

        if otp_input != user["otp"]:
            conn.close()
            flash("Wrong OTP.", "error")
            return render_template("reset_password.html")

        conn.execute(
            "UPDATE users SET password=?, otp=NULL WHERE contact=?",
            (new_password, contact),
        )
        conn.commit()
        conn.close()

        session.pop("reset_contact", None)
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


# ─── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    conn      = get_db()
    apps      = conn.execute(
        "SELECT * FROM applications WHERE user_id=? ORDER BY applied_date DESC LIMIT 5",
        (session["user_id"],),
    ).fetchall()
    score_row = conn.execute(
        "SELECT * FROM resume_scores WHERE user_id=? ORDER BY scored_at DESC LIMIT 1",
        (session["user_id"],),
    ).fetchone()
    avg_rating = conn.execute("SELECT AVG(rating) as avg FROM feedback").fetchone()
    conn.close()

    ats_score  = score_row["ats_score"] if score_row else None
    motivation = (
        get_motivation("high_ats" if ats_score and ats_score >= 80 else "low_ats")
        if ats_score else None
    )

    return render_template(
        "dashboard.html",
        applications=apps,
        ats_score=ats_score,
        motivation=motivation,
        avg_rating=round(avg_rating["avg"], 1) if avg_rating["avg"] else 0,
    )


# ─── ATS GATE ─────────────────────────────────────────────────────────────────
@app.route("/ats-gate")
@login_required
def ats_gate():
    """
    Gate page shown when a user tries to access jobs without a sufficient ATS score.
    Requires ATS score >= 70 to proceed to job recommendations.
    """
    ats_score = session.get("ats_score")

    # If score is good enough, go straight to jobs
    if ats_score and int(ats_score) >= 70:
        return redirect(url_for("jobs"))

    motivation = get_motivation("low_ats") if ats_score else None

    return render_template("ats_gate.html", ats_score=ats_score, motivation=motivation)


# ─── RESUME UPLOAD ────────────────────────────────────────────────────────────
@app.route("/upload-resume", methods=["GET", "POST"])
@login_required
def upload_resume():
    if request.method == "POST":
        role = request.form.get("role", "IT-General")
        file = request.files.get("resume")

        if not file or file.filename == "":
            flash("Please upload a resume file.", "error")
            return render_template("upload_resume.html")

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ["pdf", "docx"]:
            flash("Only PDF and DOCX files are supported.", "error")
            return render_template("upload_resume.html")

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"], f"resume_{session['user_id']}.{ext}"
        )
        file.save(filepath)

        text = parse_resume(filepath, ext)
        if not text:
            flash("Could not extract text from resume. Try a different file.", "error")
            return render_template("upload_resume.html")

        score_data = score_resume(text, role)
        skills     = extract_skills(text)

        conn = get_db()
        conn.execute(
            "INSERT INTO resume_scores (user_id, ats_score, role, skills) VALUES (?,?,?,?)",
            (session["user_id"], score_data["total"], role, json.dumps(skills)),
        )
        conn.commit()
        conn.close()

        session["ats_score"]   = score_data["total"]
        session["user_skills"] = skills
        session["user_role"]   = role
        # Store up to 2000 chars of resume text for AI semantic job matching
        session["resume_text"] = text[:2000]

        # AI: pre-fetch top 5 semantic matches from local dataset
        query = text[:500] if text else " ".join(skills)
        ai_job_matches = match_local_jobs(query, top_n=5)
        session["ai_job_matches"] = ai_job_matches

        return render_template(
            "ats_result.html",
            score=score_data,
            skills=skills,
            role=role,
            motivation=get_motivation(
                "high_ats" if score_data["total"] >= 60 else "low_ats"
            ),
            ai_job_matches=ai_job_matches,
        )

    return render_template("upload_resume.html")


# ─── RESUME BUILDER ───────────────────────────────────────────────────────────
# ─── RESUME BUILDER ───────────────────────────────────────────────────────────
import os, re
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = os.path.join('static', 'uploads')

@app.route("/build-resume", methods=["GET", "POST"])
@login_required
def build_resume():
    if request.method == "POST":
        skills_raw = request.form.get("skills", "")
        certs_raw  = request.form.get("certifications", "")

        data = {
            "name":                request.form.get("name", ""),
            "email":               request.form.get("email", ""),
            "phone":               request.form.get("phone", ""),
            "linkedin":            request.form.get("linkedin", ""),
            "github":              request.form.get("github", ""),
            "role":                request.form.get("role", ""),
            "skills":              [s.strip() for s in skills_raw.split(",") if s.strip()],
            "certifications":      [c.strip() for c in certs_raw.split(",") if c.strip()],
            "education":           [],
            "projects":            [],
            "internship_title":    "",
            "internship_duration": "",
            "internship_points":   [],
            "photo":               None,
            "template":            request.form.get("template", "template1"),
        }

        # ── Photo Upload ──────────────────────────────────────
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            fname = secure_filename(photo_file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            photo_file.save(os.path.join(UPLOAD_FOLDER, fname))
            data["photo"] = fname

        # ── Education (degree / institution / year / gpa) ─────
        for i in range(1, 5):
            degree      = request.form.get(f"degree_{i}",      "").strip()
            institution = request.form.get(f"institution_{i}", "").strip()
            year        = request.form.get(f"year_{i}",        "").strip()
            gpa         = request.form.get(f"gpa_{i}",         "").strip()
            if degree and institution:
                data["education"].append({
                    "degree": degree, "institution": institution,
                    "year": year, "gpa": gpa
                })

        # ── Projects (title / tech / description → bullets) ───
        for i in range(1, 4):
            title = request.form.get(f"project_title_{i}", "").strip()
            if not title:
                continue
            tech      = request.form.get(f"project_tech_{i}", "").strip()
            user_desc = request.form.get(f"project_desc_{i}", "").strip()
            bullets   = (_parse_to_bullets(user_desc)
                         if user_desc
                         else _generate_project_bullets(title, data["role"], tech))
            data["projects"].append({"title": title, "tech": tech, "description": bullets})

        # ── Internship / Experience ────────────────────────────
        intern_raw   = request.form.get("internship",   "").strip()
        intern_title = request.form.get("intern_title", "").strip()
        intern_start = request.form.get("intern_start", "").strip()
        intern_end   = request.form.get("intern_end",   "").strip()
        if intern_raw:
            data["internship_title"]    = intern_title or "Internship / Work Experience"
            data["internship_duration"] = (
                f"{intern_start} – {intern_end}" if intern_start and intern_end
                else intern_start or intern_end
            )
            data["internship_points"] = _parse_to_bullets(intern_raw)

        # ── AI Objective ───────────────────────────────────────
        data["objective"] = _generate_objective(data["role"], ", ".join(data["skills"]))

        session["built_resume"] = data
        return render_template("resume_output.html", data=data)

    return render_template("resume_form.html")


# ──────────────────────────────────────────────────────────────
#  HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────

def _parse_to_bullets(text: str) -> list:
    """Convert free-form text → clean bullet-point list (max 5)."""
    parts = re.split(r'[\n.;•\-–]+', text)
    action_verbs = ('Developed','Built','Implemented','Optimized','Designed',
                    'Managed','Created','Led','Completed','Worked','Collaborated',
                    'Achieved','Delivered','Streamlined','Established')
    bullets = []
    for p in parts:
        p = p.strip().rstrip('.')
        if len(p) < 6:
            continue
        p = p[0].upper() + p[1:]
        if not any(p.startswith(v) for v in action_verbs):
            p = "Worked on " + p[0].lower() + p[1:]
        bullets.append(p)
        if len(bullets) == 5:
            break
    return bullets or [text.strip()]


def _generate_project_bullets(title: str, role: str, tech: str = "") -> list:
    """Generate 4–5 ATS-friendly bullet points for a project."""
    t = f" ({tech})" if tech else ""
    r = role.lower()

    if any(k in r for k in ["data analyst", "data scientist", "ml engineer", "machine learning", "ai"]):
        return [
            f"Developed {title}{t} to analyse and process large-scale datasets",
            "Implemented data-cleaning pipelines improving data quality by 40%",
            "Built interactive dashboards delivering real-time business insights",
            "Trained predictive model achieving 85%+ accuracy on test data",
            "Deployed solution as REST API enabling seamless third-party integration",
        ]
    if any(k in r for k in ["web developer", "full stack", "frontend", "backend"]):
        return [
            f"Built {title}{t} with fully responsive, cross-browser compatible UI",
            "Developed secure RESTful APIs with JWT-based authentication",
            "Optimised frontend bundle achieving 90+ Google Lighthouse score",
            "Integrated third-party payment and notification APIs",
            "Deployed on cloud infrastructure ensuring 99.9% availability",
        ]
    if any(k in r for k in ["software engineer", "developer"]):
        return [
            f"Engineered {title}{t} following clean-code and SOLID principles",
            "Implemented RESTful microservices handling 1,000+ concurrent requests",
            "Reduced system latency by 30% through algorithmic optimisation",
            "Automated CI/CD pipeline cutting release cycle by 50%",
            "Maintained 90% unit-test coverage for production-grade reliability",
        ]
    if "devops" in r:
        return [
            f"Containerised {title}{t} using Docker and Kubernetes orchestration",
            "Automated infrastructure provisioning reducing setup time by 60%",
            "Configured Prometheus + Grafana monitoring for 99.9% SLA compliance",
            "Enforced IAM policies and secrets management best practices",
            "Reduced cloud expenditure by 25% through right-sizing optimisations",
        ]
    # Default
    return [
        f"Developed {title}{t} to automate and streamline key workflows",
        "Designed intuitive user interface boosting team adoption by 40%",
        "Delivered core features on schedule using agile sprint planning",
        "Collaborated with cross-functional stakeholders to refine requirements",
        "Documented system architecture, APIs, and deployment runbooks",
    ]


def _generate_objective(role: str, skills: str) -> str:
    """Generate a 2–3 line ATS-friendly career objective."""
    sk = (skills[:90] + "…") if len(skills) > 90 else skills
    r  = role.lower()

    if "data analyst" in r:
        return (f"Detail-oriented Data Analyst proficient in {sk}. "
                "Seeking to leverage analytical expertise to uncover actionable insights "
                "and support data-driven decision-making across business functions.")
    if "data scientist" in r or "ml engineer" in r or "machine learning" in r:
        return (f"Motivated ML/Data Science professional skilled in {sk}. "
                "Eager to apply statistical modelling and deep-learning techniques "
                "to solve complex, real-world problems at scale.")
    if "software engineer" in r or "developer" in r:
        return (f"Passionate Software Engineer experienced in {sk}. "
                "Looking to design and deliver scalable, high-quality software "
                "within a collaborative, innovation-driven environment.")
    if "web developer" in r or "full stack" in r:
        return (f"Creative Full Stack Developer proficient in {sk}. "
                "Committed to building fast, accessible, and visually engaging "
                "web applications that deliver exceptional user experiences.")
    if "devops" in r:
        return (f"Results-driven DevOps Engineer skilled in {sk}. "
                "Focused on automating infrastructure, optimising CI/CD pipelines, "
                "and enabling teams to ship reliable software continuously.")
    if "hr" in r:
        return ("People-focused HR professional with expertise in talent acquisition, "
                f"employee engagement, and organisational development. Skilled in {sk}.")
    if "marketing" in r:
        return (f"Creative Marketing professional skilled in {sk}. "
                "Passionate about crafting data-driven campaigns that build brand equity "
                "and deliver measurable ROI.")
    if "finance" in r:
        return (f"Analytical Finance professional proficient in {sk}. "
                "Committed to delivering accurate financial analysis, forecasting, "
                "and strategic insights that support business growth.")
    return (f"Motivated professional targeting the role of {role}, skilled in {sk}. "
            "Eager to contribute meaningfully to organisational goals and grow "
            "through continuous learning and collaboration.")


# ─── DOWNLOAD RESUME ──────────────────────────────────────────────────────────
@app.route("/download-resume")
@login_required
def download_resume():
    data = session.get("built_resume", {})

    if not data:
        flash("No resume data found. Please build your resume first.", "error")
        return redirect(url_for("build_resume"))

    rendered = render_template("resume_template1.html", data=data)

    # ── Try PDF generation with xhtml2pdf ─────────────────────────
    if XHTML2PDF_AVAILABLE:
        try:
            pdf_buffer  = io.BytesIO()
            pisa_status = _pisa.CreatePDF(rendered, dest=pdf_buffer)

            if not pisa_status.err:
                pdf_buffer.seek(0)
                response = make_response(pdf_buffer.read())
                response.headers["Content-Type"]        = "application/pdf"
                response.headers["Content-Disposition"] = "attachment; filename=resume.pdf"
                return response

            logger.warning("[download_resume] xhtml2pdf returned an error — falling back to HTML.")
        except Exception as e:
            logger.warning(f"[download_resume] xhtml2pdf failed: {e} — falling back to HTML.")

    # ── Fallback: return the rendered HTML for download ────────────
    response = make_response(rendered)
    response.headers["Content-Type"]        = "text/html; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=resume.html"
    return response


# ─── FRAUD DETECTION ──────────────────────────────────────────────────────────
_detector = FraudDetector()


@app.route("/fraud-detection", methods=["GET", "POST"])
@login_required
def fraud_detection():
    """
    GET  → Show the blank fraud-check form.
    POST → Run FraudDetector and pass result to template.

    FraudDetector is RULE-BASED (not AI).
    """
    result = None
    form   = {}

    if request.method == "POST":
        company     = request.form.get("company",     "").strip()
        salary      = request.form.get("salary",      "").strip()
        email       = request.form.get("email",       "").strip()
        description = request.form.get("description", "").strip()

        form = {
            "company":     company,
            "salary":      salary,
            "email":       email,
            "description": description,
        }

        try:
            result = _detector.analyze(company, salary, email, description)
            logger.info(
                f"[/fraud-detection] score={result['score']} "
                f"status={result['status']} company='{company}'"
            )
        except Exception as e:
            logger.error(f"[/fraud-detection] Unexpected error: {e}")
            result = {
                "score":        0,
                "status":       "ERROR",
                "safe_points":  [],
                "fraud_points": ["An internal error occurred. Please try again."],
                "google_link":  "#",
                "google_label": "Search unavailable",
            }

    return render_template("fraud.html", result=result, form=form)


# ─── JOB RECOMMENDATIONS ─────────────────────────────────────────────────────

# API Credentials
ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID",  "89bf58e6")
ADZUNA_API_KEY = os.environ.get("ADZUNA_API_KEY", "91eeea7971ea9491a3531ce75e4bb12d")
SERPAPI_KEY    = os.environ.get("SERPAPI_KEY",    "a23bb57be359547fc68fcd4c1b8812906147ef81b7e1d2520a13702064d903e6")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "3811d6e2-ab1e-462b-8b87-8f281763fb8f")

# Normalised job schema
def make_job(title="", company="", location="", description="", apply_link="", source=""):
    return {
        "title":       title.strip(),
        "company":     company.strip(),
        "location":    location.strip(),
        "description": description.strip(),
        "apply_link":  apply_link.strip(),
        "source":      source.strip(),
        "skills":      "",
    }


# ── External API Fetchers ─────────────────────────────────────────────────────
def fetch_adzuna_jobs(query: str, country: str = "in", max_results: int = 20) -> list:
    jobs = []
    try:
        url    = "https://api.adzuna.com/v1/api/jobs/in/search/1"
        params = {
            "app_id":           ADZUNA_APP_ID,
            "app_key":          ADZUNA_API_KEY,
            "results_per_page": max_results,
            "what":             query,
            "where":            "India",
            "content-type":     "application/json",
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        for item in data.get("results", []):
            jobs.append(make_job(
                title       = item.get("title", ""),
                company     = item.get("company", {}).get("display_name", "Unknown"),
                location    = item.get("location", {}).get("display_name", "India"),
                description = item.get("description", ""),
                apply_link  = item.get("redirect_url", ""),
                source      = "Adzuna",
            ))
        logger.info(f"[Adzuna] Fetched {len(jobs)} jobs for query: '{query}'")
    except requests.exceptions.Timeout:
        logger.warning("[Adzuna] Request timed out.")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"[Adzuna] HTTP error: {e}")
    except Exception as e:
        logger.error(f"[Adzuna] Unexpected error: {e}")
    return jobs


def fetch_indeed_jobs(query: str, max_results: int = 20) -> list:
    jobs = []
    try:
        url    = "https://serpapi.com/search"
        params = {
            "engine":  "indeed",
            "q":       query,
            "l":       "India",
            "api_key": SERPAPI_KEY,
            "num":     max_results,
        }
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        for item in data.get("jobs_results", []):
            apply_link = item.get("link") or item.get("related_links", [{}])[0].get("link", "")
            jobs.append(make_job(
                title       = item.get("title", ""),
                company     = item.get("company_name", "Unknown"),
                location    = item.get("location", "India"),
                description = item.get("snippet", ""),
                apply_link  = apply_link,
                source      = "Indeed",
            ))
        logger.info(f"[Indeed/SerpAPI] Fetched {len(jobs)} jobs for query: '{query}'")
    except requests.exceptions.Timeout:
        logger.warning("[Indeed/SerpAPI] Request timed out.")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"[Indeed/SerpAPI] HTTP error: {e}")
    except Exception as e:
        logger.error(f"[Indeed/SerpAPI] Unexpected error: {e}")
    return jobs


def fetch_jooble_jobs(query: str, max_results: int = 20) -> list:
    jobs = []
    try:
        url     = f"https://jooble.org/api/{JOOBLE_API_KEY}"
        payload = {
            "keywords":    query,
            "location":    "India",
            "page":        "1",
            "ResultOnPage": max_results,
        }
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()

        for item in data.get("jobs", []):
            jobs.append(make_job(
                title       = item.get("title", ""),
                company     = item.get("company", "Unknown"),
                location    = item.get("location", "India"),
                description = item.get("snippet", ""),
                apply_link  = item.get("link", ""),
                source      = "Jooble",
            ))
        logger.info(f"[Jooble] Fetched {len(jobs)} jobs for query: '{query}'")
    except requests.exceptions.Timeout:
        logger.warning("[Jooble] Request timed out.")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"[Jooble] HTTP error: {e}")
    except Exception as e:
        logger.error(f"[Jooble] Unexpected error: {e}")
    return jobs


# ── Pipeline Helpers ──────────────────────────────────────────────────────────
BLOCKED_DOMAINS = {"example.com", "example.org", "example.net", "localhost"}


def is_valid_job(job: dict) -> bool:
    from urllib.parse import urlparse
    link  = job.get("apply_link", "").strip()
    title = job.get("title", "").strip()
    if not title or not link or link == "#":
        return False
    try:
        domain = urlparse(link).netloc.lower().replace("www.", "")
        if domain in BLOCKED_DOMAINS:
            return False
    except Exception:
        return False
    return True


def deduplicate_jobs(jobs: list) -> list:
    seen   = set()
    unique = []
    for job in jobs:
        key = (job.get("title", "").lower(), job.get("company", "").lower())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def aggregate_jobs(user_skills: list, query: str) -> list:
    start = time.time()

    adzuna_jobs = fetch_adzuna_jobs(query)
    indeed_jobs = fetch_indeed_jobs(query)
    jooble_jobs = fetch_jooble_jobs(query)

    # Merge with local dataset jobs (from jobs.json, already in job_matcher)
    from job_matcher import DATASET_JOBS
    local = [dict(j, source=j.get("source", "Dataset")) for j in DATASET_JOBS]

    all_jobs    = adzuna_jobs + indeed_jobs + jooble_jobs + local
    valid_jobs  = [j for j in all_jobs if is_valid_job(j)]
    unique_jobs = deduplicate_jobs(valid_jobs)

    # AI-based ranking using resume text if available
    resume_text = session.get("resume_text", "")
    ranked_jobs = match_jobs(unique_jobs, user_skills, resume_text=resume_text)

    elapsed = round(time.time() - start, 2)
    logger.info(
        f"[Aggregator] Total: {len(all_jobs)} → Valid: {len(valid_jobs)} → "
        f"Unique: {len(unique_jobs)} → Ranked: {len(ranked_jobs)} | Time: {elapsed}s"
    )
    return ranked_jobs


# ─── JOBS ROUTE ───────────────────────────────────────────────────────────────
@app.route("/jobs", methods=["GET", "POST"])
@login_required
def jobs():
    """
    Job recommendations page.

    - Uses Sentence Transformers (AI) to rank jobs semantically.
    - If resume_text is in session, uses full semantic matching.
    - Falls back to skills-based query if no resume uploaded.
    - ATS gate: redirects to /ats-gate if score < 70 and no skills provided.
    """
    job_list      = []
    api_available = False
    user_skills   = session.get("user_skills", [])
    resume_text   = session.get("resume_text", "")

    # Check ATS gate (only enforce if user has uploaded resume and failed)
    ats_score = session.get("ats_score")
    if ats_score is not None and int(ats_score) < 70 and not user_skills:
        return redirect(url_for("ats_gate"))

    if request.method == "POST":
        skills_input = request.form.get("skills", "").strip()
        if skills_input:
            user_skills = [s.strip() for s in skills_input.split(",") if s.strip()]

    if user_skills or resume_text:
        query       = " ".join(user_skills[:5]) if user_skills else resume_text[:100]
        adzuna      = fetch_adzuna_jobs(query)
        indeed      = fetch_indeed_jobs(query)
        jooble      = fetch_jooble_jobs(query)
        api_available = len(adzuna + indeed + jooble) > 0

        # Include local dataset jobs
        from job_matcher import DATASET_JOBS
        local       = [dict(j, source=j.get("source", "Dataset")) for j in DATASET_JOBS]
        all_jobs    = adzuna + indeed + jooble + local
        valid_jobs  = [j for j in all_jobs if is_valid_job(j)]
        unique_jobs = deduplicate_jobs(valid_jobs)

        # ✅ AI RANKING: Sentence Transformers cosine similarity
        job_list = match_jobs(unique_jobs, user_skills, resume_text=resume_text)

    return render_template(
        "jobs.html",
        jobs=job_list,
        skills=", ".join(user_skills),
        api_available=api_available,
    )


@app.route("/api/jobs", methods=["GET"])
@login_required
def api_jobs():
    """
    JSON API endpoint for job matching.
    Usage: GET /api/jobs?skills=Python,Flask&query=developer
    """
    skills_param = request.args.get("skills", "")
    query        = request.args.get("query", skills_param)
    user_skills  = [s.strip() for s in skills_param.split(",") if s.strip()]

    if not user_skills:
        return jsonify({"error": "Provide at least one skill via ?skills="}), 400

    job_list = aggregate_jobs(user_skills, query)
    return jsonify({"count": len(job_list), "jobs": job_list})


# ─── APPLY ────────────────────────────────────────────────────────────────────
@app.route("/apply", methods=["GET", "POST"])
@login_required
def apply():
    from urllib.parse import urlparse

    job_title  = request.args.get("title", "")
    company    = request.args.get("company", "")
    apply_link = request.args.get("link", "")
    salary     = request.args.get("salary", "N/A")
    job_type   = request.args.get("job_type", "Full-time")
    location   = request.args.get("location", "")

    parsed = urlparse(apply_link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return redirect(url_for("dashboard"))

    try:
        conn     = get_db()
        existing = conn.execute(
            "SELECT id FROM applications WHERE user_id = ? AND job_title = ? AND company = ?",
            (session["user_id"], job_title, company),
        ).fetchone()

        if not existing:
            conn.execute(
                """
                INSERT INTO applications
                (user_id, job_title, company, salary, job_type, apply_link, location, status, applied_date, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Applied', datetime('now'), 'Applied via AI Job Assist')
                """,
                (session["user_id"], job_title, company, salary, job_type, apply_link, location),
            )
            conn.commit()
    finally:
        conn.close()

    return redirect(apply_link)


# ─── APPLICATIONS ─────────────────────────────────────────────────────────────
@app.route("/applications")
@login_required
def applications():
    conn = get_db()
    apps = conn.execute(
        "SELECT * FROM applications WHERE user_id=? ORDER BY applied_date DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    statuses = []
    for app_row in apps:
        if app_row["status"] == "Applied":
            rand = random.random()
            if rand < 0.3:
                new_status = "Shortlisted"
            elif rand < 0.5:
                new_status = "Rejected"
            else:
                new_status = "Applied"
        else:
            new_status = app_row["status"]

        statuses.append({
            "id":           app_row["id"],
            "job_title":    app_row["job_title"],
            "company":      app_row["company"],
            "job_type":     app_row["job_type"],
            "salary":       app_row["salary"],
            "apply_link":   app_row["apply_link"],
            "location":     app_row["location"] or "",
            "status":       new_status,
            "applied_date": app_row["applied_date"],
            "motivation":   get_motivation(
                new_status.lower()
                if new_status.lower() in ["shortlisted", "rejected"]
                else "applied"
            ),
            "ai_feedback": get_ai_feedback(new_status),
        })

    return render_template("applications.html", applications=statuses)


# ─── FEEDBACK ─────────────────────────────────────────────────────────────────
@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    conn = get_db()

    if request.method == "POST":
        rating  = request.form.get("rating")
        message = request.form.get("message", "").strip()

        if not rating:
            conn.close()
            flash("Rating is required!", "error")
            return redirect(url_for("feedback"))

        conn.execute(
            "INSERT INTO feedback (user_id, rating, message) VALUES (?,?,?)",
            (session["user_id"], int(rating), message),
        )
        conn.commit()
        flash("Thank you for your feedback! 🌟", "success")

    reviews = conn.execute("""
        SELECT f.*, u.name FROM feedback f
        JOIN users u ON f.user_id = u.id
        ORDER BY f.submitted_at DESC LIMIT 10
    """).fetchall()
    avg = conn.execute("SELECT AVG(rating) as avg FROM feedback").fetchone()
    conn.close()

    return render_template(
        "feedback.html",
        reviews=reviews,
        avg_rating=round(avg["avg"], 1) if avg["avg"] else 0,
    )


# ─── LOGOUT ───────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ─── RUN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
