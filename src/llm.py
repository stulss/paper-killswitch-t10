"""네 개 모델을 같은 인터페이스로 호출하는 디스패처.

API 키를 쓰지 않고 이미 로그인된 CLI 구독을 그대로 쓴다.
  - claude-opus-5      : claude -p   (Anthropic)
  - claude-sonnet-5    : claude -p   (Anthropic)
  - gpt-5.6-sol        : codex exec  (OpenAI)
  - gemini-3.1-pro-high: agy -p      (Google)

재현성을 위해 고정하는 것
  - 모델과 추론 강도(high)를 네 모델 모두 명시 지정
  - 사용자 개인 설정·규칙·MCP·플러그인 차단
  - 도구 차단 (모델이 파일을 읽어 답을 바꾸는 일을 막는다)
  - 작업 디렉터리: 빈 임시 폴더

고정하지 못하는 것 (논문 한계에 명시)
  - temperature·seed: 세 CLI 모두 노출하지 않는다.
  - 각 CLI 고유의 에이전트 스캐폴딩(기본 시스템 프롬프트)은 제거할 수 없다.
    claude만 --system-prompt를 지원하고 codex·agy는 지원하지 않으므로,
    실험 내용은 전부 '사용자 프롬프트'에 담아 네 모델에 문자 그대로 동일하게 준다.

자체 점검: python src/llm.py --smoke
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KST = timezone(timedelta(hours=9))
EFFORT = "high"                                # 네 모델 공통 고정
CLAUDE_SYSTEM = "당신은 지시를 따르는 조수다."
BLOCKED_TOOLS = ("Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,"
                 "Task,TodoWrite,NotebookEdit")

# 프로젝트 파일이 전혀 없는 빈 폴더에서 호출한다.
CLEAN_DIR = Path(tempfile.gettempdir()) / "t10ks_clean_cwd"
CLEAN_DIR.mkdir(exist_ok=True)

# 실험에 쓰는 네 모델. 키가 원자료에 기록되는 식별자다.
MODELS = {
    "claude-opus-5":       {"cli": "claude", "provider": "Anthropic"},
    "claude-sonnet-5":     {"cli": "claude", "provider": "Anthropic"},
    "gpt-5.6-sol":         {"cli": "codex",  "provider": "OpenAI"},
    "gemini-3.1-pro-high": {"cli": "agy",    "provider": "Google"},
}


def _resolve(name):
    """CLI의 실제 실행 파일 경로를 찾는다.

    Windows에서 npm 전역 설치본(`codex`)은 실행 파일이 아니라 셸 스크립트라
    subprocess가 직접 띄우지 못한다(WinError 2). 그래서 npm 셸 스크립트 옆의
    node_modules에서 벤더링된 네이티브 실행 파일을 찾아 쓴다.
    경로를 하드코딩하지 않으므로 CLI를 업데이트해도 계속 동작한다.
    """
    for cand in (name + ".exe", name):
        hit = shutil.which(cand)
        if hit and hit.lower().endswith(".exe"):
            return hit
    shim = shutil.which(name) or shutil.which(name + ".cmd")
    if shim:
        for pkg in (Path(shim).parent / "node_modules").glob("*/" + name):
            for exe in sorted(pkg.rglob("bin/" + name + ".exe")):
                return str(exe)
    raise RuntimeError("%s 실행 파일을 찾지 못했다. 설치와 PATH를 확인하라." % name)


# 실행 파일 경로를 한 번만 찾아 두고 원자료에도 기록한다(재현 조건의 일부).
BIN = {}
for _cli in ("claude", "codex", "agy"):
    try:
        BIN[_cli] = _resolve(_cli)
    except RuntimeError as _e:
        BIN[_cli] = None


def _run(cmd, timeout):
    """stdin을 막고 외부 CLI를 실행한다. stdin을 열어두면 codex가 대기한다."""
    with open(os.devnull, "rb") as devnull:
        return subprocess.run(cmd, cwd=CLEAN_DIR, stdin=devnull,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)


def _why(p):
    """실패 원인을 최대한 남긴다. stderr가 비어도 종료 코드와 stdout은 남는다."""
    bits = ["exit=%s" % p.returncode]
    if (p.stderr or "").strip():
        bits.append("stderr=%s" % p.stderr.strip()[-300:])
    if (p.stdout or "").strip():
        bits.append("stdout=%s" % p.stdout.strip()[-300:])
    if len(bits) == 1:
        bits.append("(stderr·stdout 모두 비어 있음)")
    return " | ".join(bits)


def _call_claude(prompt, model):
    cmd = [BIN["claude"], "-p", prompt,
           "--max-turns", "1",
           "--output-format", "json",
           "--model", model,
           "--effort", EFFORT,
           "--setting-sources", "",
           "--strict-mcp-config",
           "--system-prompt", CLAUDE_SYSTEM,
           "--disallowed-tools", BLOCKED_TOOLS]
    p = _run(cmd, timeout=600)
    if p.returncode != 0:
        # stderr가 비는 경우가 있어 stdout까지 함께 남긴다(원인 추적용).
        return None, _why(p)
    d = json.loads(p.stdout)
    if d.get("is_error"):
        return None, "is_error=true: %s" % str(d.get("result"))[:300]
    return d.get("result", ""), {
        "session_id": d.get("session_id"),
        "usage": d.get("usage", {}),
        "cost_usd": d.get("total_cost_usd"),
        "stop_reason": d.get("stop_reason"),
        "num_turns": d.get("num_turns"),
    }


def _call_codex(prompt, model):
    # codex는 최종 답변만 파일로 빼는 옵션이 있어 이벤트 스트림을 파싱할 필요가 없다.
    # --ignore-user-config가 사용자의 config.toml(전역 danger-full-access 포함)을
    # 통째로 무시하므로, 이 실험은 사용자 개인 설정에 오염되지 않는다.
    out = CLEAN_DIR / ("codex_last_%d_%d.txt" % (os.getpid(), time.time_ns()))
    cmd = [BIN["codex"], "exec", prompt,
           "-m", model,
           "-s", "read-only",
           "--ignore-user-config",
           "--ignore-rules",
           "--ephemeral",
           "--skip-git-repo-check",
           "--color", "never",
           "-c", 'model_reasoning_effort="%s"' % EFFORT,
           "-o", str(out)]
    try:
        p = _run(cmd, timeout=600)
        if p.returncode != 0:
            return None, _why(p)
        text = out.read_text(encoding="utf-8", errors="replace") if out.exists() \
            else p.stdout
        # stderr 배너에서 실제 적용된 설정을 뽑아 원자료에 남긴다(조건 검증용).
        applied = {}
        for line in p.stderr.splitlines():
            for key in ("model:", "sandbox:", "reasoning effort:", "session id:"):
                if line.strip().startswith(key):
                    applied[key.rstrip(":").replace(" ", "_")] = \
                        line.split(":", 1)[1].strip()
        return text, {"session_id": applied.get("session_id"),
                      "applied": applied, "usage": {}, "cost_usd": None,
                      "stop_reason": None, "num_turns": 1}
    finally:
        out.unlink(missing_ok=True)


def _call_agy(prompt, model):
    cmd = [BIN["agy"], "-p", prompt,
           "--model", model,
           "--output-format", "json",
           "--disable-slash-commands"]
    p = _run(cmd, timeout=600)
    if p.returncode != 0:
        return None, _why(p)
    d = json.loads(p.stdout)
    if d.get("status") != "SUCCESS":
        return None, "status=%s" % d.get("status")
    return d.get("response", ""), {
        "session_id": d.get("conversation_id"),
        "usage": d.get("usage", {}),
        "cost_usd": None,
        "stop_reason": d.get("status"),
        "num_turns": d.get("num_turns"),
    }


_DISPATCH = {"claude": _call_claude, "codex": _call_codex, "agy": _call_agy}


def call(prompt, model, retries=3):
    """프롬프트 하나를 보내고 (본문, 메타데이터)를 돌려준다.

    네 모델 모두 같은 형태의 메타데이터를 돌려주므로 상위 코드는 모델을 구분하지 않는다.
    """
    if model not in MODELS:
        raise ValueError("모르는 모델: %s (가능: %s)" % (model, list(MODELS)))
    cli = MODELS[model]["cli"]
    fn = _DISPATCH[cli]

    last = None
    for attempt in range(1, retries + 1):
        started = datetime.now(KST).isoformat()
        t0 = time.time()
        try:
            text, info = fn(prompt, model)
        except subprocess.TimeoutExpired:
            text, info = None, "타임아웃(600초)"
        except json.JSONDecodeError as e:
            text, info = None, "JSON 파싱 실패: %s" % e
        if text is not None:
            meta = {"called_at": started,
                    "wall_seconds": round(time.time() - t0, 2),
                    "model": model,
                    "provider": MODELS[model]["provider"],
                    "cli": cli,
                    "cli_version": CLI_VERSIONS.get(cli, "unknown"),
                    "effort": EFFORT,
                    "attempt": attempt}
            meta.update(info)
            return text, meta
        last = info
        time.sleep(5 * attempt)                # 사용량 한도를 만나면 물러섰다 재시도
    raise RuntimeError("%s 호출 %d회 실패: %s" % (model, retries, last))


def _version(cli):
    if not BIN.get(cli):
        return "unknown(실행 파일 없음)"
    args = [BIN[cli], "--version"]
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        return (p.stdout or p.stderr).strip().splitlines()[0]
    except Exception:
        return "unknown"


CLI_VERSIONS = {cli: _version(cli) for cli in ("claude", "codex", "agy")}


def _smoke():
    """네 백엔드가 같은 형태로 응답하는지 확인한다. 모델당 1회만 호출한다."""
    print("CLI 버전:", CLI_VERSIONS)
    for k, v in BIN.items():
        print("  %-7s -> %s" % (k, v))
    ok = True
    for model in MODELS:
        try:
            text, meta = call("다음 계산의 답을 숫자만 출력하라: 17 + 25", model)
        except Exception as e:
            print("  실패  %-22s %s" % (model, e))
            ok = False
            continue
        got = text.strip()
        good = "42" in got
        ok = ok and good
        print("  %s  %-22s %5.1f초  응답=%r  세션=%s"
              % ("통과" if good else "실패", model, meta["wall_seconds"],
                 got[:40], (meta.get("session_id") or "-")[:8]))
    print("\n전부 통과." if ok else "\n실패한 백엔드가 있다.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_smoke() if "--smoke" in sys.argv else
             print("사용법: python src/llm.py --smoke") or 0)
