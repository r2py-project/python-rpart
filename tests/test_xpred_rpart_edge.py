"""Boundary/edge-case parity tests for r2py_rpart.xpred_rpart vs. R's
xpred.rpart (called directly via rpy2 -- see _r_rpart_helpers.py's
xpred.rpart-specific plumbing section, and test_xpred_rpart_positive.py's
module docstring for why value-parity tests always pass an explicit
`xval=` vector rather than relying on the RNG-dependent scalar default).

Each test below either:
  (a) confirms R and r2py_rpart produce numerically identical output at a
      genuine functional extreme (root-only/no-split trees, a
      zero-deviance/constant response, leave-one-out cross-validation, a
      degenerate single cross-validation fold that empties every fold's
      training set, singleton/extreme `cp` values, a zero observation
      weight, `na.action` row-dropping combined with a near-fully-missing
      row); or
  (b) documents a genuine, confirmed KNOWN GAP between the two
      implementations at such an extreme -- per this codebase's established
      convention (see e.g. test_printcp_positive.py's "KNOWN GAP" tests,
      test_prune_negative.py's docstring) of keeping such findings visible
      as passing tests that assert the *actual* (divergent) behavior on
      each side, rather than silently dropping the scenario.

A GENUINE SEGFAULT, found empirically and deliberately NOT exercised here:
`xpred.rpart(fit, cp=NULL)` (an *explicit* NULL `cp=`, not simply omitting
`cp`) crashes R's own C `xpred` routine outright on this build (see
test_xpred_rpart_negative.py's module docstring for the full note). No test
here passes `cp=None`/`cp=NULL` for that reason.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing (`r_xpred`,
`r_xpred_to_numpy`, `default_xpred_cp`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart, xpred_rpart

from _r_rpart_helpers import (
    default_xpred_cp,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_xpred,
    r_xpred_to_numpy,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. Root-only tree (no splits at all): a `minsplit` far larger than the
#    dataset forces `cptable` down to its minimal single row, so the
#    default `cp` list -- and hence xpred_rpart's whole output -- collapses
#    to a single column.
# ---------------------------------------------------------------------------

def test_xpred_rpart_root_only_tree_single_cp_column_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0, minsplit=1000)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0, "minsplit": 1000})
    assert len(py_fit["cptable"]) == 1

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == (n, 1)
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 2. Zero-deviance (constant) response: the root node's `dev` is exactly 0,
#    making the default-cp formula's `cptable[0, 0]` itself `NaN` (0/0
#    inside rpart's own complexity-parameter bookkeeping) -- both sides
#    must propagate that `NaN` identically through to a well-defined
#    (constant) prediction, rather than erroring.
# ---------------------------------------------------------------------------

def test_xpred_rpart_constant_response_nan_cp_matches_r():
    df = pd.DataFrame({"y": [5.0] * 6, "x1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x1", control="rpart.control(xval=0)")

    py_fit = rpart("y ~ x1", data=df, x=True, control={"xval": 0})
    cptable = py_fit["cptable"]
    assert np.isnan(cptable["CP"].to_numpy()[0])

    xgrp = np.array([1, 2, 3, 1, 2, 3])

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == (6, 1)
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-6, equal_nan=True)
    assert_allclose(py_result.ravel(), np.full(6, 5.0))


# ---------------------------------------------------------------------------
# 3. `return_all=True` on an anova ("numresp == 1") fit is a documented
#    no-op: xpred.rpart.R's own `if (return.all && numresp > 1L)` guard
#    means the 2-D `matrix(...)` branch is taken regardless of `return.all`
#    whenever `numresp <= 1` -- confirm both sides agree the output stays
#    2-D (not spuriously promoted to 3-D) at this boundary.
# ---------------------------------------------------------------------------

def test_xpred_rpart_return_all_true_is_noop_for_numresp_one_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt", data=df, x=True, control={"xval": 0})
    assert py_fit["numresp"] == 1

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_false = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=False))
    r_true = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=True))
    py_false = xpred_rpart(py_fit, xval=xgrp, return_all=False)
    py_true = xpred_rpart(py_fit, xval=xgrp, return_all=True)

    assert r_false.shape == r_true.shape  # R's own no-op
    assert py_false.shape == py_true.shape == r_false.shape  # python's no-op, matching
    assert_allclose(py_true, r_true, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 4. Singleton `cp=` vector (length 1, taken from the fit's own cptable so
#    it is a guaranteed-achievable complexity threshold -- see
#    test_xpred_rpart_positive.py's explicit-cp test for why arbitrary
#    unreachable values are avoided).
# ---------------------------------------------------------------------------

def test_xpred_rpart_singleton_cp_array_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})
    single_cp = py_fit["cptable"]["CP"].to_numpy(dtype=float)[:1]

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, cp=single_cp))
    py_result = xpred_rpart(py_fit, xval=xgrp, cp=single_cp)

    assert py_result.shape == (n, 1)
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 5. `xval` at its maximum meaningful value: one fold per observation
#    (leave-one-out cross-validation, `xval == nobs`).
# ---------------------------------------------------------------------------

def test_xpred_rpart_leave_one_out_xval_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})

    n = len(df)
    xgrp = np.arange(1, n + 1)  # every observation its own fold

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert np.all(np.isfinite(py_result))
    assert_allclose(py_result, r_result, rtol=1e-4, atol=1e-6)


# ---------------------------------------------------------------------------
# 6. `xval` at its degenerate minimum: a single fold containing every
#    observation empties that fold's own training set (each observation's
#    held-out prediction is trained on zero rows) -- both sides are
#    confirmed (empirically) to produce `NaN` predictions here, not an
#    error, so this compares with `equal_nan=True` rather than expecting a
#    raised exception.
# ---------------------------------------------------------------------------

def test_xpred_rpart_single_degenerate_fold_produces_matching_nans():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})

    n = len(df)
    xgrp = np.ones(n, dtype=np.int32)  # everyone in the same (only) fold

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert np.any(np.isnan(py_result))
    assert np.any(np.isnan(r_result))
    assert_allclose(py_result, r_result, equal_nan=True)


# ---------------------------------------------------------------------------
# 7. `cp` values beyond the achievable range (larger than the root split's
#    own complexity, forcing a root-only/constant prediction for that
#    column) mixed with an achievable value in the same call.
# ---------------------------------------------------------------------------

def test_xpred_rpart_cp_beyond_root_complexity_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})
    achievable = py_fit["cptable"]["CP"].to_numpy(dtype=float)[0]
    cp_vals = np.array([2.0, float(achievable)])  # 2.0 exceeds any real cp

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, cp=cp_vals))
    py_result = xpred_rpart(py_fit, xval=xgrp, cp=cp_vals)

    assert py_result.shape == (n, 2)
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 8. A zero-valued observation weight: a genuine boundary for the `wt`
#    array (rpart.control's own documentation places no positivity
#    constraint on `weights=`, unlike `cost=`).
# ---------------------------------------------------------------------------

def test_xpred_rpart_zero_observation_weight_matches_r():
    df = mtcars_df()
    n = len(df)
    weights = np.ones(n)
    weights[0] = 0.0

    r_dataframe_assign("df", df)
    run_r("w_tmp <- c(" + ", ".join(repr(float(w)) for w in weights) + ")")
    r_fit = run_r("rpart(mpg ~ wt + hp, data=df, weights=w_tmp, control=rpart.control(xval=0))")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, weights=weights, control={"xval": 0})

    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert np.all(np.isfinite(py_result))
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 9. `na.action` row-dropping at its own boundary: a row with *every*
#    predictor missing (na.rpart's actual drop criterion -- a row missing
#    only *some* predictors is instead handled via surrogate splits and
#    kept) combined with an `xval` vector given at the pre-drop length,
#    exercising xpred_rpart's na.action-index-filtering branch on a minimal
#    (single dropped row) dataset.
# ---------------------------------------------------------------------------

def test_xpred_rpart_na_action_all_predictors_missing_row_matches_r():
    df = pd.DataFrame(
        {
            "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "x1": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0],
            "x2": [10.0, 9.0, np.nan, 7.0, 6.0, 5.0, 4.0, 3.0],
        }
    )
    r_dataframe_assign("df", df)
    r_fit = run_r("rpart(y ~ x1 + x2, data=df, control=rpart.control(xval=0, minsplit=2))")

    py_fit = rpart("y ~ x1 + x2", data=df, x=True, control={"xval": 0, "minsplit": 2})
    assert py_fit.get("na.action") is not None
    assert py_fit["na.action"]["indices"] == [3]  # 1-based: the fully-missing 3rd row

    n_full = len(df)
    xgrp_full = np.resize(np.arange(1, 4), n_full)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp_full))
    py_result = xpred_rpart(py_fit, xval=xgrp_full)

    n_kept = py_fit["x"].shape[0]
    assert n_kept == n_full - 1
    assert py_result.shape[0] == n_kept
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8, equal_nan=True)


# ---------------------------------------------------------------------------
# 10. KNOWN GAP -- run out-of-process, see WARNING below: a bare python
#     scalar (not a length-1 array) passed as `cp=` is accepted by R
#     (an ordinary length-1 numeric vector, since R has no scalar/array
#     distinction) but not by xpred_rpart: `np.asarray(cp, dtype=np.float64)`
#     on a python float produces a genuine 0-D numpy array, which is still
#     passed straight through to the compiled `_xpred_c` extension (the
#     `len(cp_arr)` call that would have caught this happens only *after*
#     that C call, when reshaping its output). Confirmed empirically (see
#     this module's generation notes) that this is not merely a clean,
#     contained `TypeError` in the same run that already built an rpy2-fitted
#     R model beforehand: the malformed 0-D array reaching the C extension
#     leaves the process in a state that reliably segfaults *later*, at
#     interpreter shutdown -- reproduced consistently, never in a fresh
#     process with no prior rpy2/rpart activity. This is exercised here via
#     an isolated `subprocess` (rather than in-process, which would crash
#     *this* test session too) specifically so the crash is safely contained
#     -- the workaround (wrapping the scalar in a length-1 array, e.g.
#     `numpy.array([0.2])`, exactly what every other test in this suite
#     already does for its own `cp=` arguments) is unaffected and used
#     everywhere else in this file/module.
# ---------------------------------------------------------------------------

_BARE_SCALAR_CP_REPRO_SCRIPT = """
import sys
sys.path.insert(0, "tests")
import numpy as np
from r2py_rpart import rpart, xpred_rpart
from _r_rpart_helpers import mtcars_df, r_dataframe_assign, r_fit_rpart, r_xpred, r_xpred_to_numpy

