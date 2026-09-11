"""프롬프트 180개 × 모델 4종 = 720 시행을 실행한다.

원출력(response)과 호출 메타데이터를 하나도 버리지 않고 시행마다 한 파일에 남긴다.

**재실행 안전**: 이미 결과 파일이 있는 시행은 건너뛴다. 구독 사용량 한도에
걸려 중간에 멈춰도 같은 명령을 다시 실행하면 남은 것부터 이어서 진행한다.

모델을 번갈아 배치하므로 동시 실행 중인 호출이 서로 다른 제공사로 흩어진다.

사용법
  python src/run_trials.py --pilot          예비 실행(앞 3시나리오, data/pilot/)
  python src/run_trials.py                  본 실행(전체, data/raw/trials/)
  python src/run_trials.py --models gpt-5.6-sol   특정 모델만
"""
import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "data" / "raw" / "prompts.jsonl"
PILOT_SCENARIOS = 3              # 예비 실행에 쓸 시나리오 수

_print_lock = threading.Lock()


def run_one(job):
    row, model, outdir = job
    trial_id = "%s__%s" % (row["prompt_id"], model)
    path = outdir / ("%s.json" % trial_id)
    if path.exists():
        return "skip", trial_id, ""

    try:
        response, meta = llm.call(row["prompt"], model)
    except Exception as e:
        return "fail", trial_id, str(e)[:200]

    path.write_text(json.dumps({
        "trial_id": trial_id,
        "prompt_id": row["prompt_id"],
        "scenario_id": row["scenario_id"],
        "a_level": row["a_level"],
        "b_level": row["b_level"],
        "model": model,
        "prompt": row["prompt"],          # 보낸 것 전체를 그대로 보존
        "response": response,             # 받은 것 전체를 그대로 보존
        "expected": row["expected"],
        "meta": meta,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return "ok", trial_id, "%.1f초" % meta["wall_seconds"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true",
                    help="앞 %d개 시나리오만 data/pilot/에 실행" % PILOT_SCENARIOS)
    ap.add_argument("--models", nargs="*", default=list(llm.MODELS))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    for m in a.models:
        if m not in llm.MODELS:
            sys.exit("모르는 모델: %s (가능: %s)" % (m, list(llm.MODELS)))

    rows = [json.loads(l) for l in PROMPTS.open(encoding="utf-8")]
    if a.pilot:
        keep = {"sc%02d" % i for i in range(1, PILOT_SCENARIOS + 1)}
        rows = [r for r in rows if r["scenario_id"] in keep]
        outdir = ROOT / "data" / "pilot"
    else:
        outdir = ROOT / "data" / "raw" / "trials"
    outdir.mkdir(parents=True, exist_ok=True)

    # 모델을 안쪽 루프에 두어 동시 실행이 여러 제공사로 흩어지게 한다.
    jobs = [(r, m, outdir) for r in rows for m in a.models]
    done = sum(1 for r, m, o in jobs if (o / ("%s__%s.json" % (r["prompt_id"], m))).exists())
    print("대상 %d 시행 (완료 %d, 남은 %d) → %s"
          % (len(jobs), done, len(jobs) - done, outdir.relative_to(ROOT)))
    print("모델: %s / 동시 %d" % (", ".join(a.models), a.workers))

    counts = {"ok": 0, "skip": 0, "fail": 0}
    fails = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, (status, tid, note) in enumerate(ex.map(run_one, jobs), 1):
            counts[status] += 1
            if status == "fail":
                fails.append((tid, note))
            with _print_lock:
                if status == "fail":
                    print("  실패 %s — %s" % (tid, note), flush=True)
                elif counts["ok"] and counts["ok"] % 20 == 0 and status == "ok":
                    print("  진행 %d/%d (성공 %d)" % (i, len(jobs), counts["ok"]),
                          flush=True)

    print("\n성공 %d / 건너뜀 %d / 실패 %d" % (counts["ok"], counts["skip"], counts["fail"]))
    if fails:
        print("실패한 시행은 같은 명령을 다시 실행하면 재시도된다:")
        for tid, note in fails[:10]:
            print("  -", tid, note)
        sys.exit(1)
    print("전부 완료.")


if __name__ == "__main__":
    main()
