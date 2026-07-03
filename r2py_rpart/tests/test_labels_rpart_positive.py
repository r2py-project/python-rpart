"""Positive-path parity tests for r2py_rpart.labels_rpart vs. R's
`labels.rpart` (an S3 method for the `labels` generic, `S3method(labels,
rpart)` in rpart's NAMESPACE -- see
`/groups/jli9/Yufei/python-rpart/rpart/man/labels.rpart.Rd` and
`/groups/jli9/Yufei/python-rpart/rpart/R/labels.rpart.R`).

labels_rpart(object, digits=4, minlength=1, pretty=<missing>, collapse=True,
**kwargs) is a pure function of an already-fitted model's `frame`/
`splits`/`csplit`/`_xlevels` -- no graphics device, no RNG-driven
cross-validation, no other side effects. So (unlike plotcp/plot.rpart's
hand-copied "derivation replica" strategy, or text.rpart's FUN=-capturing-
closure strategy) it is exercised here simply by calling the documented
`labels(fit, ...)` R generic and r2py_rpart's `labels_rpart(fit, ...)`
directly on *the same fitted model*, built once via R's own `rpart(...)`
(`r_fit_rpart`) and once via r2py_rpart's `rpart(...)`, from identical
data/formula -- relying only on both implementations choosing the
identical tree structure for identical inputs, already established/relied
upon throughout this test suite (see test_text_rpart_positive.py's module
docstring) for every dataset used below (kyphosis/car.test.frame/
cu.summary/stagec).

See tests/_r_rpart_helpers.py's "labels.rpart-specific plumbing" section
for the shared machinery used throughout:

  - `r_labels(fit, **kwargs)` -- calls R's `labels(fit, ...)` (the
    documented S3-generic dispatch route) and returns the raw rpy2 result.
  - `r_labels_to_python(robj)` -- converts that result into a plain
    `list[str]` (`collapse=True`) or a 2-D numpy `str` array
    (`collapse=False`), directly comparable to r2py_rpart.labels_rpart()'s
    own return value.
  - `make_synthetic_categorical_fit(...)` -- builds a minimal synthetic
    categorical-split fit (both a python dict and a matching, assigned-into-
    globalenv R list object) for scenarios impractical to reach through a
    genuine data-driven fit (e.g. a >52-level factor).

Every one of labels_rpart's own parameters -- digits=, minlength=
(including its `pretty=`-derived defaults), pretty=, collapse=, and their
combinations -- is exercised below, across continuous-only (kyphosis: both
`ncat > 0`/`ncat < 0` split directions), categorical (cu.summary: `Country`/
`Type`, multi-level unordered factors), and mixed continuous+categorical
model shapes.
"""
from __future__ import annotations

import numpy as np

from r2py_rpart import rpart
from r2py_rpart.labels_rpart import labels_rpart

from _r_rpart_helpers import (
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_labels,
    r_labels_to_python,
    run_r,
    stagec_df,
)


def _kyphosis_fits():
    """Continuous-only classification tree (Age/Number/Start), whose splits
    table exercises *both* `ncat == 1` and `ncat == -1` (i.e. both split
    directions of the `"< "`/`">= "` continuous-cutpoint formatting)."""
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    return fit, r_fit


def _car_test_frame_fits():
    """Continuous-only regression tree (Mileage ~ Weight); `xval=0` keeps
    the fit deterministic (no RNG-driven cross-validation involved in
    labels() at all, but this mirrors the rest of this test suite's own
    convention of disabling xval whenever it's irrelevant to what's being
    tested)."""
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    return fit, r_fit


def _cu_summary_fits():
    """Classification tree with multi-level unordered-factor categorical
    predictors (`Country`: 10 levels, `Type`: 6 levels) as the *primary*
    splits throughout -- exercises labels_rpart's categorical-split branch
    (csplit-driven `=`-prefixed level-set labels) exhaustively."""
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", method='"class"')
    fit = rpart("Reliability ~ Price + Country + Mileage + Type", data=df, method="class")
    return fit, r_fit


def _stagec_fits():
    """Continuous-only regression tree from a third, independent dataset
    (stagec's `grade ~ age + g2 + gleason + eet`), for extra coverage of
    the digits=/cutpoint-formatting path beyond kyphosis/car.test.frame."""
    df = stagec_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("grade ~ age + g2 + gleason + eet", control="rpart.control(xval=0)")
    fit = rpart("grade ~ age + g2 + gleason + eet", data=df, method="anova", control={"xval": 0})
    return fit, r_fit


# ---------------------------------------------------------------------------
# 1. Default arguments (digits=4, minlength=1, collapse=True), continuous-
#    only predictors -- the labels.rpart.Rd worked-example shape.
# ---------------------------------------------------------------------------

def test_labels_rpart_default_args_continuous_kyphosis():
    fit, r_fit = _kyphosis_fits()
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs


