"""참고문헌이 실제로 존재하는지 arXiv 공식 API로 확인한다.

AI가 알려 준 문헌 목록을 그대로 믿지 않기 위한 스크립트다.
제목·저자 전체·최초 공개일·게재 학회 표기를 arXiv에서 직접 받아 온다.

출력: data/raw/reference_check_arxiv.json (조회 응답 원본)
사용법: python src/verify_references.py
"""
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Windows 콘솔(cp949)에서 유니코드 출력이 죽지 않게 한다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "reference_check_arxiv.json"

# 논문에서 인용하는 arXiv 문헌 전부.
# AI가 알려 준 목록을 그대로 믿지 않고 여기서 전부 실물 대조한다.
IDS = {
    # --- 중단 저항 / 교정가능성(corrigibility)
    "2509.14260": "Schlatter 외, Incomplete Tasks Induce Shutdown Resistance",
    "2307.00787": "van der Weij 외, Evaluating Shutdown Avoidance in Textual Scenarios",
    "2506.04018": "Naik 외, AgentMisalignment",
    "2305.19861": "Carey 외, Human Control: Definitions and Algorithms",
    "2510.15395": "Hudson, Corrigibility Transformation",
    "2507.20964": "Nayebi, Core Safety Values for Provably Corrigible Agents",
    "2606.00341": "Tien 외, ROGUE: Misaligned Agent Behavior from Ordinary Computer Use",
    "2604.08465": "Dietrich, Peer-Preservation in Multi-Agent LLM Systems",
    # --- 지시 위계 / 충돌하는 지시
    "2502.08745": "Zhang 외, IHEval: Following the Instruction Hierarchy",
    "2607.25987": "McCauley 외, IH-Benchmark: Conflict-Centered Benchmark",
    "2604.09443": "Zhang 외, Many-Tier Instruction Hierarchy in LLM Agents",
    "2606.22470": "Javed 외, PRIME: Prompt Resolution Under Incompatible Instructions",
    "2602.20813": "Petrova 외, Pressure Reveals Character",
    # --- 프롬프트 인젝션 (예비 실행에서 겪은 문제의 근거)
    "2608.27092": "Rahman 외, The Framing Gap",
    "2608.23873": "Penman 외, Semantic Overlays",
    # --- 평가 인지 (이 연구의 한계 근거)
    "2603.03824": "Chaudhary 외, In-Context Environments Induce Evaluation-Awareness",
}


def query(arxiv_id):
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": 1})
    req = urllib.request.Request(url, headers={"User-Agent": "t10-study/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.parse(r).getroot()
    entry = root.find(ATOM + "entry")
    if entry is None or entry.find(ATOM + "title") is None:
        return None
    comment = entry.find(ARXIV + "comment")
    return {
        "title": " ".join(entry.find(ATOM + "title").text.split()),
        "authors": [a.find(ATOM + "name").text for a in entry.findall(ATOM + "author")],
        "published": entry.find(ATOM + "published").text[:10],
        "comment": comment.text if comment is not None else None,
        "abstract": " ".join(entry.find(ATOM + "summary").text.split()),
    }


def main():
    results, missing = {}, []
    for arxiv_id, label in IDS.items():
        try:
            r = query(arxiv_id)
        except Exception as e:
            r, err = None, str(e)
        else:
            err = None
        if r is None:
            missing.append((arxiv_id, label, err))
            print("%s  실물 없음/오류  %s" % (arxiv_id, label))
        else:
            results[arxiv_id] = {"expected_label": label, **r}
            print("%s  확인  %s 외 %d명 (%s)"
                  % (arxiv_id, r["authors"][0], len(r["authors"]) - 1, r["published"]))
        time.sleep(3)                          # arXiv API 예의상 간격

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n확인 %d건 / 실패 %d건 -> %s" % (len(results), len(missing), OUT))
    if missing:
        sys.exit("실물을 확인하지 못한 문헌이 있다. 인용에서 빼라.")


if __name__ == "__main__":
    main()
