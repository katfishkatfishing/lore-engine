from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import random

from ai import ask
from database import search, get_collection
from features import get_trivia
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
