"""근거 조립 — 카테고리별로 매핑표에 연결된 문서 섹션만 골라 챗봇에게 건넨다.

1. docs/notion_2기/*.md를 읽고 CORRECTIONS로 확정값을 반영한다 (틀린 폼 링크·기한·다른 기수 문장 숨김).
2. 제목(#) 단위로 섹션을 쪼갠다. 섹션 = 제목 줄부터 같은 수준 이상의 다음 제목 전까지 (하위 제목 포함).
3. SECTION_MAP(= docs/MAPPING.md)에 적힌 섹션만 조립한다. 문서 전체를 넣지 않는다.

실행:
    python -m common.context            # 카테고리별 조립 크기와 섹션 목록
    python -m common.context allowance  # 한 카테고리의 조립 결과 전문
"""

import re
import sys
from functools import lru_cache

from common.evaluate import ROOT

DOCS = ROOT / "docs" / "notion_2기"

# 확정값 반영 — docs/CONFLICTS.md 확정 칸 (현준님, 2026-11-03).
# (파일 앞 두 글자, 찾을 문자열, 바꿀 문자열 또는 None=그 줄 삭제). 한 번도 안 걸리면 오류 (문서가 바뀐 것).
CONFLICT_9 = " (⚠️ 이 기한은 안내 문서마다 1주/2주로 달라 운영진 확인이 필요함)"
CORRECTIONS = [
    ("00", "「AI 에이전트 훈련 정보」 페이지는 점심시간을", None),            # 수집 때 붙인 메모
    ("02", "13:00~14:00 (1시간)", "12:50~14:00"),                            # #4
    ("02", "프데분 5기의 공지사항", None),                                     # 다른 과정 채널명
    ("04", "공가는 발생일 +1일 까지 전산에 신청이 가능하니 사전에 반드시 알려주세요.",
     "공가는 발생일 하루 전까지 신청해 주세요. 당일 부득이하게 발생한 경우에도 당일에 작성해 주세요."),  # #3
    ("05", "공가는 발생일 +1일 까지 전산에 신청이 가능하니",
     "공가는 발생일 하루 전까지(당일 부득이하게 발생하면 당일에) 신청해야 하니"),                    # #3
    ("04", "forms.gle/R8ucZ232GNjcNktb7", "forms.gle/hf1qEAGA6B1hNTTg6"),   # #2
    ("05", "forms.gle/AMcwZYrYEcQ1mkJP9", "forms.gle/EWkJFEESCoBXgbR27"),   # #1
    ("05", "forms.gle/RxTDy1yL2PfaFbA86", "forms.gle/hf1qEAGA6B1hNTTg6"),   # #2
    ("04", "증빙자료: 참여확인증", "증빙자료: 예비군 훈련 증명서"),            # #5
    ("04", "증빙자료: 출산확인서", "증빙자료: 출산확인서, 가족관계증명서"),    # #7
    ("04", "(개강 후 1주 이내) 내일배움카드 발급 시 등록된 고용형태와 현재 고용형태가 다르면 반드시 알려주세요!",
     "(개강 후 1주 이내) 내일배움카드 발급 시 등록된 고용형태와 현재 고용형태가 다르면 반드시 알려주세요!" + CONFLICT_9),
    ("06", "개강 후 2주 이내로 변경 신청을 진행해야 합니다.**",
     "개강 후 2주 이내로 변경 신청을 진행해야 합니다.**" + CONFLICT_9),       # #9 미확정
    ("11", "프로덕트 데이터 분석가 5기 젭", "AI 에이전트 2기 젭"),            # 다른 과정 잔재
    ("11", "`AI에이전트1기/이름/지역`", "`AI에이전트2기/이름/지역`"),         # #8
    ("11", "`프데분2기/이름/지역`", "`AI에이전트2기/이름/지역`"),             # #8
    ("11", "이름설정은 아래 예시와 같이 변경해 주세요", None),                # 줌 이름: 다른 과정 예시뿐
    ("11", "[프데분] OOO", None),
    ("11", "ex. [프데분]", None),
]

