from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz, process
import json, os, re, time, csv, asyncio
from io import StringIO
import httpx

app = FastAPI(title="Portfolio Chatbot", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://portfolio-latest-henna.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Load data.json from repo root (still used for fallback fuzzy matching)
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
answers = data["answers"]

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
        "large-scale digital banking platforms at Mashreq Bank with focus on secure UI, "
        "API integrations, performance, and enterprise-grade standards."
    ),
}

INTENT_RULES = [
    # ✅ greetings -> your data.json index 0 = Hi response
    {"patterns": [r"^\s*(hi|hello|hey)\s*$", r"\bhi\b", r"\bhello\b", r"\bhey\b"], "answer_index": 0},

    # ✅ who / intro -> now index 3 (tell about him?)
    {"patterns": [r"\btell about him\b", r"\bwhat about him\b", r"\bwho is sathick\b", r"\bwho are you\b", r"\bintroduce\b"], "answer_index": 3},

    # ✅ contact -> now index 9
    {"patterns": [r"\bcontact\b", r"\bemail\b", r"\bphone\b", r"\breach\b", r"\bget in touch\b", r"\bhow can i contact\b"], "answer_index": 9},

    # ✅ salary -> now index 25
    {"patterns": [r"\bsalary\b", r"\bpackage\b", r"\bctc\b", r"\bexpected salary\b"], "answer_index": 25},

    # ✅ banking
    {"patterns": [r"\bbank\b", r"\bbanking\b", r"\bmashreq\b", r"\bdigital banking\b"], "skill_key": "banking"},

    # ✅ skills
    {"patterns": [r"\breact native\b", r"\brn\b"], "skill_key": "react_native"},
    {"patterns": [r"\bnext\.?js\b", r"\bnextjs\b", r"\bnext\b"], "skill_key": "next"},
    {"patterns": [r"\breact\.?js\b", r"\breactjs\b", r"\breact\b"], "skill_key": "react"},
    {"patterns": [r"\bnode\.?js\b", r"\bnodejs\b", r"\bnode\b", r"\bbackend\b", r"\bapi\b"], "skill_key": "node"},
    {"patterns": [r"\btypescript\b", r"\bts\b"], "skill_key": "typescript"},
    {"patterns": [r"\baws\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\bcloud\b"], "skill_key": "aws"},
    {"patterns": [r"\bdocker\b", r"\bci/cd\b", r"\bpipeline\b", r"\bdevops\b"], "skill_key": "devops"},
    {"patterns": [r"\bxss\b", r"\bsql injection\b", r"\bowasp\b", r"\bcsp\b", r"\bsecurity\b"], "skill_key": "security"},
    {"patterns": [r"\bperformance\b", r"\boptimi[sz]e\b", r"\blazy\b", r"\bcaching\b", r"\bprofiling\b"], "skill_key": "performance"},

    # ✅ language rules
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
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "https://docs.google.com/spreadsheets/d/e/2PACX-1vTl9SBA-l0OKroq0oeGRnSBP9t_BNl7SudbD1ijurCMkh4_uZtklOhaa1cwvEJTRPCsYCvHxkTDUUxN/pub?gid=0&single=true&output=csv").strip()
CACHE_TTL = int(os.getenv("SHEET_CACHE_TTL", "300"))

_sheet_cache = {
    "ts": 0,
    "questions": [],
    "answers": [],
}

async def load_sheet_if_needed(force: bool = False):
    now = int(time.time())
    if not force and (now - _sheet_cache["ts"] < CACHE_TTL) and _sheet_cache["questions"]:
        return

    if not SHEET_CSV_URL:
        return

    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(SHEET_CSV_URL)
        r.raise_for_status()

    rows = list(csv.DictReader(StringIO(r.text)))
    q_list, a_list = [], []

    for row in rows:
        q = (row.get("question") or "").strip()
        a = (row.get("answer") or "").strip()
        if q and a:
            q_list.append(q)
            a_list.append(a)

    _sheet_cache["ts"] = now
    _sheet_cache["questions"] = q_list
    _sheet_cache["answers"] = a_list

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
# ✅ Missed Question Logger (Apps Script Webhook)
# -----------------------------
MISSED_WEBHOOK_URL = os.getenv("MISSED_WEBHOOK_URL", "").strip()

async def log_missed_question(question: str, source: str = "vercel-api"):
    if not MISSED_WEBHOOK_URL:
        return
    payload = {"question": question, "source": source}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(MISSED_WEBHOOK_URL, json=payload)
    except Exception:
        pass

# -----------------------------
# ✅ API routes (Vercel)
# -----------------------------
@app.api_route("/", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api", methods=["GET", "POST", "OPTIONS"])
async def root(request: Request):
    if request.method == "OPTIONS":
        return "OK"

    if request.method == "GET":
        return {"status": "ok", "usage": "POST JSON {question:'...'} to /api"}

    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        return {"error": "Missing question"}

    # 1) Intent detection first
    rule = detect_intent(q)
    if rule:
        if "language_key" in rule:
            return {"answer": LANGUAGE_ANSWERS[rule["language_key"]]}

        if "skill_key" in rule:
            return {"answer": SKILL_ANSWERS.get(rule["skill_key"], "Yes, he has experience in that area.")}

        idx = rule.get("answer_index")
        if idx is not None and 0 <= idx < len(answers):
            return {"answer": answers[idx]}

    # 2) Google Sheet FAQ (no redeploy updates)
    try:
        await load_sheet_if_needed()
        ans = answer_from_sheet(q)
        if ans:
            return {"answer": ans}
    except Exception:
        # ignore sheet errors
        pass

    # 3) Local fallback fuzzy match (data.json)
    best = process.extractOne(q, questions, scorer=fuzz.WRatio)
    if best and best[1] >= 78:
        return {"answer": answers[best[2]]}

    # 4) Missed question -> log it (async, doesn't slow response)
    asyncio.create_task(log_missed_question(q, source="portfolio"))
    return {"answer": "I don't have an answer for that yet."}
