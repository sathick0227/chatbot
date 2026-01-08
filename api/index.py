import os, re, time, csv, json, asyncio
from io import StringIO

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz, process


app = FastAPI(title="Portfolio Chatbot", redirect_slashes=False)

# -----------------------------
# ✅ CORS
# -----------------------------
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://portfolio-latest-henna.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,   # keep False unless using cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# ✅ Load local fallback data.json
# -----------------------------
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data.get("questions", [])
answers = data.get("answers", [])

# -----------------------------
# ✅ Language answers
# -----------------------------
LANGUAGE_ANSWERS = {
    "english": (
        "Yes. He communicates professionally in English and uses it daily in his work "
        "for client meetings, documentation, and technical discussions."
    ),
    "tamil": (
        "Yes. Tamil is his native language, and he communicates fluently in both "
        "personal and professional contexts."
    ),
    "hindi": (
        "He has basic conversational knowledge of Hindi and is continuously improving "
        "his speaking skills."
    ),
    "arabic": (
        "He is actively learning Arabic and continuously improving his proficiency "
        "for professional and daily communication."
    ),
    "languages_overall": (
        "He is fluent in Tamil, professional in English, conversational in Hindi, "
        "and currently learning Arabic."
    ),
}

# -----------------------------
# ✅ Skill answers
# -----------------------------
SKILL_ANSWERS = {
    "react": "Yes. He has strong React/Next.js experience (5+ years), building scalable web apps including banking and enterprise systems.",
    "next": "Yes. He has experience with Next.js for production apps, focusing on performance, routing, SSR/SSG, and scalable UI architecture.",
    "react_native": "Yes. He has React Native experience and has worked on cross-platform mobile apps for Android & iOS.",
    "node": "Yes. He has Node.js experience for APIs, integrations, authentication flows, and backend services.",
    "typescript": "Yes. He uses TypeScript extensively for scalable codebases, better maintainability, and safer refactoring.",
    "aws": "Yes. He has hands-on experience with AWS for deployment, CI/CD, hosting, and scalable infrastructure.",
    "devops": "He has experience with Docker and CI/CD pipelines and follows best practices to ship reliable builds.",
    "security": "He follows OWASP practices, sanitizes inputs, uses secure headers/CSP, and ensures sensitive data is handled safely.",
    "performance": "He optimizes performance via code splitting, lazy loading, caching, list virtualization, and profiling tools.",
    "banking": (
        "Yes. He has strong banking domain experience in Dubai, including work on "
        "large-scale digital banking platforms with focus on secure UI, "
        "API integrations, performance, and enterprise-grade standards."
    ),
}

