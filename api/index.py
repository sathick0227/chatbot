from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz, process
import json, os, re

app = FastAPI(title="Portfolio Chatbot (Vercel Compatible)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # set your vercel domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data.json from repo root
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
answers = data["answers"]

if len(questions) != len(answers):
    raise ValueError("Questions and answers count must match")

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
    # greetings (your data.json has Hi/Hello/hey at indexes 0/1/2)
    {"patterns": [r"^\s*(hi|hello|hey)\s*$", r"\bhi\b", r"\bhello\b", r"\bhey\b"], "answer_index": 0},

    # contact (your contact is index 7)
    {"patterns": [r"\bcontact\b", r"\bemail\b", r"\bphone\b", r"\breach\b", r"\bget in touch\b"], "answer_index": 7},

    # salary (your salary is index 23)
    {"patterns": [r"\bsalary\b", r"\bpackage\b", r"\bctc\b", r"\bexpected salary\b"], "answer_index": 23},

    # banking
    {"patterns": [r"\bbank\b", r"\bbanking\b", r"\bmashreq\b", r"\bdigital banking\b"], "skill_key": "banking"},

    # skills
    {"patterns": [r"\breact native\b", r"\brn\b"], "skill_key": "react_native"},
    {"patterns": [r"\breact\b", r"\breactjs\b", r"\breact\.js\b"], "skill_key": "react"},
    {"patterns": [r"\bnext\b", r"\bnextjs\b", r"\bnext\.js\b"], "skill_key": "next"},
    {"patterns": [r"\bnode\b", r"\bnodejs\b", r"\bnode\.js\b", r"\bbackend\b", r"\bapi\b"], "skill_key": "node"},
    {"patterns": [r"\btypescript\b", r"\bts\b"], "skill_key": "typescript"},
    {"patterns": [r"\baws\b", r"\bec2\b", r"\bs3\b", r"\blambda\b", r"\bcloud\b"], "skill_key": "aws"},
    {"patterns": [r"\bdocker\b", r"\bci/cd\b", r"\bpipeline\b", r"\bdevops\b"], "skill_key": "devops"},
    {"patterns": [r"\bxss\b", r"\bsql injection\b", r"\bowasp\b", r"\bcsp\b", r"\bsecurity\b"], "skill_key": "security"},
    {"patterns": [r"\bperformance\b", r"\boptimi[sz]e\b", r"\blazy\b", r"\bcaching\b", r"\bprofiling\b"], "skill_key": "performance"},
]

def normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text

def detect_intent(text: str):
    t = normalize_text(text)
    for rule in INTENT_RULES:
        if any(re.search(p, t) for p in rule["patterns"]):
            return rule
    return None

class ChatRequest(BaseModel):
    question: str

def answer_for(question: str):
    q = normalize_text(question)

    rule = detect_intent(q)
    if rule:
        if "skill_key" in rule:
            return {"answer": SKILL_ANSWERS.get(rule["skill_key"], "Yes, he has experience in that area.")}

        idx = rule.get("answer_index")
        if idx is not None and 0 <= idx < len(answers):
            return {"answer": answers[idx]}

    # fuzzy fallback
    best = process.extractOne(q, questions, scorer=fuzz.WRatio)
    if best:
        _, score, idx = best
        if score >= 78:
            return {"answer": answers[idx]}

    return {"answer": "I don't have an answer for that yet. Please ask about my profile, skills, projects, or contact details."}

# ✅ Support both: / and /api
@app.get("/")
def home():
    return {"status": "ok", "hint": "POST /api/chat with JSON {question: '...'}"}
@app.get("/api")
def chat(req: ChatRequest):
    return answer_for(req.question)


# ✅ Support both: /chat and /api/chat
@app.post("/chat")
@app.post("/api/chat")

