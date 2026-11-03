"""속여 보기 — 일부러 틀린 답(data/deception_set.json)을 두 검사에 넣어 어느 검사가 무엇을 잡는지 본다.

  - 숫자 가드레일 (common/guardrail.py): 두 버전 공통
  - Jev 문장 검증 (track_jev/verifier.py): Jev 버전만

실행:
    python -m common.deception_test
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from common import guardrail
from common.evaluate import ROOT
from track_jev import verifier

TYPE_NAMES = {"number_wrong": "숫자 틀림", "fabricated_no_number": "숫자 없는 지어내기"}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from typesafe_sdk import TypeSafeClient

    items = json.loads((ROOT / "data" / "deception_set.json").read_text(encoding="utf-8"))
    evid = {x["id"]: guardrail.evidence_for([f"lookup_{x['category']}"]) for x in items}
    gr = {x["id"]: guardrail.check(x["answer"], evid[x["id"]], x["question"]) for x in items}
    with TypeSafeClient() as client, ThreadPoolExecutor(max_workers=8) as pool:
        jv = dict(zip([x["id"] for x in items],
                      pool.map(lambda x: verifier.verify(client, x["answer"], evid[x["id"]], x["question"]), items)))

    print("| # | 유형 | 틀린 답 | 숫자 가드레일 | Jev 검증 |")
    print("|---|---|---|---|---|")
    caught = {t: [0, 0, 0] for t in TYPE_NAMES}  # [건수, 가드레일, Jev]
    for x in items:
        g, j = gr[x["id"]], jv[x["id"]]
        c = caught[x["type"]]
        c[0] += 1
        c[1] += not g["ok"]
        c[2] += not j["ok"]
        gtxt = f"🚫 막음 ({', '.join(g['unsupported'])})" if not g["ok"] else "통과"
        bad = [s for s in j["sentences"] if not s["ok"]]
        jtxt = f"🚫 막음 ({bad[0]['support']})" if bad else "통과"
        print(f"| {x['id']} | {TYPE_NAMES[x['type']]} | {x['answer'][:50]} | {gtxt} | {jtxt} |")
    print()
    for t, (n, g, j) in caught.items():
        print(f"{TYPE_NAMES[t]} {n}개 — 가드레일 {g}개 막음 · Jev {j}개 막음")
    out = ROOT / "data" / "runs" / "deception_test.json"
    out.write_text(json.dumps({"guardrail": gr, "jev": jv}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"결과 저장: {out.relative_to(ROOT)}")
