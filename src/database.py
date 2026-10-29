import os
import json
import time
import random
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types
from ai import ask

load_dotenv()  # Load environment variables from .env file

# paths
BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = BASE_DIR / "data" / "cleaned" / "organisedGoesHere.json"
CHROMA_DIR = BASE_DIR / "data" / "chromadb"
COLLECTION_NAME = "buku_teks_sejarah"
BATCH_SIZE = 85

# initialise 
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in .env file.")

genai_client = genai.Client(api_key=api_key)

class GeminiEmbeddingFunction(EmbeddingFunction):
    """Custom chromadb embedding wrapper for Google Gemini API"""

    def __init__(self, task_type: str = "RETRIEVAL_DOCUMENT"):
        self.task_type = task_type

    def __call__(self, input: Documents) -> Embeddings:
        """Generate embeddings for the given input."""
        response = genai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=input,
            config=types.EmbedContentConfig(
                task_type=self.task_type,
                output_dimensionality=768
            )
        )
        return [e.values for e in response.embeddings]

def get_collection(is_query: bool = False):
    """Returns the chromadb collection wired to gemini"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # use query when searching, retrieval when indexing
    task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=GeminiEmbeddingFunction(task_type=task),
        metadata={"hnsw:space": "cosine"}
    )

def build_vector_db():
    """reads cleaned lore chunks and indexes them into a chromadb collection using gemini embeddings"""

    if not CHUNKS_FILE.exists():
        print(f"Error: {CHUNKS_FILE} not found. Run cleanData.py first.")
        return

    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if not chunks:
        print("No chunks found in the file. Exiting.")
        return

    collection = get_collection(is_query=False)
    total = len(chunks)
    print(f"Indexing {total} chunks into the vector database...")

    for startIndex in range(0, total, BATCH_SIZE):
        batch = chunks[startIndex : startIndex + BATCH_SIZE]

        ids = [chunk["id"] for chunk in batch]
        documents = [chunk["text"] for chunk in batch]
        metadatas = [
            {
                "channel": str(chunk.get("channel", "general")),
                "start_time": str(chunk.get("start_time", "")),
                "end_time": str(chunk.get("end_time", "")),
                "authors": ", ".join(chunk.get("authors", [])),
                "message_count": int(chunk.get("message_count", 1)),
                "reactions": ", ".join(chunk.get("top_reactions", []))
            }
            for chunk in batch
        ]

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        endIndex = min(startIndex + BATCH_SIZE, total)
        print(f"Indexed {endIndex}/{total} chunks...")

        if endIndex < total:
            print("adding a delay to avoid overwhelming the API...")
            time.sleep(62)  # slight delay to avoid overwhelming the API

    print(f"Successfully indexed {collection.count()} chunks into chromadb.")

def search(query: str, top_k: int = 4) -> list[dict]:
    """Embeds the user's question via gemini and retrieves the closest chat logs"""
    collection = get_collection(is_query=True)
    total_count = collection.count()
    
    if total_count == 0:
        return []

    pool_size = min(top_k * 3, total_count)
    results = collection.query(query_texts=[query], n_results=pool_size)

    if not results["documents"] or not results["documents"][0]:
        return []

    candidates = []
    # Format the results
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        candidates.append({
            "id": results["ids"][0][i],
            "score": round(1 - distance, 4),  # convert distance to similarity score
            "channel": meta["channel"],
            "time": meta["start_time"],
            "authors": meta["authors"],
            "text": results["documents"][0][i],
        })

    if len(candidates) <= top_k:
        return candidates

    best_matches = candidates[:3]
    remaining_candidates = candidates[3:]
    diverse_picks = random.sample(remaining_candidates, min(top_k - 3, len(remaining_candidates)))

    return best_matches + diverse_picks

MAX_GAP_MINUTES = 30  # maximum time gap in minutes to consider messages as part of the same chunk

def parse_time(time_str: str) -> datetime:
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    except Exception:
        return datetime.min

