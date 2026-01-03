from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz, process
import json, os, re

app = FastAPI(title="Portfolio Chatbot", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://portfolio-latest-henna.vercel.app",
    ],
    allow_credentials=False,   # keep False unless you use cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


# ✅ Load data.json from repo root
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
answers = data["answers"]

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
    # ✅ greetings
    {"patterns": [r"^\s*(hi|hello|hey)\s*$", r"\bhi\b", r"\bhello\b", r"\bhey\b"], "answer_index": 0},

    # ✅ who / intro (tell about him, what about him, who is sathick)
    {"patterns": [r"\btell about him\b", r"\bwhat about him\b", r"\bwho is sathick\b", r"\bwho are you\b", r"\bintroduce\b"], "answer_index": 3},

    # ✅ contact (now index 9)
    {"patterns": [r"\bcontact\b", r"\bemail\b", r"\bphone\b", r"\breach\b", r"\bget in touch\b"], "answer_index": 9},

    # ✅ salary (now index 25)
    {"patterns": [r"\bsalary\b", r"\bpackage\b", r"\bctc\b", r"\bexpected salary\b"], "answer_index": 25},

    # ✅ banking (skill answer)
    {"patterns": [r"\bbank\b", r"\bbanking\b", r"\bmashreq\b", r"\bdigital banking\b"], "skill_key": "banking"},

    # ✅ skills (skill answers)
    {"patterns": [r"\breact native\b", r"\brn\b"], "skill_key": "react_native"},
    {"patterns": [r"\bnext\.?js\b", r"\bnextjs\b", r"\bnext\b"], "skill_key": "next"},
    {"patterns": [r"\breact\.?js\b", r"\breactjs\b", r"\breact\b"], "skill_key": "react"},
    {"patterns": [r"\bnode\.?js\b", r"\bnodejs\b", r"\bnode\b", r"\bbackend\b", r"\bapi\b"], "skill_key": "node"},
    {"patterns": [r"\btypescript\b", r"\bts\b"], "skill_key": "typescript"},
    {"patterns": [r"\baws\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\bcloud\b"], "skill_key": "aws"},
    {"patterns": [r"\bdocker\b", r"\bci/cd\b", r"\bpipeline\b", r"\bdevops\b"], "skill_key": "devops"},
    {"patterns": [r"\bxss\b", r"\bsql injection\b", r"\bowasp\b", r"\bcsp\b", r"\bsecurity\b"], "skill_key": "security"},
    {"patterns": [r"\bperformance\b", r"\boptimi[sz]e\b", r"\blazy\b", r"\bcaching\b", r"\bprofiling\b"], "skill_key": "performance"},
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


@app.api_route("/", methods=["GET", "POST"])
@app.api_route("/api", methods=["GET", "POST"])
async def root(request: Request):
    if request.method == "GET":
        return {"status": "ok", "usage": "POST JSON {question:'...'}"}

    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        return {"error": "Missing question"}

    # your existing logic
    rule = detect_intent(q)
    if rule:
        if "skill_key" in rule:
            return {"answer": SKILL_ANSWERS.get(rule["skill_key"], "Yes, he has experience in that area.")}
        idx = rule.get("answer_index")
        if idx is not None and 0 <= idx < len(answers):
            return {"answer": answers[idx]}

    best = process.extractOne(q, questions, scorer=fuzz.WRatio)
    if best and best[1] >= 78:
        return {"answer": answers[best[2]]}

    return {"answer": "I don't have an answer for that yet."}