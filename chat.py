"""터미널에서 챗봇에게 직접 질문해 보는 프로그램 (track_llm 버전).

실행:  .venv/Scripts/python.exe chat.py
끝내기: 빈 줄에서 Enter, 또는 Ctrl+C
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from track_llm.agent import ANSWER_MODEL, ask  # noqa: E402  (.env를 먼저 읽어야 함)
from track_llm.router import CLASSIFY_MODEL, CONFIDENCE_THRESHOLD  # noqa: E402

NAMES = {"attendance": "출결·공가", "allowance": "장려금·고용형태", "dismissal": "제적·참여규칙",
         "learning": "학습생활", "schedule": "일정·수료", "out_of_scope": "범위 밖"}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not sys.stdin.isatty():  # 파이프로 질문을 넘길 때(테스트)도 한글이 깨지지 않게
        sys.stdin.reconfigure(encoding="utf-8")
    print(f"AI 에이전트 2기 상담 챗봇 (분류 {CLASSIFY_MODEL} · 답변 {ANSWER_MODEL})")
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
        print(f"  분류: {NAMES[r['category']]} (확신도 {r['confidence']:.2f} → {gate})")
        print(f"  부른 도구: {', '.join(r['tools']) or '없음'}")
        if r["sources"]:
            print(f"  근거 섹션 {len(r['sources'])}개: {' / '.join(r['sources'][:4])}"
                  + (" …" if len(r["sources"]) > 4 else ""))
        print(f"\n챗봇> {r['answer']}\n")
    print("끝.")
