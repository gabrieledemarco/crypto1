"""Tests for _validate_bars — data quality guard in api/routers/runs.py."""
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _get_validate_bars():
    from api.routers.runs import _validate_bars
    return _validate_bars


class TestValidateBars:
    def setup_method(self):
        self._validate_bars = _get_validate_bars()
        n = 100
        idx = pd.date_range("2022-01-01", periods=n, freq="1h")
        self.good_df = pd.DataFrame(
            {
                "Open": np.ones(n) * 100,
                "High": np.ones(n) * 101,
                "Low": np.ones(n) * 99,
                "Close": np.ones(n) * 100,
                "Volume": np.ones(n) * 10,
            },
            index=idx,
        )

    def test_valid_data_passes(self):
        self._validate_bars(self.good_df)  # should not raise

    def test_none_raises(self):
        with pytest.raises(ValueError):
            self._validate_bars(None)

    def test_empty_dataframe_raises(self):
        with pytest.raises((ValueError, KeyError)):
            self._validate_bars(pd.DataFrame())

    def test_nan_close_raises(self):
        df = self.good_df.copy()
        df.loc[df.index[5], "Close"] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            self._validate_bars(df)

    def test_negative_close_raises(self):
        df = self.good_df.copy()
        df.loc[df.index[0], "Close"] = -1.0
        with pytest.raises(ValueError):
            self._validate_bars(df)

    def test_zero_close_raises(self):
        df = self.good_df.copy()
        df.loc[df.index[0], "Close"] = 0.0
        with pytest.raises(ValueError):
            self._validate_bars(df)

    def test_high_less_than_low_raises(self):
        df = self.good_df.copy()
        df.loc[df.index[0], "High"] = 95.0
        df.loc[df.index[0], "Low"] = 100.0
        with pytest.raises(ValueError, match="High < Low"):
            self._validate_bars(df)

    def test_duplicate_timestamps_raises(self):
        df = self.good_df.copy()
        df.index = [df.index[0]] * len(df)  # all same timestamp
        with pytest.raises(ValueError, match="Duplicate"):
            self._validate_bars(df)

    def test_single_duplicate_timestamp_raises(self):
        df = self.good_df.copy()
        new_idx = list(df.index)
        new_idx[1] = new_idx[0]  # one duplicate
        df.index = new_idx
        with pytest.raises(ValueError, match="Duplicate"):
            self._validate_bars(df)

    def test_multiple_nan_close_raises(self):
        df = self.good_df.copy()
        df.loc[df.index[10:15], "Close"] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            self._validate_bars(df)

    def test_valid_realistic_prices_passes(self):
        """Realistic BTC-like prices should pass validation."""
        n = 200
        idx = pd.date_range("2023-01-01", periods=n, freq="1h")
        rng = np.random.default_rng(0)
        close = 30000 + np.cumsum(rng.normal(0, 50, n))
        close = np.maximum(close, 1.0)
        df = pd.DataFrame(
            {
                "Open": close * (1 + rng.normal(0, 0.001, n)),
                "High": close * (1 + rng.uniform(0, 0.005, n)),
                "Low": close * (1 - rng.uniform(0, 0.005, n)),
                "Close": close,
                "Volume": rng.uniform(100, 1000, n),
            },
            index=idx,
        )
        self._validate_bars(df)  # should not raise

    def test_all_nan_close_raises(self):
        df = self.good_df.copy()
        df["Close"] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            self._validate_bars(df)
