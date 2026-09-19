import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
)
from app.config.database import get_db
from app.models import models
from app.RAG.retrieve import chatbot
from app.schemas import ChatMessageRequest

router = APIRouter()


@router.get("/{doc_id}/get_messages", status_code=status.HTTP_200_OK)
def get_all_messages(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):

    result = db.execute(select(models.Chat).where(models.Chat.document_id == doc_id))
    chat = result.scalars().first()

    messages_result = db.execute(
        select(models.Message).where(models.Message.chat_id == chat.id)
    )
    messages = messages_result.scalars().all()

    return {"messages": messages}


@router.put("/{doc_id}")
def chat(
    chat: ChatMessageRequest,
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    question = chat.question

    doc = (
        db.execute(select(models.Document).where(models.Document.id == doc_id))
        .scalars()
        .first()
    )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this chat",
        )

    chat_id = doc.chat.id

    def generate():
        allowed_nodes = {"generate", "revise_answer", "conversation_generate"}
        streamed_run_id = None
        stream_finished = False
        hit_no_answer_found = False

        try:
            for stream_mode, payload in chatbot.stream(
                {"question": question, "messages": [HumanMessage(content=question)]},
                config={
                    "configurable": {
                        "thread_id": chat_id,
                        "doc_id": doc_id,
                    }
                },
                stream_mode=["messages", "updates"],
            ):
                if stream_mode == "updates":
                    if "no_answer_found" in payload:
                        hit_no_answer_found = True
                    continue

                # stream_mode == "messages"
                message, metadata = payload
                node = metadata.get("langgraph_node")
                run_id = metadata.get("run_id")

                if node not in allowed_nodes or stream_finished:
                    continue

                if streamed_run_id is None:
                    streamed_run_id = run_id
                elif run_id != streamed_run_id:
                    stream_finished = True
                    continue

                if not message.content or not isinstance(message.content, str):
                    continue

                yield json.dumps({"type": "token", "content": message.content}) + "\n"

            final_state = chatbot.get_state(
                {
                    "configurable": {
                        "thread_id": chat_id,
                        "doc_id": doc_id,
                    }
                }
            )
            final_answer = final_state.values.get("answer", "")

            if hit_no_answer_found:
                for word in final_answer.split(" "):
                    yield json.dumps({"type": "token", "content": word + " "}) + "\n"
                    time.sleep(0.03)

            human_message = models.Message(
                chat_id=chat_id, role="human", message=question
            )
            ai_message = models.Message(
                chat_id=chat_id, role="ai", message=final_answer
            )
            db.add_all([human_message, ai_message])
            db.commit()

            yield json.dumps({"type": "final", "content": final_answer}) + "\n"

        except Exception:
            db.rollback()
            yield (
                json.dumps(
                    {"type": "error", "message": "Failed to generate a response."}
                )
                + "\n"
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
    )
