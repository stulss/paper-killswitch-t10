"""사전등록 문서가 모든 원자료보다 먼저 만들어졌는지 확인한다.

Git 저장소가 아니므로 커밋 타임스탬프 대신 파일 수정 시각으로 선후를 증명한다.

**ZIP으로 배포된 사본에서는 파일 수정 시각이 압축 해제 시각으로 덮여 쓸모가 없다.**
그래서 패키징 시점에 원본 파일시스템에서 읽은 시각과 SHA256을 매니페스트
(`data/raw/timestamps_manifest.json`)에 박아 둔다. 이 스크립트는

  1) 파일 시각이 쓸 만하면 파일 시각으로 확인하고,
  2) 시각이 뭉개져 있으면 매니페스트로 확인하되,
  3) 어느 쪽이든 **SHA256이 매니페스트와 일치하는지**를 함께 검사한다.

매니페스트도 결국 본인이 만든 파일이므로 외부 기관 등록만큼의 증거력은 없다.
그 한계는 논문 2.1절과 이 파일 아래 주석에 그대로 적어 둔다.

사용법: python src/verify_prereg.py
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949)에서 유니코드 출력이 죽지 않게 한다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "docs" / "02_사전등록.md"
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "timestamps_manifest.json"


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fmt(t):
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


def raw_files():
    return sorted(p for p in RAW.rglob("*")
                  if p.is_file() and p.name != MANIFEST.name)


def outcome_files():
    """**결과 자료** = 모델의 응답. 사전등록보다 나중이어야 하는 것은 이쪽이다.

    자극 자료(시나리오·프롬프트)는 사전등록보다 먼저 만들어지는 것이 정상이다.
    사전등록 3~5절이 그 내용을 이미 기술하고 있고, 사전등록 11절도 선후 관계의
    대상을 `data/raw/trials/`로 못박아 두었다. 자극을 먼저 만들고 가설을 확정한
    뒤 결과를 모으는 순서가 원래 맞다.
    """
    return sorted((RAW / "trials").glob("*.json"))


def stimulus_files():
    """자극 자료와 참고문헌 조회 기록. 선후 판정 대상이 아니지만 시각은 공개한다."""
    outcomes = set(outcome_files())
    return [p for p in raw_files() if p not in outcomes]


def check_by_mtime(pre_m, files):
    """파일 시각이 신뢰할 만한지 판단하고, 그렇다면 선후를 확인한다."""
    times = {round(p.stat().st_mtime) for p in files} | {round(pre_m)}
    if len(times) <= 2:                    # 전부 같은 시각 = 압축 해제로 덮인 사본
        return None, "파일 시각이 뭉개져 있다 (ZIP 사본으로 보인다)"
    bad = [p for p in files if p.stat().st_mtime <= pre_m]
    return not bad, "결과 자료 %d개 중 사전등록보다 이른 것 %d개" % (len(files), len(bad))


def main():
    if not PREREG.exists():
        sys.exit("사전등록 문서가 없다: %s" % PREREG)
    files = raw_files()
    outcomes = outcome_files()
    if not outcomes:
        sys.exit("결과 자료가 없다: %s" % (RAW / "trials"))

    pre_hash = sha256(PREREG)
    print("사전등록 문서 SHA256 : %s" % pre_hash)

    # 자극 자료는 사전등록보다 먼저 만들어지는 것이 정상이다. 숨기지 않고 공개한다.
    stim = stimulus_files()
    if stim:
        print("자극 자료(선후 판정 대상 아님) : %d개" % len(stim))
        for p in stim:
            print("    %-38s %s" % (p.relative_to(ROOT).as_posix(),
                                    fmt(p.stat().st_mtime)))
        print("    └ 시나리오·프롬프트는 사전등록 3~5절에 내용이 기술돼 있다.")

    # --- 1. 파일 시각으로 확인 (결과 자료만)
    ok, note = check_by_mtime(PREREG.stat().st_mtime, outcomes)
    if ok is True:
        print("파일 시각 확인      : 통과 — %s" % note)
        print("  사전등록 %s / 가장 이른 결과 자료 %s"
              % (fmt(PREREG.stat().st_mtime),
                 fmt(min(p.stat().st_mtime for p in outcomes))))
    elif ok is False:
        sys.exit("파일 시각 확인      : 실패 — %s" % note)
    else:
        print("파일 시각 확인      : 건너뜀 — %s" % note)

    # --- 2. 매니페스트로 확인 (ZIP 사본에서 유일하게 남는 증거)
    if not MANIFEST.exists():
        if ok is True:
            print("\n통과: 파일 시각으로 확인했다. (매니페스트 없음)")
            return
        sys.exit("매니페스트가 없어 확인할 수 없다: %s" % MANIFEST)

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if man["prereg"]["sha256"] != pre_hash:
        sys.exit("실패: 사전등록 문서가 패키징 이후 변경됐다. "
                 "매니페스트 %s vs 현재 %s"
                 % (man["prereg"]["sha256"][:16], pre_hash[:16]))
    print("사전등록 내용 일치   : 통과 (매니페스트와 SHA256 동일)")

    pre_t = man["prereg"]["mtime"]
    rec_out = [f for f in man["raw_files"] if "/trials/" in f["path"]]
    rec_stim = [f for f in man["raw_files"] if "/trials/" not in f["path"]]
    earlier = [f for f in rec_out if f["mtime"] <= pre_t]
    print("매니페스트 기록      : 사전등록 %s / 결과 자료 %d개 (자극 자료 %d개는 판정 제외)"
          % (man["prereg"]["mtime_readable"], len(rec_out), len(rec_stim)))
    if earlier:
        print("실패: 사전등록보다 먼저 만들어진 결과 자료가 있다.")
        for f in earlier[:10]:
            print("  -", f["path"], f["mtime_readable"])
        sys.exit(1)

    # --- 3. 원자료 내용이 매니페스트 기록과 같은지
    recorded = {f["path"]: f["sha256"] for f in man["raw_files"]}
    changed = [p.relative_to(ROOT).as_posix() for p in files
               if recorded.get(p.relative_to(ROOT).as_posix()) not in (None, sha256(p))]
    missing = [k for k in recorded if not (ROOT / k).exists()]
    if changed or missing:
        print("실패: 원자료가 패키징 이후 변경/삭제됐다.")
        for x in (changed + missing)[:10]:
            print("  -", x)
        sys.exit(1)
    print("원자료 내용 일치     : 통과 (%d개 파일 SHA256 동일)" % len(recorded))

    print("\n통과: 사전등록 문서가 모든 결과 자료보다 먼저 만들어졌고, "
          "이후 사전등록과 원자료 모두 변경되지 않았다.")
    print("      (자극 자료인 시나리오·프롬프트는 사전등록보다 먼저 만들었다. "
          "사전등록 3~5절에 그 내용이 기술돼 있다.)")
    print("주의: 매니페스트는 연구자 본인이 만든 파일이므로 외부 기관 등록만큼의 "
          "증거력은 없다. 이 한계는 논문 2.1절에 적어 두었다.")


if __name__ == "__main__":
    main()
