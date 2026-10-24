from google.genai import types
from src.database import genai_client, search
from collections import deque

SYSTEM_PROMPT = """
You are the sarcastic, deadpan server historian for this private friend group.
Answer the user's question using ONLY the retrieved Discord chat logs below.
Cite who said what and when. Do not make up events if the logs don't support it.
"""

CHAT_HISTORY = deque(maxlen=5)  # Store the last 5 questions and answers

def ask(question: str, mode: str ="auto", top_k = 8) -> dict:
    """Queries the database for relevant chat logs and generates a response using Gemini AI. Returns answer and sources."""

    search_query = f"{CHAT_HISTORY[-1]['question']} {question}" if CHAT_HISTORY else question
    matches = search(search_query, top_k=top_k)

    if not matches:
        return {
            "answer": "I do not recall any relevant information.",
            "sources": []
        }

    # Format the retrieved chat logs into a single string
    contextBlocks = [
        f"[{match['time']} | #{match['channel']} | {match['authors']}]\n{match['text']}"
        for match in matches
    ]
    contextStr = "\n\n---\n\n".join(contextBlocks)

    mode_instruction = ""
    if mode and mode.lower() != "auto":
        mode_instruction = f"\n Respond specifically in {mode.upper()} MODE.\n"

    recent_context = "\n".join([
        f"User: {item['question']}\nAi: {item['answer']}" for item in CHAT_HISTORY
    ]) if CHAT_HISTORY else "None yet."

    prompt = (
        f"[RETRIEVED CHAT LOGS]\n\n{contextStr}\n\n"
        f"[RECENT CONVERSATION WITH YOU]\n"
        f"User's current question: {question}\n"
        f"{mode_instruction}"
    )


    try:
        response = genai_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.45, 
                max_output_tokens=1500
            )
        )
        answer = response.text

        CHAT_HISTORY.append({"question": question, "answer": answer})

    except Exception as e:
        answer = f"An error occurred while generating the response: {str(e)}"

    return {
        "answer": answer,
        "sources": matches
    }

if __name__ == "__main__":
    # Sample usage
    print("--- Sample Search ---")
    while True:
        q = input("\nAsk a question (or type 'q' to quit): ").strip()
        if not q or q.lower() == 'q':
            break
        print("\nSearching for relevant chat logs...")
        result = ask(q)
        print("\n" + "=" * 60)
        print("Answer:\n", result["answer"])
        print("\nSources:")
        for source in result["sources"]:
            print(f"- [{source['time']} | #{source['channel']} | {source['authors']}] {source['text']}")