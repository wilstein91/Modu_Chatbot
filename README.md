# Project_CSC — 모두연 AI에이전트 2기 훈련생 상담 챗봇

훈련생이 출결·공가·장려금·제적 같은 규정을 물으면, **질문 종류를 가르고 → 그 종류의 공지만 근거로 → 답한 뒤 → 근거에 없는 내용이 섞였는지 검사**하고, 모르면 운영진에게 넘기는 챗봇.
아이펠 AI에이전트 2기 「에이전트 팀 꾸리기」 5번 노드(고객 응대 에이전트 만들기 [프로젝트]) 과제.

- 작성자: Sung, Hyun-Joon
- 근거 문서: [docs/](docs/README.md) — 2기 노션 공지 19개 문서

## 두 가지 버전을 나란히 만든다

같은 근거 문서·같은 평가셋으로 두 버전을 만들고 점수를 비교한다. 노드 4에서 배운 "노드 하나만 갈아 끼우고 같은 평가셋으로 다시 잰다"를 버전 단위로 하는 것이다.

| | `track_llm/` (JEV 미사용) | `track_jev/` (JEV 사용) |
|---|---|---|
| ① 카테고리 판정 | LLM 구조화 출력(`Literal` 스키마) + 확신도 | Jev **Choice**(어느 카테고리?) + **Noul**(규정 범위 안의 질문인가?) |
| 넘기기 판단 | 확신도 임계값 (노드 4 `gate`) | Jev 확률을 코드의 **진리표**로 판정 (판단은 Jev, 결정은 코드) |
| ② 근거 조립 | 공통 (`common/`) | 공통 (`common/`) |
| ③ 답변 생성 | LLM | LLM (Jev는 문장을 만들지 않는다) |
| ④ 검증 | 숫자 출처 역추적 가드레일 (노드 4 §7) | 숫자 가드레일 + Jev가 문장별로 "근거가 이 문장을 뒷받침하나/반대하나/말이 없나" 판정 |

> 💡 **Jev(제브)**: TypeSafe의 판단 전용 모델. 글을 쓰지 않고, 정해 준 질문에 "선택지 중 무엇인가(Choice)", "이 문장이 참일 확률(Noul)"을 확률로 돌려준다. 그래서 분류·검증처럼 **판단**만 필요한 자리에 쓴다.

## 결과 요약 (평가용 36문항)

| 버전 | 분류 macro F1 | 도구 호출 적절성 | 답변 적절성 | 거짓 답 8개 차단 |
|---|---|---|---|---|
| 키워드 규칙 (기준선, 분류만) | 0.451 | — | — | — |
| LLM 버전 | 0.944 | 0.806 | 0.861 | 1 / 8 (숫자 가드레일) |
| Jev 버전 | 0.913 | 0.806 | 0.806 | 8 / 8 (가드레일 + Jev 문장 검증) |

설계 판단·실패 분석·개선 기록은 [REPORT.md](REPORT.md).

## 폴더 구조

```
Project_CSC/
├── docs/
│   ├── notion_2기/      # 근거 문서 19개 (2기 노션 → md)
│   ├── CONFLICTS.md     # 문서끼리 어긋나는 곳과 확정값
│   ├── FIXED_VALUES.md  # 규정 숫자 29개 (숫자 가드레일 정답지)
│   ├── MAPPING.md       # 카테고리 ↔ 문서 섹션 매핑표
│   └── images/          # 데모 캡처
├── data/
│   ├── goldenset.json      # 평가셋 48문항 (예시용 12 + 평가용 36)
│   ├── model_answers.json  # 채점기 검증용 모범 답안 36개
│   ├── deception_set.json  # 검증 시험용 거짓 답 8개
│   └── runs/               # 측정 결과
├── common/
│   ├── context.py        # 섹션 단위 근거 조립 + 확정값 반영
│   ├── tools.py          # 조회 도구 5개 + escalate_to_staff
│   ├── guardrail.py      # 숫자·시간·링크 가드레일
│   ├── evaluate.py       # 분류 지표 + 도구 호출·답변 적절성 채점, 자가 검사
│   └── deception_test.py # 거짓 답으로 두 검사 비교
├── track_llm/            # JEV 미사용: prompts.py(분류 지침·답변 규칙), router.py(규칙·LLM 라우터), agent.py(LangGraph)
├── track_jev/            # JEV 사용: questions.py(Jev 질문), router.py(진리표), verifier.py(문장 검증), agent.py
├── app.py                # streamlit 데모 (두 버전 전환)
├── chat.py               # 터미널 대화
├── run_eval.py           # 전체 파이프라인 채점
├── requirements.txt
└── REPORT.md
```

## 실행 방법

**1. 설치** (Python 3.13에서 확인)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

macOS·Linux는 `.venv/Scripts/python.exe` 대신 `.venv/bin/python`.

**2. 키 넣기** — 프로젝트 폴더에 `.env` 파일을 만들고 두 줄을 적는다 (저장소에 올리지 않음).

```
OPENAI_API_KEY=...
TYPESAFE_API_KEY=...
```

- `OPENAI_API_KEY` — 두 버전 모두 (분류 `gpt-5.6-luna`, 답변 `gpt-5.6-terra`. 환경변수 `CLASSIFY_MODEL`, `ANSWER_MODEL`로 바꿀 수 있음)
- `TYPESAFE_API_KEY` — Jev 버전만

**3. 실행**

```bash
.venv/Scripts/streamlit.exe run app.py              # 데모 화면
.venv/Scripts/python.exe chat.py                    # 터미널 대화 (LLM 버전, --jev 를 붙이면 Jev 버전)
.venv/Scripts/python.exe run_eval.py llm            # 전체 채점 (llm / jev)
```

**API 키 없이 확인할 수 있는 것**

```bash
.venv/Scripts/python.exe -m common.evaluate --selftest          # 채점기 자가 검사
.venv/Scripts/python.exe -m common.evaluate data/model_answers.json  # 모범 답안 채점 (36/36)
.venv/Scripts/python.exe -m common.context --check              # 근거 조립 검사 (52/52)
.venv/Scripts/python.exe -m track_llm.router                    # 키워드 규칙 기준선
```
