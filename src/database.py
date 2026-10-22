import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chrommadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types

load_dotenv()  # Load environment variables from .env file

# paths
CHUNKS_FILE = Path("data/clean/lore_chunks.json")
CHROMA_DIR = Path("data/chromadb")
COLLECTION_NAME = "buku_teks_sejarah"
BATCH_SIZE = 250

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
            config=types.EmbedContentCOnfig(
                task_type=self.task_type,
                output_dimensionality=768
            )
        )
        return [e.values for e in response.embeddings]

def get_collection(is_query: bool = False):
    """Returns the chromadb collection wired to gemini"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistantClient(path=str(CHROMA_DIR))

    # use query when searching, retrieval when indexing
    task = "RETRIEVAL_DOCUMENT" if is_query else "RETRIEVAL_DOCUMENT"

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

        time.sleep(0.5)  # slight delay to avoid overwhelming the API

    print(f"Successfully indexed {collection.count()} chunks into chromadb.")

def search(query: str, top_k: int = 4) -> list[dict]:
    """Embeds the user's question via gemini and retrieves the closest chat logs"""
    collection = get_collection(is_query=True)
    if collection.count() == 0:
        return []

    results = collection.query(query_texts=[query], n_results=top_k)
    formatted = []

    if not results["documents"] or not results["documents"][0]:
        return formatted

    # Format the results
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i]
        distance = results["distance"][0][i]
        formatted.append({
            "id": results["ids"][0][i],
            "score": round(1 - distance, 4),  # convert distance to similarity score
            "channel": meta["channel"],
            "time": meta["start_time"],
            "authors": meta["authors"],
            "text": results["documents"][0][i],
        })
    return formatted