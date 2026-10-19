from datetime import datetime, timezone


def normalize_message(
    source,
    message_id,
    sender,
    text,
    timestamp,
    subject=None,
    conversation_id=None,
    user_id=None,
    account_id=None,
    reply_to_message_id=None,
):
    return {
        "user_id": user_id,
        "account_id": account_id,
        "source": source,
        "message_id": str(message_id),
        "conversation_id": str(conversation_id or message_id),
        "reply_to_message_id": (
            str(reply_to_message_id)
            if reply_to_message_id is not None
            else None
        ),
        "sender": sender,
        "subject": subject,
        "text": text,
        "timestamp": timestamp,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }