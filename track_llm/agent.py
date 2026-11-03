"""track_llm 파이프라인: 판정 → 관문 → (근거 조회 ↔ 답변) 루프 → 검증.

    classify ──(확신도 < 0.8)──▶ escalate ──▶ END
       │
       ▼
     agent ◀──▶ tools        (첫 호출은 분류된 카테고리의 조회 도구를 코드로 강제)
       │  ▲
       ▼  │ (1회 다시 쓰기)
     verify ──(또 실패)──▶ escalate ──▶ END
       │
       ▼
      END
"""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from common import guardrail
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
    messages: Annotated[list, add_messages]  # agent·tools·verify 여러 곳에서 들어오므로 리듀서로 이어 붙인다
    checks: list      # 검증 결과 기록 (다시 쓰기 전·후)
    escalated: str    # 넘긴 이유 ("" = 안 넘김)


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


MAX_REWRITES = 1  # 검증 실패 시 다시 쓰기 횟수 (현준님 결정: 1회, 또 실패하면 이관)


def escalate(state):
    """관문 또는 검증에서 걸린 질문: 답을 내보내지 않고 운영진에게 넘긴다."""
    reason = "검증 실패: 근거와 맞지 않는 내용" if state.get("checks") else "판정 단계에서 넘김"
    call = {"name": "escalate_to_staff", "args": {"reason": reason}, "id": f"esc{len(state['messages'])}"}
    result = escalate_to_staff.invoke(call["args"])
    text = ("답변을 확인하는 과정에서 문서와 맞지 않는 부분이 있어 운영진에게 넘겼어요. 운영매니저님께 확인 부탁드려요."
            if state.get("checks") else
            "안내 문서만으로 답하기 어려운 질문이라 운영진에게 넘겼어요. 운영매니저님께 확인 부탁드려요.")
    return {"escalated": reason, "messages": [
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=result, tool_call_id=call["id"]),
        AIMessage(content=text),
    ]}


def called_tools(messages):
    return [c["name"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls]


def verify(state):
    """숫자 가드레일. 실패하면 이유를 붙여 agent에게 다시 쓰게 한다 (횟수는 after_verify가 센다)."""
    answer = str(state["messages"][-1].text)
    r = guardrail.check(answer, guardrail.evidence_for(called_tools(state["messages"])), state["question"])
    update = {"checks": state.get("checks", []) + [r]}
    if not r["ok"]:
        update["messages"] = [HumanMessage(
            f"[검증 실패] 답변의 {', '.join(r['unsupported'])}은(는) 근거 문서에 그대로 없습니다. "
            "근거에 적힌 표기만 써서 다시 답해 주세요. 계산한 숫자는 쓰지 마세요.")]
    return update


def after_verify(state):
    if state["checks"][-1]["ok"]:
        return END
    return "agent" if len(state["checks"]) <= MAX_REWRITES else "escalate"


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


def build(classify=classify, after_classify=after_classify, verify=verify):
    """그래프 조립. track_jev는 판정(classify·after_classify)과 검증(verify) 노드만 바꿔 끼운다."""
    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("escalate", escalate)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(ALL_TOOLS))
    g.add_node("verify", verify)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", after_classify, ["escalate", "agent"])
    g.add_edge("escalate", END)
    g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "verify"})
    g.add_edge("tools", "agent")
    g.add_conditional_edges("verify", after_verify, ["agent", "escalate", END])
    return g.compile()


def summarize(state):
    """결과에서 데모·채점에 필요한 것만 꺼낸다: 답변, 부른 도구, 근거 섹션, 검증 결과."""
    sources = [l[len("[출처: "):-1] for m in state["messages"] if isinstance(m, ToolMessage)
               for l in m.content.splitlines() if l.startswith("[출처: ")]
    return {
        "category": state["category"],
        "confidence": state["confidence"],
        "route_reason": state.get("route_reason", ""),
        "tools": called_tools(state["messages"]),
        "sources": list(dict.fromkeys(sources)),
        "checks": state.get("checks", []),
        "escalated": state.get("escalated", ""),
        "answer": str(state["messages"][-1].text),  # Responses API는 content가 블록 목록이라 글자만 꺼낸다
    }


GRAPH = None


def run(graph, question):
    state = graph.invoke({"question": question, "messages": [], "checks": [], "escalated": ""},
                         {"recursion_limit": RECURSION_LIMIT})
    return summarize(state)


def ask(question):
    global GRAPH
    GRAPH = GRAPH or build()
    return run(GRAPH, question)
