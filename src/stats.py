"""통계 함수 모음 (표준 라이브러리만 사용).

사전등록 6절의 분석 계획에 필요한 것만 담는다.
  - Wilcoxon 부호순위검정 (정규근사 + 연속성 보정 + 동점 보정)
  - Holm-Bonferroni 다중비교 보정
  - Cliff's delta 효과크기
  - Spearman 순위상관
  - 페어드 부트스트랩 신뢰구간

scipy로 값을 대조 검증했다(docs/트러블슈팅.md 참고).
자체 검증: python src/stats.py
"""
import math
import random
from collections import Counter


def _norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _ranks(values):
    """동점은 평균 순위를 준다."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def wilcoxon(x, y):
    """대응표본 Wilcoxon 부호순위검정(양측). 0인 차이는 제외(Wilcoxon 원법)."""
    diffs = [a - b for a, b in zip(x, y) if a != b]
    n = len(diffs)
    if n == 0:
        return {"n": 0, "W": None, "z": None, "p": 1.0,
                "note": "모든 차이가 0이라 검정 불가"}
    ranks = _ranks([abs(d) for d in diffs])
    w_pos = sum(r for d, r in zip(diffs, ranks) if d > 0)
    w_neg = sum(r for d, r in zip(diffs, ranks) if d < 0)
    W = min(w_pos, w_neg)
    mean = n * (n + 1) / 4
    tie_corr = sum(t ** 3 - t for t in Counter(ranks).values())
    var = (n * (n + 1) * (2 * n + 1) - tie_corr / 2) / 24
    if var <= 0:
        return {"n": n, "W": W, "z": None, "p": 1.0, "note": "분산 0"}
    z = (W - mean + 0.5) / math.sqrt(var)      # 연속성 보정
    p = 2 * _norm_cdf(z)
    return {"n": n, "W": W, "W_pos": w_pos, "W_neg": w_neg,
            "z": round(z, 4), "p": min(1.0, round(p, 6)),
            "method": "정규근사(연속성·동점 보정)"}


def holm(pvals):
    """Holm-Bonferroni 보정. 입력 순서 그대로 보정된 p를 돌려준다."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * pvals[i]
        running = max(running, val)            # 단조성 유지
        adj[i] = min(1.0, running)
    return adj


def cliffs_delta(x, y):
    """Cliff's delta = P(X>Y) - P(X<Y). -1~1."""
    gt = sum(1 for a in x for b in y if a > b)
    lt = sum(1 for a in x for b in y if a < b)
    return (gt - lt) / (len(x) * len(y))


def rank_biserial_paired(x, y):
    """대응표본용 효과크기: (W+ - W-) / (W+ + W-). -1~1."""
    r = wilcoxon(x, y)
    if r["W"] is None:
        return 0.0
    total = r["W_pos"] + r["W_neg"]
    return (r["W_pos"] - r["W_neg"]) / total if total else 0.0


def spearman(x, y):
    """Spearman 순위상관계수."""
    rx, ry = _ranks(x), _ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def bootstrap_ci(data, stat, n_boot=10000, alpha=0.05, seed=20260907):
    """복원추출 부트스트랩 백분위 신뢰구간. data는 관측 단위(씨앗)의 리스트."""
    rng = random.Random(seed)
    n = len(data)
    vals = []
    for _ in range(n_boot):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        vals.append(stat(sample))
    vals.sort()
    lo = vals[int((alpha / 2) * n_boot)]
    hi = vals[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return round(lo, 6), round(hi, 6)


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def quartiles(xs):
    s = sorted(xs)
    return round(median(s[:len(s) // 2]), 4), round(median(s), 4), \
        round(median(s[(len(s) + 1) // 2:]), 4)


def _self_check():
    # 순위: 동점은 평균 순위
    assert _ranks([10, 20, 20, 40]) == [1.0, 2.5, 2.5, 4.0]
    # Wilcoxon: 모든 차이가 한 방향이면 W=0, p가 작다
    r = wilcoxon(list(range(1, 11)), [0] * 10)
    assert r["W"] == 0 and r["p"] < 0.01, r
    # 차이가 전혀 없으면 검정 불가
    assert wilcoxon([1, 2, 3], [1, 2, 3])["n"] == 0
    # 대칭: x,y를 바꿔도 p는 같다
    a = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
    b = [2, 2, 3, 2, 4, 7, 3, 5, 4, 4]
    assert abs(wilcoxon(a, b)["p"] - wilcoxon(b, a)["p"]) < 1e-12
    # Holm: 단조 증가하고 원래 p 이상
    adj = holm([0.01, 0.04, 0.03])
    assert all(x >= y for x, y in zip(adj, [0.01, 0.04, 0.03]))
    assert abs(adj[0] - 0.03) < 1e-12
    # Cliff's delta 양 끝
    assert cliffs_delta([5, 6, 7], [1, 2, 3]) == 1.0
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    # Spearman: 완전 단조
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-9
    # 부트스트랩: 상수 데이터면 구간이 그 값
    assert bootstrap_ci([2.0] * 20, lambda s: sum(s) / len(s), 200) == (2.0, 2.0)
    # 부트스트랩 재현성: 같은 seed면 같은 결과
    d = [random.Random(1).random() for _ in range(30)]
    assert bootstrap_ci(d, lambda s: sum(s) / len(s), 500) == \
        bootstrap_ci(d, lambda s: sum(s) / len(s), 500)
    assert quartiles([1, 2, 3, 4, 5]) == (1.5, 3, 4.5)
    print("stats self-check OK")


if __name__ == "__main__":
    _self_check()