# 카테고리 → (파일 앞 두 글자, 섹션 제목의 앞부분 또는 None=문서 전체, 하위 제목 포함 여부)
# docs/MAPPING.md의 표를 코드로 옮긴 것. 표를 바꾸면 여기도 바꾼다.
SECTION_MAP = {
    "attendance": [
        ("00", "LMS · QR 찍는 시간", True),
        ("00", "기본 시간표", True),
        ("00", "출석부 — 반드시 사전에", True),
        ("04", "**👀 중요사항 한 눈에 보기**", True),   # 정상 출석·외출·결석이 하위 제목으로 들어 있음
        ("04", "공가(출석인정요청) 한", True),
        *[("04", f"[하위 페이지] {t}", True) for t in
          ["예비군 / 민방위", "사망", "휴가", "입사시험", "자격시험", "결혼", "질병 / 입원", "출산(배우자)", "해커톤 참여"]],
        ("05", None, True),
        ("13", "[하위 페이지] 온라인 수업 때 캠을", True),
        ("13", "[하위 페이지] 오프닝 장소와 클로징 장소가", True),
        ("13", "[하위 페이지] 인터넷이 불안정하여", True),
        ("13", "[하위 페이지] 오늘 캠이 없습니다", True),
    ],
    "allowance": [
        ("04", "[하위 페이지] 훈련 장려금 지급/확인", True),
        ("06", None, True),
        ("13", "[하위 페이지] 교육과정 중에 취업이 되었습니다", True),
    ],
    "dismissal": [
        ("07", None, True),
        ("08", None, True),
    ],
    "learning": [
        ("00", "강의실 입장", True),
        ("02", "[하위 페이지] 툴 세팅", True),
        *[(f, None, True) for f in ["10", "11", "12", "14", "15", "16", "17", "18"]],
        ("13", "[하위 페이지] 스터디를 만들고 싶은데", True),
        ("13", "[하위 페이지] <참고>", True),
        ("13", "[하위 페이지] Oooooo00ops", True),
    ],
    "schedule": [
        ("00", "기본 시간표", True),
        ("01", None, True),
        ("02", "AI 에이전트 훈련 정보", False),         # 툴 세팅 앞부분: 과정 정보·단위기간·수료/졸업
        ("03", None, True),
        ("09", None, True),
    ],
}

HEADING = re.compile(r"^(#{1,6}) (.+)$")


@lru_cache
def load_docs():
    """{파일 앞 두 글자: (파일 이름, 확정값을 반영한 줄 목록)}"""
    docs = {}
    for p in sorted(DOCS.glob("*.md")):
        lines = [l for l in p.read_text(encoding="utf-8").splitlines()
                 if not l.startswith("> 출처: 모두의연구소")]          # 수집 메타데이터
        docs[p.name[:2]] = (p.stem, lines)
    for key, old, new in CORRECTIONS:
        stem, lines = docs[key]
        hit = [i for i, l in enumerate(lines) if old in l]
        if not hit:
            raise ValueError(f"확정값 반영 실패: {stem}에 '{old}'가 없습니다 (문서가 바뀌었나요?)")
        if new is None:
            lines = [l for i, l in enumerate(lines) if i not in hit]
        else:
            lines = [l.replace(old, new) if i in hit else l for i, l in enumerate(lines)]
        docs[key] = (stem, lines)
    return docs


def get_section(key, title, children=True):
    """섹션 하나의 (출처 이름, 본문). title=None이면 문서 전체."""
    stem, lines = load_docs()[key]
    if title is None:
        return stem, "\n".join(lines).strip()
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m and m.group(2).startswith(title):
            level = len(m.group(1))
            end = len(lines)
            for j in range(i + 1, len(lines)):
                n = HEADING.match(lines[j])
                if n and (not children or len(n.group(1)) <= level):
                    end = j
                    break
            return f"{stem} > {m.group(2).strip('*# ')}", "\n".join(lines[i:end]).strip()
    raise ValueError(f"섹션을 찾을 수 없습니다: {stem} > {title}")


