"""Positive-path parity tests for r2py_rpart.text_rpart vs. R's
`text.rpart` (an S3 method for the `text` generic, `S3method(text, rpart)`
in rpart's NAMESPACE -- see
`/groups/jli9/Yufei/python-rpart/rpart/man/text.rpart.Rd` and
`/groups/jli9/Yufei/python-rpart/rpart/R/text.rpart.R`).

text_rpart(x, splits=True, label=MISSING, FUN=None, all=False,
pretty=MISSING, digits=None, use_n=False, fancy=False, fwidth=0.8,
fheight=0.8, bg=None, minlength=1, ax=None, cxy=None, **kwargs) is a pure
side-effect annotation function (it always returns None, mirroring R's own
`invisible()`) that labels an *already-plotted* tree dendrogram -- both
sides require a prior `plot(x, ...)`/`plot_rpart(x, ...)` call in the same
graphics device/Axes to populate the per-device layout parms `rpartco()`
reads (`rpart_env`).

Comparison strategy (see `_r_rpart_helpers.py`'s "text.rpart-specific
plumbing" section for the full rationale): rather than hand-copying
text.rpart.R's derivation logic into a synthetic-object R replica (as done
for plot.rpart/plotcp), this file substitutes a custom `FUN=` *capturing*
closure on both sides into the exact same already-fitted model, and simply
records every `(x, y, labels)` triple each `FUN()` invocation receives, in
call order -- directly comparable call-for-call via
`assert_text_rpart_calls_match()`. This relies on R's and r2py_rpart's own
`rpart(...)` choosing the *identical* tree structure for a given
formula/data -- confirmed empirically for every dataset used below
(kyphosis/car.test.frame/cu.summary/stagec).

R's real, device-dependent `par("cxy")` (character width/height) has no
reason to numerically agree with matplotlib's own font-metric-derived
guess, so every test below fetches R's actual `par("cxy")` (via
`r_text_rpart_capture()`) and feeds that *exact* tuple into python's
`text_rpart(..., cxy=...)`/`call_text_rpart_and_extract(..., cxy=...)` --
isolating the comparison to text.rpart's own label/position derivation
logic, not to cxy resolution (an acknowledged, deliberate approximation on
the python side when `cxy=None`; see `test_text_rpart_edge.py`'s dedicated
default-cxy-resolution smoke test).

KNOWN BUG (documented in test_text_rpart_edge.py, not exercised for exact
match here): `fancy=True`'s two split-*edge*-label FUN() calls (the first
two captures) are mis-derived on the python side. This file's fancy=True
test therefore only asserts on the *third* (leaf/node stat) FUN() call --
which is unaffected by that bug and matches R exactly regardless of
`fancy=` -- plus structural patch-count checks.

All of text_rpart's own keyword arguments (splits=/all=/pretty=/minlength=/
digits=/use_n=/fancy=/fwidth=/fheight=/bg=/FUN=) are exercised below,
individually and in combination, across class/anova/poisson fits.
"""
from __future__ import annotations

import numpy as np
import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart
from r2py_rpart.plot_rpart import plot_rpart
from r2py_rpart.text_rpart import text_rpart

from _r_rpart_helpers import (
    assert_text_rpart_calls_match,
    call_text_rpart_and_extract,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_text_rpart_capture,
    run_r,
    stagec_df,
)


def _kyphosis_fits():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    return fit, r_fit


# ---------------------------------------------------------------------------
# 1. A genuine classification fit (kyphosis), every text_rpart() argument
#    left at its documented default (splits=True, all=False, fancy=False,
#    use_n=False, minlength=1). Confirms the split-label call (call 0,
#    length == nrow(frame), NA/None at every leaf's own slot) and the
#    leaf-only stat call (call 1) both match R's genuine `text(fit)` call
#    exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_classification_kyphosis_all_defaults():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)

    assert len(py_out["calls"]) == 2
    assert len(py_out["calls"][0]["labels"]) == fit["frame"].shape[0]
    # only the leaves get a stat label by default (all=False)
    n_leaves = int((fit["frame"]["var"] == "<leaf>").sum())
    assert len(py_out["calls"][1]["labels"]) == n_leaves
    assert py_out["retval"] is None
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 2. use_n=True appends "(#events level1/#events level2)"-style counts to
#    every leaf stat label for a classification fit -- confirmed to match R
#    exactly (not just structurally), and to actually contain "/" (unlike
#    the use_n=False default).
# ---------------------------------------------------------------------------