def fetch_neighbour(collection, matched_chunks: list[dict]) -> list[dict]:
    """for each matched chunk, fetches the previous and next chunk if they are in the same channel and within a 30-minute gap"""
    if not matched_chunks:
        return []

    # calc neighbour chunk ids
    neighbour_ids = set()
    parsed_ids = {} # chunk_id -> int

    for m in matched_chunks:
        chunk_id = m["id"]
        if  chunk_id.startswith("chunk_") and chunk_id.split("_")[1].isdigit():
            num_id = int(chunk_id.split("_")[1])
            parsed_ids[chunk_id] = num_id
            if num_id > 1:
                neighbour_ids.add(f"chunk_{num_id - 1:05d}")
            neighbour_ids.add(f"chunk_{num_id + 1:05d}")

        if not neighbour_ids:
            return matched_chunks

        raw_neighbours = collection.get(ids=list(neighbour_ids), include=["documents", "metadatas"])

        neighbour_map = {}
        for i, n_id in enumerate(raw_neighbours["ids"]):
            neighbour_map[n_id] = {
                "id": n_id,
                "text": raw_neighbours["documents"][i],
                "metadata": raw_neighbours["metadatas"][i] or {}
            }

        expanded_results = []
        seen_ids = set()

        for m in matched_chunks:
            chunk_id = m["id"]
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)

            if chunk_id not in parsed_ids:
                expanded_results.append(m)
                continue

            num_id = parsed_ids[chunk_id]
            prev_id = f"chunk_{num_id - 1:05d}"
            next_id = f"chunk_{num_id + 1:05d}"

            channel = m["channel"]
            current_time = parse_time(m["time"])
            current_end_time = parse_time(m["time"] or m.get("end_time"))

            combined_texts = []
            combined_authors = set(author.strip() for author in m["authors"].split(",") if author.strip())
            final_start_str = m["time"]

            # Check previous chunk
            if prev_id in neighbour_map and prev_id not in seen_ids:
                prev_chunk = neighbour_map[prev_id]
                prev_metadata = prev_chunk["metadata"]
                prev_end = parse_time(prev_metadata.get("end_time") or prev_metadata.get("start_time", ""))
                gap_minutes = abs((current_time - prev_end).total_seconds()) / 60.0

                if prev_metadata.get("channel") == channel and gap_minutes <= MAX_GAP_MINUTES:
                    combined_texts.append(f"[Earlier in the conversation...\n{prev_chunk['text']}]")
                    for author in prev_metadata.get("authors", "").split(","):
                        if author.strip():
                            combined_authors.add(author.strip())
                    final_start_str = prev_metadata.get("start_time", final_start_str)
                    seen_ids.add(prev_id)

            # Add current chunk
            combined_texts.append(m["text"])

            # Check next chunk
            if next_id in neighbour_map and next_id not in seen_ids:
                next_chunk = neighbour_map[next_id]
                next_metadata = next_chunk["metadata"]
                next_start = parse_time(next_metadata.get("start_time", ""))
                gap_minutes = abs((next_start - current_end_time).total_seconds()) / 60.0

                if next_metadata.get("channel") == channel and gap_minutes <= MAX_GAP_MINUTES:
                    combined_texts.append(f"[Continuing the conversation...]\n{next_chunk['text']}")
                    for author in next_metadata.get("authors", "").split(","):
                        if author.strip():
                            combined_authors.add(author.strip())
                    seen_ids.add(next_id)

            expanded_results.append({
                "id": chunk_id,
                "score": m["score"],
                "channel": channel,
                "time": final_start_str,
                "authors": ", ".join(sorted(combined_authors)),
                "text": "\n\n".join(combined_texts)
            })
        return expanded_results

def search_lore(query: str, top_k: int = 6, expand_context: bool = True) -> list[dict]:
    """Retrieves relevant chat logs with diversity and auto attach the neighbouring chunks if convo is split across chunks."""
      

if __name__ == "__main__":
    build_vector_db()

    print("\n--- Sample Search ---")
    while True:
        q = input("\n Ask a question (or type 'q' to quit): ").strip()
        if not q or q.lower() == 'q':
            break
        print("\nSearching for relevant chat logs...")
        answer = ask(q)
        print("\n" + "=" * 60)
        print(answer)
        print("=" * 60)