import os
import chromadb
from chromadb.utils import embedding_functions
from google import genai
from dotenv import load_dotenv

load_dotenv()

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

def search(query: str, top_k: int = 5) -> list[dict]:
    """Searches the bot's live quote archive."""
    collection = get_collection()
    
    if collection.count() == 0:
        return []

    # query the database
    results = collection.query(query_texts=[query], n_results=top_k)

    if not results["documents"] or not results["documents"][0]:
        return []

    candidates = []
    # format the results to match ai.py expects
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i]
        
        candidates.append({
            "id": results["ids"][0][i],
            "channel": meta.get("channel", "unknown"),
            "time": "Recent", # The bot doesn't save timestamps yet, so we use a placeholder
            "authors": meta.get("messager_name", "Unknown User"), 
            "text": results["documents"][0][i],
        })

    return candidates

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