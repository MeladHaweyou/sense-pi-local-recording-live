from sensepi.analysis.rate import RateController


def test_rate_controller_estimates_rate_for_regular_samples() -> None:
    rc = RateController(window_size=100)
    t = 0.0
    for _ in range(100):
        rc.add_sample_time(t)
        t += 0.01  # 100 Hz
    est = rc.estimated_hz
    assert 90.0 < est < 110.0
