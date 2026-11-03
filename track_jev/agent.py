"""track_jev 파이프라인: track_llm과 같은 그래프에서 판정·검증 노드만 Jev 버전으로 바꾼다.

  - classify: Jev 판단 3개(카테고리·범위 안·본인 기록) → 진리표(decide)로 카테고리와 행동 결정
  - verify:   숫자 가드레일(공통) → 통과하면 Jev 문장 검증

근거 조립·답변 생성·도구는 track_llm과 똑같다. 그래서 두 버전의 점수 차이는 판정·검증에서만 나온다.
"""

from langchain_core.messages import HumanMessage

from common import guardrail
from track_jev import verifier
from track_jev.router import ask_jev, decide
from track_llm import agent as base

_client = None


def client():
    global _client
    if _client is None:
        from typesafe_sdk import TypeSafeClient
        _client = TypeSafeClient()
    return _client


def classify(state):
    j = ask_jev(client(), state["question"])  # 실패는 예외로 올라간다
    category, action = decide(j)
    top = j["category_probs"][j["category"]]
    reason = f"범위 안 {j['in_scope']:.2f} · 본인 기록 {j['personal_record']:.2f} · 1위 확률 {top:.2f} → {action}"
    # confidence 칸에는 행동을 숫자로 담는다: 1.0 = 진행, 0.0 = 진리표가 이관 결정 (화면·채점에서 같은 칸을 쓰려고)
    return {"category": category, "confidence": 0.0 if action == "escalate" else 1.0, "route_reason": reason}


def after_classify(state):
    return "escalate" if state["confidence"] == 0.0 else "agent"


def verify(state):
    """숫자 가드레일 먼저, 통과하면 Jev 문장 검증. 실패하면 이유를 붙여 다시 쓰게 한다."""
    answer = str(state["messages"][-1].text)
    evidence = guardrail.evidence_for(base.called_tools(state["messages"]))
    r = guardrail.check(answer, evidence, state["question"])
    r["kind"] = "숫자"
    if r["ok"]:
        j = verifier.verify(client(), answer, evidence, state["question"])
        bad = [s["text"] for s in j["sentences"] if not s["ok"]]
        r = {"ok": j["ok"], "kind": "문장", "tokens": [s["text"] for s in j["sentences"]], "unsupported": bad,
             "sentences": j["sentences"]}
    update = {"checks": state.get("checks", []) + [r]}
    if not r["ok"]:
        what = "근거 문서에 그대로 없는 숫자" if r["kind"] == "숫자" else "근거 문서가 뒷받침하지 않는 문장"
        update["messages"] = [HumanMessage(
            f"[검증 실패] {what}: {' / '.join(r['unsupported'])}. 근거에 적힌 내용만으로 다시 답해 주세요.")]
    return update


GRAPH = None


def ask(question):
    global GRAPH
    GRAPH = GRAPH or base.build(classify=classify, after_classify=after_classify, verify=verify)
    return base.run(GRAPH, question)
