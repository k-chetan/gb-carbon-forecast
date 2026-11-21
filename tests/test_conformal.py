import numpy as np
import pandas as pd

from gbcarbon import conformal


def make_stream(days: int, bias: float) -> pd.DataFrame:
    """Daily issues, three horizons (one per bucket); y sits `bias` above p90."""
    rows = []
    start = pd.Timestamp("2026-01-01", tz="UTC")
    for d in range(days):
        issue = start + pd.Timedelta(days=d)
        for h in (3.0, 12.0, 30.0):
            target = issue + pd.Timedelta(hours=h)
            p50 = 100.0
            rows.append(
                {
                    "issue_time": issue,
                    "target_time": target,
                    "horizon_h": h,
                    "y": p50 + bias,
                    "p10": p50 - 1.0,
                    "p50": p50,
                    "p90": p50 + 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_trailing_widens_once_errors_mature():
    stream = make_stream(days=60, bias=5.0)  # constant miss: score = 4.0
    out = conformal.apply_trailing(stream, seed_offsets={}, min_n=20)
    early = out[out["issue_time"] < "2026-01-08"]
    late = out[out["issue_time"] > "2026-02-10"]
    assert (early["conformal_widen"] == 0.0).all()  # nothing matured yet
    assert np.allclose(late["conformal_widen"], 4.0, atol=0.01)
    # widened intervals now cover
    assert (late["p90"] >= late["y"]).all()


def test_seed_used_until_min_n():
    stream = make_stream(days=5, bias=5.0)
    out = conformal.apply_trailing(
        stream, seed_offsets={"01_06h": 9.0, "07_24h": 9.0, "25_48h": 9.0}, min_n=400
    )
    assert (out["conformal_widen"] == 9.0).all()


def test_admissibility_no_same_day_information():
    # massive error on the last day only: its own offsets must not see it
    stream = make_stream(days=40, bias=0.0)  # covered: scores negative
    last_day = stream["issue_time"].max()
    stream.loc[stream["issue_time"] == last_day, "y"] = 500.0
    out = conformal.apply_trailing(stream, seed_offsets={}, min_n=20)
    last = out[out["issue_time"] == last_day]
    # offsets on the last day derive from earlier, covered days (negative
    # scores -> negative offsets allowed to narrow), never from its own miss
    assert (last["conformal_widen"] < 1.0).all()
