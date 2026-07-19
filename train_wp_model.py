#!/usr/bin/env python3
"""
승률(WP) 모델 학습 — 실측 WE 매트릭스가 후반/만루 셀에서 노이즈가 심해 LI 도출이
불가하므로, DB의 전체 타석으로 매끄러운 로지스틱 WP 를 학습한다.

입력: 각 타석 상태(inning, half, outs, r1,r2,r3, score_diff) → 그 경기 홈팀 승리(0/1)
출력: data/wp_model.json (raw-space 계수). pli-api helpers 가 로드해 LI 전이에 사용.
의존성 추가 없음(numpy 로지스틱, GD).
"""
import os, sys, ast, json, math
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
import django
django.setup()

from ballrae_backend.games.models import Game, AtBat


def make_features(inning, half, outs, r1, r2, r3, sd):
    """홈팀 관점 피처. helpers.py 와 반드시 동일하게 유지."""
    outs = min(max(int(outs), 0), 2)
    inning = min(max(int(inning), 1), 11)
    prog = (((inning - 1) * 6) + (0 if half == "top" else 3) + outs) / 51.0
    bat_home = 1.0 if half == "bot" else 0.0
    base_threat = 0.9 * r1 + 1.1 * r2 + 1.3 * r3
    base_signed = base_threat * (1.0 if half == "bot" else -1.0)
    # [sd, sd*prog, prog, bat_home, outs, base_signed]
    return [float(sd), float(sd) * prog, prog, bat_home, float(outs), base_signed]


FEATURE_NAMES = ["sd", "sd*prog", "prog", "bat_home", "outs", "base_signed"]


def main():
    # 1) 경기별 홈팀 승패
    game_home_won = {}
    for g in Game.objects.exclude(score__isnull=True).only("id", "score"):
        if not g.score or ":" not in g.score:
            continue
        try:
            away, home = map(int, g.score.split(":"))
        except Exception:
            continue
        if home == away:
            continue  # 무승부 제외
        game_home_won[g.id] = 1 if home > away else 0
    print(f"라벨 있는 경기: {len(game_home_won)}")

    # 2) 타석 → (피처, 라벨)
    X, y = [], []
    n_seen = 0
    for ab in AtBat.objects.select_related("inning").only(
        "out", "score", "on_base", "inning__inning_number", "inning__half", "inning__game_id"
    ).iterator(chunk_size=5000):
        n_seen += 1
        gid = ab.inning.game_id
        if gid not in game_home_won:
            continue
        if not ab.score or ":" not in str(ab.score):
            continue
        try:
            a, h = map(int, str(ab.score).split(":"))
        except Exception:
            continue
        sd = h - a
        try:
            outs = int(ab.out or 0)
        except Exception:
            outs = 0
        r1 = r2 = r3 = 0
        ob = ab.on_base
        if ob:
            try:
                d = ast.literal_eval(ob) if isinstance(ob, str) else ob
                r1 = 1 if int(d.get("base1", 0) or 0) > 0 else 0
                r2 = 1 if int(d.get("base2", 0) or 0) > 0 else 0
                r3 = 1 if int(d.get("base3", 0) or 0) > 0 else 0
            except Exception:
                pass
        X.append(make_features(ab.inning.inning_number, ab.inning.half, outs, r1, r2, r3, sd))
        y.append(game_home_won[gid])

    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    print(f"학습 표본: {len(y)} (타석 스캔 {n_seen}), 홈승률 평균 {y.mean():.3f}")

    # 3) 표준화 후 로지스틱 GD (L2)
    mu = X.mean(axis=0)
    sd_ = X.std(axis=0)
    sd_[sd_ == 0] = 1.0
    Z = (X - mu) / sd_
    n, d = Z.shape
    w = np.zeros(d)
    b = 0.0
    lr = 0.5
    lam = 1e-4
    for it in range(4000):
        z = Z @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        gw = Z.T @ (p - y) / n + lam * w
        gb = (p - y).mean()
        w -= lr * gw
        b -= lr * gb
        if it % 1000 == 0:
            eps = 1e-9
            loss = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)).mean()
            print(f"  it{it} logloss={loss:.4f}")

    # 4) raw-space 계수로 환산 (helpers 는 raw 피처로 sigmoid 계산)
    raw_w = (w / sd_).tolist()
    raw_b = float(b - np.sum(w * mu / sd_))

    model = {"features": FEATURE_NAMES, "weights": raw_w, "bias": raw_b}
    os.makedirs("data", exist_ok=True)
    with open("data/wp_model.json", "w") as f:
        json.dump(model, f, indent=2)
    print("저장: data/wp_model.json")
    print("weights:", {k: round(v, 4) for k, v in zip(FEATURE_NAMES, raw_w)}, "bias", round(raw_b, 4))

    # 5) 검증: 홈팀 WP 예측 (단조성/캘리브레이션 눈으로 확인)
    def wp(inn, half, o, r1, r2, r3, sd):
        f = make_features(inn, half, o, r1, r2, r3, sd)
        z = raw_b + sum(wi * fi for wi, fi in zip(raw_w, f))
        return 1.0 / (1.0 + math.exp(-z))

    print("\n=== WP 검증 (홈팀 승률) ===")
    cases = [
        ("1회초 0사 무주자 동점", 1, "top", 0, 0, 0, 0, 0),
        ("9말 2사 만루 동점", 9, "bot", 2, 1, 1, 1, 0),
        ("9말 2사 무주자 동점", 9, "bot", 2, 0, 0, 0, 0),
        ("9말 0사 무주자 홈5점앞", 9, "bot", 0, 0, 0, 0, 5),
        ("9말 0사 무주자 홈5점뒤", 9, "bot", 0, 0, 0, 0, -5),
        ("4말 1사 무주자 홈5점앞", 4, "bot", 1, 0, 0, 0, 5),
    ]
    for name, inn, half, o, r1, r2, r3, sd in cases:
        print(f"  WP(home)={wp(inn, half, o, r1, r2, r3, sd):.3f}  {name}")


if __name__ == "__main__":
    main()
