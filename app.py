from flask import Flask, render_template, request, jsonify
from google import genai
import json
import math
import traceback

app = Flask(__name__)
client = genai.Client()

chat_sessions = {}


def load_documents():
    with open("docs.json", "r", encoding="utf-8") as file:
        return json.load(file)


def chunk_text(text, chunk_size=80, overlap=20):
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap

    return chunks


def prepare_chunks(documents):
    all_chunks = []

    for doc in documents:
        title = doc["title"]
        content = doc["content"]

        for idx, chunk in enumerate(chunk_text(content)):
            all_chunks.append({
                "title": title,
                "chunk_id": idx,
                "text": chunk
            })

    return all_chunks


def generate_embedding(text):
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )

    # SDK response shape can vary slightly by version
    if hasattr(result, "embeddings") and result.embeddings:
        first = result.embeddings[0]
        if hasattr(first, "values"):
            return list(first.values)

    raise ValueError("Failed to read embedding response")


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def build_vector_store(chunks):
    store = []

    for chunk in chunks:
        embedding = generate_embedding(chunk["text"])
        store.append({
            "title": chunk["title"],
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "embedding": embedding
        })

    return store


def get_recent_history(session_id, max_pairs=5):
    history = chat_sessions.get(session_id, [])
    return history[-(max_pairs * 2):]


def build_prompt(context_chunks, history, user_question):
    context_text = "\n\n".join(
        [f"[{i+1}] {chunk['title']}: {chunk['text']}" for i, chunk in enumerate(context_chunks)]
    )

    history_text = "\n".join(
        [f"{msg['role'].capitalize()}: {msg['content']}" for msg in history]
    )

    return f"""
You are a grounded support assistant.

Rules:
1. Answer only from the provided context.
2. If the context does not contain the answer, say:
   "I could not find enough information in the provided documents."
3. Keep the answer clear and concise.
4. Do not invent facts.

Context:
{context_text}

Conversation History:
{history_text}

User Question:
{user_question}
""".strip()


documents = load_documents()
all_chunks = prepare_chunks(documents)
vector_store = build_vector_store(all_chunks)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400

        session_id = str(data.get("sessionId", "")).strip()
        user_message = str(data.get("message", "")).strip()

        if not session_id:
            return jsonify({"error": "sessionId is required"}), 400

        if not user_message:
            return jsonify({"error": "message is required"}), 400

        query_embedding = generate_embedding(user_message)

        scored_chunks = []
        for item in vector_store:
            score = cosine_similarity(query_embedding, item["embedding"])
            scored_chunks.append({
                "title": item["title"],
                "chunk_id": item["chunk_id"],
                "text": item["text"],
                "score": score
            })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        top_chunks = scored_chunks[:3]
        best_score = top_chunks[0]["score"] if top_chunks else 0.0

        if session_id not in chat_sessions:
            chat_sessions[session_id] = []

        recent_history = get_recent_history(session_id)

        if best_score < 0.45:
            reply = "I could not find enough information in the provided documents."
            tokens_used = None
        else:
            prompt = build_prompt(top_chunks, recent_history, user_message)

            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt
            )

            reply = response.text if hasattr(response, "text") else "No response generated."
            tokens_used = None

        chat_sessions[session_id].append({"role": "user", "content": user_message})
        chat_sessions[session_id].append({"role": "assistant", "content": reply})
        chat_sessions[session_id] = chat_sessions[session_id][-10:]

        return jsonify({
            "reply": reply,
            "tokensUsed": tokens_used,
            "retrievedChunks": len(top_chunks),
            "similarityScores": [round(chunk["score"], 4) for chunk in top_chunks]
        })

    except Exception as e:
        print("ERROR:", str(e))
        traceback.print_exc()
        return jsonify({
            "error": "Server error",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)