# -----------------------------
# ✅ Intent rules (FIXED indexes)
# -----------------------------
INTENT_RULES = [
    {"patterns": [r"^\s*(hi|hello|hey)\s*$", r"\bhi\b", r"\bhello\b", r"\bhey\b"], "answer_index": 0},
    {"patterns": [r"\btell about him\b", r"\bwhat about him\b", r"\bwho is sathick\b", r"\bwho are you\b", r"\bintroduce\b"], "answer_index": 3},
    {"patterns": [r"\bcontact\b", r"\bemail\b", r"\bphone\b", r"\breach\b", r"\bget in touch\b", r"\bhow can i contact\b"], "answer_index": 9},
    {"patterns": [r"\bsalary\b", r"\bpackage\b", r"\bctc\b", r"\bexpected salary\b"], "answer_index": 25},

    {"patterns": [r"\bbank\b", r"\bbanking\b", r"\bmashreq\b", r"\bdigital banking\b"], "skill_key": "banking"},

    {"patterns": [r"\breact native\b", r"\brn\b"], "skill_key": "react_native"},
    {"patterns": [r"\bnext\.?js\b", r"\bnextjs\b", r"\bnext\b"], "skill_key": "next"},
    {"patterns": [r"\breact\.?js\b", r"\breactjs\b", r"\breact\b"], "skill_key": "react"},
    {"patterns": [r"\bnode\.?js\b", r"\bnodejs\b", r"\bnode\b", r"\bbackend\b", r"\bapi\b"], "skill_key": "node"},
    {"patterns": [r"\btypescript\b", r"\bts\b"], "skill_key": "typescript"},
    {"patterns": [r"\baws\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\bcloud\b"], "skill_key": "aws"},
    {"patterns": [r"\bdocker\b", r"\bci/cd\b", r"\bpipeline\b", r"\bdevops\b"], "skill_key": "devops"},
    {"patterns": [r"\bxss\b", r"\bsql injection\b", r"\bowasp\b", r"\bcsp\b", r"\bsecurity\b"], "skill_key": "security"},
    {"patterns": [r"\bperformance\b", r"\boptimi[sz]e\b", r"\blazy\b", r"\bcaching\b", r"\bprofiling\b"], "skill_key": "performance"},

    {"patterns": [r"\blanguages?\b", r"\bwhat languages\b", r"\bspoken languages\b", r"\bwhich language\b"], "language_key": "languages_overall"},
    {"patterns": [r"\benglish\b", r"\bcan he speak english\b", r"\benglish fluency\b"], "language_key": "english"},
    {"patterns": [r"\btamil\b", r"\bnative language\b", r"\bmother tongue\b"], "language_key": "tamil"},
    {"patterns": [r"\bhindi\b", r"\bcan he speak hindi\b"], "language_key": "hindi"},
    {"patterns": [r"\barabic\b", r"\bcan he speak arabic\b", r"\blearning arabic\b"], "language_key": "arabic"},
]


def norm(t: str) -> str:
    t = (t or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def detect_intent(q: str):
    q = norm(q)
    for rule in INTENT_RULES:
        if any(re.search(p, q) for p in rule["patterns"]):
            return rule
    return None


class ChatRequest(BaseModel):
    question: str


# -----------------------------
# ✅ Google Sheet Read (CSV) + Cache
# -----------------------------
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "").strip()
CACHE_TTL = int(os.getenv("SHEET_CACHE_TTL", "300"))

_sheet_cache = {"ts": 0, "questions": [], "answers": [], "meta": {}}


def _normalize_headers(fieldnames):
    if not fieldnames:
        return []
    return [re.sub(r"\s+", " ", (h or "").strip().lower()) for h in fieldnames]


async def load_sheet_if_needed(force: bool = False):
    """
    Loads Google Sheet CSV into _sheet_cache.
    Fixes:
      ✅ follow redirects (Google Sheets often returns 302)
      ✅ detect HTML (means not public / wrong URL)
      ✅ accept flexible headers: question/answer (case + spaces)
      ✅ keep meta for debugging
    """
    now = int(time.time())

    if not force and (now - _sheet_cache["ts"] < CACHE_TTL) and _sheet_cache["questions"]:
        return

    _sheet_cache["meta"] = {
        "sheet_url_set": bool(SHEET_CSV_URL),
        "last_error": "",
        "content_type": "",
        "status_code": None,
        "row_count": 0,
        "headers": [],
        "loaded_at": now,
    }

    if not SHEET_CSV_URL:
        _sheet_cache["meta"]["last_error"] = "SHEET_CSV_URL is empty. Set env var on server."
        return

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(SHEET_CSV_URL)
            _sheet_cache["meta"]["status_code"] = r.status_code
            _sheet_cache["meta"]["content_type"] = (r.headers.get("content-type") or "").lower()
            r.raise_for_status()

        # If sheet is not public, Google often returns HTML
        if "text/html" in _sheet_cache["meta"]["content_type"]:
            _sheet_cache["meta"]["last_error"] = (
                "Got HTML instead of CSV. Make the sheet public (Anyone with link: Viewer) "
                "and ensure the URL is a CSV export link."
            )
            return

        reader = csv.DictReader(StringIO(r.text))
        headers = _normalize_headers(reader.fieldnames)
        _sheet_cache["meta"]["headers"] = headers

        # Map flexible header names
        # Accept: question, questions, q | answer, answers, a
        q_key = None
        a_key = None

        # Build original->normalized mapping
        original_fields = reader.fieldnames or []
        norm_map = {orig: re.sub(r"\s+", " ", (orig or "").strip().lower()) for orig in original_fields}

        # Find question column
        for orig, n in norm_map.items():
            if n in ("question", "questions", "q"):
                q_key = orig
                break

        # Find answer column
        for orig, n in norm_map.items():
            if n in ("answer", "answers", "a"):
                a_key = orig
                break

        if not q_key or not a_key:
            _sheet_cache["meta"]["last_error"] = (
                f"CSV headers must include question/answer columns. Found: {original_fields}"
            )
            return

        q_list, a_list = [], []
        for row in reader:
            q = (row.get(q_key) or "").strip()
            a = (row.get(a_key) or "").strip()
            if q and a:
                q_list.append(q)
                a_list.append(a)

        _sheet_cache["ts"] = now
        _sheet_cache["questions"] = q_list
        _sheet_cache["answers"] = a_list
        _sheet_cache["meta"]["row_count"] = len(q_list)

    except Exception as e:
        _sheet_cache["meta"]["last_error"] = str(e)
        # do not raise; keep fallback working
        return