def assemble(category):
    """카테고리의 근거 섹션 목록 [{"source", "text"}]. 범위 밖은 빈 목록."""
    return [dict(zip(("source", "text"), get_section(*spec))) for spec in SECTION_MAP.get(category, [])]


def format_context(category):
    """LLM에게 건넬 근거 문자열. 섹션마다 출처를 붙여 답변에서 근거를 밝힐 수 있게 한다."""
    return "\n\n".join(f"[출처: {s['source']}]\n{s['text']}" for s in assemble(category))


def check():
    """Step 5 통과 기준을 문자열 검사로 확인한다."""
    ctx = {c: format_context(c) for c in SECTION_MAP}
    every = "\n".join(ctx.values())
    tests = [
        # 카테고리별로 다른 근거만 — 장려금 근거에 제적 규정이 섞이지 않는다
        ("장려금 근거에 제적 규정 없음", all(s not in ctx["allowance"] for s in ["레드 카드", "옐로 카드", "제35조"])),
        ("출결 근거에 장려금 금액 없음", "1일 20,000원" not in ctx["attendance"]),
        ("범위 밖은 근거 없음", assemble("out_of_scope") == []),
        # 확정과 다른 문장은 어느 카테고리에도 안 보인다
        *[(f"숨김: {s}", s not in every) for s in
          ["AMcwZYrYEcQ1mkJP9", "RxTDy1yL2PfaFbA86", "R8ucZ232GNjcNktb7", "+1일", "13:00~14:00",
           "AI에이전트1기", "프데분", "프로덕트 데이터 분석가"]],
        # 확정값은 보인다
        ("공가 신청 폼 (#1)", "EWkJFEESCoBXgbR27" in ctx["attendance"]),
        ("증빙 제출 폼 (#2)", "hf1qEAGA6B1hNTTg6" in ctx["attendance"]),
        ("신청 기한 전일 (#3)", "하루 전까지" in ctx["attendance"]),
        ("점심 12:50 (#4)", "12:50 ~ 14:00" in ctx["schedule"] and "12:50~14:00" in ctx["schedule"]),
        ("예비군 증빙 (#5)", "참여확인증" not in ctx["attendance"]),
        ("배우자 출산 증빙 (#7)", "출산확인서, 가족관계증명서" in ctx["attendance"]),
        ("닉네임 2기 (#8)", "AI에이전트2기/이름/지역" in ctx["learning"]),
        ("1주/2주 미확정 표시 (#9)", ctx["allowance"].count("운영진 확인이 필요함") == 2),
    ]
    # 고정값 표의 원문 표기가 조립된 근거 어딘가에 남아 있다 (Step 7 가드레일이 이걸로 검사)
    fixed = (ROOT / "docs" / "FIXED_VALUES.md").read_text(encoding="utf-8")
    for row in re.findall(r"^\| (\d+) \|.*$", fixed, re.M):
        line = next(l for l in fixed.splitlines() if l.startswith(f"| {row} |"))
        for s in re.findall(r"`([^`]+)`", line.split("|")[4]):
            tests.append((f"고정값 #{row} `{s}`", s in every))
    for name, ok in tests:
        if not ok:
            print(f"[실패] {name}")
    passed = sum(ok for _, ok in tests)
    print(f"통과 {passed}/{len(tests)}")
    return passed == len(tests)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--check"]:
        sys.exit(0 if check() else 1)
    if len(sys.argv) > 1:
        print(format_context(sys.argv[1]))
        sys.exit()
    total = sum(len("\n".join(l)) for _, l in load_docs().values())
    print(f"전체 문서 {total:,}자\n")
    for cat in SECTION_MAP:
        secs = assemble(cat)
        n = len(format_context(cat))
        print(f"{cat:<11} {n:>6,}자 ({n / total:.0%}) · 섹션 {len(secs)}개")
        for s in secs:
            print(f"    {s['source']}")
