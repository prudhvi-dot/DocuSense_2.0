import re
from typing import Annotated, Literal, TypedDict

from app.config.config import settings
from app.RAG.config import get_vectorstore
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DB_URI = settings.DATABASE_URL

llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0)

UPPER_TH = 0.7
LOWER_TH = 0.3


class State(TypedDict):
    question: str
    retrieval_query: str
    messages: Annotated[list[BaseMessage], add_messages]

    route: str

    docs: list[Document]
    good_docs: list[Document]
    verdict: str
    reason: str

    strips: list[str]
    kept_strips: list[str]
    refined_context: str

    answer: str
    context: str

    issup: Literal["fully_supported", "partially_supported", "no_support"]
    issup_retries: int

    isuse: Literal["useful", "not_useful"]
    use_reason: str

    retrieval_retries: int
    rewrite_tries: int


class RouteDecision(BaseModel):
    route: Literal["document", "conversation"] = Field(
        ...,
        description="Route the question to document retrieval or conversation history.",
    )


route_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You decide how the user's question should be answered.

            Choose one route:

            - "conversation":
              The question is EXPLICITLY about the conversation itself, prior turns,
              or what was previously said — not about any external topic or the document's content.
              Examples:
              - "What did I ask you before?"
              - "What was my first question?"
              - "What did you just tell me?"
              - "What were we discussing earlier?"

            - "document":
              Everything else — including questions about the document's content,
              general knowledge questions, and anything not explicitly about the
              conversation's own history. This is the DEFAULT route.
              Examples:
              - "Why did Elias use the emergency bell?"
              - "Summarize the document."
              - "Who is Pawan Kalyan?" (not about our conversation — route to document,
                 where retrieval will correctly report if it's not covered)

            Rule: only choose "conversation" if the question is unambiguously about
            the chat history itself. If there is ANY doubt, choose "document" — the
            document pipeline already handles "not found" gracefully, while the
            conversation route does not.

            Return only the structured output.
            """,
        ),
        ("human", "Question: {question}"),
    ]
)

route_llm = llm.with_structured_output(RouteDecision)

route_chain = route_prompt | route_llm


def decide_route(state: State):
    decision: RouteDecision = route_chain.invoke({"question": state["question"]})

    return {"route": decision.route}


def route_after_decision(state: State):
    if state["route"] == "conversation":
        return "conversation"

    return "document"


conversation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a conversation-aware assistant.

            Answer the user's question using the previous conversation messages.

            Rules:
            - Use the previous messages to understand what the user is referring to.
            - If the user asks what they previously asked, identify the relevant
              question from the conversation history.
            - Do not invent previous questions, answers, or events.
            - If the requested information is not present in the conversation,
              say that you cannot answer something that is not in the document or in the Conversation history.
            - Answer directly and concisely.
            """,
        ),
        (
            "human",
            """Previous conversation:
{previous_messages}

Current question:
{question}""",
        ),
    ]
)

conversation_chain = conversation_prompt | llm


def conversation_generate(state: State):
    messages = state["messages"]

    out = conversation_chain.invoke(
        {
            "previous_messages": messages,
            "question": state["question"],
        }
    )

    return {
        "answer": out.content,
        "messages": [out],
    }


# def retrieve(state: State, config: RunnableConfig):
#     user_id = config["configurable"]["user_id"]
#     doc_id = config["configurable"]["doc_id"]

#     vector_store = get_vectorstore()

#     q = state.get("retrieval_query") or state["question"]

#     retriever = vector_store.as_retriever(
#         search_kwargs={
#             "namespace": user_id,
#             "filter": {"doc_id": doc_id},
#             "k": 5,
#         }
#     )

#     docs = retriever.invoke(q)

#     return {"docs": docs}

import time


def retrieve(state: State, config: RunnableConfig):
    start = time.perf_counter()

    user_id = config["configurable"]["user_id"]
    doc_id = config["configurable"]["doc_id"]

    vector_store = get_vectorstore()

    t1 = time.perf_counter()

    q = state.get("retrieval_query") or state["question"]

    retriever = vector_store.as_retriever(
        search_kwargs={
            "namespace": doc_id,
            # "filter": {"doc_id": doc_id},
            "k": 5,
        }
    )

    t2 = time.perf_counter()

    docs = retriever.invoke(q)

    t3 = time.perf_counter()

    print(f"get_vectorstore: {t1 - start:.3f}s")
    print(f"retriever setup: {t2 - t1:.3f}s")
    print(f"retriever.invoke: {t3 - t2:.3f}s")
    print(f"TOTAL retrieve: {t3 - start:.3f}s")

    return {"docs": docs}


class DocEvalScore(BaseModel):
    score: float


doc_eval_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a retrieval relevance evaluator for a RAG system.

You will be given ONE retrieved document chunk and a user's question.

Return a relevance score between 0.0 and 1.0.

Scoring:
- 1.0: highly relevant; contains important information needed to answer the question.
- 0.7-0.9: clearly relevant and useful.
- 0.4-0.6: somewhat relevant or contains supporting information.
- 0.1-0.3: mostly irrelevant.
- 0.0: completely irrelevant.

Important:
- Evaluate whether the chunk is RELEVANT to the question.
- Do NOT require the chunk to answer the entire question by itself.
- For summary questions, a chunk containing any important part of the document should receive a meaningful relevance score.
- Be conservative, but do not reject a chunk simply because it contains only part of the information needed.

Return only the structured score.""",
        ),
        (
            "human",
            "Question: {question}\n\nChunk:\n{chunk}",
        ),
    ]
)

doc_eval_chain = doc_eval_prompt | llm.with_structured_output(DocEvalScore)


def eval_each_doc_node(state: State):
    q = state["question"]
    docs = state["docs"]

    if not docs:
        return {
            "good_docs": [],
            "verdict": "INCORRECT",
        }

    inputs = [
        {
            "question": q,
            "chunk": doc.page_content,
        }
        for doc in docs
    ]

    results = doc_eval_chain.batch(inputs)

    scores = [result.score for result in results]

    good_docs = [doc for doc, score in zip(docs, scores) if score > LOWER_TH]

    if not good_docs:
        return {
            "good_docs": [],
            "verdict": "INCORRECT",
        }

    return {
        "good_docs": good_docs,
        "verdict": "CORRECT",
    }


def route_after_eval(
    state: State,
) -> Literal["refine", "rewrite_query_for_retrieval", "no_answer_found"]:
    if state["verdict"] == "CORRECT":
        return "refine"
    if state.get("retrieval_retries", 0) >= 2:
        return "no_answer_found"
    return "rewrite_query_for_retrieval"


rewrite_for_retrieval_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Rewrite the user's QUESTION into a query optimized for vector retrieval over the uploaded document.
            Rules:
            - Keep it short (6-16 words).
            - Preserve key entities/terms from the question.
            - Add 2-5 high-signal keywords likely to appear in the document.
            - Do NOT answer the question.
            - Output JSON with key: retrieval_query""",
        ),
        (
            "human",
            "QUESTION:\n{question}\n\nPrevious retrieval query:\n{retrieval_query}",
        ),
    ]
)


class RewriteDecision(BaseModel):
    retrieval_query: str = Field(
        ...,
        description="Rewritten query optimized for vector retrieval against the uploaded document.",
    )


rewrite_llm = llm.with_structured_output(RewriteDecision)


def rewrite_query_for_retrieval(state: State):
    decision: RewriteDecision = rewrite_llm.invoke(
        rewrite_for_retrieval_prompt.format_messages(
            question=state["question"], retrieval_query=state.get("retrieval_query", "")
        )
    )
    return {
        "retrieval_query": decision.retrieval_query,
        "retrieval_retries": state.get("retrieval_retries", 0) + 1,
        "docs": [],
        "good_docs": [],
    }