def test_labels_rpart_default_args_continuous_car_test_frame():
    fit, r_fit = _car_test_frame_fits()
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs


# ---------------------------------------------------------------------------
# 2. Default arguments, categorical predictors (Country/Type) -- exercises
#    the `ncat > 1L` branch and its default `minlength == 1L` single-letter
#    abbreviation.
# ---------------------------------------------------------------------------

def test_labels_rpart_default_args_categorical_cu_summary():
    fit, r_fit = _cu_summary_fits()
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs
    # Sanity-check that this fit actually exercises the categorical branch
    # (an "=" prefix on at least one non-root label) -- otherwise the test
    # would silently degenerate into a second continuous-only check.
    assert any("=" in lab for lab in py_labs)


# ---------------------------------------------------------------------------
# 3. digits=: every distinct value changes only the continuous cutpoints'
#    numeric formatting (formatg(..., digits)) -- exercised across a wide
#    range, including the documented default (4) and both R's own default
#    getOption("digits") (7) and single-digit/very-precise extremes.
# ---------------------------------------------------------------------------

def test_labels_rpart_digits_values_continuous_kyphosis():
    fit, r_fit = _kyphosis_fits()
    for digits in (1, 2, 4, 7, 10):
        r_labs = r_labels_to_python(r_labels(r_fit, digits=digits))
        py_labs = labels_rpart(fit, digits=digits)
        assert py_labs == r_labs, f"digits={digits}"


def test_labels_rpart_digits_values_continuous_stagec():
    fit, r_fit = _stagec_fits()
    for digits in (1, 3, 4, 6):
        r_labs = r_labels_to_python(r_labels(r_fit, digits=digits))
        py_labs = labels_rpart(fit, digits=digits)
        assert py_labs == r_labs, f"digits={digits}"


# ---------------------------------------------------------------------------
# 4. minlength=: every documented value (0 = no abbreviation, 1 = single
#    letters, 2+ = abbreviate()) on the categorical (cu.summary) fit --
#    confirms the hand-replicated `abbreviate()` priority-based vowel/
#    consonant/uppercase-stripping algorithm agrees with R's real
#    `abbreviate()` exactly, across every minlength in range.
# ---------------------------------------------------------------------------

def test_labels_rpart_minlength_values_categorical_cu_summary():
    fit, r_fit = _cu_summary_fits()
    for minlength in (0, 1, 2, 3, 4, 5, 8):
        r_labs = r_labels_to_python(r_labels(r_fit, minlength=minlength))
        py_labs = labels_rpart(fit, minlength=minlength)
        assert py_labs == r_labs, f"minlength={minlength}"


def test_labels_rpart_minlength_zero_uses_full_level_names():
    """minlength=0 -> "no abbreviation is done" (labels.rpart.Rd): the
    level-set labels must contain the *full*, comma-joined level names."""
    fit, r_fit = _cu_summary_fits()
    py_labs = labels_rpart(fit, minlength=0)
    r_labs = r_labels_to_python(r_labels(r_fit, minlength=0))
    assert py_labs == r_labs
    assert any("Country=" in lab and "," in lab for lab in py_labs)


def test_labels_rpart_minlength_one_uses_single_letters():
    """minlength=1 -> "single English letters are used" (labels.rpart.Rd,
    with no separating comma, `cl <- ""`): confirm the level-set labels are
    letters-only with no commas."""
    fit, r_fit = _cu_summary_fits()
    py_labs = labels_rpart(fit, minlength=1)
    r_labs = r_labels_to_python(r_labels(r_fit, minlength=1))
    assert py_labs == r_labs
    country_labels = [lab for lab in py_labs if lab.startswith("Country=")]
    assert country_labels
    for lab in country_labels:
        letters_part = lab.split("=", 1)[1]
        assert "," not in letters_part
        assert letters_part.isalpha()


# ---------------------------------------------------------------------------
# 5. pretty=: the three documented compatibility mappings (pretty=NULL ->
#    minlength=1L, pretty=0 -> minlength=0L, pretty=TRUE -> minlength=4L),
#    plus pretty=FALSE (also -> minlength=0L, per labels.rpart.R's `else
#    0L` branch for any non-TRUE logical) -- confirmed to produce output
#    identical to explicitly passing the equivalent minlength=.
# ---------------------------------------------------------------------------

def test_labels_rpart_pretty_none_matches_minlength_one():
    fit, r_fit = _cu_summary_fits()
    py_pretty = labels_rpart(fit, pretty=None)
    py_minlength = labels_rpart(fit, minlength=1)
    r_pretty = r_labels_to_python(r_labels(r_fit, pretty=None))
    assert py_pretty == py_minlength == r_pretty


def test_labels_rpart_pretty_zero_matches_minlength_zero():
    fit, r_fit = _cu_summary_fits()
    py_pretty = labels_rpart(fit, pretty=0)
    py_minlength = labels_rpart(fit, minlength=0)
    r_pretty = r_labels_to_python(r_labels(r_fit, pretty=0))
    assert py_pretty == py_minlength == r_pretty


