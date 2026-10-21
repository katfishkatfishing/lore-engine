import json
import re
from datetime import datetime
from pathlib import Path

#configs
TIME_GAP_THRESHOLD = 300
MAX_MESSAGES_PER_CHUNK = 15
RAW_FILE = Path("data/raw/chatexportGoesHere.json")
OUTPUT_FILE = Path("data/cleaned/organisedGoesHere.json")

#ignore bot commands
BOT_PREFIXES = ("!", "/", "?", "-", "$")

def parse_iso_time(ts_string: str) -> datetime:
    """Parses ISO 8601 timestamp from chatlog"""
    # Remove timezone info if present
    clean_ts = ts_string.split(".")[0].replace("Z", "")
    if "+" in clean_ts:
        clean_ts = clean_ts.split("+")[0]
    return datetime.fromisoformat(clean_ts)

def clean_text(content:str) -> str:
    """Removes URLS, custom emojis, and extra whitespace from text"""
    if not content:
        return ""
    # Remove URLs
    text = re.sub(r"http?://\S+", "", content)
    # Remove custom emojis
    text = re.sub(r"<a?:([a-zA-Z0-9_]+):\d+>", r":\1:", text)
    # turns mention ids into @username
    text = re.sub(r"<@!?\d+>", "@username", text)
    return text.strip()

def process_messages():
    if not RAW_FILE.exists():
        print(f"Raw file {RAW_FILE} does not exist. Drop your export into data/raw/ first.")
        return

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        rawData = json.load(f)

        rawMessages = rawData.get("messages", [])
        channelName = rawData.get("channel", {}).get("name", "general")
        print(f"Processing {len(rawMessages)} raw messages. Beginning filtering and chunking messages...")

        chunks = []
        currentChunk = []
        lastTimestamp = None

        for msg in rawMessages:
            content = msg.get("content", "").strip()
            author = msg.get("author", {}).get("name", "Unknown")

            # skip bot commands, webhooks, and empty attachments
            if not content or content.startswith(BOT_PREFIXES) or msg.get("author", {}).get("isBot", False):
                continue

            sanitisedContent = clean_text(content)
            if not sanitisedContent:
                continue  # skip messages that are empty after cleaning

            try:
                msgTimestamp = parse_iso_time(msg["timestamp"])
            except Exception:
                continue  # skip messages with invalid timestamps

            #check if we need to start a new chunk
            timeGap = (msgTimestamp - lastTimestamp).total_seconds() if lastTimestamp else 0
            shouldSplit = (
                timeGap > TIME_GAP_THRESHOLD or len(currentChunk) >= MAX_MESSAGES_PER_CHUNK
            )

            if shouldSplit and currentChunk:
                chunks.append(finaliseChunk(currentChunk, channelName, len(chunks) + 1))
                currentChunk = []

            #get reactions
            reactions = [r.get("emoji", {}).get("name", "") for r in msg.get("reactions", [])]

            currentChunk.append({
                "author": author,
                "content": sanitisedContent,
                "time": msgTimestamp,
                "reactions": reactions
            })
            lastTimestamp = msgTimestamp

        # flush final chunk
        if currentChunk:
            chunks.append(finaliseChunk(currentChunk, channelName, len(chunks) + 1))

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)

        print(f"Finished processing. {len(chunks)} chunks written to {OUTPUT_FILE}.")

def finaliseChunk(msgList: list, channel: str, chunkIndex: int) -> dict:
    """Finalises a chunk of messages into a indexed chunk"""
    authors = sorted(list(set(msg['author'] for msg in msgList)))
    startStr = msgList[0]["time"].strftime("%Y-%m-%d %H:%M")
    endStr = msgList[-1]["time"].strftime("%Y-%m-%d %H:%M")

    # format transcript lines
    transcript = "\n".join([f"{m['author']}: {m['text']}" for m in msgList])

    #aggregate reactions
    allReactions = []
    for m in msgList:
        allReactions.extend([r for r in m["reactions"] if r])

    return {
        "id": f"chunk_{chunkIndex:04d}",
        "channel": channel,
        "start_time": startStr,
        "end_time": endStr,
        "authors": authors,
        "text": transcript,
        "message_count": len(msgList),
        "top_reactions": list(set(allReactions))[:5] #limit to top 5 unique reactions
    }

# Entry point
if __name__ == "__main__":
    process_messages()



        

