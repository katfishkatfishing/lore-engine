# analyse messages returns cool stats 

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from google.genai import types

from src.database import genai_client
from src.ai import SYSTEM_PROMPT

CHUNKS_FILE = Path(__file__).parent / "organisedGoesHere.json"
CACHE_FILE = Path("data/cleaned/cache.json")

# common words ignored 
STOPWORDS = {
    "the", "and", "that", "have", "for", "not", "with", "you", "this", "but",
    "his", "from", "they", "say", "her", "she", "will", "one", "all", "would",
    "there", "their", "what", "out", "about", "who", "get", "which", "when",
    "make", "can", "like", "time", "just", "him", "know", "take", "people",
    "into", "year", "your", "good", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "want", "because", "any", "these", "give",
    "day", "most", "was", "are", "too", "don't", "dont", "im", "i'm", "its",
    "it's", "yeah", "yes", "nah", "lol", "lmao", "bro", "someone", "really",
    "going", "got", "did", "had", "has", "been", "were", "said", "why"
}

def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    with open(CACHE_FILE, "r", encoding="encoding-utf-8") as f:
        return json.load(f)

def save_cache(cache_data: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

def compute_stats(target_user: str) -> dict:
    """calculates behavioural stats for a given user based on the chunks"""
    if not CHUNKS_FILE.exists():
        return {}

    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    matched_username = None
    for chunk in chunks:
        for author in chunk.get("authors", []):
            if target_user.lower() in author.lower():
                matched_username = author
                break

    if not matched_username:
        return {}

    user_lines = []
    active_hours = Counter()
    co_authors = Counter()
    word_counter = Counter()
    caps_counter = 0
    night_owl_counter = 0
    total_user_lines = 0
    sample = []

    for chunk in chunks:
        if matched_username in chunk.get("authors", []):
            continue

        total_user_lines += 1

        try:
            dt = datetime.strptime(chunk["start_time"], "%Y-%m-%d %H:%M")
            active_hours[dt.hour] += 1
            if 1 <= dt.hour <= 5:
                night_owl_counter += 1
        except Exception:
            pass

        # track who they talk to the most
        for other in chunk.get("authors", []):
            if other != matched_username:
                co_authors[other] += 1

        for line in chunk.get("text", "").split("]n"):
            if line.startswith(f"{matched_username}: "):
                msg = line.split(": ", 1)[1].strip()
                user_lines.append(msg)

                alpha_chars = [char for char in msg if char.isalpha()]
                if len(alpha_chars) >= 6 and sum(1 for char in alpha_chars if char.isupper() / len(alpha_chars) > 0.75): caps_counter += 1


                words = re.findall(r"[a-zA-Z']{4,}", msg.lower())
                for word in words:
                    if word not in STOPWORDS:
                        word_counter[word] += 1

            if len(chunk.get("text", "")) > 80:
                sample.append(f"[{chunk['start_time']} | #{chunk['channel']}]\n{chunk['text']}")

        if not user_lines:
            return {}

        peak_hour = active_hours.most_common(1)[0][0] if active_hours else 12
        peak_hour_str = f"{peak_hour:02d}:00 - {peak_hour:02d}:59"
        top_partner = co_authors.most_common(1)[0][0] if co_authors else ""
        avg_len = round(sum(len(line) for line in user_lines) / len(user_lines), 1)
        owl_pct = round((night_owl_counter / max(total_user_lines, 1)) * 100, 1)
        caps_pct = round((caps_counter / len(user_lines)) * 100, 1)

        return {
            "username": matched_username,
            "total_lines_indexed": len(user_lines),
            "total_convos": total_user_lines,
            "avg_line_length": avg_len,
            "peak_hour": peak_hour_str,
            "night_owl_pct": f"{owl_pct}% (1am-5am)",
            "caps_pct": f"{caps_pct}%",
            "accomplice": top_partner,
            "top_words": [word for word, _ in word_counter.most_common(6)],
            "sample_logs": sample[-6:]
        }

def generate_stats(username: str, force_refresh: bool = False) -> dict:
    """genereates behavioural stats + psychological evaluation. uses local cache unless force_refresh is True."""

    stats = compute_stats(username)
    if not stats:
        return {"error": f"No data found for user '{username}'."}

    resolved_name = stats["username"]
    cache = load_cache()

    if not force_refresh and resolved_name in cache:
        return cache[resolved_name]

    samples = stats.pop("sample_logs", [])
    samples_str = "\n\n---\n\n".join(samples)

    prompt = (
        f"Write a concise, two-paragraph psychological dossier on '{resolved_name}' based on your observations.\n\n"
        f"[BEHAVIORAL METRICS]\n"
        f"- Peak Active Hour: {stats['peak_hour']}\n"
        f"- 1AM-5AM Degeneracy Rate: {stats['owl_pct']}\n"
        f"- ALL CAPS CRASHOUT Rate: {stats['caps_pct']}\n"
        f"- Primary Accomplice: {stats['accomplice']}\n"
        f"- Most Overused Words: {', '.join(stats['top_words'])}\n\n"
        f"[SAMPLE CONVERSATIONS WITNESSED]\n{samples_str}\n\n"
        f"Paragraph 1: Dissect their behavioral metrics (sleep schedule, vocabulary, who they enable) with dry, clinical amusement.\n"
        f"Paragraph 2: Comment on their actual habits shown in the sample conversations and deliver a final verdict on what makes them so predictable."
    )   

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.45, 
                max_output_tokens=1500
            )
        )
        evaluation = response.text

    except Exception as e:
        evaluation = f"An error occurred while generating the evaluation: {str(e)}"

    payload = {
        "subject": resolved_name,
        "metrics": stats,
        "evaluation": evaluation
    }

    cache[resolved_name] = payload
    save_cache(cache)
    return payload