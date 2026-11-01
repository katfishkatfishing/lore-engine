# analyse messages returns cool stats 
import re
from collections import Counter
from google.genai import types
from database import get_collection
from ai import SYSTEM_PROMPT, genai_client
import asyncio
import time

DOSSIER_CACHE = {}


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



def compute_stats(target_aliases: list) -> dict:
    """calculates behavioural stats for a given user based on the chunks"""
    collection = get_collection()

    results = collection.get(
        where={"messager_name": {"$in": target_aliases}},
        limit= 15000,
        include=["documents", "metadatas"]
        )

    if not results or not results.get("documents"):
        return None

    user_lines = []
    word_counter = Counter()
    caps_counter = 0

    docs = results["documents"]
    metas = results.get("metadatas", [])

    for i in range(len(docs)):
        meta = metas[i] if metas and metas[i] else {}
        
        # convert string metadata back to a dictionary
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta.replace("'", '"'))
            except:
                meta = {}

        author = meta.get("messager_name", "Unknown User")

        # Process quotes from the target user
        if not any(alias.lower() in author.lower() for alias in target_aliases):
            continue

        msg = docs[i].strip()
        user_lines.append(msg)

        # Caps lock detection
        alpha_chars = [char for char in msg if char.isalpha()]
        if len(alpha_chars) >= 6 and (sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)) > 0.75: 
            caps_counter += 1

        # Word frequency
        words = re.findall(r"[a-zA-Z']{4,}", msg.lower())
        for word in words:
            if word not in STOPWORDS:
                word_counter[word] += 1

    if not user_lines:
        return {}

    avg_len = round(sum(len(line) for line in user_lines) / len(user_lines), 1)
    caps_pct = round((caps_counter / len(user_lines)) * 100, 1)

    return {
        "username": target_aliases,
        "total_lines_indexed": len(user_lines),
        "avg_line_length": avg_len,
        "caps_pct": f"{caps_pct}%",
        "accomplice": "The Voices", # placeholder for now
        "peak_hour": "Unknown", 
        "night_owl_pct": "Unknown",
        "top_words": [word for word, _ in word_counter.most_common(6)],
        "sample_logs": user_lines[-5:]
    }

async def generate_stats(aliases: list, primary_name: str) -> dict:

    if primary_name in DOSSIER_CACHE:
        return DOSSIER_CACHE[primary_name]

    print(f"\n[DEBUG] Fetching chromaDB for {primary_name}")
    db_start = time.time()

    stats = await asyncio.to_thread(compute_stats, aliases)

    db_end = time.time()
    print(f"[DEBUG] chromaDB fetch took: {db_end - db_start:.2f} seconds")

    if not stats:
        return{"error": f"No data found for user '{primary_name}'."}

    stats["username"] = primary_name

    sample_logs = stats.pop("sample_logs", [])
    samples_str = "\n\n---\n\n".join(sample_logs[:15])

    prompt = (
        f"Write a concise, two-paragraph psychological dossier on '{primary_name}' based on your observations.\n\n"
        f"[BEHAVIORAL METRICS]\n"
        f"- ALL CAPS CRASHOUT Rate: {stats.get('caps_pct', '0%')}\n"
        f"- Most Overused Words: {', '.join(stats.get('top_words', []))}\n\n"
        f"[SAMPLE CONVERSATIONS WITNESSED]\n{samples_str}\n\n"
        f"Paragraph 1: Dissect their vocabulary and sentence structure with dry, clinical amusement.\n"
        f"Paragraph 2: Comment on their actual habits shown in the sample conversations and deliver a final verdict."
    )

    print(f"[DEBUG] Sending {len(prompt)} characters to gemini")
    ai_start = time.time()
    evaluation = None

    for attempt in range(3):
        try:
            print(f"[DEBUG] Attempt {attempt + 1}")
            response = await asyncio.wait_for(
                genai_client.aio.models.generate_content(
                    model="gemini-3.5-flash-lite",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.45,
                            max_output_tokens=5000
                    )
                ),
                timeout=4.0
            )
            evaluation = response.text

        except asyncio.TimeoutError:
            print(f"[DEBUG] Attempt {attempt + 1} timedout")

        except Exception as e:
            evaluation = f"An error occured while generating evaluation"
            print(f"[DEBUG] Ai hard error: {str(e)}")
            break

    if not evaluation:
        evaluation = "Scam Altman stole all of google service wacao"

    ai_end = time.time()
    print(f"[DEBUG] AI took: {ai_end - ai_start:.2f} seconds")

    final_report = {
        "subject": primary_name,
        "metrics": stats,
        "evaluation": evaluation
    }
    DOSSIER_CACHE[primary_name] = final_report

    return final_report