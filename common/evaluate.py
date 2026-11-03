"""채점기 — 두 버전(track_llm, track_jev)을 같은 기준으로 잰다.

지표 세 가지 (노드 5 요건):
1. 분류 지표: 정확도, macro F1, 혼동 행렬 — 카테고리를 맞게 골랐나
2. 도구 호출 적절성: 호출한 도구 집합 == 기대 도구 집합이면 1점
3. 답변 적절성: 필수 사실(must)을 전부 담고 금지 표현(forbid)이 0개면 1점

실행:
    python -m common.evaluate --selftest              # 채점기 자체 검사
    python -m common.evaluate data/model_answers.json # 답안 파일 채점
"""

import argparse
import json
import sys
from pathlib import Path

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parent.parent
GOLDENSET = ROOT / "data" / "goldenset.json"
CATEGORIES = ["attendance", "allowance", "dismissal", "learning", "schedule", "out_of_scope"]


def load_goldenset(split=None):
    """평가셋을 읽는다. split='eval' 이면 평가용만, 'fewshot' 이면 예시용만."""
    items = json.loads(GOLDENSET.read_text(encoding="utf-8"))
    return [x for x in items if split is None or x["split"] == split]


# ---------- 문항 하나 채점 ----------

def score_tools(called, expected):
    """호출한 도구 집합이 기대 도구 집합과 똑같으면 1. 순서·중복 호출은 따지지 않는다."""
    return int(set(called) == set(expected))


def score_answer(answer, must, forbid):
    """필수 사실을 전부 담고 금지 표현이 하나도 없으면 1.

    must 는 [[변형1, 변형2], [사실2]] 형태 — 사실 하나당 변형 중 하나만 있으면 된다.
    표현이 아니라 사실을 보도록 변형을 여러 개 둔다 (예: "20,000원" / "2만원").
    """
    missing = [fact for fact in must if not any(v in answer for v in fact)]
    found_forbid = [f for f in forbid if f in answer]
    return {
        "score": int(not missing and not found_forbid),
        "missing": missing,
        "forbidden": found_forbid,
    }


# ---------- 전체 채점 ----------

def evaluate(results, split="eval"):
    """results: {문항id: {"category": ..., "tools": [...], "answer": "..."}}

    빠진 문항은 0점으로 친다 (조용한 실패 방지 — 답이 없는 걸 넘어가지 않는다).
    """
    gold = load_goldenset(split)
    y_true, y_pred, rows = [], [], []
    for item in gold:
        r = results.get(item["id"])
        if r is None:
            r = {"category": "(없음)", "tools": None, "answer": ""}
        y_true.append(item["category"])
        y_pred.append(r.get("category", "(없음)"))
        tool = score_tools(r["tools"], item["expected_tools"]) if r.get("tools") is not None else 0
        ans = score_answer(r.get("answer", ""), item["must"], item["forbid"])
        rows.append({"id": item["id"], "category": item["category"], "tool": tool, **ans})

    labels = CATEGORIES + sorted(set(y_pred) - set(CATEGORIES))
    n = len(rows)
    return {
        "n": n,
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, labels=CATEGORIES, average="macro", zero_division=0),
        "confusion": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
        "tool_score": sum(r["tool"] for r in rows) / n,
        "answer_score": sum(r["score"] for r in rows) / n,
        "rows": rows,
    }


def print_report(rep):
    print(f"문항 {rep['n']}개")
    print(f"  분류 정확도   {rep['accuracy']:.3f}   macro F1 {rep['macro_f1']:.3f}")
    print(f"  도구 호출 적절성 {rep['tool_score']:.3f}")
    print(f"  답변 적절성     {rep['answer_score']:.3f}")
    labels = rep["confusion"]["labels"]
    short = [l[:6] for l in labels]
    print("\n혼동 행렬 (행 = 정답, 열 = 예측)")
    print(" " * 14 + " ".join(f"{s:>6}" for s in short))
    for lab, row in zip(labels, rep["confusion"]["matrix"]):
        print(f"{lab:>13} " + " ".join(f"{v:>6}" for v in row))
    fails = [r for r in rep["rows"] if not (r["tool"] and r["score"])]
    if fails:
        print(f"\n틀린 문항 {len(fails)}개")
        for r in fails:
            why = []
            if not r["tool"]:
                why.append("도구 불일치")
            if r["missing"]:
                why.append("빠진 사실 " + " | ".join("/".join(f) for f in r["missing"]))
            if r["forbidden"]:
                why.append("금지 표현 " + ", ".join(r["forbidden"]))
            print(f"  {r['id']} ({r['category']}): " + "; ".join(why))


# ---------- 채점기 자체 검사 ----------

def selftest():
    """채점기가 맞게 채점하는지, 결과를 이미 아는 가짜 답안으로 확인한다.

    - 모범: 필수 사실의 첫 변형을 모두 넣고 기대 도구를 그대로 → 전부 1점이어야 함
    - 금지 섞기: 모범 + 금지 표현 하나 → 금지 표현이 있는 문항은 0점이어야 함
    - 빈 답: 아무것도 안 함 → 필수 사실이 있는 문항은 0점이어야 함
    - 답 없음: 결과에서 문항이 빠짐 → 0점이어야 함
    """
    gold = load_goldenset("eval")
    ok = True

    def check(name, results, expect):
        nonlocal ok
        rep = evaluate(results)
        got = {r["id"]: (r["tool"], r["score"]) for r in rep["rows"]}
        bad = [i for i, e in expect.items() if got[i] != e]
        ok &= not bad
        print(f"[{'통과' if not bad else '실패'}] {name}" + (f" — 어긋난 문항 {bad}" if bad else ""))

    perfect = {x["id"]: {"category": x["category"], "tools": x["expected_tools"],
                         "answer": " ".join(f[0] for f in x["must"])} for x in gold}
    check("모범 답안 → 전부 1점", perfect, {x["id"]: (1, 1) for x in gold})

    poisoned = {i: {**r, "answer": r["answer"] + " " + (x["forbid"][0] if x["forbid"] else "")}
                for x in gold for i, r in [(x["id"], perfect[x["id"]])]}
    check("금지 표현 섞기 → 금지 있는 문항 0점", poisoned,
          {x["id"]: (1, 0 if x["forbid"] else 1) for x in gold})

    empty = {x["id"]: {"category": x["category"], "tools": [], "answer": ""} for x in gold}
    check("빈 답 → 필수 사실 있는 문항 0점", empty,
          {x["id"]: (int(not x["expected_tools"]), int(not x["must"])) for x in gold})

    check("답 없음 → 0점", {}, {x["id"]: (0, int(not x["must"])) for x in gold})
    return ok


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("answers", nargs="?", help="답안 JSON 파일 {문항id: {category, tools, answer}}")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.answers:
        p.error("답안 파일 경로 또는 --selftest 를 주세요")
    print_report(evaluate(json.loads(Path(a.answers).read_text(encoding="utf-8"))))
