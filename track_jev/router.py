"""카테고리 판정 — Jev 버전. 판단은 Jev가, 결정은 코드(진리표)가 한다.

Jev에게는 질문 하나당 한 번의 요청에 판단 3개(카테고리 Choice, 범위 안 Noul, 본인 기록 Noul)를 묶어 보낸다.
"넘길까?"는 Jev에게 묻지 않고 decide()의 진리표가 정한다.

실행:
    python -m track_jev.router --split fewshot   # 예시용 12개로 작동 확인
    python -m track_jev.router                   # 평가용 36개 측정
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from common.evaluate import ROOT, evaluate, load_goldenset, print_confusion
from track_jev.questions import CATEGORY_MIN_PROB, NOUL_NO, NOUL_YES, QUESTIONS

load_dotenv(ROOT / ".env")

# 질문만 보면 "어디에 질문해요?"가 2기 과정 얘기인지 알 수 없다 (사람도 못 맞힘).
# 코드가 이미 아는 사실이라 state에 적어 준다. (예시용 12개 시험에서 발견: 2026-11-03)
ASKED_BY = "모두의연구소 AI 에이전트 2기 훈련생이 과정 상담 챗봇에 보낸 질문이다."


def ask_jev(client, question):
    """질문 하나를 Jev에 보내고 세 판단을 꺼낸다. 실패는 예외로 올린다 (실패를 '아니오'로 취급하지 않음)."""
    res = client.system_one(state={"asked_by": ASKED_BY, "trainee_question": question}, questions=QUESTIONS)
    cat = res.answers["category"]
    return {
        "category": cat.choice,
        "category_probs": dict(cat.probabilities),
        "in_scope": res.answers["in_scope"].noul,
        "personal_record": res.answers["personal_record"].noul,
    }


def decide(j):
    """진리표. (분류 결과, 행동)을 돌려준다. 행동: answer = 문서 보고 답함 / escalate = 운영진 이관 / out_of_scope = 범위 밖 안내

    | 범위 안 (②)   | 본인 기록 (③) | 1위 카테고리 확률 | 결정
    |---------------|---------------|-------------------|------------------------------
    | < 0.3         | —             | —                 | 범위 밖 안내
    | 0.3 ~ 0.7     | —             | —                 | 운영진 이관 (범위가 애매)
    | > 0.7         | > 0.7         | —                 | 운영진 이관 (문서로 답할 수 없는 본인 기록)
    | > 0.7         | 0.3 ~ 0.7     | —                 | 운영진 이관 (본인 기록인지 애매)
    | > 0.7         | < 0.3         | < 0.5             | 운영진 이관 (카테고리가 애매)
    | > 0.7         | < 0.3         | ≥ 0.5             | 그 카테고리로 답함
    """
    top_prob = j["category_probs"][j["category"]]
    if j["in_scope"] < NOUL_NO:
        return "out_of_scope", "out_of_scope"
    if j["in_scope"] <= NOUL_YES:
        return j["category"], "escalate"
    if j["personal_record"] > NOUL_YES:
        return "out_of_scope", "escalate"
    if j["personal_record"] >= NOUL_NO:
        return j["category"], "escalate"
    if top_prob < CATEGORY_MIN_PROB:
        return j["category"], "escalate"
    return j["category"], "answer"


def run(questions):
    from typesafe_sdk import TypeSafeClient

    with TypeSafeClient() as client, ThreadPoolExecutor(max_workers=8) as pool:
        def safe(q):
            try:
                return ask_jev(client, q)
            except Exception as e:  # 호출 실패는 결과에 그대로 남겨 아래에서 멈춘다
                return e
        return list(pool.map(safe, questions))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="eval", choices=["eval", "fewshot"])
    split = ap.parse_args().split
    items = load_goldenset(split)
    out = run([x["question"] for x in items])
    errors = [(x["id"], o) for x, o in zip(items, out) if isinstance(o, Exception)]
    if errors:
        for i, e in errors:
            print(f"호출 실패 {i}: {type(e).__name__}: {e}")
        sys.exit(1)

    decisions = [decide(j) for j in out]
    results = {x["id"]: {"category": d[0], "tools": [], "answer": ""} for x, d in zip(items, decisions)}
    rep = evaluate(results, split=split)
    print(f"Jev 라우터 · {split} {rep['n']}문항")
    print(f"  정확도 {rep['accuracy']:.3f}   macro F1 {rep['macro_f1']:.3f}")
    print_confusion(rep)

    print("\n문항별 (✗ = 분류 틀림)   범위안  본인기록  1위확률  결정")
    for x, j, (cat, act) in zip(items, out, decisions):
        mark = "✓" if cat == x["category"] else "✗"
        top = j["category_probs"][j["category"]]
        print(f"  {mark} {x['id']} 정답 {x['category']:<12} 예측 {cat:<12} "
              f"{j['in_scope']:.2f}   {j['personal_record']:.2f}     {top:.2f}   {act}")
    answered = [(x, d) for x, d in zip(items, decisions) if d[1] == "answer"]
    print(f"\n넘김·범위밖 {len(items) - len(answered)}개 · 답변 대상 {len(answered)}개 중 분류 정답 "
          f"{sum(d[0] == x['category'] for x, d in answered)}")

    run_file = ROOT / "data" / "runs" / f"jev_router_{split}.json"
    run_file.parent.mkdir(exist_ok=True)
    run_file.write_text(json.dumps({x["id"]: j for x, j in zip(items, out)}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"결과 저장: {run_file.relative_to(ROOT)}")