def rewrite_query_for_usefulness(state: State):
    decision: RewriteDecision = rewrite_llm.invoke(
        rewrite_for_retrieval_prompt.format_messages(
            question=state["question"], retrieval_query=state.get("retrieval_query", "")
        )
    )
    return {
        "retrieval_query": decision.retrieval_query,
        "rewrite_tries": state.get("rewrite_tries", 0) + 1,
        "docs": [],
        "good_docs": [],
    }


def decompose_to_sentences(text: str):
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


class KeepOrDrop(BaseModel):
    keep: bool


filter_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a relevance filter for a document-grounded RAG system.

            Decide whether the sentence should be kept as part of the context
            used to answer the question.

            Return keep=true if the sentence:
            - directly answers the question, OR
            - provides necessary context, evidence, cause, explanation, or consequence
              needed to answer the question.

            Keep sentences that are useful when combined with other sentences
            from the same document.

            Do NOT require the sentence to answer the question by itself.

            Return keep=false only when the sentence is clearly unrelated
            to answering the question.

            Output JSON only.""",
        ),
        ("human", "Question: {question}\n\nSentence:\n{sentence}"),
    ]
)

filter_chain = filter_prompt | llm.with_structured_output(KeepOrDrop)


def refine(state: State):
    context = "\n\n".join(d.page_content for d in state["good_docs"]).strip()
    strips = decompose_to_sentences(context)

    refined_context = "\n".join(strips).strip()

    return {"refined_context": refined_context}


rag_generation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You answer questions about the uploaded document.

            Use ONLY the provided context and previous messages.

            Rules:
            - Do not use outside knowledge.
            - Do not introduce facts that are not supported by the context.
            - Answer the user's question directly.
            - If the context does not contain enough information to answer, say that the information is not available in the document.
            """,
        ),
        (
            "human",
            "Question: {question}\n\nContext:\n{refined_context}\n\nPrevious Messages: {previous_messages}",
        ),
    ]
)


def generate(state: State):

    out = (rag_generation_prompt | llm).invoke(
        {
            "question": state["question"],
            "refined_context": state["refined_context"],
            "previous_messages": state["messages"],
        }
    )

    return {
        "answer": out.content,
        "context": state["refined_context"],
        "messages": [out],
    }


class IsSupDecision(BaseModel):
    issup: Literal["fully_supported", "partially_supported", "no_support"]


issup_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are verifying whether the ANSWER is supported by the CONTEXT.
            Return JSON with key: issup.
            issup must be one of: fully_supported, partially_supported, no_support.
            Be strict: any unsupported interpretive phrasing not present in CONTEXT -> partially_supported.
            If key claims are unsupported -> no_support.
            Do not use outside knowledge.""",
        ),
        ("human", "Question:\n{question}\n\nAnswer:\n{answer}\n\nContext:\n{context}"),
    ]
)

issup_llm = llm.with_structured_output(IsSupDecision)


def is_sup(state: State):
    decision: IsSupDecision = issup_llm.invoke(
        issup_prompt.format_messages(
            question=state["question"],
            answer=state.get("answer", ""),
            context=state.get("context", ""),
        )
    )
    return {"issup": decision.issup}


def route_after_issup(
    state: State,
) -> Literal["accept_answer", "revise_answer", "no_answer_found"]:
    if state.get("issup") == "fully_supported":
        return "accept_answer"

    if state.get("issup_retries", 0) >= 2:
        if state.get("issup") == "no_support":
            return "no_answer_found"
        return "accept_answer"

    return "revise_answer"


revise_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a strict answer reviser.

            Rewrite the answer using ONLY information explicitly supported by the CONTEXT.

            Rules:
            - Remove every unsupported claim.
            - Do not introduce new information.
            - You may paraphrase information from the context.
            - Every factual claim must be supported by the context.
            - Answer the question directly and concisely.
            """,
        ),
        ("human", "Question:\n{question}\n\nAnswer:\n{answer}\n\nContext:\n{context}"),
    ]
)