def answer_from_sheet(user_q: str):
    qs = _sheet_cache["questions"]
    ans = _sheet_cache["answers"]
    if not qs:
        return None

    best = process.extractOne(user_q, qs, scorer=fuzz.WRatio)
    if best and best[1] >= 78:
        return ans[best[2]]
    return None


# -----------------------------
# ✅ Logger to Apps Script (logs + missed + telegram from Apps Script)
# -----------------------------
LOG_WEBHOOK_URL = os.getenv("LOG_WEBHOOK_URL", "").strip()


async def send_log(question: str, request: Request, type_: str):
    if not LOG_WEBHOOK_URL:
        return

    payload = {
        "question": question,
        "type": type_,
        "source": "portfolio",
        "ip": request.client.host if request.client else "",
        "ua": request.headers.get("user-agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(LOG_WEBHOOK_URL, json=payload)
    except Exception:
        pass


# -----------------------------
# ✅ Debug endpoints (IMPORTANT)
# -----------------------------
@app.get("/debug/sheet")
async def debug_sheet():
    # Force load to see real status
    await load_sheet_if_needed(force=True)
    return {
        "meta": _sheet_cache.get("meta", {}),
        "cache_count": len(_sheet_cache["questions"]),
        "sample_questions": _sheet_cache["questions"][:5],
    }


# -----------------------------
# ✅ Routes
# -----------------------------
@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api", methods=["GET", "POST", "OPTIONS"])
async def root(request: Request):
    if request.method == "OPTIONS":
        return "OK"

    if request.method == "GET":
        return {"status": "ok", "usage": "POST /api with JSON {question: '...'}"}

    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        return {"error": "Missing question"}

    # ✅ log every request (async)
    asyncio.create_task(send_log(q, request, "log"))

    # 1) Intent
    rule = detect_intent(q)
    if rule:
        if "language_key" in rule:
            return {"answer": LANGUAGE_ANSWERS.get(rule["language_key"], "He can communicate in multiple languages.")}

        if "skill_key" in rule:
            return {"answer": SKILL_ANSWERS.get(rule["skill_key"], "Yes, he has experience in that area.")}

        idx = rule.get("answer_index")
        if idx is not None and 0 <= idx < len(answers):
            return {"answer": answers[idx]}

    # 2) Sheet FAQ (live)
    try:
        await load_sheet_if_needed()
        sheet_ans = answer_from_sheet(q)
        if sheet_ans:
            return {"answer": sheet_ans}
    except Exception:
        # keep fallback working
        pass

    # 3) Local fallback fuzzy match
    best = process.extractOne(q, questions, scorer=fuzz.WRatio)
    if best and best[1] >= 78:
        return {"answer": answers[best[2]]}

    # 4) Missed
    asyncio.create_task(send_log(q, request, "missed"))
    return {"answer": "I don't have an answer for that yet."}
