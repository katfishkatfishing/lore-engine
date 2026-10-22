import json
from pathlib import Path

DATA_DIR = Path("data/cleaned/loreChunks.json")

def inspect():
    if not DATA_DIR.exists():
        print("Run cleanData.py first")
        return

    with open(DATA_DIR,"r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Total conversational chunks: {len(chunks)}")
    print("-", * 50)
    print("Sample Chunk (Index 0):")
    print(json.dumps(chunks[0], indent=2))
    print("-", * 50)

    while True:
        query = input("Enter a chunk index to inspect (or 'q' to quit): ").strip().lower()

        if query == 'q':
            break
        matches = [c for c in chunks if query in c["text"].lower()]
        print(f"Found {len(matches)} matching chunks.")
        for m in matches[:2]:
            print(f"\n[{m['start_time']} | {', '.join(m['authors'])}]:\n{m['text']}\n")

if __name__ == "__main__":
    inspect()