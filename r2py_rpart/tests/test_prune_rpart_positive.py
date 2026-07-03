"""Positive-path parity tests for r2py_rpart.prune_rpart itself (imported and
called *directly*, rather than through the `prune()` S3-generic wrapper) vs.
R's `rpart:::prune.rpart` (its S3 method, called directly with the same
"tree, cp" positional/keyword flexibility R's own method signature offers).

test_prune_positive.py/test_prune_negative.py/test_prune_edge.py already give
`prune_rpart` exhaustive coverage of its *value*-level behavior (every
combination of method/cp/tree shape that matters numerically) by calling it
indirectly through `r2py_rpart.prune.prune(tree, **kwargs)` -- and, per that
module's own docstring, `prune()` does nothing but
`return prune_rpart(tree, **kwargs)`, so every one of those tests already
exercises `prune_rpart`'s numeric logic exactly.

What `prune()`'s thin wrapper does *not* exercise is `prune_rpart`'s own
concrete call *signature* -- `def prune_rpart(tree, cp)`, two fixed
positional-or-keyword parameters, no `**kwargs` catch-all -- since
`prune(tree, **kwargs)` only ever forwards `cp` (and anything else) as a
*keyword*, never positionally, and never lets `tree` be passed by keyword
either (it is `prune`'s own first positional parameter). R's
`prune.rpart(tree, cp, ...)` method itself supports both plain positional
calls (`prune.rpart(fit, 0.1)`) and fully-named, reordered calls
(`prune.rpart(cp=0.1, tree=fit)`) -- both confirmed live against R below,
and both are exactly what calling `prune_rpart` directly (rather than through
`prune()`) newly makes possible/testable on the python side. That
signature-level parity -- not the already-well-covered numeric logic -- is
this file's focus.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart
from r2py_rpart.prune_rpart import prune_rpart

from _r_rpart_helpers import (
    extract_r_fit,
    kyphosis_df,
    mtcars_df,
    r_assign,
    r_dataframe_assign,
    r_fit_rpart,
    run_r,
    stagec_df,
)


def _assert_pruned_matches_r(py_pruned: dict, r_pruned) -> None:
    """Same field-for-field comparison as test_prune_positive.py's helper of
    the same name (frame var/complexity/ncompete/nsurrogate/row-ids, cptable,
    where, variable.importance) -- reproduced here (rather than imported)
    since it is a private helper of that module."""
    r_out = extract_r_fit(r_pruned)

    py_frame = py_pruned["frame"]
    assert py_frame["var"].tolist() == r_out["var"]
    assert_allclose(py_frame.index.to_numpy(dtype=float), r_out["frame_index"].astype(float))
    assert_allclose(py_frame["complexity"].to_numpy(), r_out["complexity"], rtol=1e-6, atol=1e-8)
    assert_allclose(py_frame["ncompete"].to_numpy(), r_out["ncompete"])
    assert_allclose(py_frame["nsurrogate"].to_numpy(), r_out["nsurrogate"])

    assert_allclose(py_pruned["cptable"].to_numpy(dtype=float), r_out["cptable"], rtol=1e-5, atol=1e-8)
    assert_allclose(np.asarray(py_pruned["where"], dtype=float), r_out["where"])


# ---------------------------------------------------------------------------
# 1. `cp` passed *positionally* (`prune_rpart(fit, 0.1)`), matching R's own
#    `prune.rpart(fit, 0.1)` positional call -- a call form `prune()`'s
#    keyword-only-forwarding wrapper never exercises.
# ---------------------------------------------------------------------------

def test_prune_rpart_positional_cp_argument_matches_r_anova_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_pos_tmp", r_fit)
    r_pruned = run_r("prune.rpart(prune_rpart_pos_tmp, 0.1)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune_rpart(py_fit, 0.1)

    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 2. Fully-named, *reordered* keyword call (`prune_rpart(cp=0.02,
#    tree=fit)`), matching R's `prune.rpart(cp=0.02, tree=fit)` -- exercising
#    that `prune_rpart`'s parameter is genuinely named `tree` (not just
#    positional-only), on a classification fit.
# ---------------------------------------------------------------------------

def test_prune_rpart_reordered_keyword_arguments_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_kw_tmp", r_fit)
    r_pruned = run_r("prune.rpart(cp=0.02, tree=prune_rpart_kw_tmp)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    py_pruned = prune_rpart(cp=0.02, tree=py_fit)

    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 3. Positional-call vs. keyword-call agreement, on the *same* fit: whichever
#    calling convention is used, `prune_rpart` must produce numerically
#    identical output (a pure python-side self-consistency check, not a new
#    R comparison, but specific to exercising both of `prune_rpart`'s own
#    call forms side by side rather than relying on only one).
# ---------------------------------------------------------------------------

def test_prune_rpart_positional_and_keyword_calls_agree_with_each_other():
    df = mtcars_df()
    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})

    py_pruned_positional = prune_rpart(py_fit, 0.05)
    py_pruned_keyword = prune_rpart(py_fit, cp=0.05)

    assert py_pruned_positional["frame"]["var"].tolist() == py_pruned_keyword["frame"]["var"].tolist()
    assert_allclose(
        py_pruned_positional["cptable"].to_numpy(dtype=float),
        py_pruned_keyword["cptable"].to_numpy(dtype=float),
    )


# ---------------------------------------------------------------------------
# 4. `cp` passed as a python `int` (e.g. `cp=0`), positionally, causing a
#    genuine (partial) prune: exercises that `prune_rpart`'s `cp: float`
#    annotation is not enforced at runtime and an int works exactly like the
#    equivalent float, matching R's own int-vs-double insensitivity
#    (`prune.rpart(fit, 0L)` behaves identically to `cp=0`).
# ---------------------------------------------------------------------------

def test_prune_rpart_int_cp_zero_matches_r_no_op():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_int_tmp", r_fit)
    r_pruned = run_r("prune.rpart(prune_rpart_int_tmp, 0L)")
    r_nrow = int(np.asarray(run_r("nrow(prune.rpart(prune_rpart_int_tmp, 0L)$frame)"))[0])

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune_rpart(py_fit, 0)

    assert py_pruned["frame"].shape[0] == r_nrow == py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 5. `cp` passed as a python `int` at a genuinely-tossing, non-zero value
#    (`cp=1`, an int -- large enough to collapse the tree to its root),
#    confirming int-vs-float insensitivity also holds when `toss` actually is
#    non-empty (test 4 above is a no-op, so `snip_rpart`/`cptable`
#    recomputation is never reached there).
# ---------------------------------------------------------------------------

def test_prune_rpart_int_cp_large_value_matches_r_collapse_to_root():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_int2_tmp", r_fit)
    r_pruned = run_r("prune.rpart(prune_rpart_int2_tmp, 1L)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune_rpart(py_fit, 1)

    assert py_pruned["frame"].shape[0] == 1
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 6. Implementation invariant (python-specific, not an R-comparison test):
#    `prune_rpart`'s own early-return (`if len(toss) == 0: return tree`) means
#    a no-op prune must return the *exact same dict object* (`is`, not just
#    equal), not merely an equal-valued copy -- this reference-identity
#    contract is invisible when only comparing field values against R (R has
#    no such notion), but is a genuine, testable part of `prune_rpart`'s own
#    documented "no-op" behavior (see its `if len(toss) == 0` early-out).
# ---------------------------------------------------------------------------

def test_prune_rpart_no_op_returns_the_identical_tree_object():
    df = mtcars_df()
    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})

    py_pruned = prune_rpart(py_fit, 0.0)

    assert py_pruned is py_fit


# ---------------------------------------------------------------------------
# 7. Implementation invariant (python-specific): whenever a genuine toss
#    *does* occur, `prune_rpart` must instead return a brand-new object
#    (produced by `snip_rpart`), leaving the original, unpruned `tree` dict
#    completely untouched -- both objects coexist afterwards with their own,
#    different frame shapes.
# ---------------------------------------------------------------------------

def test_prune_rpart_genuine_toss_returns_a_new_object_and_leaves_original_untouched():
    df = mtcars_df()
    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    original_nrow = py_fit["frame"].shape[0]

    py_pruned = prune_rpart(py_fit, 0.1)

    assert py_pruned is not py_fit
    assert py_fit["frame"].shape[0] == original_nrow  # original left unmodified
    assert py_pruned["frame"].shape[0] < original_nrow


# ---------------------------------------------------------------------------
# 8. Positional-cp call on a `method="poisson"` (Surv()-style two-column
#    response) fit, a deeper tree pruned down to a mid-range cp -- combining
#    the signature-level focus of this file (positional `cp`) with the
#    surrogate/csplit-heavy fit already used in test_prune_positive.py's test
#    3, to confirm the positional-call form isn't only exercised on the
#    simplest (anova/mtcars) fits above.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    m = df[predictors].copy()
    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv_response"] + predictors,
        "response": 1,
        "xlevels": {"ploidy": list(df["ploidy"].cat.categories)},
    }
    m.attrs["response"] = np.column_stack(
        [df["pgtime"].to_numpy(dtype=float), df["pgstat"].to_numpy(dtype=float)]
    )
    return m


def test_prune_rpart_positional_cp_matches_r_poisson_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.001))'
    )
    r_assign("prune_rpart_pos_stagec_tmp", r_fit)
    r_pruned = run_r("prune.rpart(prune_rpart_pos_stagec_tmp, 0.02)")

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.001},
    )
    py_pruned = prune_rpart(py_fit, 0.02)

    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)
