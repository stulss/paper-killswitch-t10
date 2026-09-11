#!/usr/bin/env bash
# 전체 재현 스크립트. 실패하면 즉시 멈춘다.
#
# 주의: 4단계(run_trials)만 LLM을 부른다. 수십 분 걸리고 구독 사용량을 쓴다.
#       한도에 걸려 멈추면 이 스크립트를 다시 실행하면 남은 것부터 이어서 한다.
#       CLI 로그인이 없으면 4단계를 건너뛰고 5단계부터 돌려 분석만 재현할 수 있다.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1        # Windows 기본 인코딩(cp949)에서 한글이 깨지는 것을 막는다

echo "== 0. 구현 자체 검증 (LLM 호출 없음) =="
python src/stats.py
python src/score.py

echo "== 1. CLI 연결 점검 (모델당 1회 호출) =="
python src/llm.py --smoke

echo "== 2. 시나리오 20종 생성 (시드 고정) =="
python src/gen_scenarios.py

echo "== 3. 프롬프트 180개 조립 =="
python src/build_prompts.py

echo "== 4. 본 실행 720 시행 (오래 걸린다) =="
python src/run_trials.py

echo "== 5. 채점 =="
python src/score.py --all

echo "== 6. 표·그림 생성 =="
python src/analyze.py

echo "== 7. 검증 =="
python src/verify_prereg.py
python src/check_submission.py

echo "== 완료. results/결과표.md 를 열어 보라. =="
