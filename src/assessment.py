# analyse messages returns cool stats 
import re
from collections import Counter
from google.genai import types
from database import get_collection
from ai import SYSTEM_PROMPT, genai_client


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



def compute_stats(target_user: str) -> dict:
    """calculates behavioural stats for a given user based on the chunks"""
    collection = get_collection()
    results = collection.get()

    if not results or not results.get("documents"):
        return {}

    user_lines = []
    word_counter = Counter()
    caps_counter = 0

    docs = results["documents"]
    metas = results["documents"]

    for i in range(len(docs)):
        meta = metas[i] if metas and metas[i] else {}
        
        # FIX: Convert accidental string metadata back to a dictionary
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta.replace("'", '"'))
            except:
                meta = {}

        author = meta.get("messager_name", "Unknown User")

        # Only process quotes from the target user
        if target_user.lower() not in author.lower():
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
        "username": target_user,
        "total_lines_indexed": len(user_lines),
        "avg_line_length": avg_len,
        "caps_pct": f"{caps_pct}%",
        "accomplice": "The Voices", # placeholder for now
        "peak_hour": "Unknown", 
        "night_owl_pct": "Unknown",
        "top_words": [word for word, _ in word_counter.most_common(6)],
        "sample_logs": user_lines[-5:]
    }

def generate_stats(username: str) -> dict:
    """Generates psychological evaluation based on live stats."""
    stats = compute_stats(username)
    
    if not stats:
        return {"error": f"No data found for user '{username}'."}

    samples_str = "\n\n---\n\n".join(stats.pop("sample_logs"))

    prompt = (
        f"Write a concise, two-paragraph psychological dossier on '{stats['username']}' based on your observations.\n\n"
        f"[BEHAVIORAL METRICS]\n"
        f"- ALL CAPS CRASHOUT Rate: {stats['caps_pct']}\n"
        f"- Most Overused Words: {', '.join(stats['top_words'])}\n\n"
        f"[SAMPLE CONVERSATIONS WITNESSED]\n{samples_str}\n\n"
        f"Paragraph 1: Dissect their vocabulary and sentence structure with dry, clinical amusement.\n"
        f"Paragraph 2: Comment on their actual habits shown in the sample conversations and deliver a final verdict."
    )   

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents= prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.45, 
                max_output_tokens=1500
            )
        )
        evaluation = response.text

    except Exception as e:
        evaluation = f"An error occurred while generating the evaluation: {str(e)}"

    return {
        "subject": stats["username"],
        "metrics": stats,
        "evaluation": evaluation
    }
