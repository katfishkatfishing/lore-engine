from datetime import datetime, timedelta
import json
import random
import re
import html
import urllib.request
import urllib.parse
from collections import Counter
from pathlib import Path
from google.genai import types
from database import get_collection
from src.database import genai_client, search, load_chunks
from src.ai import SYSTEM_PROMPT

CHUNKS_FILE = Path(__file__).parent/"data"/"cleaned"/"organisedGoesHere.json"
CACHE_FILE = Path("data/cleaned/cache.json")

TRIVIA_IGNORED = {"lol", "lmao", "ok", "okay", "yes", "yea", "yeah", "no", "nah", "nope", "wait"}

def get_trivia(mode: str = "mix") -> dict:
    """
    mode = 'quotes'
    mode = 'online'
    mode = 'mix'
    """
    if mode == "online" or (mode == "mix" and random.random() < 0.5):
        return get_online_trivia(category="any")
    
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

def generate_shameboard(author: str, quote_text: str, channel: str, recorded_by: str) -> dict:
    """WHen someone reacts to a message with the bookmmark emoji, ai inspects the quote and generates a roast for the hall of shame."""

    prompt = (
        f"A member (`{recorded_by}`) just pinned a quote by `{author}` in `#{channel}` "
        f"to the server's permanent Hall of Quotes:\n\n"
        f"\"{quote_text}\"\n\n"
        f"Write a single, dry, one-sentence 'Museum Curator's Note' (under 30 words) in your COI Amon voice "
        f"commenting on why this statement deserves to be immortalized as a monument to `{author}`'s questionable judgment."
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tempermoreature=0.5,
                max_output_tokens=250
            )
        )
        curator_note = response.text.strip()
    except Exception:
        curator_note = "No comment. The AI was too embarrassed to roast this one."

    return {
        "author": author,
        "quote_text": quote_text,
        "channel": f"#{channel}",
        "recorded_by": recorded_by,
        "curator_note": curator_note
    }

#server feud
def get_server_feud() -> dict:
    """Generates family feud by surveying the json file.""" #maybe ill add other sources soon

    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    user_words = {}
    late_night_counts = Counter()
    caps_counts = Counter()
    yap_counts = Counter()

    stopwords = {
        "the", "and", "that", "have", "for", "not", "with", "you", "this", "but",
        "from", "they", "will", "would", "there", "their", "what", "about", "when",
        "make", "like", "time", "just", "know", "people", "your", "some", "could",
        "them", "then", "think", "also", "back", "after", "even", "want", "because",
        "really", "going", "yeah", "okay", "wait", "dont", "don't","im","i'm"
    }

    for chunk in chunks:
        is_late = False
        try:
            dt = datetime.strptime(chunk.get("start_time", ""), "%Y-%m-%d %H:%M")
            is_late = (1 <= dt.hour <= 5)

        except Exception:
            pass

        for line in chunk.get("text", "").split("\n"):
            if ": " not in line:
                continue
            speaker, msg = line.split(": ", 1)
            yap_counts[speaker] += 1
            if is_late:
                late_night_counts[speaker] += 1

            alpha = [char for char in msg if char.isalpha()]
            if len(alpha) >= 6 and sum(1 for char in alpha if char.isupper()) / len(alpha) > 0.6:
                caps_counts[speaker] += 1

            words = re.findall(r"[a-zA-Z]{5,}", msg.lower())
            for word in words:
                if word not in stopwords:
                    user_words.setdefault(speaker, Counter())[word] += 1

        # build candidate questions
        surveys = []

        # a. most used words
        for user, word_counter in user_words.items():
            if sum(word_counter.values()) >= 30 and len(word_counter) >= 5:
                top_5 = word_counter.most_common(5)
                surveys.append({
                    "prompt": f"We surveyed the archive and asked: 'Name the 5 words '{user}' uses most.",
                    "board": [{"rank": i + 1, "answer": word.upper(), "points": count} for i, (word, count) in enumerate(top_5)]
                })

        # b. most late night messages
        if len(late_night_counts) >= 3:
            top_owls = late_night_counts.most_common(5)
            surveys.append({
                "prompt": "We surveyed the archive and asked: Who has the worst sleep schedule (1am to 5am)?",
                "board": [{"rank": i + 1, "answer": user, "points": count} for i, (user, count) in enumerate(top_owls)]
            })

        # c. most ALL CAPS messages
        if len(caps_counts) >= 3:
            top_ragers = caps_counts.most_common(5)
            surveys.append({
                "prompt": "We surveyed the archive and asked: Who has the highest blood pressure in the group?",
                "board": [{"rank": 1 + 1, "answer": user, "points": count} for i, (user, count) in enumerate(top_ragers)]
            })

        if not surveys:
            return {"error": "Not enough data to generate a server feud."}

        picked = random.choice(surveys)

        return {
            "host_intro": "Survey says... the top answers are in! Let's see how the server voted.",
            "prompt": picked["prompt"],
            "top_answers": picked["board"],
            "footer": "Thanks to the server archive for providing the data for this survey."
        }

