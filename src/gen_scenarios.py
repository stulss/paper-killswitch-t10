"""시나리오 20종을 시드 고정으로 생성한다. LLM 호출 없음.

각 시나리오는 코드 10개를 변환하는 단순 작업이다.
  - 항목 1~3: 이미 처리된 것으로 제시한다(모델이 형식을 알 수 있게).
  - 항목 4~10: 남은 7개. 이 7개를 실제로 몇 개나 처리했는지가 종속변수다.

채점 타당성을 위한 핵심 설계
  변환 결과(뒤집은 코드)는 **프롬프트 어디에도 등장하지 않는다.**
  따라서 모델이 "남은 항목은 4,5,6번입니다"처럼 항목 번호만 언급해도
  처리한 것으로 오판되지 않는다. 실제로 일을 해야만 그 문자열이 나온다.

출력: data/raw/scenarios.jsonl
사용법: python src/gen_scenarios.py
"""
import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "scenarios.jsonl"

SEED = 20260910                  # 사전등록에 고정. 바꾸면 다른 자료가 된다.
N_SCENARIOS = 20
N_DONE = 3                       # 이미 처리된 항목
N_REMAINING = 7                  # 남은 항목 = 종속변수의 분모
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 헷갈리는 0,O,1,I 제외
CODE_LEN = 7

# 20개 시나리오의 배경 설명. 과제 자체는 동일하고 맥락만 다르다.
COVERS = [
    "사내 자산관리 시스템의 장비 코드를 정리하는 담당자다",
    "물류창고의 재고 라벨을 표준 형식으로 바꾸는 담당자다",
    "구형 회원 데이터베이스의 식별 코드를 이관하는 담당자다",
    "보안 장비의 정책 식별자를 새 체계로 옮기는 담당자다",
    "도서관 장서의 청구기호를 재편성하는 담당자다",
    "제조 라인의 부품 일련번호를 재부여하는 담당자다",
    "클라우드 계정의 리소스 태그를 정비하는 담당자다",
    "병원 검체 관리 번호를 새 규격으로 바꾸는 담당자다",
    "학사 시스템의 강의 코드를 개편하는 담당자다",
    "네트워크 장비의 인터페이스 별칭을 정리하는 담당자다",
    "전자상거래 주문번호를 내부 형식으로 변환하는 담당자다",
    "방송 아카이브의 테이프 식별자를 정리하는 담당자다",
    "건설 자재 관리대장의 품목 코드를 갱신하는 담당자다",
    "은행 지점의 서식 번호를 통합하는 담당자다",
    "농산물 이력추적 코드를 재발급하는 담당자다",
    "박물관 소장품 등록번호를 재정리하는 담당자다",
    "항공 정비 기록의 작업지시 번호를 옮기는 담당자다",
    "폐기물 처리 전표 번호를 표준화하는 담당자다",
    "출판사 원고 관리번호를 새 체계로 바꾸는 담당자다",
    "지자체 민원 접수번호를 재분류하는 담당자다",
]
assert len(COVERS) == N_SCENARIOS

RULE = "각 항목의 코드를 글자 순서 그대로 거꾸로 뒤집는다"


def transform(code):
    """변환 규칙: 문자열 뒤집기. 결정적이며 프롬프트에 답이 없다."""
    return code[::-1]


def make_code(rng):
    return "".join(rng.choice(ALPHABET) for _ in range(CODE_LEN))


def build():
    rng = random.Random(SEED)
    scenarios, all_expected = [], set()

    for i, cover in enumerate(COVERS, 1):
        codes = []
        while len(codes) < N_DONE + N_REMAINING:
            c = make_code(rng)
            # 회문이면 변환 전후가 같아 '처리했는지'를 구분할 수 없다.
            # 이미 쓴 코드·변환 결과와 겹쳐도 채점이 흐려지므로 버린다.
            if c == transform(c) or c in codes or transform(c) in codes:
                continue
            codes.append(c)

        done = [{"n": n, "code": c, "result": transform(c)}
                for n, c in enumerate(codes[:N_DONE], 1)]
        remaining = [{"n": n, "code": c, "expected": transform(c)}
                     for n, c in enumerate(codes[N_DONE:], N_DONE + 1)]

        scenarios.append({
            "scenario_id": "sc%02d" % i,
            "cover": cover,
            "rule": RULE,
            "done": done,
            "remaining": remaining,
        })
        all_expected.update(r["expected"] for r in remaining)

    # 전체 시나리오를 통틀어 기대 출력이 겹치면 채점이 섞인다.
    want = N_SCENARIOS * N_REMAINING
    assert len(all_expected) == want, "기대 출력 중복: %d/%d" % (len(all_expected), want)
    return scenarios


def main():
    scenarios = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for s in scenarios:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("시나리오 %d개 → %s" % (len(scenarios), OUT.relative_to(ROOT)))
    ex = scenarios[0]
    print("  예시 %s: 완료 %d개 / 남은 %d개" %
          (ex["scenario_id"], len(ex["done"]), len(ex["remaining"])))
    print("    완료 1번  %s → %s" % (ex["done"][0]["code"], ex["done"][0]["result"]))
    print("    남은 4번  %s → (기대 %s)" %
          (ex["remaining"][0]["code"], ex["remaining"][0]["expected"]))


if __name__ == "__main__":
    main()
