import json
import re
from datetime import datetime
from pathlib import Path

#configs
TIME_GAP_THRESHOLD = 300
MAX_MESSAGES_PER_CHUNK = 15
RAW_FILE = Path("data/raw")
OUTPUT_FILE = Path("data/cleaned/organisedGoesHere.json")

#ignore bot commands
BOT_PREFIXES = ("!", "/", "?", "-", "$")

def parseIsoTime(ts_string: str) -> datetime:
    """Parses ISO 8601 timestamp from chatlog"""
    # Remove timezone info if present
    clean_ts = ts_string.split(".")[0].replace("Z", "")
    if "+" in clean_ts:
        clean_ts = clean_ts.split("+")[0]
    return datetime.fromisoformat(clean_ts)

def cleanText(content:str) -> str:
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

def processMessages(filePath: Path, startChunkIndex: int) -> list[dict]:
    """Processes json export into cleaned and chunked messages"""

    try:
        with open(filePath, "r", encoding="utf-8") as f:
            rawData = json.load(f)
    except Exception as e:
        print(f"Err skipping {filePath.name} (Invalid JSON: {e})")
        return []

    rawMessages = rawData.get("messages", [])
    if not rawMessages:
        print(f"No messages found in {filePath.name}. Skipping.")
        return []
    
    channelName = rawData.get("channel", {}).get("name", filePath.stem)

    rawMessages.sort(key=lambda x: x.get("timestamp", ""))  # sort by timestamp
    print(f"Processing {len(rawMessages)} raw messages. Beginning filtering and chunking messages...")

    chunks = []
    currentChunk = []
    lastTimestamp = None
    seenMessageIds = set()

    for msg in rawMessages:

        msgId = msg.get("id")
        if not msgId or msgId in seenMessageIds:
            continue  # skip messages without IDs or duplicates
        if msgId:
            seenMessageIds.add(msgId)

        content = msg.get("content", "").strip()
        author = msg.get("author", {}).get("name", "Unknown")

        # skip bot commands, webhooks, and empty attachments
        if not content or content.startswith(BOT_PREFIXES) or msg.get("author", {}).get("isBot", False):
            continue

        sanitisedContent = cleanText(content)
        if not sanitisedContent:
            continue  # skip messages that are empty after cleaning

        try:
            msgTimestamp = parseIsoTime(msg["timestamp"])
        except Exception:
            continue  # skip messages with invalid timestamps

        #check if we need to start a new chunk
        timeGap = (msgTimestamp - lastTimestamp).total_seconds() if lastTimestamp else 0
        shouldSplit = (
            timeGap > TIME_GAP_THRESHOLD or len(currentChunk) >= MAX_MESSAGES_PER_CHUNK
        )

        if shouldSplit and currentChunk:
            chunkId = startChunkIndex + len(chunks) + 1
            chunks.append(finaliseChunk(currentChunk, channelName, chunkId))
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
        chunkId = startChunkIndex + len(chunks) + 1
        chunks.append(finaliseChunk(currentChunk, channelName, chunkId))

    print(f" + {filePath.name} (#{channelName}): {len(rawMessages)} messages processed, {len(chunks)} chunks created.")
    return chunks


def finaliseChunk(msgList: list, channel: str, chunkIndex: int) -> dict:
    """Finalises a chunk of messages into a indexed chunk"""
    authors = sorted(list(set(msg['author'] for msg in msgList)))
    startStr = msgList[0]["time"].strftime("%Y-%m-%d %H:%M")
    endStr = msgList[-1]["time"].strftime("%Y-%m-%d %H:%M")

    # format transcript lines
    transcript = "\n".join([f"{m['author']}: {m['content']}" for m in msgList])

    #aggregate reactions
    allReactions = []
    for m in msgList:
        allReactions.extend([r for r in m["reactions"] if r])

    return {
        "id": f"chunk_{chunkIndex:05d}",
        "channel": channel,
        "start_time": startStr,
        "end_time": endStr,
        "authors": authors,
        "text": transcript,
        "message_count": len(msgList),
        "top_reactions": list(set(allReactions))[:5] #limit to top 5 unique reactions
    }

def processAllFiles():
    if not RAW_FILE.exists():
        RAW_FILE.mkdir(parents=True, exist_ok=True)
        print(f"Created {RAW_FILE} directory. Place your raw JSON files here and re-run the script.")
        return

    jsonFiles = sorted(RAW_FILE.glob("*.json"))
    if not jsonFiles:
        print(f"no json files found in {RAW_FILE}")
        return

    print(f"Found {len(jsonFiles)} JSON file(s) in {RAW_FILE}. Processing...")

    allChunks = []
    for file_path in jsonFiles:
        newChunks = processMessages(file_path, len(allChunks))
        allChunks.extend(newChunks)

    # sort all chunks by start_time before saving
    allChunks.sort(key=lambda c: c["start_time"])

    # re-index chunks after sorting
    for idx, chunk in enumerate(allChunks, start=1):
        chunk["id"] = f"chunk_{idx:05d}"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(allChunks, f, indent=2, ensure_ascii=False)

    print(f"\nSucessfully merged {len(allChunks)} total chunks across {len(jsonFiles)} files into {OUTPUT_FILE}.")

# Entry point
if __name__ == "__main__":
    processAllFiles()



        

