"""챗봇이 부를 수 있는 도구 — 이름은 평가셋의 expected_tools와 똑같이 맞춘다.

조회 도구 5개는 카테고리별 근거(context.py)를 돌려주고, escalate_to_staff는 운영진 이관을 기록한다.
"""

from langchain_core.tools import tool

from common.context import format_context


@tool
def lookup_attendance() -> str:
    """출결·공가 안내를 조회한다: 입·퇴실 시간, 지각·조퇴·외출·결석 기준, 공가·휴가 종류와 증빙, 신청 폼, 캠."""
    return format_context("attendance")


@tool
def lookup_allowance() -> str:
    """장려금·고용형태 안내를 조회한다: 훈련장려금 지급 기준·금액, 고용형태 신고·변경, 아르바이트, 취업 시 할 일."""
    return format_context("allowance")


@tool
def lookup_dismissal() -> str:
    """제적·참여규칙 안내를 조회한다: 제적 사유(레드카드), 경고(옐로카드), 훈련 참여 규칙."""
    return format_context("dismissal")


@tool
def lookup_learning() -> str:
    """학습생활 안내를 조회한다: 질문하는 방법, ZEP·디스코드·LMS 사용과 닉네임, 노드 저작권, 조별학습, 퀘스트, 나의 도메인 개발하기."""
    return format_context("learning")


@tool
def lookup_schedule() -> str:
    """일정·수료 안내를 조회한다: 과정 소개, 훈련 기간·단위기간, 커리큘럼 일정, 시간표, 수료·졸업 기준, 노드 개선 내역."""
    return format_context("schedule")


@tool
def escalate_to_staff(reason: str) -> str:
    """안내 문서로 답할 수 없는 질문을 운영진(운영매니저)에게 넘긴다. 본인 기록 조회, 문서에 없는 규정, 문서끼리 다른 내용일 때 쓴다."""
    # 데모용: 실제 메시지는 보내지 않고 이관 사실만 돌려준다.
    return f"운영진 이관 접수: {reason}"


LOOKUP_TOOLS = {
    "attendance": lookup_attendance,
    "allowance": lookup_allowance,
    "dismissal": lookup_dismissal,
    "learning": lookup_learning,
    "schedule": lookup_schedule,
}
ALL_TOOLS = [*LOOKUP_TOOLS.values(), escalate_to_staff]
