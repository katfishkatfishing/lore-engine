import random
import json
from database import get_collection

TRIVIA_IGNORED = {"lol", "lmao", "ok", "okay", "yes", "yea", "yeah", "no", "nah", "nope", "wait"}

def get_trivia() -> dict:
    """Scans the live ChromaDB archive for suitable trivia quotes."""
    collection = get_collection()
    results = collection.get()

    if not results or not results.get("documents"):
        return {"error": "No quotes found in the archive yet."}

    docs = results["documents"]
    metas = results["metadatas"]
    ids = results["ids"]

    all_authors = set()
    candidate_quotes = []

    # Parse live ChromaDB documents
    for i in range(len(docs)):
        quote = docs[i].strip()
        meta = metas[i] if metas and metas[i] else {}
        
        # Safety net: Convert string metadata to dictionary
        if isinstance(meta, str):
            try:
                meta = json.loads(meta.replace("'", '"'))
            except:
                meta = {}
                
        author = meta.get("messager_name", "Unknown User")
        channel = meta.get("channel", "general")
        
        all_authors.add(author)

        if not (15 <= len(quote) <= 180) or quote.lower() in TRIVIA_IGNORED:
            continue

        candidate_quotes.append({
            "quote": quote,
            "author": author,  
            "channel": channel,
            "chunk_id": ids[i]
        })

    if not candidate_quotes:
        return {"error": "Not enough suitable quotes found for trivia yet."}

    picked = random.choice(candidate_quotes)
    correct = picked["author"]

    # Generate wrong answers from the live author list
    other_authors = list(all_authors - {correct})
    wrong_authors = random.sample(other_authors, min(3, len(other_authors)))

    options = wrong_authors + [correct]
    random.shuffle(options)

    return {
        "question_id": picked["chunk_id"],
        "question": f'Who said: "{picked["quote"]}"',
        "options": options,
        "correct_answer": correct,
        "hint": {
            "channel": f"#{picked['channel']}",
            "date": "Recent"
        }
    }