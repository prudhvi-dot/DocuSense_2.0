import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
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


@router.put("/{chat_id}")
def chat(
    chat: ChatMessageRequest,
    chat_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    question = chat.question
    doc_id = chat.doc_id

    human_message = models.Message(chat_id=chat_id, role="ai", message=question)
    db.add(human_message)

    result = chatbot.invoke(
        {"question": question, "messages": [HumanMessage(content=question)]},
        config={
            "configurable": {
                "thread_id": chat_id,
                "user_id": current_user.id,
                "doc_id": doc_id,
            }
        },
    )

    ai_message = models.Message(
        chat_id=chat_id, role="ai", message=result["messages"][-1].content
    )
    db.add(ai_message)

    db.commit()

    return {"ai_response": result["messages"][-1].content}
