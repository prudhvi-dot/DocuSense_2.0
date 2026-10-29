import re
from typing import Annotated, Literal, TypedDict

from app.config.config import settings
from app.RAG.config import get_vectorstore
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage
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

REQUIRE_SUBJECT_MATCH = True
ACCEPT_THRESHOLD = 0.6
NOT_IN_DOCUMENT = "NOT_IN_DOCUMENT"
NO_ANSWER_MESSAGE = (
    "I couldn't find information about that in this document. "
    "Feel free to ask something else about its contents."
)


class State(TypedDict):
    question: str
    retrieval_query: str
    messages: Annotated[list[BaseMessage], add_messages]

    route: str

    docs: list[Document]
    good_docs: list[Document]
    verdict: str

    refined_context: str

    answer: str
    context: str

    issup: str
    issup_retries: int

    isuse: str
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
  or what was previously said, not about the document's content.
  Examples:
  - "What did I ask you before?"
  - "What was my first question?"
  - "What did you just tell me?"
  - "What were we discussing earlier?"

- "document":
  Everything else, including questions about the document's content,
  summaries, general-knowledge questions, and anything not explicitly about
  the conversation's own history. This is the DEFAULT route.
  Examples:
  - "What is the termination notice period?"
  - "Summarize the document."
  - "Who is the CEO of some unrelated company?" (not about our conversation,
    so route to document, where retrieval will correctly report if it's not covered)

Rule: only choose "conversation" if the question is unambiguously about
the chat history itself. If there is ANY doubt, choose "document".

Return only the structured output.
""",
        ),
        ("human", "Question: {question}"),
    ]
)

route_chain = route_prompt | llm.with_structured_output(RouteDecision)


def decide_route(state: State):
    decision: RouteDecision = route_chain.invoke({"question": state["question"]})

    return {
        "route": decision.route,
        "retrieval_query": "",
        "retrieval_retries": 0,
        "rewrite_tries": 0,
        "issup_retries": 0,
        "issup": "",
        "isuse": "",
        "use_reason": "",
        "docs": [],
        "good_docs": [],
        "verdict": "",
        "refined_context": "",
        "answer": "",
        "context": "",
    }


def route_after_decision(state: State):
    if state["route"] == "conversation":
        return "conversation"
    return "document"


# --------------------------------------------------------------------------
# Conversation route
# --------------------------------------------------------------------------
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
  say that you cannot answer something that is not in the document or in the conversation history.
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
    out = conversation_chain.invoke(
        {
            "previous_messages": state["messages"],
            "question": state["question"],
        }
    )
    return {"answer": out.content, "messages": [out]}


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
def retrieve(state: State, config: RunnableConfig):
    doc_id = config["configurable"]["doc_id"]
    vector_store = get_vectorstore()
    q = state.get("retrieval_query") or state["question"]

    retriever = vector_store.as_retriever(
        search_kwargs={
            "namespace": doc_id,
            "k": 20,
        }
    )
    return {"docs": retriever.invoke(q)}


class DocEvalScore(BaseModel):
    evidence_quote: str = Field(
        ...,
        description="Passage copied verbatim from the chunk that could answer the question. Empty string if none.",
    )
    quote_subject: str = Field(
        ...,
        description="The entity, topic, or item the quoted text is actually about, resolving pronouns and references from the chunk. Empty string if no quote.",
    )
    subject_matches_question: bool = Field(
        ...,
        description="True only if quote_subject is an entity/topic the question asks about.",
    )
    answers_question: bool = Field(
        ...,
        description="True only if the quote explicitly states information that answers the whole question or a meaningful part of it.",
    )
    score: float = Field(..., description="Relevance from 0.0 to 1.0.")


doc_eval_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a careful retrieval relevance evaluator for a RAG system.
The documents can be of any type (contracts, manuals, reports, articles,
fiction, etc.). Do not assume a domain.

You will receive ONE user question and ONE retrieved document chunk.
The chunk may begin or end mid-sentence.

MULTI-PART QUESTIONS:
- Identify the distinct facts or sub-questions being asked.
- A chunk may answer one sub-question without answering the others. Do not
  reject it merely because it does not answer the entire question.
- If the chunk explicitly answers at least one sub-question, set
  answers_question=true.

Fill the fields in this order:
1. evidence_quote: ONE contiguous passage copied VERBATIM from the chunk,
   without skipping words. If the evidence is in two places, join the passages
   with " … ". Use "" if none.
2. quote_subject: the entity, topic, or item that passage is actually about.
   Resolve pronouns and references using the surrounding text in the chunk.
   Use "" if no quote.
3. subject_matches_question: true ONLY if quote_subject is an entity or topic
   the question asks about. Descriptive references count (e.g. "the clerk at
   the front desk" matches a passage about "the woman at the desk"). If the
   question has no specific subject (e.g. a request to summarize), set true
   when the passage is on-topic.
4. answers_question: true ONLY if the passage explicitly states information
   that answers the question or a meaningful part of it, about that subject.
5. score: 0.0 to 1.0.

SCORING:
- 0.8-1.0: Explicitly states an answer or strong evidence for a requested part.
- 0.6-0.7: Explicitly answers a meaningful but limited part of the question.
- 0.3-0.5: Topically related, but does not explicitly answer any requested part.
- 0.0-0.2: Unrelated, or the information concerns a different subject.

RULES:
1. Judge semantic relevance, not keyword overlap.
2. Mentioning an entity from the question is not evidence by itself.
3. Information about a different entity is never evidence, even when both
   appear in the same chunk.
4. For specific lookups (numbers, dates, names, amounts, durations, origins),
   do not infer a value. Accept only if the exact value is stated about the
   exact subject, or the chunk explicitly states that the value is unknown,
   unrecorded, or undetermined.
5. A passage that explicitly says the requested information is unknown or not
   recorded IS evidence and answers the question.
6. Use only the chunk. Never use outside knowledge or inference.
7. If you cannot copy a supporting passage, set evidence_quote="" and
   answers_question=false.

Return only the structured output.""",
        ),
        ("human", "Question: {question}\n\nChunk:\n{chunk}"),
    ]
)

