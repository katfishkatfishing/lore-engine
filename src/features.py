from datetime import datetime, timedelta
import json
import random
import re
from collections import Counter
from pathlib import Path
from google.genai import types
from database import get_collection
from src.database import genai_client, search, load_chunks
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

def get_guess_game() -> dict:
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
        f"Study these real Discord messages from '{matched_user}':\n{style_reference}\n\n"
        f"Write ONE single fabricated message (between 35 and 130 characters) that '{matched_user}' "
        f"never actually said, but matches their exact capitalization, punctuation, slang, and typical complaints. "
        f"Output ONLY the raw fake message text, with no quotation marks or explanation."
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

# generate like patch notes for all members
def get_patch_notes(days_window: int = 30) -> dict:
    """use server activity to make game style server patch notes."""

    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    # parse timestamps and sort
    dated_chunks = []
    for chunk in chunks:
        try:
            dt = datetime.strptime(chunk.get("start_time", ""), "%Y-%m-%d %H:%M")
            dated_chunks.append((dt, chunk))

        except Exception:
            continue

    if not dated_chunks:
        return {"error": "No valid timestamps found in chunks."}

    dated_chunks.sort(key=lambda x: x[0])
    latest_date = dated_chunks[-1][0]
    cutoff_recent = latest_date - timedelta(days=days_window)
    cutoff_previous = cutoff_recent - timedelta(days=days_window)

    recent_messages = Counter()
    previous_messages = Counter()
    recent_late_night = Counter()
    recent_caps = Counter()
    recent_samples = ()

    for dt, chunk in dated_chunks:
        lines = [line for line in chunk.get("text", "").split("\n") if ": " in line]
        is_recent = dt >= cutoff_recent
        is_previous = cutoff_previous <= dt < cutoff_recent

        for line in lines:
            speaker, msg = line.split(": ", 1)
            if is_recent:
                recent_messages[speaker] += 1
                if 1 <= dt.hour <= 5:
                    recent_late_night[speaker] += 1
                alpha = [char for char in msg if char.isalpha()]
                if len(alpha) >= 6 and sum(1 for char in alpha if char.isupper()) / len(alpha) > 0.5:
                    recent_caps[speaker] += 1
            elif is_previous:
                previous_messages[speaker] += 1

        if is_recent and len(chunk.get("text", "")) > 80:
            recent_samples.append(f"[{chunk['start_time']} | #{chunk['channel']}]\n{chunk['text']}")

    # if archive is old and everything is together, split archive in half
    if sum(previous_messages.values()) == 0 and len(dated_chunks) >= 4:
        mid_index = len(dated_chunks) // 2
        recent_messages.clear()
        previous_messages.clear()
        for dt, chunk in dated_chunks[:mid_index]:
            for line in chunk.get("text", "").split("\n"):
                if ": " in line:
                    previous_messages[line.split(": ", 1)[0]] += 1

        for dt, chunk in dated_chunks[mid_index:]:
            for line in chunk.get("text", "").split("\n"):
                if ": " in line:
                    recent_messages[line.split(": ", 1)[0]] += 1

    # format the patch notes per user
    all_users = set(recent_messages.keys()) | set(previous_messages.keys())
    stat_deltas = []

    for user in sorted(all_users):
        recent_count = recent_messages[user]
        previous_count = previous_messages[user]

        if recent_count + previous_count < 3:
            continue
        diff = recent_count - previous_count
        direction = "BUFFED (More active)" if diff >= 0 else "NERFED (Quieter)"
        stat_deltas.append(
            f"- {user}: {previous_count} msgs -> {recent_count} msgs ({direction} by {abs(diff)} messages) | "
            f"1am to 5am: {recent_late_night[user]} | ALL CAPS screams: {recent_caps[user]}"
        )

    deltas_str = "\n".join(stat_deltas)
    picked_samples = random.sample(recent_samples, min(6, len(recent_samples))) if recent_samples else []
    samples_str = "\n\n---\n\n".join(picked_samples)

    version_tag = f"v{latest_date.strftime('%Y.%m')}"

    prompt = (
        f"[SERVER TELEMETRY DELTAS — PATCH {version_tag}]\n{deltas_str}\n\n"
        f"[RECENT INCIDENTS WITNESSED]\n{samples_str}\n\n"
        f"Write the official '{version_tag} Friend Group Balance Patch Notes'."
        f"Include:\n"
        f"1. **Character Adjustments (Buffs & Nerfs):** Comment on who has been yapping more, who went quiet, and whose sleep schedule or blood pressure deteriorated.\n"
        f"2. **Bug Fixes & Known Issues:** Reference 2 or 3 specific funny incidents from the recent logs above as 'unresolved bugs' in their behavior.\n"
        f"Keep it concise, sharp, and formatted cleanly for Discord/Web."
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instructions=SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=800
            )
        )
        patch_notes = response.text
    except Exception as e:
        return {"error": f"AI generation failed: {str(e)}"}

    return {
        "version_tag": version_tag,
        "telemetry": stat_deltas,
        "patch_notes": patch_notes,
    }
        