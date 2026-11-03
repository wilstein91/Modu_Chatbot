"""두 버전 전체 파이프라인을 평가용 문항으로 돌려 세 지표를 잰다.

실행:
    .venv/Scripts/python.exe run_eval.py llm
    .venv/Scripts/python.exe run_eval.py jev
결과: data/runs/full_<버전>.json (문항별 답변·도구·검증) + 화면에 점수표와 틀린 문항
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from common.evaluate import ROOT, evaluate, load_goldenset, print_report  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    track = sys.argv[1] if len(sys.argv) > 1 else "llm"
    if track == "jev":
        from track_jev.agent import ask
    else:
        from track_llm.agent import ask

    items = load_goldenset("eval")

    def safe(x):
        try:
            return ask(x["question"])
        except Exception as e:  # 실패한 문항은 답 없음(0점)으로 남기고 이유를 기록한다
            return {"error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=6) as pool:
        out = list(pool.map(safe, items))

    errors = [(x["id"], o["error"]) for x, o in zip(items, out) if "error" in o]
    for i, e in errors:
        print(f"실패 {i}: {e}")
    results = {x["id"]: o for x, o in zip(items, out) if "error" not in o}
    rep = evaluate(results)
    print(f"[{track} 버전 전체 파이프라인]")
    print_report(rep)
    path = ROOT / "data" / "runs" / f"full_{track}.json"
    path.write_text(json.dumps({"results": results, "errors": dict(errors),
                                "scores": {k: rep[k] for k in ("accuracy", "macro_f1", "tool_score", "answer_score")},
                                "rows": rep["rows"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {path.relative_to(ROOT)}")
