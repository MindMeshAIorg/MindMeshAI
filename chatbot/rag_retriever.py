import asyncio
from typing import Optional

async def retrieve_context(message: str, user_id: str) -> Optional[str]:
    """
    Retrieve relevant context for chatbot prompt.
    Tries vector retrieval if available; otherwise falls back gracefully to None.
    """
    try:
        from RAG.search_and_retrival import retrieve

        def _sync_retrieve():
            results = retrieve(
                "BAAI/bge-m3",
                question=message,
                user_id=user_id,
                top_k=5,
            )
            if not results:
                return None
            lines = []
            for r in results:
                chat = r.get("chat_name", "Unknown")
                time_str = r.get("time", "")
                text = r.get("text", "")
                lines.append(f"[{chat} | {time_str}]: {text}")
            return "\n".join(lines)

        return await asyncio.to_thread(_sync_retrieve)
    except Exception as e:
        print(f"[RAG Retriever] Error retrieving context for user {user_id}: {e}")
        return None
