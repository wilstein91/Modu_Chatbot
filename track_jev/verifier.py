"""Jev 문장 검증 — 숫자 가드레일이 못 잡는 "숫자 없는 지어내기"를 잡는다.

답변을 문장으로 쪼개, 문장마다 두 판단을 한 요청에 묶어 Jev에게 묻는다.
  - support (Choice): 근거가 이 문장을 뒷받침하나 / 반대하나 / 말이 없나
  - claim (Noul): 이 문장이 규정에 대한 사실 주장인가 (인사·문의처 안내는 검사할 필요 없음)
통과 여부는 코드(judge)의 진리표가 정한다.

실행:
    python -m track_jev.verifier   # 퀴즈 문장 + 모범 답안 36개로 시험
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, NoulCriteria

from common.evaluate import ROOT, load_goldenset
from common.guardrail import evidence_for

load_dotenv(ROOT / ".env")

# 답변 규칙이 정해 준 문구 — 근거 문서에 없어도 검사하지 않는다 (현준님: "일정은 변동될 수 있어요"도 주장이지만 규칙 문구)
# LLM이 표현을 조금 바꿔 쓰므로("운영 상황에 따라 변동될 수 있어요") 핵심 구절로 찾는다.
RULE_SENTENCES = ["변동될 수 있", "질문만 답변드릴 수 있", "질문에만 답할 수 있"]

SUPPORT_CRITERIA = {
    "supported": "근거에 이 문장의 내용이 적혀 있다. 표현이 달라도 뜻이 같으면 여기다.",
    "contradicted": "근거에 이 문장과 다른 내용이 적혀 있다. 예: 근거는 오후 6시 퇴실인데 문장은 오후 5시 퇴실이라고 한다.",
    "not_in_evidence": "근거에 이 문장의 내용이 없다. 예: 근거에 없는 조건이나 예외를 덧붙인다.",
}
# 검사 대상 기준: 현준님 예/아니오 (2026-11-03)
CLAIM_CRITERIA = NoulCriteria(
    true="기한, 제출 서류, 금액, 인정 여부, 일정처럼 안내 문서로 맞고 틀림을 확인할 수 있는 내용을 말한다. 예: '공가 신청서는 하루 전까지 내야 해요.'",
    false="인사, 문의처 안내, 다시 물어보라는 권유처럼 확인할 사실이 없다. 예: '운영매니저님께 확인해 주세요.', '궁금한 점 있으면 물어보세요!'",
)
CLAIM_NO = 0.3  # TypeSafe 문서의 Noul 출발값


def split_sentences(answer):
    """(근거: …) 표시와 마크다운을 지우고 문장으로 쪼갠다. 규칙 문구는 뺀다."""
    body = re.sub(r"\(근거:[^)]*\)", "", answer).replace("**", "")
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [p.strip() for p in parts
            if len(p.strip()) > 3 and not any(r in p for r in RULE_SENTENCES)]


def questions_for(sentences):
    qs = {}
    for i, s in enumerate(sentences):
        qs[f"support_{i}"] = Choice(
            instructions={"질문": "`evidence`의 안내 문서와 비교할 때 이 문장은 어떤가?", "문장": s},
            criteria=SUPPORT_CRITERIA)
        qs[f"claim_{i}"] = Noul(
            instructions={"질문": "이 문장은 훈련 규정이나 절차에 대한 사실을 말하는가?", "문장": s},
            criteria=CLAIM_CRITERIA)
    return qs


def judge(support, claim):
    """진리표: 사실 주장이 아니면(claim < 0.3) 통과. 주장이거나 애매하면 Choice 1위가 '뒷받침'이어야 통과.

    | 주장? (Noul) | 근거와 비교 (Choice 1위) | 결정
    |--------------|--------------------------|------
    | < 0.3        | —                        | 통과 (인사·문의처 안내)
    | ≥ 0.3        | supported                | 통과
    | ≥ 0.3        | contradicted             | 실패 (근거와 반대)
    | ≥ 0.3        | not_in_evidence          | 실패 (지어낸 내용)
    """
    return claim < CLAIM_NO or support == "supported"


def verify(client, answer, evidence, question=""):
    """{"ok": bool, "sentences": [{text, support, p_supported, claim, ok}]}. API 실패는 예외로 올린다."""
    sentences = split_sentences(answer)
    if not sentences:
        return {"ok": True, "sentences": []}
    res = client.system_one(
        state={"evidence": evidence or "(조회한 안내 문서 없음)", "trainee_question": question},
        questions=questions_for(sentences))
    rows = []
    for i, s in enumerate(sentences):
        sup, claim = res.answers[f"support_{i}"], res.answers[f"claim_{i}"].noul
        probs = dict(sup.probabilities)
        rows.append({"text": s, "support": sup.choice, "p_supported": probs["supported"], "claim": claim,
                     "ok": judge(sup.choice, claim)})
    return {"ok": all(r["ok"] for r in rows), "sentences": rows}


def _show(title, r):
    print(f"{'✅ 통과' if r['ok'] else '🚫 막음'}  {title}")
    for s in r["sentences"]:
        print(f"     {'·' if s['ok'] else '✗'} 주장 {s['claim']:.2f} {s['support']:<15} (뒷받침 {s['p_supported']:.2f}) {s['text'][:60]}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from typesafe_sdk import TypeSafeClient

    ev = evidence_for(["lookup_attendance"])
    quiz = ["진료확인서를 내면 공가로 인정돼요.", "영수증을 내도 공가로 인정돼요.",
            "질병 공가는 한 달에 3번까지만 쓸 수 있어요.", "조퇴한 날도 공결로 처리돼요.",
            "운영매니저님께 확인해 주세요.", "궁금한 점 있으면 언제든 물어보세요!"]
    answers = json.loads((ROOT / "data" / "model_answers.json").read_text(encoding="utf-8"))
    gold = {x["id"]: x for x in load_goldenset("eval")}
    with TypeSafeClient() as client, ThreadPoolExecutor(max_workers=8) as pool:
        print("== 퀴즈 문장 (근거: 출결·공가) ==")
        for s, r in zip(quiz, pool.map(lambda s: verify(client, s, ev), quiz)):
            _show(s, r)
        print("\n== 모범 답안 36개 (맞는 답이므로 전부 통과해야 오탐 없음) ==")
        ids = list(answers)
        results = list(pool.map(lambda i: verify(client, answers[i]["answer"], evidence_for(answers[i]["tools"]),
                                                 gold[i]["question"]), ids))
        blocked = [(i, r) for i, r in zip(ids, results) if not r["ok"]]
        for i, r in blocked:
            _show(i, r)
        print(f"\n모범 답안 {len(ids)}개 중 막힌 것 {len(blocked)}개")