doc_eval_chain = doc_eval_prompt | llm.with_structured_output(DocEvalScore)


def _squash(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.lower())


def _quote_in_text(quote: str, text: str) -> bool:
    """Verify the quote clause by clause so lightly edited quotes still match
    while invented text does not."""
    text_sq = _squash(text)
    clauses = [c for c in re.split(r"\.\.\.|…|[.,;:!?]", quote) if len(_squash(c)) >= 8]
    if not clauses:
        whole = _squash(quote)
        return len(whole) >= 4 and whole in text_sq
    return all(_squash(c) in text_sq for c in clauses)


def _chunk_index(doc):
    try:
        return int(str(doc.id).rsplit("_", 1)[1])
    except (IndexError, ValueError, AttributeError):
        return None


def _window_text(doc, by_idx):
    i = _chunk_index(doc)
    if i is None:
        return doc.page_content
    return "\n\n".join(by_idx[j].page_content for j in (i - 1, i, i + 1) if j in by_idx)


def eval_each_doc_node(state: State):
    q = state["question"]
    docs = state["docs"]

    if not docs:
        return {"good_docs": [], "verdict": "INCORRECT"}

    by_idx = {}
    for d in docs:
        i = _chunk_index(d)
        if i is not None:
            by_idx[i] = d

    windows = [_window_text(d, by_idx) for d in docs]
    inputs = [{"question": q, "chunk": w} for w in windows]
    results = doc_eval_chain.batch(inputs, config={"max_concurrency": 8})

    good_docs = []
    for doc, window, result in zip(docs, windows, results):
        quote = result.evidence_quote.strip()
        accepted = (
            bool(quote)
            and _quote_in_text(quote, window)
            and (result.subject_matches_question or not REQUIRE_SUBJECT_MATCH)
            and result.answers_question
            and float(result.score) >= ACCEPT_THRESHOLD
        )
        if accepted:
            good_docs.append(doc)

    return {
        "good_docs": good_docs,
        "verdict": "CORRECT" if good_docs else "INCORRECT",
    }


def route_after_eval(
    state: State,
) -> Literal["refine", "rewrite_query_for_retrieval", "no_answer_found"]:
    if state["verdict"] == "CORRECT":
        return "refine"
    if state.get("retrieval_retries", 0) >= 1:
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


def _rewrite(state: State) -> str:
    decision: RewriteDecision = rewrite_llm.invoke(
        rewrite_for_retrieval_prompt.format_messages(
            question=state["question"],
            retrieval_query=state.get("retrieval_query", ""),
        )
    )
    return decision.retrieval_query


def rewrite_query_for_retrieval(state: State):
    return {
        "retrieval_query": _rewrite(state),
        "retrieval_retries": state.get("retrieval_retries", 0) + 1,
        "docs": [],
        "good_docs": [],
    }


def rewrite_query_for_usefulness(state: State):
    return {
        "retrieval_query": _rewrite(state),
        "rewrite_tries": state.get("rewrite_tries", 0) + 1,
        "docs": [],
        "good_docs": [],
    }


def refine(state: State):
    """Accepted chunks plus their retrieved neighbours, in reading order,
    de-duplicated, so passages cut at chunk edges are completed."""
    good_docs = state.get("good_docs", [])
    docs = state.get("docs", [])

    by_idx = {}
    for d in docs:
        i = _chunk_index(d)
        if i is not None:
            by_idx[i] = d

    selected = {}
    unindexed = []
    for d in good_docs:
        i = _chunk_index(d)
        if i is None:
            unindexed.append(d)
            continue
        for j in (i - 1, i, i + 1):
            if j in by_idx:
                selected[j] = by_idx[j]

    ordered = [selected[k] for k in sorted(selected)] + unindexed
    parts = [d.page_content.strip() for d in ordered if d.page_content.strip()]
    return {"refined_context": "\n\n".join(parts)}


