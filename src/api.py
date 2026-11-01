from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import random

from ai import ask
from database import search, get_collection
from features import get_trivia, get_guess_game, get_two_truths_one_lie, get_patch_notes
from assessment import generate_stats

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

@app.get("/api/quotes")
def get_quotes(limit: int = Query(20, ge=1, le=100)):
    """Returns quotes directly from the live ChromaDB archive."""
    collection = get_collection()
    results = collection.get()
    
    if not results or not results.get("documents"):
        return []

    docs = results["documents"]
    metas = results["metadatas"]
    ids = results["ids"]
    
    combined = [{"id": ids[i], "text": docs[i], "metadata": metas[i]} for i in range(len(docs))]
    random.shuffle(combined)
    
    return combined[:limit]

@app.get("/api/members")
def list_members():
    """Returns a list of all unique usernames in the live database."""
    collection = get_collection()
    results = collection.get()
    
    if not results or not results.get("metadatas"):
        return {"members": []}
        
    members = sorted(list(set(
        meta.get("messager_name") for meta in results["metadatas"] if meta and meta.get("messager_name")
    )))
    return {"members": members}

@app.get("/api/game/guess")
def play_guess_game():
    """Returns a redacted convo where players guess who and what was said."""
    result = get_guess_game()
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/api/game/two_truths_one_lie")
def play_two_truths_one_lie(username: Optional[str] = Query(None, description="Optional user selection")):
    """Returns 2 real quotes and 1 fake ai generated quote for a member."""
    result = get_two_truths_one_lie(username)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/api/patch-notes")
def server_patch_notes(days_window: int = Query(30, ge=7, le=365)):
    """Generates game style patch notes based on server activity."""
    result = get_patch_notes(days_window)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result