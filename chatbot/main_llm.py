import asyncio
import os
import sys
import traceback
from pathlib import Path

CHATBOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CHATBOT_DIR.parent

for p in (CHATBOT_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv

load_dotenv()  # must run before TypeSafeClient() so the API key is loaded

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chatbot.llm import generate_answer
from chatbot.memory import (
    get_recent_messages,
    save_message,
    get_long_term_memory,
    remember,
)
from chatbot.rag_retriever import retrieve_context
from typesafe_sdk import TypeSafeClient, Choice

jev_client = TypeSafeClient()

# Retrieve when Jev's probability of YES is at least this value.
# LOWER  = retrieves more often (safer, more RAG)
# HIGHER = retrieves less often (fewer RAG calls on casual chat)
YES_THRESHOLD = float(os.getenv("RAG_YES_THRESHOLD", "0.35"))


def should_use_rag(message, history=None, memories=None):
    history = history or []
    memories = memories or []

    try:
        response = jev_client.system_one(
            state={
                "latest_message": message,
                "recent_conversation": str(history)[-2000:],
                "saved_memories": str(memories)[-1000:],
            },
            questions={
                "rag_decision": Choice(
                    instructions=(
                        "Decide whether `latest_message` requires searching "
                        "the user's personal connected data (Gmail, Telegram, "
                        "WhatsApp, tasks, deadlines). Use `recent_conversation` "
                        "and `saved_memories` to check whether the answer is "
                        "already available. Understand the actual meaning and "
                        "intention of the message, not just keywords. When "
                        "uncertain, choose YES."
                    ),
                    criteria={
                        "YES": (
                            "Choose this category when the user asks about "
                            "their emails, chats, or connected accounts; "
                            "their assignments, tasks, deadlines, or "
                            "meetings; information that may exist in their "
                            "connected personal data; or a follow-up "
                            "question that requires retrieved personal data. "
                            "Examples: 'What deadlines do I have this week?', "
                            "'Did anyone message me about the hackathon?', "
                            "'What did he say about the meeting?'"
                        ),
                        "NO": (
                            "Choose this category for greetings or casual "
                            "conversation, general knowledge or programming "
                            "questions, and questions already answerable "
                            "from `recent_conversation` or `saved_memories`. "
                            "Examples: 'Hi', 'Explain Python decorators', "
                            "'Thanks!'. Do not choose this category if the "
                            "message could depend on the user's personal "
                            "data."
                        ),
                    },
                )
            },
        )

        answer = response.answers["rag_decision"]
        probs = getattr(answer, "probabilities", None) or {}
        p_yes = probs.get("YES")

        print(
            f"[router] msg={message[:60]!r} choice={answer.choice} "
            f"p_yes={p_yes} confidence={getattr(answer, 'confidence', None)}"
        )

        # Preferred: decide on the YES probability.
        if p_yes is not None:
            return p_yes >= YES_THRESHOLD

        # Fallback if the SDK doesn't expose probabilities.
        return answer.choice != "NO"

    except Exception:
        print("[router] FAILED, defaulting to RAG:")
        traceback.print_exc()
        # Safely retrieve context if routing fails.
        return True


app = FastAPI(title="MindMeshAI Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://localhost:5137",
        ).split(",")
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(min_length=1, max_length=128)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "MindMeshAI Chatbot",
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    message = request.message.strip()
    user_id = request.user_id.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID cannot be empty.",
        )

    if message.lower().startswith("remember:"):
        fact = message[len("remember:"):].strip()

        if not fact or len(fact) > 300:
            raise HTTPException(
                status_code=400,
                detail="Memory must be 1 to 300 characters.",
            )

        remember(user_id, fact)

        return {
            "answer": "I'll remember that for future conversations."
        }

    try:
        history = get_recent_messages(user_id)
        memories = get_long_term_memory(user_id)

        # Ask Jev whether personal data retrieval is necessary.
        # Run in a thread so the blocking SDK call doesn't stall the server.
        needs_rag = await asyncio.to_thread(
            should_use_rag,
            message,
            history=history,
            memories=memories,
        )

        context = ""

        # Search personal data only when necessary.
        if needs_rag:
            context = await retrieve_context(message, user_id)

        # Generate the final response.
        answer = generate_answer(
            message,
            context=context,
            history=history,
            memories=memories,
        )

        save_message(user_id, "user", message)
        save_message(user_id, "assistant", answer)

        return {
            "answer": answer,
            "used_rag": needs_rag,
        }

    except Exception as e:
        traceback.print_exc()

        raise HTTPException(
            status_code=502,
            detail=f"Chatbot failed: {type(e).__name__}: {e}",
        )