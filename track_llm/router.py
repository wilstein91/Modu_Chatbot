"""카테고리 판정 — 기준선: 키워드 규칙 라우터.

모델 없이 "질문에 이 단어가 있으면 이 카테고리"로만 고른다.
LLM 라우터(Step 4)가 이 점수보다 얼마나 나은지가 모델을 쓰는 근거가 된다.

실행:
    python -m track_llm.router    # 평가용 문항으로 분류 점수 측정
"""

import sys

from common.evaluate import evaluate, load_goldenset, print_confusion

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


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    items = load_goldenset("eval")
    # 분류만 잰다 — 도구·답변 점수는 이 단계에서 의미 없음
    results = {x["id"]: {"category": rule_route(x["question"]), "tools": [], "answer": ""} for x in items}
    rep = evaluate(results)
    print(f"규칙 라우터 · 평가용 {rep['n']}문항")
    print(f"  정확도 {rep['accuracy']:.3f}   macro F1 {rep['macro_f1']:.3f}")
    print_confusion(rep)
    wrong = [(x, results[x["id"]]["category"]) for x in items if results[x["id"]]["category"] != x["category"]]
    print(f"\n틀린 문항 {len(wrong)}개 (정답 → 예측)")
    for x, pred in wrong:
        print(f"  {x['id']} {x['category']} → {pred}  | {x['question']}")