def revise_answer(state: State):
    out = llm.invoke(
        revise_prompt.format_messages(
            question=state["question"],
            answer=state.get("answer", ""),
            context=state.get("context", ""),
        )
    )
    return {"answer": out.content, "issup_retries": state.get("issup_retries", 0) + 1}


class IsUSEDecision(BaseModel):
    isuse: Literal["useful", "not_useful"]
    reason: str = Field(..., description="Short reason in 1 line.")


isuse_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are judging USEFULNESS of the ANSWER for the QUESTION.
            Return JSON with keys: isuse, reason.
            useful: the answer directly addresses the question.
            not_useful: generic, off-topic, or only background info.
            Do NOT re-check grounding — only check whether the question was answered.""",
        ),
        ("human", "Question:\n{question}\n\nAnswer:\n{answer}"),
    ]
)

isuse_llm = llm.with_structured_output(IsUSEDecision)


def is_use(state: State):
    decision: IsUSEDecision = isuse_llm.invoke(
        isuse_prompt.format_messages(
            question=state["question"], answer=state.get("answer", "")
        )
    )
    return {"isuse": decision.isuse, "use_reason": decision.reason}


def route_after_isuse(
    state: State,
) -> Literal["END", "rewrite_query_for_usefulness", "no_answer_found"]:
    if state.get("isuse") == "useful":
        return "END"
    if state.get("rewrite_tries", 0) >= 2:
        return "no_answer_found"
    return "rewrite_query_for_usefulness"


def no_answer_found(state: State):
    return {
        "answer": "I couldn't find information about that in this document. Feel free to ask something else about its contents.",
        "context": "",
    }


def get_chatbot():

    pool = ConnectionPool(
        conninfo=DB_URI,
        min_size=1,
        max_size=5,
        kwargs={
            "autocommit": True,
        },
        check=ConnectionPool.check_connection,
    )

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    # checkpointer = InMemorySaver()

    g = StateGraph(State)
    g.add_node("decision_route", decide_route)
    g.add_node("conversation_generate", conversation_generate)
    g.add_node("retrieve", retrieve)
    g.add_node("eval_each_doc", eval_each_doc_node)
    g.add_node("rewrite_query_for_retrieval", rewrite_query_for_retrieval)
    g.add_node("rewrite_query_for_usefulness", rewrite_query_for_usefulness)
    g.add_node("refine", refine)
    g.add_node("generate", generate)
    g.add_node("is_sup", is_sup)
    g.add_node("revise_answer", revise_answer)
    g.add_node("is_use", is_use)
    g.add_node("no_answer_found", no_answer_found)

    g.add_edge(
        START,
        "decision_route",
    )

    g.add_conditional_edges(
        "decision_route",
        route_after_decision,
        {"document": "retrieve", "conversation": "conversation_generate"},
    )
    # g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "eval_each_doc")
    g.add_conditional_edges(
        "eval_each_doc",
        route_after_eval,
        {
            "refine": "refine",
            "rewrite_query_for_retrieval": "rewrite_query_for_retrieval",
            "no_answer_found": "no_answer_found",
        },
    )
    g.add_edge("rewrite_query_for_retrieval", "retrieve")
    g.add_edge("refine", "generate")
    g.add_edge("generate", "is_sup")
    g.add_conditional_edges(
        "is_sup",
        route_after_issup,
        {
            "accept_answer": "is_use",
            "revise_answer": "revise_answer",
            "no_answer_found": "no_answer_found",
        },
    )
    g.add_edge("revise_answer", "is_sup")
    g.add_conditional_edges(
        "is_use",
        route_after_isuse,
        {
            "END": END,
            "rewrite_query_for_usefulness": "rewrite_query_for_usefulness",
            "no_answer_found": "no_answer_found",
        },
    )
    g.add_edge("rewrite_query_for_usefulness", "retrieve")
    g.add_edge("no_answer_found", END)

    return g.compile(checkpointer=checkpointer)
    # png = app.get_graph().draw_mermaid_png()

    # with open("graph2.png", "wb") as f:
    #     f.write(png)


chatbot = get_chatbot()
