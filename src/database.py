import os
import json
import chromadb
from pathlib import Path
from chromadb.utils import embedding_functions
from google import genai
from dotenv import load_dotenv

load_dotenv()

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

def get_collection():
    """Connects exactly to the Discord bot's live ChromaDB archive!"""
    # force path to look at root lore engine folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    db_path = os.path.join(root_dir, "library_db")
    
    chroma_client = chromadb.PersistentClient(path=db_path)
    default_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    return chroma_client.get_or_create_collection(
        name="server_quotes", 
        embedding_function=default_ef
    )

def search(query: str, top_k: int = 20) -> list[dict]:
    """Searches the bot's live quote archive."""
    collection = get_collection()
    total_count = collection.count()
    
    if collection.count() == 0:
        return []

    query_lower = query.lower()

    # query the database
    meta_sample = collection.get(limit=5000, include=["metadatas"])
    known_names = {
        m.get("messager_name")
        for m in (meta_sample.get("metadatas") or [])
        if isinstance(m, dict) and m.get("messager_name")
    }
    matched_authors = [name for name in known_names if name.lower() in query_lower]

    seen_ids = set()
    candidates = []


    def add_results(results):
        if not results or not results.get("documents") or not results["documents"][0]:
            return
        for i in range(len(results["documents"][0])):
            doc_id = results["ids"][0][i]
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            meta = results["metadatas"][0][i] or {}
            candidates.append({
                "id": results["ids"][0][i],
                "channel": meta.get("channel", "unknown"),
                "time": "Recent", # The bot doesn't save timestamps yet, so we use a placeholder
                "authors": meta.get("messager_name", "Unknown User"), 
                "text": results["documents"][0][i],
            })
    limit = min(top_k, total_count)

    if matched_authors:
        author_results = collection.query(
            query_texts=[query],
            n_results=limit,
            where={"messager_name": {"$in": matched_authors}}
        )
        add_results(author_results)

    general_results = collection.query(
        query_texts=[query],
        n_results=limit,
    )
    add_results(general_results)
    
    return candidates[:top_k]

def load_chunks() -> list[dict]:
    """Loads the cleaned lore chunks from the JSON file."""
    if not CHUNKS_FILE.exists():
        print(f"Error: {CHUNKS_FILE} not found. Run cleanData.py first.")
        return []

    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    return chunks

if __name__ == "__main__":

    from ai import ask
    
    collection = get_collection()
    print(f"Connected to library_db! Found {collection.count()} saved quotes.")
    
    print("\n--- Sample Search ---")
    while True:
        q = input("\n Ask a question (or type 'q' to quit): ").strip()
        if not q or q.lower() == 'q':
            break
        print("\nSearching for relevant chat logs...")
        answer = ask(q)
        print("\n" + "=" * 60)
        print(answer['answer'])
        print("=" * 60)
