from .state import WorkerState, EmailExtractionResult
from langchain_core.messages import SystemMessage, HumanMessage
from .helper import decode_str, strip_html, clean_text
import email
from .model import agent, SYSTEM_PROMPT, FOLDER_MAPPING


def clean_node(state: WorkerState) -> dict:
    """Cleaning Node: extracts sender, subject, and stripped plain text body."""
    raw_bytes = (
        state.raw_bytes if hasattr(state, "raw_bytes") else state["raw_bytes"]
    )
    msg = email.message_from_bytes(raw_bytes)

    # 1. Extract Subject and Sender
    subject = decode_str(msg.get("Subject", "No Subject"))
    sender = decode_str(msg.get("From", "Unknown Sender"))

    # 2. Traverse MIME parts to isolate text (ignoring attachments and images)
    plain_text_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            # Explicitly ignore attachments (files, PDFs, docs, etc.)
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition.lower():
                continue

            content_type = part.get_content_type()
            # Ignore images or non-text MIME types
            if not content_type.startswith("text/"):
                continue

            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded_text = payload.decode(charset, errors="ignore")

                if content_type == "text/plain":
                    plain_text_parts.append(decoded_text)
                elif content_type == "text/html":
                    html_parts.append(decoded_text)
            except Exception:
                continue
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload and content_type.startswith("text/"):
            charset = msg.get_content_charset() or "utf-8"
            decoded_text = payload.decode(charset, errors="ignore")
            if content_type == "text/plain":
                plain_text_parts.append(decoded_text)
            elif content_type == "text/html":
                html_parts.append(decoded_text)

    # 3. Prioritize plain text; fallback to sanitized HTML if no plain text exists
    if plain_text_parts:
        raw_body = "\n".join(plain_text_parts)
    elif html_parts:
        raw_body = strip_html("\n".join(html_parts))
    else:
        raw_body = ""

    cleaned_body = clean_text(raw_body)[:1500]

    # 4. Return the state update dictionary
    return {
        "sender": sender,
        "subject": subject,
        "cleaned_body": cleaned_body,
    }


def classify_node(state: WorkerState) -> dict:
    sender = state.sender if hasattr(state, "sender") else state.get("sender")
    subject = state.subject if hasattr(state, "subject") else state.get("subject")
    cleaned_body = state.cleaned_body if hasattr(state, "cleaned_body") else state.get("cleaned_body")

    user_content = f"""
    From: {sender}
    Subject: {subject}
    Body:\n{cleaned_body}
    """

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    extraction_result: EmailExtractionResult = agent.invoke(messages)

    return {"result": extraction_result}


async def move_email_node(state: WorkerState, imap_pool: "ImapConnectionPool") -> dict:
    mail_uid = state.mail_uid if hasattr(state, "mail_uid") else state["mail_uid"]
    result = state.result if hasattr(state, "result") else state.get("result")

    if not result:
        raise ValueError("Missing classification result in state.")

    category = result.category
    target_folder = FOLDER_MAPPING.get(category)

    # Acquire a dedicated connection from the pool to perform IMAP actions
    async with imap_pool.get_connection() as imap_client:
        await imap_client.select("INBOX")

        # Copy the message to the destination folder
        res, _ = await imap_client.uid("COPY", mail_uid, f'"{target_folder}"')

        if res == "OK":
            # Flag the original message as Deleted and expunge to complete the move
            await imap_client.uid("STORE", mail_uid, "+FLAGS", r"(\Deleted)")
            await imap_client.expunge()
        else:
            raise RuntimeError(
                f"Failed to copy email UID {mail_uid} to {target_folder}"
            )

    # Return the state update dictionary
    return {"moved_to_folder": target_folder}