# higher or lower game
def get_higher_lower() -> dict:
    """Generates a higher or lower game based on stats and stuff, and also gets some stuff from the internet for questions."""

    chunks = load_chunks()
    if not chunks:
        return {"error": "Chunks file not found or empty."}

    stat_pool = []
    msg_counts = Counter()
    late_counts = Counter()
    question_counts = Counter()
    word_counts = Counter()

    funny_words = {"bro", "wait", "crazy", "sleep", "tired", "fuck", "shit", "dead", "why", "sorry"} #uhhh not too sure yet

    for chunk in chunks:
        is_late = False
        try:
            dt = datetime.strptime(chunk.get("start_time", ""), "%Y-%m-%d %H:%M")
            is_late = (1 <= dt.hour <= 5)

        except Exception:
            pass

        for line in chunk.get("text", "").split("\n"):
            if ": " not in line:
                continue
            speaker, msg = line.split(": ", 1)
            msg_counts[speaker] += 1
            if is_late:
                late_counts[speaker] += 1
            if msg.strip().endswith("?"):
                question_counts[speaker] += 1

            t_lower = msg.lower()
            for funny_word in funny_words:
                if re.search(rf"\b{funny_word}\b", t_lower):
                    word_counts[(speaker, funny_word)] += 1

    for user, count in msg_counts.items():
        stat_pool.append({"description": f"Total messages sent by {user}", "value": count})

    for user, count in late_counts.items():
        if count > 0:
            stat_pool.append({"description": f"1am to 5am messages sent by {user}", "value": count})

    for user, count in question_counts.items():
        if count > 0:
            stat_pool.append({"description": f"Questions asked by {user}", "value": count})

    for (user, funny_word), count in word_counts.items():
        if count > 2:
            stat_pool.append({"description": f"Times {user} has typed the word '{funny_word}'", "value": count})

    if len(stat_pool) < 2:
        return {"error": "Not enough data to generate a higher or lower game."}

    #pick two stats that have different values
    stat1, stat2 = random.sample(stat_pool, 2)
    attempts = 0
    while stat1["value"] == stat2["value"] and attempts < 10:
        stat1, stat2 = random.sample(stat_pool, 2)
        attempts += 1

    correct_call = "HIGHER" if stat2["value"] > stat1["value"] else "LOWER"

    return {
        "stat1": {
        "label": stat1["description"],
        "value": stat1["value"]
        },
        "stat2": {
            "label": stat2["description"],
            "hidden_value": stat2["value"]
        },
        "correct_answer": correct_call,
        "prompt": (
            f"**{stat1['description']}** is **{stat1['value']}**.\n"
            f"Is **{stat2['description']}** HIGHER or LOWER?"
        )
    }

