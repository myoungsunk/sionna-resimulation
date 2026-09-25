"""검증된 참조 기하. 계획표 ΔL 열과 12/12 점 ≤0.005 cm 일치 확인됨."""
import numpy as np


def specular_2d(d_m: float, r_m: float, theta_signed_deg: float) -> dict:
    """판 C=(d/2,-r), 법선 n=(-sin t, cos t). 무한평면 기준 정반사 해."""
    t = np.radians(theta_signed_deg)
    n = np.array([-np.sin(t), np.cos(t)])
    u = np.array([np.cos(t), np.sin(t)])            # 면내(수평) 축 = v축에 대응
    TX, RX, C = np.array([0.0, 0.0]), np.array([d_m, 0.0]), np.array([d_m / 2, -r_m])
    s = (TX - C) @ n
    TXm = TX - 2 * s * n                             # 상(image)
    a, b = (TXm - C) @ n, (RX - C) @ n
    P = TXm + (a / (a - b)) * (RX - TXm)
    vt, vr = P - TX, P - RX
    return dict(
        P=P,
        s_along=float((P - C) @ u),                  # 판 중심에서 면내 변위 (부호 포함)
        # 정오표 E1: 이 값은 면(surface) 기준 GRAZING 각이다. 법선 기준 inc 와는
        # 여각이며(inc = 90 - grazing), 이전 이름 `inc_deg` 는 오해를 낳았다.
        # `grazing_deg` 가 정본 이름이고, `inc_deg` 는 기존 호출부 호환을 위한
        # 폐기 예정 별칭이다. 새 코드는 grazing_deg 를 쓸 것.
        grazing_deg=float(90 - np.degrees(np.arccos(abs(vt @ n) / np.linalg.norm(vt)))),
        inc_deg=float(90 - np.degrees(np.arccos(abs(vt @ n) / np.linalg.norm(vt)))),
        dL_m=float(np.linalg.norm(vt) + np.linalg.norm(vr) - d_m),
        th_tx_deg=float(np.degrees(np.arccos(np.clip(vt @ np.array([1., 0.]) / np.linalg.norm(vt), -1, 1)))),
        th_rx_deg=float(np.degrees(np.arccos(np.clip(vr @ np.array([-1., 0.]) / np.linalg.norm(vr), -1, 1)))),
    )


def dL_closed_form(d_m: float, r_m: float, theta_deg: float) -> float:
    return abs(np.cos(np.radians(theta_deg))) * np.hypot(d_m, 2 * r_m) - d_m


def recover_theta_rm(theta_tx_deg, theta_rx_deg):
    """724 전용. (theta_rm, is_off_pointing) 반환. 각도 결측이면 (None, None)."""
    if theta_tx_deg is None or theta_rx_deg is None:
        return None, None
    hd = abs(theta_tx_deg - theta_rx_deg) / 2.0
    return (0.0, True) if abs(hd - 2.5) < 1e-9 else (hd, False)


# --------------------------------------------------------------------------
# self-test (필수): 실행 시 계획표 ΔL 을 ≤0.01 cm 로 재현하지 못하면 중단
# --------------------------------------------------------------------------
_PLAN_TABLE = {
    # block: (d_m, r_m, {theta_deg: dL_cm})
    "G135": (1.350, 0.675, {0: 55.92, 10: 53.02, 20: 44.41, 30: 30.34}),
    "F90":  (0.900, 0.675, {0: 72.25, 10: 69.78, 20: 62.46, 30: 50.51}),
    "R180": (1.800, 1.125, {0: 108.14, 10: 103.76, 20: 90.76, 30: 69.54}),
}


def _self_test(tol_cm: float = 0.01, verbose: bool = True) -> None:
    worst = 0.0
    rows = []
    for block, (d, r, table) in _PLAN_TABLE.items():
        for th, want_cm in table.items():
            got_cm = dL_closed_form(d, r, th) * 100.0
            err = abs(got_cm - want_cm)
            worst = max(worst, err)
            rows.append((block, d, r, th, want_cm, got_cm, err))
    if verbose:
        print(f"{'block':>6} {'d':>6} {'r':>6} {'theta':>6} "
              f"{'plan[cm]':>9} {'closed[cm]':>11} {'err[cm]':>9}")
        for b, d, r, th, w, g, e in rows:
            print(f"{b:>6} {d:6.3f} {r:6.3f} {th:6d} {w:9.2f} {g:11.4f} {e:9.4f}")
        print(f"\nworst |err| = {worst:.4f} cm   (tolerance {tol_cm} cm)")
    if worst > tol_cm:
        raise AssertionError(
            f"dL_closed_form fails the plan table: worst error {worst:.4f} cm > {tol_cm} cm")

    # specular_2d 와 폐형식의 상호 일치 (무한평면 기준)
    worst2 = 0.0
    for block, (d, r, table) in _PLAN_TABLE.items():
        for th in table:
            a = specular_2d(d, r, -float(th))["dL_m"]
            b = dL_closed_form(d, r, th)
            worst2 = max(worst2, abs(a - b))
    if verbose:
        print(f"specular_2d vs closed form: worst |delta| = {worst2:.3e} m")
    if worst2 > 1e-9:
        raise AssertionError(
            f"specular_2d disagrees with dL_closed_form by {worst2:.3e} m")

    # inc 가 theta 에 불변인지 (§2.1)
    #
    # 규약 주의: specular_2d 의 'inc_deg' 필드는 `90 - arccos(...)` 이므로
    # 면(surface) 기준 grazing angle 이다. §2.1 의 inc (tan(inc) = (d/2)/r) 는
    # 법선(normal) 기준이며 둘은 서로 여각이다. 예: F90 에서 필드값 56.31 deg,
    # §2.1 값 33.69 deg. 참조 구현은 "그대로 사용, 재작성 금지" 이므로
    # 함수는 손대지 않고, 여기서 90 - field 로 변환해 §2.1 을 검정한다.
    worst3 = 0.0
    for block, (d, r, table) in _PLAN_TABLE.items():
        want = np.degrees(np.arctan((d / 2) / r))          # §2.1, 법선 기준
        inc0 = 90.0 - specular_2d(d, r, 0.0)["inc_deg"]
        if abs(inc0 - want) > 1e-9:
            raise AssertionError(
                f"{block}: 90 - inc_deg = {inc0} != atan((d/2)/r) = {want}")
        for th in table:
            for sgn in (+1, -1):
                inc = 90.0 - specular_2d(d, r, sgn * float(th))["inc_deg"]
                worst3 = max(worst3, abs(inc - inc0))
    if verbose:
        print(f"inc (normal-referenced, = 90 - inc_deg field) invariance in theta: "
              f"worst |delta| = {worst3:.3e} deg")
    if worst3 > 1e-9:
        raise AssertionError(f"inc not invariant in theta: {worst3:.3e} deg")

    if verbose:
        print("\nSELF-TEST PASSED")


if __name__ == "__main__":
    _self_test()
