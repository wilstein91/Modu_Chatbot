"""데모 화면 — 두 버전을 전환하며 질문하고, 답변·호출한 도구·근거 섹션·검증 결과를 함께 본다.

실행:  .venv/Scripts/streamlit run app.py
"""

import json

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from common.context import format_context  # noqa: E402
from common.evaluate import ROOT  # noqa: E402

NAMES = {"attendance": "출결·공가", "allowance": "장려금·고용형태", "dismissal": "제적·참여규칙",
         "learning": "학습생활", "schedule": "일정·수료", "out_of_scope": "범위 밖"}
EXAMPLES = ["병원 때문에 조퇴하면 공가 되나요?", "장려금 하루에 얼마예요?", "결석 많이 하면 어떻게 돼요?",
            "디스코드 닉네임 어떻게 바꿔요?", "제 출석률 지금 몇 %예요?", "오늘 점심 뭐 먹을까요?"]

st.set_page_config(page_title="AI 에이전트 2기 상담 챗봇", page_icon="💬", layout="wide")
st.title("💬 AI 에이전트 2기 상담 챗봇")
st.caption("2기 노션 공지만 근거로 답합니다. 문서로 답할 수 없으면 운영진에게 넘깁니다. · 작성: Sung, Hyun-Joon")

with st.sidebar:
    track = st.radio("버전", ["LLM 버전 (JEV 미사용)", "Jev 버전 (JEV 사용)"])
    jev = track.startswith("Jev")
    st.markdown(
        "**LLM 버전**: LLM이 카테고리·확신도를 고르고 0.8 미만이면 이관 · 숫자 가드레일로 검증\n\n"
        "**Jev 버전**: Jev 판단 3개 → 진리표로 결정 · 숫자 가드레일 + Jev 문장별 검증")
    st.divider()
    st.markdown("**평가용 36문항 점수**")
    for t in ("llm", "jev"):
        p = ROOT / "data" / "runs" / f"full_{t}.json"
        if p.exists():
            s = json.loads(p.read_text(encoding="utf-8"))["scores"]
            st.markdown(f"- {t.upper()}: 분류 F1 {s['macro_f1']:.3f} · 도구 {s['tool_score']:.3f} · 답변 {s['answer_score']:.3f}")


@st.cache_resource
def get_ask(use_jev):
    if use_jev:
        from track_jev.agent import ask
    else:
        from track_llm.agent import ask
    return ask


cols = st.columns(len(EXAMPLES))
picked = None
for c, ex in zip(cols, EXAMPLES):
    if c.button(ex, use_container_width=True):
        picked = ex
question = st.chat_input("질문을 입력하세요") or picked

if question:
    st.chat_message("user").write(question)
    with st.spinner("근거를 찾고 답변을 검증하는 중…"):
        try:
            r = get_ask(jev)(question)
        except Exception as e:
            st.error(f"오류: {type(e).__name__}: {e}")
            st.stop()
    st.chat_message("assistant").markdown(r["answer"])

    left, right = st.columns(2)
    with left:
        st.subheader("① 판정")
        st.write(f"카테고리: **{NAMES[r['category']]}**")
        st.write(r["route_reason"] if jev else f"확신도 {r['confidence']:.2f} (0.8 미만이면 이관)")
        if r["escalated"]:
            st.warning(f"운영진 이관: {r['escalated']}")
        st.subheader("② 호출한 도구")
        st.write(", ".join(f"`{t}`" for t in r["tools"]) or "없음")
    with right:
        st.subheader("④ 검증")
        if not r["checks"]:
            st.write("검증 없음 (판정 단계에서 이관)")
        for i, c in enumerate(r["checks"]):
            title = f"{'다시 쓴 뒤 ' if i else ''}{c.get('kind', '숫자')} 검증"
            if c["ok"]:
                st.success(f"{title}: 통과")
            else:
                st.error(f"{title}: 실패 — {' / '.join(c['unsupported'])}")
            for s in c.get("sentences", []):
                mark = "✅" if s["ok"] else "❌"
                st.caption(f"{mark} 주장 {s['claim']:.2f} · {s['support']} — {s['text']}")
            if c.get("kind", "숫자") == "숫자" and c["tokens"]:
                st.caption("확인한 숫자: " + ", ".join(c["tokens"]))

    st.subheader("③ 근거로 쓴 문서 섹션")
    st.write(f"{len(r['sources'])}개 섹션 (카테고리 매핑표대로 조립)")
    for cat in dict.fromkeys(t.removeprefix("lookup_") for t in r["tools"] if t.startswith("lookup_")):
        with st.expander(f"{NAMES[cat]} 근거 펼쳐 보기"):
            st.text(format_context(cat))