df = mtcars_df()
r_dataframe_assign("df", df)
r_fit = r_fit_rpart("mpg ~ wt", control="rpart.control(xval=0)")

py_fit = rpart("mpg ~ wt", data=df, x=True, control={"xval": 0})
n = len(df)
xgrp = np.resize(np.arange(1, 4), n)

# R accepts a bare scalar cp=0.2 without complaint.
r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, cp=0.2))
assert r_result.shape == (n, 1)
print("R_OK", flush=True)

# python raises a clean TypeError for the same bare-scalar cp=0.2 --
# but (see module note) this process may still crash afterward.
try:
    xpred_rpart(py_fit, xval=xgrp, cp=0.2)
    print("PY_NO_ERROR", flush=True)
except TypeError as exc:
    print("PY_TYPE_ERROR:", exc, flush=True)

print("REACHED_END", flush=True)
"""


def test_xpred_rpart_bare_scalar_cp_known_gap_segfaults_out_of_process():
    repo_root = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.run(
        [sys.executable, "-u", "-c", _BARE_SCALAR_CP_REPRO_SCRIPT],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=120,
    )

    # Both sides completed their own logical work before the process died:
    # R succeeded, and python's own TypeError was raised and caught cleanly.
    assert "R_OK" in proc.stdout
    assert "PY_TYPE_ERROR" in proc.stdout
    assert "REACHED_END" in proc.stdout

    # ...yet the *process* itself does not exit cleanly: it is killed by a
    # signal (SIGSEGV, i.e. returncode -11) during shutdown -- the actual
    # confirmed bug being documented by this test. If a future fix to
    # xpred_rpart's C bridge validates `cp`'s dimensionality *before*
    # calling into the C extension (rather than only failing on the
    # downstream `len()`), this process will instead exit cleanly (0); if
    # so, update this assertion to `proc.returncode == 0` to reflect the fix.
    assert proc.returncode != 0, (
        "expected the known cp=<bare scalar> memory-corruption bug to still "
        f"reproduce (nonzero/signal exit); got returncode={proc.returncode}, "
        f"stdout={proc.stdout!r}"
    )