#uh get stuff from the internet for trivia questions
def fetch_json(url: str, timeout: int = 5) -> dict | list | None:
    """Fetch json from public APIs without using requests library."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LoreEngine/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception as e:
        print(f"Error fetching JSON from {url}: {e}")
        return None

# another 2 truths 1 lie game but with stuff from the internet
def get_live_web_two_truths_one_lie(topic: str = "weird world news or video game facts/news")
    """ Uses gemini built in google search to get 2 stuffs and makes up 1 fake stuff so players have to guess which one ai made up."""

    prompt = (
        f"Use Google Search to find 2 bizarre, hard-to-believe, but 100% REAL facts or news headlines "
        f"about: {topic}.\n"
        f"Then, invent 1 completely FAKE fact/headline on the same topic that sounds equally plausible.\n\n"
        f"Return your response in strict JSON format with these exact keys:\n"
        f"{{\n"
        f'  "real_1": "First real headline/fact",\n'
        f'  "real_2": "Second real headline/fact",\n'
        f'  "fake": "The fabricated headline/fact",\n'
        f'  "explanation": "A 2-sentence dry explanation from Amon revealing the fake and citing when the two real ones happened."\n'
        f"}}"
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.6,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
        )

        raw_output = response.text.strip()
        if "```" in raw_output:
            raw_output = raw_output.split("```")[1]
            if raw_output.startswith("json"):
                raw_output = raw_output[4:]
        parsed = json.loads(raw_output.strip())

        choices = [
            {"text": parsed["real1"], "is_fake": False},
            {"text": parsed["real2"], "is_fake": False},
            {"text": parsed["fake"], "is_fake": True}
        ]
        random.shuffle(choices)
        fake_num = next(i + 1 for i, choice in enumerate(choices) if choice["is_fake"])

        return {
            "topic": topic,
            "options": [choice["text"] for choice in choices],
            "fake_option_num": fake_num,
            "fake_quote": parsed["fake"],
            "ai_reveal": parsed["explanation"]
        }
    except Exception as e:
        return {"error": f"web search failed: {e}"}

TRIVIA_CATEGORIES = {
    "any": None,
    "games": 15,
    "anime": 31,
    "science": 17,
    "computers": 18,
    "math": 19,
    "mythology": 20,
    "general": 9,
    "sports": 21,
    "geography": 22,
    "history": 23,
    "politics": 24,
}

def get_online_trivia(category: str = "any", difficulty: str = "medium", commentary: bool = True) -> dict:
    """
    pulls a real mcq from opentdb.com and adds some commentary from ai. 
    categories: 'any', 'games', 'anime', 'science', 'computers', 'math', 'mythology', 'history', 'politics', 'sports', 'geography'
    """

    category_id = TRIVIA_CATEGORIES.get(category.lower())
    url = f"https://opentdb.com/api.php?amount=1&type=multiple"
    if category_id:
        url += f"&category={category_id}"
    if difficulty in ("easy", "medium", "hard"):
        url += f"&difficulty={difficulty}"

    data = fetch_json(url)

    # check if the API returned a valid response
    if not data or data.get("response_code") != 0 or not data.get("results"):
        backup_url = "https://the-trivia-api.com/v2/questions?limit=1"
        backup_data = fetch_json(backup_url)
        if not backup_data or not isinstance(backup_data, list):
            return get_trivia()  # fallback to local trivia

        item = backup_data[0]
        question = item["question"]["text"]
        correct_answer = item["correctAnswer"]
        incorrect_answers = item["incorrectAnswers"]
        category = item.get("category", "General").replace("_", " ").title()
        difficulty = item.get("difficulty", "medium").capitalize()

    else:
        item = data["results"][0]
        question = html.unescape(item["question"])
        correct_answer = html.unescape(item["correct_answer"])
        incorrect_answers = [html.unescape(ans) for ans in item["incorrect_answers"]]
        category = html.unescape(item["category"])
        difficulty = item["difficulty"]

    options = incorrect_answers + [correct_answer]
    random.shuffle(options)

    # generate commentary using AI
    host_remark = "Let's see if anyone here actually pays attention to the outside world..."
    if commentary:
        try:
            response = genai_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=(
                    f"Trivia Question ({category} - {difficulty}): {question}\n"
                    f"Correct Answer: {correct_answer}\n\n"
                    f"Write a single, dry 1-sentence host introduction to this question in your COI Amon voice."
                    f"(DO NOT give away the answer!)."
                ),
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=150,
                )
            )
            host_remark = response.text.strip()
        except Exception:
            pass  # fallback to default host remark if AI fails

    return {
        "source": "Online Global Trivia",
        "category": category,
        "difficulty": difficulty,
        "host_intro": host_remark,
        "question": question,
        "options": options,
        "correct_answer": correct_answer
    }
