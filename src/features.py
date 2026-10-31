import json
import random
import re
from collections import Counter
from pathlib import Path
from google.genai import types

from src.api import load_chunks
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

def get_guess_game() -> dict:
    """picks an active multi person conversation chunk, hides the people as Person A, B, C, etc. and has ai redact the central topic so players have to guess who and what the convo is about."""

    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    #filter for chunks with multiple authors
    candidates = [
        chunk for chunk in chunks
        if chunk.get("message_count", 0) >= 5 and len(chunk.get("authors", [])) >= 2
    ]

    if not candidates:
        return {"error": "No suitable multi-person conversation chunks found."}

    picked = random.choice(candidates)
    raw_lines = [line for line in picked.get("text", "").splt("\n") if ": " in line][:10]

    #replace authors with Person A, B, C, etc.
    author_map = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    anonymized_lines = []

    for line in raw_lines:
        speaker, content = line.split(": ", 1)
        if speaker not in author_map:
            idx = min(len(author_map), len(letters) - 1)
            author_map[speaker] = f"Person {letters[idx]}"

        anon_line = f"{author_map[speaker]}: {content}"

        #strip any mentions of the original authors in the content
        for original, anon in author_map.items():
            anon_line = anon_line.replace(original, f"[{anon}]")
        anonymized_lines.append(anon_line)

    anon_transcript = "\n".join(anonymized_lines)

 #use ai to redact the topic of the conversation

    prompt = (

    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=1000
            )
        )

        output = response.text.strip()
        if "SUMMARY:" in output:
            redacted_chat, topic_summary = output.split("SUMMARY:", 1)
            redacted_chat = redacted_chat.strip()
            topic_summary = topic_summary.strip()
        else:
            redacted_chat = output
            topic_summary = "An incident in #" + picked.get("channel", "general")

    except Exception as e:
        return {"error": f"AI generation failed: {str(e)}"}

    # invert the author_map to get Person A -> original author
    reveal_indentities = {v: k for k, v in author_map.items()}

    return {
        "chunk_id": picked.get("id"),
        "date": picked.get("start_time", "Unknown Date").split(" ")[0],
        "channel": f"#{picked.get('channel', 'general')}",
        "redacted_chat": redacted_chat,
        "topic_summary": topic_summary,
        "reveal_identities": reveal_indentities,
        "original_chat": "\n".join(raw_lines)
    }

        