import json
import random
import re
from collections import Counter
from pathlib import Path
from google.genai import types
from database import get_collection
from src.api import load_chunks
from src.database import genai_client, search
from src.ai import SYSTEM_PROMPT

CHUNKS_FILE = Path(__file__).parent/"data"/"cleaned"/"organisedGoesHere.json"
CACHE_FILE = Path("data/cleaned/cache.json")

TRIVIA_IGNORED = {"lol", "lmao", "ok", "okay", "yes", "yea", "yeah", "no", "nah", "nope", "wait"}

def get_trivia() -> dict:
    collection = get_collection()
    results = collection.get()

    if not results or not results.get("documents"):
        return {"error": "No quotes found in the archive yet."}

    docs = results["documents"]
    metas = results["metadatas"]
    ids = results["ids"]

    all_authors = set()
    candidate_quotes = []

    # parse chromadb docs
    for i in range(len(docs)):
        quote = docs[i].strip()
        meta = metas[i] if metas and metas[i] else {}

        if isinstance(meta, str):
            try:
                meta = json.loads(meta.replace("'", "'"))
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
        return{"error": "Not enough suitable quotes found for trivia yet."}

    picked = random.choice(candidate_quotes)
    correct = picked["author"]

    other_authors = list(all_authors - {correct})
    wrong_authors = random.sample(other_authors, min(3, len(other_authors)))

    options = wrong_authors + [correct]
    random.shuffle(options)

    return{
        "question_id": picked["chunk_id"],
        "question": f'Who said: "{picked["quote"]}"',
        "options": options,
        "correct_answer": correct,
        "hint": {
            "channel": f"#{picked['channel']}",
            "date": "Recent"
        }
    }

def guess_game() -> dict:
    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    # filter chunks with multiple authors
    candidates = [
        chunk for chunk in chunks
        if chunk.get("message_count", 0) >= 5 and len(chunk.get("authors", [])) >= 2
    ]

    if not candidates:
        return {"error": "No suitable multi-person conversation chunks found."}

    picked = random.choice(candidates)
    raw_lines = [line for line in picked.get("text", "").split("\n") if ": " in line][:10]

    author_map = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    anonymized_lines = []

    for line in raw_lines:
        speaker, content = line.split(": ", 1)
        if speaker not in author_map:
            idx = min(len(author_map), len(letters) - 1)
            author_map[speaker] = f"Person {letters[idx]}"

        anon_line = f"{author_map[speaker]}: {content}"

        # remove mention of author in sentence
        for original, anon in author_map.items():
            anon_line = anon_line.replace(original, f"[{anon}]")
        anonymized_lines.append(anon_line)

    anon_transcript = "\n".join(anonymized_lines)

    prompt = (
        f"Read this anonymized chat transcript:\n\n{anon_transcript}\n\n"
        "Provide your output exactly in this format:\n"
        "[Redacted Chat Text]\n"
        "SUMMARY: [One short, funny sentence summarizing what they are talking about without using specific names]"
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

    reveal_identities = {v: k for k, v in author_map.items()}

    return {
        "chunk_id": picked.get("id"),
        "date": picked.get("start_time", "Unknown Date").split(" ")[0],
        "channel": f"#{picked.get('channel', 'general')}",
        "redacted_chat": redacted_chat,
        "topic_summary": topic_summary,
        "reveal_identities": reveal_identities,
        "original_chat": "\n".join(raw_lines)
    }


def get_two_truths_one_lie(username: str = None) -> dict:
    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    # gather eligible lines
    author_lines = {}
    for chunk in chunks:
        for line in chunk.get("text", "").split("\n"):
            if ": " not in line:
                continue
            speaker, quote = line.split(": ", 1)
            message = quote.strip()
            if 30 <= len(message) <= 140 and not message.startswith("@") and "https" not in message and "http" not in message:
                author_lines.setdefault(speaker, []).append(message)

    # filter authors
    eligible_authors = {author: lines for author, lines in author_lines.items() if len(lines) >= 10}
    if not eligible_authors:
        return {"error": "No eligible authors with enough lines found."}

    matched_user = None
    if username:
        for author in eligible_authors:
            if username.lower() in author.lower():
                matched_user = author
                break
                
        if not matched_user:
            return {"error": f"Not enough data for user '{username}' to generate a quote."}
    else:
        matched_user = random.choice(list(eligible_authors.keys()))

    samples = random.sample(eligible_authors[matched_user], min(20, len(eligible_authors[matched_user])))
    real_quotes = samples[:2]
    style_reference = "\n".join([f"- {quote}" for quote in samples[2:]])


    prompt = (
        f"You are studying the conversational style of a user named {matched_user}.\n"
        f"Here are some examples of things they have said:\n{style_reference}\n\n"
        "Generate exactly ONE new, completely fake sentence that sounds exactly like something this person would say. "
        "Do not include quotes around it. Do not include their name."
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=400
            )
        )
        fake_quote = response.text.strip().strip('"').strip("'")
    except Exception as e:
        return {"error": f"AI generation failed: {str(e)}"}

    options = [
        {"text": real_quotes[0], "is_fake": False},
        {"text": real_quotes[1], "is_fake": False},
        {"text": fake_quote, "is_fake": True}
    ]
    random.shuffle(options)

    fake_index = next(i for i, option in enumerate(options) if option["is_fake"])

    return {
        "username": matched_user,
        "options": [choice["text"] for choice in options],
        "fake_option_num": fake_index + 1,
        "fake_quote": fake_quote,
        "real_quotes": real_quotes,
    }