rag_generation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You answer questions about the uploaded document.

Use ONLY the provided context and previous messages.

Rules:
- Do not use outside knowledge or introduce unsupported facts.
- Context chunks are in reading order and may be cut mid-sentence at their
  edges. When a passage clearly continues in the next chunk, read them together.
- Answer every part of the question that the context supports. For list-style
  questions, include every relevant item found in the context.
- If the context explicitly says the requested information is unknown or not
  recorded, say exactly that, and include what the context does say.
- If the context does not address the question at all, reply with exactly:
  {NOT_IN_DOCUMENT}
""",
        ),
        (
            "human",
            "Question: {question}\n\nContext:\n{refined_context}\n\nPrevious Messages: {previous_messages}",
        ),
    ]
)


def _is_not_in_doc(text: str) -> bool:
    return (text or "").strip().upper().startswith(NOT_IN_DOCUMENT)


def generate(state: State):
    out = (rag_generation_prompt | llm).invoke(
        {
            "question": state["question"],
            "refined_context": state["refined_context"],
            "previous_messages": state["messages"],
        }
    )

    return {"answer": out.content, "context": state["refined_context"]}


def route_after_generate(state: State) -> Literal["is_sup", "no_answer_found"]:
    if _is_not_in_doc(state.get("answer", "")):
        return "no_answer_found"
    return "is_sup"


class IsSupDecision(BaseModel):
    issup: Literal["fully_supported", "partially_supported", "no_support"]


issup_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a strict factual-grounding evaluator for a RAG system.

Your task is to determine whether the ANSWER is supported by the
provided CONTEXT. Use only the context as evidence.

Check every factual claim in the answer individually, including:
- Names, dates, numbers, and quantities
- Relationships and events
- Causes, motivations, and consequences
- Interpretations presented as established facts

Rules:
1. A claim is supported only if the context explicitly states it
   or clearly entails it.
2. Do not infer a specific value (such as an age, date, or amount) from a
   role, appearance, or relationship.
3. If a specific value is absent from the context, it is unsupported.
4. Do not use outside knowledge.
5. A statement that the context itself says something is unknown or unrecorded
   is supported if the context does say so.
6. If every factual claim is supported, return fully_supported.
7. If some claims are supported but at least one material claim
   is unsupported, return partially_supported.
8. If the central answer has no supporting evidence, return no_support.

Be conservative. When evidence is insufficient, do not mark the
answer fully_supported.

Return only the required structured output.""",
        ),
        (
            "human",
            "Question:\n{question}\n\nAnswer:\n{answer}\n\nContext:\n{context}",
        ),
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

    if state.get("issup_retries", 0) >= 1:
        return "no_answer_found"

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
useful: the answer directly addresses the question. An answer that correctly
states that the document says the information is unknown or unrecorded also
counts as useful.
not_useful: generic, off-topic, or only background info.
Do NOT re-check grounding. Only check whether the question was answered.""",
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
) -> Literal["finalize", "rewrite_query_for_usefulness", "no_answer_found"]:
    if state.get("isuse") == "useful":
        return "finalize"
    if state.get("rewrite_tries", 0) >= 1:
        return "no_answer_found"
    return "rewrite_query_for_usefulness"


def finalize(state: State):
    """Store the accepted (possibly revised) answer in the chat history."""
    return {"messages": [AIMessage(content=state["answer"])]}


def no_answer_found(state: State):
    return {
        "answer": NO_ANSWER_MESSAGE,
        "context": "",
        "messages": [AIMessage(content=NO_ANSWER_MESSAGE)],
    }


def get_chatbot():
    pool = ConnectionPool(
        conninfo=DB_URI,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True},
        check=ConnectionPool.check_connection,
    )

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

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
    g.add_node("finalize", finalize)
    g.add_node("no_answer_found", no_answer_found)

    g.add_edge(START, "decision_route")

    g.add_conditional_edges(
        "decision_route",
        route_after_decision,
        {"document": "retrieve", "conversation": "conversation_generate"},
    )
    g.add_edge("conversation_generate", END)

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

    g.add_conditional_edges(
        "generate",
        route_after_generate,
        {"is_sup": "is_sup", "no_answer_found": "no_answer_found"},
    )
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
            "finalize": "finalize",
            "rewrite_query_for_usefulness": "rewrite_query_for_usefulness",
            "no_answer_found": "no_answer_found",
        },
    )
    g.add_edge("rewrite_query_for_usefulness", "retrieve")
    g.add_edge("finalize", END)
    g.add_edge("no_answer_found", END)

    return g.compile(checkpointer=checkpointer)


chatbot = get_chatbot()
