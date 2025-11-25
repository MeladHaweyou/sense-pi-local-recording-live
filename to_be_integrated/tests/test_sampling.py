from __future__ import annotations
import numpy as np
from ..util.rate_control import RateController
from ..util.resample import resample_to_fixed_rate


def test_rate_controller_fuses_status_and_ts():
    rc = RateController(alpha=0.5, default_hz=20.0)
    # only status
    e = rc.update_from_status(interval=None, hz=50.0)
    assert e.hz_raw_status > 45 and e.quality in ("status_only", "fused")
    # timestamps ~48-52 Hz
    t = np.cumsum(np.random.uniform(1/52.0, 1/48.0, size=400))
    e = rc.update_from_timestamps(t)
    assert e.hz_ts_window > 45
    assert e.hz_effective > 35


def test_resample_downsample_100_to_25():
    fs_in = 100.0
    t = np.arange(0.0, 2.0, 1.0/fs_in)
    y = np.sin(2*np.pi*2.0*t)
    t_out, y_out, last = resample_to_fixed_rate(t, y, 25.0, None)
    assert abs(t_out.size - int(2.0*25.0) - 1) <= 1  # approx count
    assert np.isfinite(y_out).all()


def test_resample_handles_drift():
    # 50 Hz jittered
    dt = np.random.normal(loc=1/50.0, scale=0.0005, size=4000)
    t = np.cumsum(dt); y = np.cos(2*np.pi*3.0*t)
    t_out, y_out, _ = resample_to_fixed_rate(t, y, 25.0, None)
    assert t_out.size > 0 and y_out.size == t_out.size
