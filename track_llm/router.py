"""카테고리 판정 — 키워드 규칙 라우터(기준선)와 LLM 라우터.

규칙 라우터: 모델 없이 "질문에 이 단어가 있으면 이 카테고리"로만 고른다.
LLM 라우터: 지침문(prompts.py)을 보고 카테고리 + 확신도를 구조화 출력으로 고른다.
LLM이 규칙보다 얼마나 나은지가 모델을 쓰는 근거가 된다.

실행:
    python -m track_llm.router         # 규칙 라우터 측정
    python -m track_llm.router --llm   # LLM 라우터 측정 (OpenAI 호출)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from common.evaluate import ROOT, evaluate, load_goldenset, print_confusion
from track_llm.prompts import ROUTER_SYSTEM, router_fewshot

load_dotenv(ROOT / ".env")
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "gpt-5.6-luna")

# 키워드: 현준님 작성 (2026-11-03, 평가용 질문을 보지 않고 작성)
# 순서 = 우선순위. 두 카테고리 단어가 함께 나오면 위쪽이 이긴다. (순서는 Claude 제안)
#   1. 제적 — 결과(불이익)를 묻는 질문은 제적으로 보낸다 (경계 시험 A)
#   2. 출결 — 장려금이 걸려도 답은 출결 문서에 있는 경우가 많다 (경계 시험 B)
#   3. 장려금
#   4. 일정 — "학습·생활·규칙"은 너무 흔한 단어라 학습생활을 맨 뒤로
#   5. 학습생활
RULES = [
    ("dismissal", ["제적", "카메라", "마이크"]),
    ("attendance", ["결석", "병가", "휴가", "지각", "공가", "출석"]),
    ("allowance", ["장려금", "금액", "액수", "고용형태", "구직", "취직", "취업"]),
    ("schedule", ["일정", "커리큘럼", "어젠다", "수정", "수료", "수료증"]),
    ("learning", ["학습", "생활", "규칙"]),
]


def rule_route(question):
    """처음 걸리는 규칙의 카테고리. 아무 단어에도 안 걸리면 범위 밖."""
    for category, keywords in RULES:
        if any(k in question for k in keywords):
            return category
    return "out_of_scope"


class RouteDecision(BaseModel):
    """LLM이 채워야 하는 양식. Literal이라 목록 밖 카테고리는 나올 수 없다."""
    category: Literal["attendance", "allowance", "dismissal", "learning", "schedule", "out_of_scope"]
    confidence: float = Field(ge=0, le=1, description="0~1, 망설였으면 낮게")
    reason: str = Field(description="고른 이유 한 문장")


# 넘기기 임계값: 현준님 결정 (2026-11-03). 평가용 36문항의 확신도 표를 보고 정한 값이라
# 평가 점수가 실제보다 조금 좋게 나올 수 있다 (REPORT에 한계로 적는다).
CONFIDENCE_THRESHOLD = 0.8


def gate(decision):
    """카테고리 고르기와 따로, 넘길지만 정한다. 확신도가 임계값 미만이면 운영진 이관."""
    return "escalate" if decision.confidence < CONFIDENCE_THRESHOLD else "answer"


def make_llm_router():
    from langchain_openai import ChatOpenAI

    system = ROUTER_SYSTEM + "\n" + router_fewshot(load_goldenset("fewshot"))
    llm = ChatOpenAI(model=CLASSIFY_MODEL, temperature=0).with_structured_output(RouteDecision)

    def route(questions):
        """질문 여러 개를 한 번에 분류. 실패한 건 예외를 그대로 돌려준다 (조용히 '범위 밖' 처리하지 않음)."""
        msgs = [[("system", system), ("user", q)] for q in questions]
        return llm.batch(msgs, config={"max_concurrency": 8}, return_exceptions=True)

    return route


def report(name, items, preds):
    results = {x["id"]: {"category": p, "tools": [], "answer": ""} for x, p in zip(items, preds)}
    rep = evaluate(results)  # 분류만 잰다 — 도구·답변 점수는 이 단계에서 의미 없음
    print(f"{name} · 평가용 {rep['n']}문항")
    print(f"  정확도 {rep['accuracy']:.3f}   macro F1 {rep['macro_f1']:.3f}")
    print_confusion(rep)
    wrong = [(x, p) for x, p in zip(items, preds) if p != x["category"]]
    print(f"\n틀린 문항 {len(wrong)}개 (정답 → 예측)")
    for x, p in wrong:
        print(f"  {x['id']} {x['category']} → {p}  | {x['question']}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    items = load_goldenset("eval")
    if not ap.parse_args().llm:
        report("규칙 라우터", items, [rule_route(x["question"]) for x in items])
        sys.exit()

    out = make_llm_router()([x["question"] for x in items])
    errors = [(x["id"], o) for x, o in zip(items, out) if isinstance(o, Exception)]
    if errors:
        for i, e in errors:
            print(f"호출 실패 {i}: {type(e).__name__}: {e}")
        sys.exit(1)
    report(f"LLM 라우터 ({CLASSIFY_MODEL})", items, [o.category for o in out])

    # 확신도 표 — 임계값(이보다 낮으면 운영진에게 넘김)을 정할 재료
    rows = sorted(zip(items, out), key=lambda t: t[1].confidence)
    print("\n확신도 낮은 순 (✗ = 틀림)")
    for x, o in rows:
        print(f"  {o.confidence:.2f} {'✓' if o.category == x['category'] else '✗'} {x['id']} {o.category:<12} | {o.reason}")
    run = ROOT / "data" / "runs" / "llm_router.json"
    run.parent.mkdir(exist_ok=True)
    run.write_text(json.dumps({x["id"]: o.model_dump() for x, o in zip(items, out)}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n결과 저장: {run.relative_to(ROOT)}")
