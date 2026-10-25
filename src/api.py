import json
import random
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.ai import ask
from src.database import search
from src.features import get_trivia
from src.assessment import generate_stats, CHUNKS_FILE

CHUNKS_FILE = Path("data/cleaned/lore_chunks.json")

app = FastAPI(
    title="Lore Engine API",
    description="Backend API for the Lore Engine",
    version="1.0.0",
)

#enable CORS for all origins (for development purposes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str
    mode: Optional[str] = "auto" 
    top_k: Optional[int] = 5

def load_chunks() -> list[dict]:
    if not CHUNKS_FILE.exists():
        return[]
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/health")
def health_check():
    chunks = load_chunks()
    return {"status": "online", "indexed_chunks": len(chunks)}

@app.get("/api/quotes")
def get_quotes(
    limit: int = Query(20, ge=1, le=100),
    author: Optional[str] = None,
    channel: Optional[str] = None,
    shuffle: bool = False
):
    """Returns cleaned chunks for the frontend hall of fame."""
    chunks = load_chunks()
    if not chunks:
        return[]

    # Filter chunks by author if specified
    if author:
        chunks = [
            c for c in chunks
            if any(author.lower() in a.lower() for a in c.get("authors", []))
        ]

    # Filter chunks by channel if specified
    if channel:
        chunks = [c for c in chunks if channel.lower() in c.get("channel", "").lower()]

    if shuffle:
        chunks = random.sample(chunks, min(len(chunks), limit))
    else:
        chunks = chunks[:limit]

    return chunks

@app.get("/api/stats")
def get_stats():
    """Computes quick server statistics for frontend."""
    chunks = load_chunks()
    if not chunks:
        return {
            "total_chunks": 0,
            "total_messages": 0,
            "channels": [],
            "top_authors": {}
        }

    total_messages = sum(chunk.get("message_count", 0) for chunk in chunks)
    channels = sorted(list(set(chunk.get("channel", "general") for chunk in chunks)))

    author_counts = {}
    for chunk in chunks:
        for author in chunk.get("authors", []):
            author_counts[author] = author_counts.get(author, 0) + 1

        # sort authors by how many chunks they appear in
        top_authors = dict(sorted(author_counts.items(), key=lambda item: item[1], reverse=True)[:10])

        return {
            "total_chunks": len(chunks),
            "total_messages": total_messages,
            "channels": channels,
            "top_authors": top_authors
        }

@app.get("/api/search")
def semantic_search(q: str = Query(..., min_length=1), to_k: int = 5):
    """Direct vector search without calling llm."""
    return {"results": search(q, top_k=to_k)}

@app.post("/api/ask")
def ask_archive(request: AskRequest):
    """Consults ai using RAG and returns answer and sources."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    result = ask(
        question=request.question.strip(),
        mode=request.mode or "auto",
        top_k=request.top_k or 5
    )
    return result

@app.get("/api/game/who-said-it")
def play_trivia():
    """Returns a random quote and 4 options for 'Who said it?' trivia game."""
    result = get_trivia()
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/api/members")
def list_members():
    """returns a list of all unique usernames in the database."""
    chunks = load_chunks()
    members = sorted(list(set(author for chunk in chunks for author in chunk.get("authors", []))))
    return {"members": members}

@app.get("/api/assessment/{username}")
def get_assessment(
    username: str,
    refresh: bool = Query(False, description="Force refresh of cached stats")
):
    """returns behavioural stats and psychological evaluation for a given username."""
    result = generate_stats(username, force_refresh=refresh)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result