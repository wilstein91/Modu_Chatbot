"""숫자 가드레일 — 답변 속 숫자·시간·날짜·링크가 근거에 글자 그대로 있는지 기계적으로 검사한다 (두 버전 공통).

LLM이 가장 그럴듯하게 틀리는 곳이 숫자다. 답변에서 숫자가 든 토큰을 뽑아,
조립된 근거(또는 질문)에서 문자열로 찾는다. 하나라도 못 찾으면 실패.
숫자가 없는 지어내기("영수증도 됩니다")는 이 검사로 못 잡는다 → track_jev/verifier.py의 몫.

실행:
    python -m common.guardrail   # 모범 답안 36개로 오탐(맞는 답을 막는 것) 검사
"""

import json
import re
import sys

from common.context import format_context
from common.evaluate import ROOT, load_goldenset

# 링크 / 날짜(2026-11-25, 11-25) / 시각(12:50) / 숫자+단위(20,000원, 80%, 3회, 20일)
PATTERNS = [
    r"forms\.gle/\w+",
    r"\d{4}-\d{2}-\d{2}",
    r"\b\d{1,2}-\d{2}\b",
    r"\d{1,2}:\d{2}",
    r"\d[\d,]*(?:\.\d+)?\s?(?:%|퍼센트|원|일|회|번|주|개월|시간|분|시|기|명|차|세)",
]
TOKEN = re.compile("|".join(f"(?:{p})" for p in PATTERNS))


def extract(text):
    """답변에서 검사할 토큰을 뽑는다. (근거: …) 출처 표시는 검사하지 않는다."""
    body = re.sub(r"\(근거:[^)]*\)", "", text)
    return list(dict.fromkeys(m.group().replace(" ", "") for m in TOKEN.finditer(body)))


# 답변 규칙이 정해 준 고정 문구 — 근거 문서가 없어도 허용 (범위 밖 안내의 "2기")
ALLOWED_TEXT = "AI 에이전트 2기 관련 질문만 답변드릴 수 있어요"


def check(answer, evidence, question=""):
    """{"ok": bool, "tokens": [...], "unsupported": [...]} — 근거·질문·고정 문구 어디에도 없는 토큰이 unsupported."""
    haystack = (evidence + "\n" + question + "\n" + ALLOWED_TEXT).replace(" ", "")
    tokens = extract(answer)
    unsupported = [t for t in tokens if t not in haystack]
    return {"ok": not unsupported, "tokens": tokens, "unsupported": unsupported}


def evidence_for(tools):
    """부른 조회 도구들의 근거를 이어 붙인다 (escalate_to_staff는 근거 없음)."""
    cats = [t.removeprefix("lookup_") for t in tools if t.startswith("lookup_")]
    return "\n\n".join(format_context(c) for c in dict.fromkeys(cats))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    answers = json.loads((ROOT / "data" / "model_answers.json").read_text(encoding="utf-8"))
    gold = {x["id"]: x for x in load_goldenset("eval")}
    blocked = 0
    for qid, a in answers.items():
        r = check(a["answer"], evidence_for(a["tools"]), gold[qid]["question"])
        if not r["ok"]:
            blocked += 1
            print(f"  막힘 {qid}: {r['unsupported']}  | {a['answer'][:80]}")
    print(f"모범 답안 {len(answers)}개 중 가드레일에 막힌 것 {blocked}개 (0이어야 오탐 없음)")