def test_labels_rpart_pretty_true_matches_minlength_four():
    fit, r_fit = _cu_summary_fits()
    py_pretty = labels_rpart(fit, pretty=True)
    py_minlength = labels_rpart(fit, minlength=4)
    r_pretty = r_labels_to_python(r_labels(r_fit, pretty=True))
    assert py_pretty == py_minlength == r_pretty


def test_labels_rpart_pretty_false_matches_minlength_zero():
    fit, r_fit = _cu_summary_fits()
    py_pretty = labels_rpart(fit, pretty=False)
    py_minlength = labels_rpart(fit, minlength=0)
    r_pretty = r_labels_to_python(r_labels(r_fit, pretty=False))
    assert py_pretty == py_minlength == r_pretty


# ---------------------------------------------------------------------------
# 6. collapse=False: a two-column array of left/right descendant labels,
#    with "<leaf>" placeholders for terminal nodes -- exercised on both a
#    continuous-only and a categorical fit.
# ---------------------------------------------------------------------------

def test_labels_rpart_collapse_false_continuous_kyphosis():
    fit, r_fit = _kyphosis_fits()
    r_mat = r_labels_to_python(r_labels(r_fit, collapse=False))
    py_mat = labels_rpart(fit, collapse=False)
    assert isinstance(py_mat, np.ndarray)
    assert py_mat.shape == r_mat.shape
    assert (py_mat == r_mat).all()
    # Every leaf row's own left/right pair must be exactly "<leaf>","<leaf>".
    is_leaf = (fit["frame"]["var"].to_numpy() == "<leaf>")
    assert (py_mat[is_leaf] == "<leaf>").all()


def test_labels_rpart_collapse_false_categorical_cu_summary():
    fit, r_fit = _cu_summary_fits()
    r_mat = r_labels_to_python(r_labels(r_fit, collapse=False))
    py_mat = labels_rpart(fit, collapse=False)
    assert py_mat.shape == r_mat.shape
    assert (py_mat == r_mat).all()


# ---------------------------------------------------------------------------
# 7. Combinations: digits/minlength/collapse varied jointly (a full
#    parameter-combination sweep across all of labels_rpart's own knobs at
#    once), on both a continuous and a categorical fit.
# ---------------------------------------------------------------------------

def test_labels_rpart_all_parameter_combinations_continuous():
    fit, r_fit = _kyphosis_fits()
    for digits in (2, 4):
        for minlength in (0, 1, 3):
            for collapse in (True, False):
                r_res = r_labels_to_python(
                    r_labels(r_fit, digits=digits, minlength=minlength, collapse=collapse)
                )
                py_res = labels_rpart(fit, digits=digits, minlength=minlength, collapse=collapse)
                if collapse:
                    assert py_res == r_res, (digits, minlength, collapse)
                else:
                    assert (np.asarray(py_res) == r_res).all(), (digits, minlength, collapse)


def test_labels_rpart_all_parameter_combinations_categorical():
    fit, r_fit = _cu_summary_fits()
    for digits in (2, 4):
        for minlength in (0, 1, 3):
            for collapse in (True, False):
                r_res = r_labels_to_python(
                    r_labels(r_fit, digits=digits, minlength=minlength, collapse=collapse)
                )
                py_res = labels_rpart(fit, digits=digits, minlength=minlength, collapse=collapse)
                if collapse:
                    assert py_res == r_res, (digits, minlength, collapse)
                else:
                    assert (np.asarray(py_res) == r_res).all(), (digits, minlength, collapse)


# ---------------------------------------------------------------------------
# 8. Synthetic categorical fixture, exact-match sanity check: confirms
#    `make_synthetic_categorical_fit()`'s own hand-built frame/splits/
#    csplit/_xlevels shape (used more heavily by the edge-case suite for
#    the >52-level warning) produces genuinely R-matching output for an
#    ordinary, small (<=52-level) factor too, independent of any real
#    dataset's variable-selection behavior.
# ---------------------------------------------------------------------------

def test_labels_rpart_synthetic_small_categorical_fixture():
    from _r_rpart_helpers import make_synthetic_categorical_fit, r_labels_result

    py_obj, r_expr = make_synthetic_categorical_fit(
        num_levels=6, left_levels=[0, 2, 4], var_name="X"
    )
    r_labs = r_labels_to_python(r_labels_result(r_expr, generic=False))
    py_labs = labels_rpart(py_obj)
    assert py_labs == r_labs
    # minlength defaults to 1 -> single letters, position-indexed into the
    # level list (letter "a" for the 1st level, "b" for the 2nd, ...), with
    # no separator ("ace"/"bdf", not "a,c,e"/"b,d,f").
    assert py_labs == ["root", "X=ace", "X=bdf"]
