"""터미널에서 챗봇에게 직접 질문해 보는 프로그램.

실행:  .venv/Scripts/python.exe chat.py         # LLM 버전
       .venv/Scripts/python.exe chat.py --jev   # Jev 버전
끝내기: 빈 줄에서 Enter, 또는 Ctrl+C
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from track_llm.agent import ANSWER_MODEL  # noqa: E402  (.env를 먼저 읽어야 함)
from track_llm.router import CLASSIFY_MODEL, CONFIDENCE_THRESHOLD  # noqa: E402

JEV = "--jev" in sys.argv
if JEV:
    from track_jev.agent import ask  # noqa: E402
else:
    from track_llm.agent import ask  # noqa: E402

NAMES = {"attendance": "출결·공가", "allowance": "장려금·고용형태", "dismissal": "제적·참여규칙",
         "learning": "학습생활", "schedule": "일정·수료", "out_of_scope": "범위 밖"}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not sys.stdin.isatty():  # 파이프로 질문을 넘길 때(테스트)도 한글이 깨지지 않게
        sys.stdin.reconfigure(encoding="utf-8")
    judge = "Jev 진리표" if JEV else CLASSIFY_MODEL
    print(f"AI 에이전트 2기 상담 챗봇 [{'Jev' if JEV else 'LLM'} 버전] (분류 {judge} · 답변 {ANSWER_MODEL})")
    print("질문을 입력하고 Enter. 빈 줄에서 Enter를 누르면 끝납니다.\n")
    while True:
        try:
            q = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        try:
            r = ask(q)
        except Exception as e:
            print(f"  ⚠️ 오류: {type(e).__name__}: {e}\n")
            continue
        gate = "운영진 이관" if r["confidence"] < CONFIDENCE_THRESHOLD else "통과"
        detail = r["route_reason"] if JEV else f"확신도 {r['confidence']:.2f}"
        print(f"  분류: {NAMES[r['category']]} ({detail} → {gate})")
        print(f"  부른 도구: {', '.join(r['tools']) or '없음'}")
        if r["sources"]:
            print(f"  근거 섹션 {len(r['sources'])}개: {' / '.join(r['sources'][:4])}"
                  + (" …" if len(r["sources"]) > 4 else ""))
        for i, c in enumerate(r["checks"]):
            label = (f"{c.get('kind', '숫자')} 검증" if i == 0 else "다시 쓴 뒤 검증")
            print(f"  {label}: " + ("통과" if c["ok"] else f"실패 — 근거에 없는 {', '.join(c['unsupported'])}")
                  + (f" (확인한 {'문장' if c.get('kind') == '문장' else '숫자'} {len(c['tokens'])}개)"
                     if c["ok"] and c["tokens"] else ""))
        if r["escalated"]:
            print(f"  → 운영진 이관: {r['escalated']}")
        print(f"\n챗봇> {r['answer']}\n")
    print("끝.")
