"""Tests for r2py_rpart.rpart — the main decision-tree interface."""

import numpy as np
import pandas as pd
import pytest
from r2py_rpart import rpart


def _model_frame(X: np.ndarray, y: np.ndarray, col_names: list) -> pd.DataFrame:
    """Minimal pre-built model frame accepted by rpart(model=...)."""
    m = pd.DataFrame(X, columns=col_names)
    m.attrs["response"] = y
    return m


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

def test_rpart_returns_dict_with_required_keys():
    rng = np.random.default_rng(0)
    n = 100
    x = rng.standard_normal((n, 1))
    y = x[:, 0] * 3 + rng.standard_normal(n) * 0.1
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    assert isinstance(fit, dict)
    for key in ("frame", "where", "cptable", "method", "parms", "control", "functions"):
        assert key in fit, f"Missing key in rpart output: {key!r}"


def test_rpart_frame_is_dataframe():
    rng = np.random.default_rng(1)
    n = 80
    x = rng.standard_normal((n, 1))
    y = x[:, 0] + rng.standard_normal(n) * 0.05
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    assert isinstance(fit["frame"], pd.DataFrame)


def test_rpart_cptable_has_expected_columns():
    rng = np.random.default_rng(2)
    n = 80
    x = rng.standard_normal((n, 1))
    y = x[:, 0] + rng.standard_normal(n) * 0.1
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    assert "CP" in fit["cptable"].columns
    assert "nsplit" in fit["cptable"].columns
    assert "rel error" in fit["cptable"].columns


# ---------------------------------------------------------------------------
# where array
# ---------------------------------------------------------------------------

def test_rpart_where_length_matches_observations():
    rng = np.random.default_rng(3)
    n = 60
    x = rng.standard_normal((n, 2))
    y = x[:, 0] + rng.standard_normal(n) * 0.1
    fit = rpart("y ~ x1 + x2", model=_model_frame(x, y, ["x1", "x2"]), method="anova", xval=0)

    assert fit["where"].shape == (n,)


def test_rpart_where_values_are_valid_row_indices():
    rng = np.random.default_rng(4)
    n = 100
    x = rng.standard_normal((n, 1))
    y = x[:, 0] * 2 + rng.standard_normal(n) * 0.05
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    # where contains 1-based row indices into fit["frame"] (matching R's $where semantics)
    n_rows = len(fit["frame"])
    assert np.all(fit["where"] >= 1), "where must be >= 1"
    assert np.all(fit["where"] <= n_rows), f"where must be <= {n_rows}"


# ---------------------------------------------------------------------------
# Method selection
# ---------------------------------------------------------------------------

def test_rpart_method_anova_recorded():
    rng = np.random.default_rng(5)
    n = 80
    x = rng.standard_normal((n, 1))
    y = x[:, 0] + rng.standard_normal(n) * 0.1
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    assert fit["method"] == "anova"


def test_rpart_method_class_recorded():
    rng = np.random.default_rng(6)
    n = 100
    x = rng.standard_normal((n, 2))
    y = (x[:, 0] > 0).astype(float)
    fit = rpart("y ~ x1 + x2", model=_model_frame(x, y, ["x1", "x2"]), method="class", xval=0)

    assert fit["method"] == "class"


# ---------------------------------------------------------------------------
# Splitting behaviour
# ---------------------------------------------------------------------------

def test_rpart_anova_produces_split_on_clear_signal():
    rng = np.random.default_rng(7)
    n = 200
    x = rng.standard_normal((n, 1))
    # Strong signal: y = sign(x)
    y = np.where(x[:, 0] > 0, 10.0, -10.0) + rng.standard_normal(n) * 0.01
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    # At least one split should be found
    assert "splits" in fit
    assert len(fit["frame"]) > 1


def test_rpart_constant_response_produces_no_split():
    rng = np.random.default_rng(8)
    n = 100
    x = rng.standard_normal((n, 1))
    y = np.ones(n)  # constant — nothing to split on
    fit = rpart("y ~ x", model=_model_frame(x, y, ["x"]), method="anova", xval=0)

    assert len(fit["frame"]) == 1  # root only


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_rpart_raises_without_prebuilt_model():
    with pytest.raises(NotImplementedError):
        rpart("y ~ x", data=pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]}))


def test_rpart_raises_on_negative_weights():
    rng = np.random.default_rng(9)
    n = 50
    x = rng.standard_normal((n, 1))
    y = x[:, 0] + rng.standard_normal(n) * 0.1
    m = _model_frame(x, y, ["x"])
    m.attrs["weights"] = np.full(n, -1.0)

    with pytest.raises(ValueError, match="negative weights"):
        rpart("y ~ x", model=m, method="anova", xval=0)