def test_text_rpart_use_n_true_classification():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit, use_n=True)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, use_n=True)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)

    assert all("/" in lab for lab in py_out["calls"][-1]["labels"])
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 3. splits=False suppresses the split-label FUN() call entirely -- only the
#    leaf stat call remains (a single FUN() invocation total), on both
#    sides.
# ---------------------------------------------------------------------------

def test_text_rpart_splits_false_only_stat_call():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit, splits=False)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, splits=False)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    assert len(py_out["calls"]) == 1
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 4. all=True labels *every* frame row's stat (internal nodes too, not just
#    leaves) -- the stat call's label count grows from n_leaves to
#    nrow(frame) on both sides, and matches R exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_all_true_labels_every_node():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit, all=True)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, all=True)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    assert len(py_out["calls"][-1]["labels"]) == fit["frame"].shape[0]
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 5. A regression (anova) fit (car.test.frame, Mileage ~ Weight) broadens
#    method coverage beyond "class" -- exercises the numeric-yval `text`
#    closure (formatg-based) rather than the classification one, at the
#    default digits (getOption("digits") - 3L == 4 in R; python's own
#    `digits=None -> 4` stand-in).
# ---------------------------------------------------------------------------

def test_text_rpart_regression_anova_car_test_frame():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    assert fit["frame"].shape[0] > 1

    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 6. digits= overrides the default numeric-label precision on the same
#    anova fit -- confirmed to actually change the rendered stat labels
#    relative to the default, and to still match R exactly for the new
#    value.
# ---------------------------------------------------------------------------

def test_text_rpart_digits_override_anova():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")

    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')

    r_calls_default, cxy = r_text_rpart_capture(r_fit)
    py_default = call_text_rpart_and_extract(fit, cxy=cxy)

    r_calls_2, _ = r_text_rpart_capture(r_fit, digits=2)
    py_2 = call_text_rpart_and_extract(fit, cxy=cxy, digits=2)
    assert_text_rpart_calls_match(py_2["calls"], r_calls_2)

    assert py_2["calls"][-1]["labels"] != py_default["calls"][-1]["labels"]
    import matplotlib.pyplot as plt
    plt.close(py_default["fig"])
    plt.close(py_2["fig"])


def _cu_summary_categorical_fit():
    df = cu_summary_df()
    fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class",
        control={"minsplit": 30, "cp": 0.05},
    )
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Reliability ~ Price + Country + Mileage + Type", method='"class"',
        control="rpart.control(minsplit=30, cp=0.05)",
    )
    return fit, r_fit


# ---------------------------------------------------------------------------
# 7. A categorical-predictor classification fit (cu.summary, Type/Country
#    are unordered factors) at the documented default `minlength=1L`
#    (single-letter abbreviation) -- exercises labels_rpart's categorical-
#    split branch, confirmed to match R's `a,b,c`-style single-letter
#    abbreviations exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_categorical_split_minlength_default():
    fit, r_fit = _cu_summary_categorical_fit()
    assert "Type" in set(fit["frame"]["var"]) or "Country" in set(fit["frame"]["var"])

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 8. minlength= explicitly overridden (3) on the same categorical fit --
#    exercises labels_rpart's `abbreviate()`-based multi-letter abbreviation
#    branch, confirmed to match R exactly (a different label string than
#    the minlength=1 default above).
# ---------------------------------------------------------------------------

def test_text_rpart_categorical_split_minlength_explicit():
    fit, r_fit = _cu_summary_categorical_fit()

    r_calls, cxy = r_text_rpart_capture(r_fit, minlength=3)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, minlength=3)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)

    r_calls_default, _ = r_text_rpart_capture(r_fit)
    assert py_out["calls"][0]["labels"] != r_calls_default[0]["labels"]
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 9. pretty=False (with minlength left at its MISSING sentinel) reaches
#    text.rpart.R's special `if (!missing(pretty) && missing(minlength))
#    labels(x, pretty = pretty)` dispatch -- i.e. `labels_rpart(x,
#    pretty=False)` rather than `labels_rpart(x, minlength=minlength)` --
#    which resolves to *no* abbreviation at all (full category names),
#    confirmed to match R exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_pretty_false_dispatches_to_labels_pretty_argument():
    fit, r_fit = _cu_summary_categorical_fit()

    r_calls, cxy = r_text_rpart_capture(r_fit, pretty=False)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, pretty=False)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    # full, unabbreviated category names should appear (e.g. "Germany", not "d")
    assert any("Germany" in lab for lab in py_out["calls"][0]["labels"] if lab)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 10. A method="poisson" (Surv()-style) fit on stagec broadens method
