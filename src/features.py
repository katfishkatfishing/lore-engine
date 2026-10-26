import json
import random
import re
from collections import Counter
from pathlib import Path
from google.genai import types

from src.database import genai_client, search
from src.ai import SYSTEM_PROMPT

CHUNKS_FILE = Path(__file__).parent / "data" / "cleaned" / "organisedGoesHere.json"
CACHE_FILE = Path("data/cleaned/cache.json")

TRIVIA_IGNORED = {
    "lol", "lmao", "ok", "okay", "yes", "yea", "yeah", "no", "nah", "nope", "wait"
}

def get_trivia() -> dict:
    """ scans chunks for quotes that are suitable for trivia questions. Generates a 4 option mcq of 'Who said it?"""

    if not CHUNKS_FILE.exists():
        return {"error": "Chunks file not found."}

    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    all_authors = set()
    candidate_quotes = []

    for chunk in chunks:
        for author in chunk.get("authors", []):
            all_authors.add(author)

        lines = chunk.get("text", "").split("\n")
        for line in lines:
            if ": " not in line:
                continue
            speaker, quote = line.split(": ", 1)
            quote = quote.strip()

            if not (35 <= len(quote) <= 180):
                continue
            if quote.lower() in TRIVIA_IGNORED:
                continue

            candidate_quotes.append({
                "quote": quote,
                "correct_author": speaker,
                "timestamp": chunk.get("start_time", "Unknown Date"),
                "channel": chunk.get("channel",  "general"),
                "chunk_id": chunk.get("id"),
                "full_context": chunk.get("text")
            })

    if not candidate_quotes:
        return {"error": "No suitable quotes found for trivia."}

    picked = random.choice(candidate_quotes)
    correct = picked["correct_author"]

    other_authors = [author for author in all_authors if author != correct]
    wrong_authors = random.sample(other_authors, min(3, len(other_authors)))

    options = wrong_authors + [correct]
    random.shuffle(options)

    return {
        "question_id": picked["chunk_id"],
        "question": f'Who said: "{picked["quote"]}"',
        "options": options,
        "correct_answer": correct,
        "hint": {
            "channel": f"Channel: #{picked['channel']}",
            "date": f"Date: {picked['timestamp']}",
        },
        "context": {
            "timestamp": picked["timestamp"],
            "full_convo": picked["full_context"]
        }
    }