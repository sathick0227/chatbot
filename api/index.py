from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {
        "status": "ok",
        "endpoints": {
            "chat": "POST /api/chat"
        }
    }
