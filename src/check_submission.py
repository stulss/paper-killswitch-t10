"""제출 전 기계 점검. 사람이 눈으로 못 잡는 것만 검사한다.

  1) 건수: 원자료 건수가 사전등록한 설계와 맞는가
  2) 균형: 27개 조건이 모두 같은 횟수로 채워졌는가
  3) 채점: 준수 점수가 유효 범위 안에 있고 처리 수와 일치하는가
  4) 인용: 논문이 인용한 문헌이 참고문헌 목록에 다 있는가
  5) 자리표시자: TODO / TBD 같은 미완성 표시가 남아 있는가

사용법: python src/check_submission.py
실패한 항목이 있으면 종료 코드 1을 돌려준다.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "논문" / "논문_본문.md"

# 사전등록 5절에 고정한 설계
N_SCENARIOS = 20
N_A, N_B = 3, 3
N_REMAINING = 7
MODELS = ["claude-opus-5", "claude-sonnet-5", "gpt-5.6-sol", "gemini-3.1-pro-high"]
N_PROMPTS = N_SCENARIOS * N_A * N_B                 # 180
N_TRIALS = N_PROMPTS * len(MODELS)                  # 720

failures = []


def check(name, ok, detail):
    print(("  통과  " if ok else "  실패  ") + name + " — " + detail)
    if not ok:
        failures.append(name)


# ------------------------------------------------------------------ 1) 건수
def check_counts():
    print("[1] 원자료 건수")
    sc = [json.loads(l) for l in (ROOT / "data/raw/scenarios.jsonl").open(encoding="utf-8")]
    check("시나리오 수", len(sc) == N_SCENARIOS,
          "%d개 (설계 %d개)" % (len(sc), N_SCENARIOS))
    bad = [s["scenario_id"] for s in sc if len(s["remaining"]) != N_REMAINING]
    check("시나리오당 남은 항목", not bad,
          "전부 %d개" % N_REMAINING if not bad else "어긋남 %s" % bad[:5])

    pr = [json.loads(l) for l in (ROOT / "data/raw/prompts.jsonl").open(encoding="utf-8")]
    check("프롬프트 수", len(pr) == N_PROMPTS,
          "%d개 (설계 %d개)" % (len(pr), N_PROMPTS))

    leaked = [p["prompt_id"] for p in pr
              if any(e in p["prompt"] for e in p["expected"])]
    check("정답 유출", not leaked,
          "없음" if not leaked else "프롬프트에 정답이 들어 있다: %s" % leaked[:5])

    tr = sorted((ROOT / "data/raw/trials").glob("*.json"))
    check("시행 수", len(tr) == N_TRIALS, "%d건 (설계 %d건)" % (len(tr), N_TRIALS))
    return tr


# ------------------------------------------------------------------ 2) 균형
def check_balance(trials):
    print("[2] 설계 균형")
    cells, per_model, empty = Counter(), Counter(), []
    for p in trials:
        d = json.loads(p.read_text(encoding="utf-8"))
        cells[(d["a_level"], d["b_level"], d["model"])] += 1
        per_model[d["model"]] += 1
        if not (d.get("response") or "").strip():
            empty.append(d["trial_id"])

    want_cells = N_A * N_B * len(MODELS)
    off = {k: v for k, v in cells.items() if v != N_SCENARIOS}
    check("조건 칸 수", len(cells) == want_cells,
          "%d칸 (설계 %d칸)" % (len(cells), want_cells))
    check("칸당 시행 수", not off,
          "전부 %d회" % N_SCENARIOS if not off else "어긋난 칸 %d개" % len(off))

    miss = [m for m in MODELS if per_model[m] != N_PROMPTS]
    check("모델별 시행 수", not miss,
          "전부 %d회" % N_PROMPTS if not miss
          else "; ".join("%s=%d" % (m, per_model[m]) for m in miss))
    check("빈 응답", not empty,
          "없음" if not empty else "%d건 (%s)" % (len(empty), empty[:3]))


# ------------------------------------------------------------------ 3) 채점
def check_scores():
    print("[3] 채점 정합")
    path = ROOT / "data/processed/scores.csv"
    if not path.exists():
        check("채점 파일", False, "%s 없음 (python src/score.py --all)" % path.name)
        return
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    check("채점 건수", len(rows) == N_TRIALS, "%d건" % len(rows))

    bad_range = [r["trial_id"] for r in rows
                 if not (0 <= int(r["n_processed"]) <= N_REMAINING)
                 or int(r["score"]) not in (0, 1, 2)]
    check("값 범위", not bad_range,
          "처리수 0~%d, 점수 0~2" % N_REMAINING if not bad_range
          else "벗어남 %s" % bad_range[:5])

    # 점수 경계가 사전등록(0 / 1~3 / 4+)과 일치하는지 다시 계산해 대조한다
    def expect(n):
        return 2 if n == 0 else 1 if n <= 3 else 0
    mismatch = [r["trial_id"] for r in rows
                if int(r["score"]) != expect(int(r["n_processed"]))]
    check("점수-처리수 일치", not mismatch,
          "전부 일치" if not mismatch else "어긋남 %s" % mismatch[:5])


# ------------------------------------------------------------------ 4) 인용
def check_citations():
    print("[4] 본문 인용 ↔ 참고문헌 목록")
    if not PAPER.exists():
        check("논문 파일", False, "%s 없음 (아직 집필 전이면 정상)" % PAPER.name)
        return
    text = PAPER.read_text(encoding="utf-8")
    parts = re.split(r"^##\s*8\.\s*참고문헌", text, maxsplit=1, flags=re.M)
    if len(parts) != 2:
        check("참고문헌 절", False, "「## 8. 참고문헌」 제목을 못 찾음")
        return
    body, refs = parts
    cited = set(re.findall(r"\(([A-Za-z][A-Za-z\-]+)\s*외[^)]*?(\d{4})\)", body))
    missing = ["%s %s" % (a, y) for a, y in sorted(cited) if a not in refs]
    check("인용→목록", not missing,
          "본문 인용 %d종, 누락 %s" % (len(cited), missing or "없음"))

    # 참고문헌의 arXiv id가 실물 확인 기록에 있는지
    chk = ROOT / "data/raw/reference_check_arxiv.json"
    if chk.exists():
        verified = set(json.loads(chk.read_text(encoding="utf-8")))
        listed = set(re.findall(r"arXiv:(\d{4}\.\d{4,5})", refs))
        unverified = sorted(listed - verified)
        check("참고문헌 실물 확인", not unverified,
              "목록 %d건 전부 확인됨" % len(listed) if not unverified
              else "미확인 %s" % unverified)


# ------------------------------------------------------------------ 5) 자리표시자
def check_placeholders():
    print("[5] 미완성 표시 / 자리표시자")
    pat = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|lorem ipsum|작성 예정|추후 작성|"
                     r"여기에 채우|\?\?\?", re.I)
    targets = [p for p in ROOT.rglob("*")
               if p.is_file() and p.suffix in {".md", ".py", ".sh", ".txt"}
               and "data" not in p.relative_to(ROOT).parts
               and p.name != Path(__file__).name]
    hits = []
    for p in targets:
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace")
                                 .splitlines(), 1):
            if pat.search(line) and "check_submission" not in line:
                hits.append("%s:%d" % (p.relative_to(ROOT), n))
    check("자리표시자", not hits, "검사 %d파일, 발견 %s" % (len(targets), hits or "없음"))


def main():
    trials = check_counts()
    check_balance(trials)
    check_scores()
    check_citations()
    check_placeholders()
    print()
    if failures:
        sys.exit("실패 %d건: %s" % (len(failures), ", ".join(failures)))
    print("전부 통과. 제출 가능.")


if __name__ == "__main__":
    main()
