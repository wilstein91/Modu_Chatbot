"""track_llm 파이프라인: 판정 → 관문 → (근거 조회 ↔ 답변) 루프.

    classify ──(확신도 < 0.8)──▶ escalate ──▶ END
       │
       ▼
     agent ◀──▶ tools        (첫 호출은 분류된 카테고리의 조회 도구를 코드로 강제)
       │
       ▼
      END

검증(Step 7)은 아직 없다.
"""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from common.tools import ALL_TOOLS, LOOKUP_TOOLS, escalate_to_staff
from track_llm.prompts import ANSWER_SYSTEM
from track_llm.router import CONFIDENCE_THRESHOLD, make_llm_router

ANSWER_MODEL = os.getenv("ANSWER_MODEL", "gpt-5.6-terra")
RECURSION_LIMIT = 10  # agent ↔ tools가 끝없이 돌지 않게


class State(TypedDict):
    question: str
    category: str
    confidence: float
    route_reason: str
    messages: Annotated[list, add_messages]  # agent·tools 두 곳에서 들어오므로 리듀서로 이어 붙인다


_route = None
# gpt-5.6-terra는 도구 호출을 Responses API에서만 받는다 (chat/completions는 400 오류).
_llm = ChatOpenAI(model=ANSWER_MODEL, temperature=0, use_responses_api=True)
_llm_auto = _llm.bind_tools(ALL_TOOLS)


def classify(state):
    global _route
    _route = _route or make_llm_router()
    d = _route([state["question"]])[0]
    if isinstance(d, Exception):
        raise d  # 분류 실패를 조용히 넘기지 않는다
    return {"category": d.category, "confidence": d.confidence, "route_reason": d.reason}


def after_classify(state):
    return "escalate" if state["confidence"] < CONFIDENCE_THRESHOLD else "agent"


def escalate(state):
    """관문에서 걸린 질문: 답을 만들지 않고 운영진에게 넘긴다."""
    call = {"name": "escalate_to_staff", "args": {"reason": "분류 확신도 낮음"}, "id": "gate"}
    result = escalate_to_staff.invoke(call["args"])
    return {"messages": [
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=result, tool_call_id="gate"),
        AIMessage(content="질문 내용을 정확히 판단하기 어려워 운영진에게 넘겼어요. 운영매니저님께 확인 부탁드려요."),
    ]}


def agent(state):
    msgs = state["messages"]
    if not msgs:
        msgs = [SystemMessage(ANSWER_SYSTEM + f"\n\n# 분류 결과\n이 질문의 카테고리는 {state['category']}이다."),
                HumanMessage(state["question"])]
        lookup = LOOKUP_TOOLS.get(state["category"])
        # 첫 호출: 카테고리 조회 도구를 코드로 강제한다 (프롬프트는 요청일 뿐 보장이 아니다).
        # 범위 밖은 강제하지 않는다 — 잡담이면 도구 없이, 본인 기록이면 escalate_to_staff를 고르게 둔다.
        llm = _llm.bind_tools(ALL_TOOLS, tool_choice=lookup.name) if lookup else _llm_auto
        return {"messages": msgs + [llm.invoke(msgs)]}
    return {"messages": [_llm_auto.invoke(msgs)]}


def build():
    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("escalate", escalate)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(ALL_TOOLS))
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", after_classify, ["escalate", "agent"])
    g.add_edge("escalate", END)
    g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


def summarize(state):
    """결과에서 데모·채점에 필요한 것만 꺼낸다: 답변, 부른 도구, 근거 섹션."""
    tools, sources = [], []
    for m in state["messages"]:
        if isinstance(m, AIMessage):
            tools += [c["name"] for c in m.tool_calls]
        if isinstance(m, ToolMessage):
            sources += [l[len("[출처: "):-1] for l in m.content.splitlines() if l.startswith("[출처: ")]
    return {
        "category": state["category"],
        "confidence": state["confidence"],
        "tools": tools,
        "sources": sources,
        "answer": str(state["messages"][-1].text),  # Responses API는 content가 블록 목록이라 글자만 꺼낸다
    }


GRAPH = None


def ask(question):
    global GRAPH
    GRAPH = GRAPH or build()
    state = GRAPH.invoke({"question": question, "messages": []}, {"recursion_limit": RECURSION_LIMIT})
    return summarize(state)
