"""재현 패키지 ZIP을 만든다.

넣는 것과 빼는 것의 기준은 docs/05_배포.md 4절과 같다.
만든 뒤 ZIP 안의 목록을 다시 읽어 필수 파일이 다 들어갔는지 확인한다.

사용법: python src/package.py
출력: 과제10_재현패키지.zip
"""
import hashlib
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949)에서 유니코드 출력이 죽지 않게 한다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "과제10_재현패키지.zip"

INCLUDE_DIRS = ["논문", "docs", "src", "data", "results"]
INCLUDE_FILES = ["README.md", "작업내역_체크리스트.md", "CLAUDE.md", "run_all.sh"]
EXCLUDE_NAMES = {"bash.exe.stackdump", ".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIX = {".pyc", ".zip", ".stackdump", ".log"}
EXCLUDE_PARTS = {"__pycache__", ".git", ".ipynb_checkpoints"}

N_TRIALS = 720          # 사전등록 5절에 고정한 본 실행 시행 수

# 이것들이 ZIP 안에 없으면 실패로 본다
REQUIRED = [
    "README.md", "CLAUDE.md", "run_all.sh", "작업내역_체크리스트.md",
    "논문/논문_본문.md",
    "docs/00_과제_요구사항_매핑.md", "docs/01_기획.md", "docs/02_사전등록.md",
    "docs/03_선행연구_검증.md", "docs/05_배포.md",
    "docs/검증안내서.md", "docs/트러블슈팅.md", "docs/AI_3줄.md",
    "src/llm.py", "src/gen_scenarios.py", "src/build_prompts.py",
    "src/run_trials.py", "src/score.py", "src/stats.py", "src/analyze.py",
    "src/check_submission.py", "src/verify_prereg.py", "src/verify_references.py",
    "data/raw/scenarios.jsonl", "data/raw/prompts.jsonl",
    "data/raw/reference_check_arxiv.json",
    "data/raw/timestamps_manifest.json",
    "data/processed/scores.csv",
    "results/결과표.md", "results/figure1_모델별_조건별_준수율.svg",
]


def wanted(p):
    if not p.is_file():
        return False
    if p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIX:
        return False
    return not (EXCLUDE_PARTS & set(p.relative_to(ROOT).parts))


def write_manifest():
    """원본 파일시스템의 시각과 SHA256을 매니페스트로 굳힌다.

    ZIP 압축 해제는 파일 수정 시각을 해제 시각으로 덮어쓴다. 그러면 "사전등록이
    원자료보다 먼저"라는 증거가 패키지 안에서 사라진다. 그래서 패키징 직전에
    원본에서 읽은 값을 파일로 남긴다. (src/verify_prereg.py가 이걸 읽는다)
    """
    def entry(p):
        st = p.stat()
        return {"path": p.relative_to(ROOT).as_posix(),
                "mtime": st.st_mtime,
                "mtime_readable": datetime.fromtimestamp(st.st_mtime)
                .strftime("%Y-%m-%d %H:%M:%S"),
                "bytes": st.st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    prereg = ROOT / "docs" / "02_사전등록.md"
    raw = ROOT / "data" / "raw"
    manifest_path = raw / "timestamps_manifest.json"
    files = sorted(p for p in raw.rglob("*")
                   if p.is_file() and p.name != manifest_path.name)
    manifest = {
        "설명": "사전등록 문서와 원자료의 원본 생성 시각·해시. "
                "ZIP 해제 시 파일 시각이 덮여 쓸모없어지므로 여기 굳혀 둔다.",
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prereg": entry(prereg),
        "raw_files": [entry(p) for p in files],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print("매니페스트 기록: 원자료 %d개 + 사전등록 1개" % len(files))
    return manifest_path


def main():
    write_manifest()
    targets = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if wanted(p):
            targets.append(p)
    for d in INCLUDE_DIRS:
        targets += [p for p in sorted((ROOT / d).rglob("*")) if wanted(p)]

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in targets:
            z.write(p, p.relative_to(ROOT).as_posix())

    with zipfile.ZipFile(ZIP) as z:
        names = set(z.namelist())
        bad = z.testzip()
    missing = [r for r in REQUIRED if r not in names]
    trials = sum(1 for n in names
                 if n.startswith("data/raw/trials/") and n.endswith(".json"))
    pilots = sum(1 for n in names
                 if n.startswith("data/pilot") and n.endswith(".json"))

    print("%s  (%.1f MB, %d개 파일)" % (ZIP.name, ZIP.stat().st_size / 1e6, len(names)))
    print("  본 실행 원자료: %d개 / 예비 실행 원자료: %d개" % (trials, pilots))
    print("  ZIP 무결성: %s" % ("정상" if bad is None else "손상 " + bad))
    if missing:
        sys.exit("필수 파일 누락: %s" % missing)
    if trials != N_TRIALS:
        sys.exit("data/raw/trials 파일이 %d개가 아니다: %d개" % (N_TRIALS, trials))
    print("\n필수 파일 %d개 모두 포함. 다른 폴더에 풀어 확인하라." % len(REQUIRED))


if __name__ == "__main__":
    main()