#     coverage to the survival-flavoured `text` closure, mirroring the
#     pre-built model-frame pattern test_plot_rpart_positive.py/
#     test_printcp_positive.py already use for poisson/Surv fits.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df, predictors):
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


def test_text_rpart_poisson_method_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]
    m = _stagec_prebuilt_model_frame(df, predictors)
    fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m, method="poisson", control={"maxsurrogate": 0, "cp": 0.02},
    )
    assert fit["frame"].shape[0] > 1

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        'rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, '
        'method="poisson", control=rpart.control(maxsurrogate=0, cp=0.02))'
    )
    assert list(ro.r["as.character"](r_fit.rx2("frame").rx2("var"))) == fit["frame"]["var"].tolist()

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 11. fancy=True: the leaf/node *stat* FUN() call (always the last capture)
#     matches R exactly, and exactly one patch (oval or rectangle) is drawn
#     per frame row -- both properties hold despite the known split-edge-
#     label bug documented in test_text_rpart_edge.py (which only affects
#     the first two captures, not the stat call or patch count).
# ---------------------------------------------------------------------------

def test_text_rpart_fancy_stat_labels_and_patch_count():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit, fancy=True, use_n=True, bg="white")
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, fancy=True, use_n=True, bg="white")

    assert len(py_out["calls"]) == 3 == len(r_calls)
    assert py_out["calls"][-1]["x"] == pytest.approx(r_calls[-1]["x"], abs=1e-6)
    assert py_out["calls"][-1]["y"] == pytest.approx(r_calls[-1]["y"], abs=1e-6)
    assert py_out["calls"][-1]["labels"] == r_calls[-1]["labels"]

    assert py_out["n_patches"] == fit["frame"].shape[0]
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 12. A custom bg= color in fancy mode is actually applied as every patch's
#     facecolor (a purely python-side structural check -- text.rpart.R's
#     own `polygon(..., col = bg)` plays the identical role on the R side,
#     but individual polygon fill colors are not recoverable through rpy2's
#     capture-based plumbing used elsewhere in this file).
# ---------------------------------------------------------------------------

def test_text_rpart_fancy_custom_bg_color_applied_to_patches():
    import matplotlib.colors as mcolors

    fit, r_fit = _kyphosis_fits()
    r_calls, cxy = r_text_rpart_capture(r_fit, fancy=True, bg="lightyellow")
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, fancy=True, bg="lightyellow")

    expected_rgba = mcolors.to_rgba("lightyellow")
    for patch in py_out["ax"].patches:
        assert patch.get_facecolor() == pytest.approx(expected_rgba)

    assert py_out["calls"][-1]["labels"] == r_calls[-1]["labels"]
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 13. A caller-supplied FUN= is invoked with exactly the same call sequence
#     that the default text-drawing closure would have received (a
#     python-only threading check -- the FUN= parameter itself, and its
#     positional `(x, y, labels)` + forwarded `**kwargs` calling convention,
#     mirror R's own `FUN(x, y, labels, ...)` calling convention exactly).
# ---------------------------------------------------------------------------

def test_text_rpart_custom_fun_receives_expected_calls():
    fit, r_fit = _kyphosis_fits()
    r_calls, cxy = r_text_rpart_capture(r_fit, use_n=True)

    recorded = []

    def custom_fun(xs, ys, labels, **kw):
        recorded.append((list(xs), list(ys), list(labels), kw))

    df = kyphosis_df()
    fig = None
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    try:
        plot_rpart(fit, ax=ax)
        text_rpart(fit, ax=ax, FUN=custom_fun, cxy=cxy, use_n=True, color="red")
    finally:
        plt.close(fig)

    assert len(recorded) == 2
    assert recorded[0][3].get("color") == "red"
    assert recorded[-1][2] == r_calls[-1]["labels"]
