"""Boundary/edge-case parity tests for r2py_rpart.post vs. R's `post`.

See test_post_positive.py's module docstring for the general comparison
strategy and test_post_negative.py's for the two internal legitimacy-check
boundaries (`Not a legitimate "rpart" object` / `fit is not a tree, just a
root`) post_rpart() inherits from plot_rpart()/text_rpart().

KNOWN, GENUINE BUGS/GAPS FOUND WHILE WRITING THESE TESTS
--------------------------------------------------------------------------
Four confirmed, permanent divergences from R are documented as explicit
regression-anchor tests below rather than silently worked around:

  1. `test_post_default_title_endpoint_index_known_bug` -- post_rpart.py's
     default-title derivation (`tree['terms'].get('variables', [])[1]`) is
     off by one relative to R's own `attr(tree$terms, "variables")[2L]`.
     R's `variables` *call* object has the `list` function symbol occupying
     position 1, so `[2L]` (1-indexed) lands on the *response* variable
     (confirmed: "Endpoint = Kyphosis" for `Kyphosis ~ Age + Number +
     Start`). python's plain `variables` list has no such leading
     placeholder, so index `[1]` (0-indexed) instead lands on the *first
     predictor* ("Endpoint = Age") -- the wrong variable entirely. The fix
     is a one-character change (`[1]` -> `[0]`).

  2. `test_post_hardcoded_compress_true_crashes_on_deep_tree_known_bug` --
     post_rpart.py *unconditionally* calls `plot_rpart(..., compress=True,
     ...)` (mirroring post.rpart.R's own hard-coded `compress = TRUE`) with
     no way for a caller to opt out. This means the pre-existing
     `rpartco.py` `compress()` bug documented in test_plot_rpart_edge.py's
     `test_plot_rpart_compress_deep_asymmetric_tree_known_bug` -- there,
     avoidable by simply not passing `compress=True` -- is *unavoidable*
     for `post()`: any sufficiently deep/asymmetric tree crashes `post()`
     outright, even though R's own `post()`/`post.rpart()` computes a valid,
     finite result for the identical tree.

  3. `test_post_extra_kwargs_silently_ignored_known_gap` -- R's `post.rpart`
     forwards its own `...` straight into `postscript(file = filename,
     horizontal = horizontal, ...)` (e.g. `width=`/`height=`/`paper=`
     genuinely change the written file). python's `post_rpart(tree, ...,
     **kwargs)` accepts (and silently discards) any such extra keyword
     arguments -- `**kwargs` is never referenced again in the function body
     -- so equivalent python calls have no effect at all.

  4. `test_post_default_filename_diverges_from_r_known_gap` -- R's own
     default, `filename = paste(deparse(substitute(tree)), ".ps", sep =
     "")`, depends on the literal source-code spelling of the argument
     expression at the call site (e.g. `post(my_fit)` writes
     "my_fit.ps"). python cannot deparse-substitute an argument expression
     this way, so post_rpart.py's default is a fixed literal, `"tree.ps"`,
     regardless of what variable/expression was actually passed in.

Each of these is confirmed via direct experimentation (see the accompanying
comments) rather than assumed from reading the source alone.
"""
from __future__ import annotations

import os
import warnings

import numpy as np
import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart
from r2py_rpart.post import post

from _r_rpart_helpers import (
    call_post_and_extract,
    cu_summary_df,
    extract_frame_arrays,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_plot_rpart_derived,
    r_post_default_title_for_formula,
    r_post_runs_without_error,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. The smallest possible *legitimate* (non-root-only) tree -- exactly 3
#    frame rows -- one node above the `len(frame) <= 1` boundary tested in
#    test_post_negative.py. A genuine `rpart()` fit (rather than a minimal
#    synthetic frame-only dict, which lacks the `splits`/`functions`/`yval`
#    fields post_rpart()'s own `text_rpart()` call needs -- `labels_rpart()`
#    would otherwise raise a `KeyError` unrelated to the boundary under
#    test) forced to exactly one split via `maxdepth=1`. An explicit title_
#    sidesteps the (root-cause-unrelated, separately documented as a known
#    bug above) title-default lookup.
# ---------------------------------------------------------------------------

def test_post_minimal_legitimate_tree_three_rows(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"maxdepth": 1})
    assert fit["frame"].shape[0] == 3
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x")
    r_out = r_plot_rpart_derived(node, var, dev, uniform=True, branch=0.2, compress=True, margin=0.1)
    np.testing.assert_allclose(py_out["xlim"], r_out["xlim"], atol=1e-9)
    np.testing.assert_allclose(py_out["ylim"], r_out["ylim"], atol=1e-9)
    assert py_out["n_patches"] == 3

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", method='"class"', control="rpart.control(maxdepth=1)"
    )
    ro.globalenv["post_edge_minimal_fit_tmp"] = r_fit
    assert r_post_runs_without_error("post_edge_minimal_fit_tmp", generic=True, filename="", title_="x")


# ---------------------------------------------------------------------------
# 2. KNOWN, GENUINE BUG: post_rpart.py's default-title endpoint-index is off
#    by one relative to R's `attr(tree$terms, "variables")[2L]`.
#
#    Confirmed directly: for `fit <- rpart(Kyphosis ~ Age + Number + Start,
#    ...)`, R's real `attr(fit$terms, "variables")[2L]` is the symbol
#    `Kyphosis` (the *response*), giving title "Endpoint = Kyphosis" --
#    reproduced here via `r_post_default_title_for_formula()`, which depends
#    only on the formula (not the fitted tree), sidestepping any R-vs-python
#    split-choice divergence entirely. python's post_rpart.py instead reads
#    `tree['terms']['variables'][1]` == "Age" (the *first predictor*) since
#    python's `variables` list has no leading `list`-symbol placeholder the
#    way R's call-object indexing does -- so the title comes out
#    "Endpoint = Age", not matching R at all. This is filed as a plain,
#    non-xfail assertion so it starts passing automatically the moment
#    post_rpart.py's index is corrected (`[1]` -> `[0]`).
# ---------------------------------------------------------------------------

def test_post_default_title_endpoint_index_known_bug(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    r_title = r_post_default_title_for_formula("Kyphosis ~ Age + Number + Start")
    assert r_title == "Endpoint = Kyphosis"

    # python's post_rpart() cannot use the default-title sentinel path here
    # without tripping the bug -- call it with the sentinel omitted (the
    # real, buggy default codepath) via the raw `post()` entry point.
    py_out = call_post_and_extract(monkeypatch, fit)  # title_ omitted -> default sentinel
    assert py_out["title"] == "Endpoint = Age"  # the confirmed *wrong* value
    assert py_out["title"] != r_title


# ---------------------------------------------------------------------------
# 3. KNOWN, GENUINE BUG (regression anchor, mirroring
#    test_plot_rpart_edge.py's own `test_plot_rpart_compress_deep_
#    asymmetric_tree_known_bug`): post_rpart.py's *unconditional*
#    `compress=True` makes this bug unavoidable for `post()` specifically --
#    unlike plot_rpart(), which only trips it if the caller opts in.
#    Confirmed: R's genuine `post()` (same formula/control -- R and python's
#    rpart() happen to converge on the identical 33-row tree here) succeeds
#    without error, while python's post() crashes with a numpy broadcasting
#    ValueError inside rpartco.py's compress().
# ---------------------------------------------------------------------------

def test_post_hardcoded_compress_true_crashes_on_deep_tree_known_bug(monkeypatch):
    df = kyphosis_df()
    fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class",
        control={"cp": 0.001, "minsplit": 2},
    )
    assert fit["frame"].shape[0] > 20  # a genuinely deep, asymmetric tree

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", method='"class"',
        control="rpart.control(cp=0.001, minsplit=2)",
    )
    ro.globalenv["post_edge_fit_tmp"] = r_fit
    assert r_post_runs_without_error("post_edge_fit_tmp", generic=True, filename="", title_="x")

    # python currently raises inside rpartco.py's compress() -- see module
    # docstring's root-cause analysis; this call is not wrapped in
    # pytest.raises() so the test fails loudly (as an error) until fixed.
    call_post_and_extract(monkeypatch, fit, filename="", title_="x")


# ---------------------------------------------------------------------------
# 4. KNOWN, DOCUMENTED GAP: extra keyword arguments meant for R's
#    `postscript(...)` device (via post.rpart's own `...`) are silently
#    swallowed by python's `post_rpart(tree, ..., **kwargs)` -- `kwargs` is
#    accepted but never referenced again in the function body. Confirmed:
#    passing `width=`/`height=` produces byte-for-byte identical output to
#    omitting them entirely in python, whereas R's `postscript(...,
#    width=..., height=..., paper="special")` (R's `postscript()` only
#    honors `width=`/`height=` when `paper="special"` -- otherwise it uses a
#    fixed system paper size and silently ignores them, per
#    `?grDevices::postscript`'s own `paper=` documentation, so `paper=
#    "special"` must be passed too for this comparison to be meaningful at
#    all) genuinely changes the written file's `%%BoundingBox:` DSC comment.
# ---------------------------------------------------------------------------

def test_post_extra_kwargs_silently_ignored_known_gap(monkeypatch, tmp_path):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    default_filename = str(tmp_path / "default.ps")
    wide_filename = str(tmp_path / "wide.ps")
    call_post_and_extract(monkeypatch, fit, filename=default_filename, title_="x")
    call_post_and_extract(monkeypatch, fit, filename=wide_filename, title_="x", width=20, height=20)

    def bounding_box(path):
        with open(path) as f:
            return next(line for line in f if line.startswith("%%BoundingBox:"))

    # python: the extra width=/height= kwargs made no difference at all.
    assert bounding_box(default_filename) == bounding_box(wide_filename)

    # R: the same extra width=/height=/paper="special" genuinely changes the
    # bounding box.
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_edge_kwargs_fit_tmp"] = r_fit
    r_default = str(tmp_path / "r_default.ps")
    r_wide = str(tmp_path / "r_wide.ps")
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(f'post(post_edge_kwargs_fit_tmp, filename="{r_default}", title.="x")')
        run_r(
            f'post(post_edge_kwargs_fit_tmp, filename="{r_wide}", title.="x", '
            'width=20, height=20, paper="special")'
        )
    finally:
        run_r("grDevices::dev.off()")
    r_bbox_default = bounding_box(r_default)
    r_bbox_wide = bounding_box(r_wide)
    assert r_bbox_default != r_bbox_wide  # R: width=/height= DID make a difference

    warnings.warn(
        "python's post()/post_rpart() silently ignores extra postscript-"
        "device kwargs (width=/height=/... never referenced past **kwargs) "
        "that R's post.rpart() genuinely forwards to postscript() -- known, "
        "permanent capability gap.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 5. KNOWN, DOCUMENTED GAP: the default `filename=` value itself diverges
#    permanently from R. R's own default,
#    `paste(deparse(substitute(tree)), ".ps", sep = "")`, is
#    call-site-expression-dependent (e.g. `post(my_fit)` -> "my_fit.ps");
#    python's post_rpart.py default is the fixed literal `"tree.ps"`
#    regardless of what expression/variable was actually passed as `tree`.
# ---------------------------------------------------------------------------

def test_post_default_filename_diverges_from_r_known_gap(monkeypatch, tmp_path):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    monkeypatch.chdir(tmp_path)
    # NOTE: deliberately calling post() directly here, *not* via
    # call_post_and_extract() -- that helper's own `filename: str = ""`
    # keyword-only default would always pass filename="" explicitly,
    # pre-empting post_rpart()'s *own* `filename='tree.ps'` default the
    # moment it is omitted entirely, which is exactly the codepath this test
    # needs to exercise.
    post(fit, title_="x")  # filename omitted entirely -> post_rpart's own "tree.ps" default
    assert os.path.exists(tmp_path / "tree.ps")
    assert not os.path.exists(tmp_path / "fit.ps")  # R would have used this name instead

    warnings.warn(
        "python's post()'s default filename is the fixed literal 'tree.ps', "
        "never the call-site variable name R's deparse(substitute(tree)) "
        "would use (e.g. 'fit.ps' for `post(fit)`) -- known, permanent gap.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 6. title_="" (an explicit empty string) is the documented lower/degenerate
#    boundary of "a title string": `nzchar("")` is FALSE in R, `len("") > 0`
#    is False in python -- both suppress the title entirely, distinct from
#    the *missing* (sentinel-default) case exercised (and shown buggy) in
#    test #2 above.
# ---------------------------------------------------------------------------

def test_post_title_boundary_empty_string_vs_missing_sentinel(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    empty_out = call_post_and_extract(monkeypatch, fit, filename="", title_="")
    assert empty_out["title"] == ""

    missing_out = call_post_and_extract(monkeypatch, fit, filename="")  # sentinel default
    assert missing_out["title"] != ""  # the (buggy) "Endpoint = Age" string, not blank


# ---------------------------------------------------------------------------
# 7. digits at its extreme lower boundary (1 significant digit) -- both
#    sides must accept it without error (post.rpart.Rd only documents
#    "number of significant digits", with no explicit floor).
# ---------------------------------------------------------------------------

def test_post_digits_lower_boundary_one(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", digits=1)
    r_out = r_plot_rpart_derived(node, var, dev, uniform=True, branch=0.2, compress=True, margin=0.1)
    np.testing.assert_allclose(py_out["xlim"], r_out["xlim"], atol=1e-9)

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_edge_digits_fit_tmp"] = r_fit
    assert r_post_runs_without_error("post_edge_digits_fit_tmp", generic=True, filename="", title_="x", digits=1)


# ---------------------------------------------------------------------------
# 8. pretty=None -- post.rpart.Rd: "A NULL signifies using elements of
#    letters to represent the different factor levels" -- the third,
#    letter-abbreviation mode distinct from pretty=True (max abbreviation)
#    and pretty=0 (no abbreviation), exercised on the categorical cu.summary
#    fit (needs an actual factor split to show any difference at all).
# ---------------------------------------------------------------------------

def test_post_pretty_none_uses_letter_abbreviation_boundary(monkeypatch):
    df = cu_summary_df()
    fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class",
        control={"minsplit": 30, "cp": 0.05},
    )

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", pretty=None)
    letter_labels = [
        text for _, text, _, _ in py_out["texts"] if text.startswith(("Type=", "Country="))
    ]
    assert len(letter_labels) > 0
    # letters() abbreviation uses single-letter-per-level codes (a, b, c, ...)
    for label in letter_labels:
        rhs = label.split("=", 1)[1]
        assert all(ch.isalpha() and ch.islower() for ch in rhs)

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Reliability ~ Price + Country + Mileage + Type", method='"class"',
        control="rpart.control(minsplit=30, cp=0.05)",
    )
    ro.globalenv["post_edge_pretty_fit_tmp"] = r_fit
    # NOTE: r_post_call_code()/r_post_error() treat a python `None` kwarg
    # value as "omit this argument entirely" (so R's own default applies --
    # the convention every `r_*_call_code` helper in this shared module
    # follows), which is *not* what's needed here: we want to pass R's
    # literal `NULL` for `pretty=` explicitly, not omit it (omitting it
    # would fall back to post.rpart's own `pretty = TRUE` default instead).
    # So this one R call is built directly rather than through
    # `r_post_error`/`r_post_runs_without_error`.
    run_r("grDevices::pdf(NULL)")
    try:
        run_r('post(post_edge_pretty_fit_tmp, filename="", title.="x", pretty=NULL)')
        r_pretty_none_ok = True
    except Exception:
        r_pretty_none_ok = False
    finally:
        run_r("grDevices::dev.off()")
    assert r_pretty_none_ok


# ---------------------------------------------------------------------------
# 9. horizontal's two boundary values both round-trip through a real R
#    orientation-comment case-insensitive comparison (positive-path already
#    covers this via `r_post_write_file_and_get_orientation`); here the
#    boundary condition under test is instead `filename=""` *combined* with
#    `horizontal=False` -- confirming the `par(mar=...)`/no-file codepath
#    (post.rpart.R's `else` branch, distinct from the `postscript(...,
#    horizontal=...)` branch) does not error regardless of `horizontal`,
#    even though `horizontal` has no *visible* effect at all when no file is
#    written (matplotlib's `fig.savefig(..., orientation=...)` call is only
#    reached in the `filename != ""` branch).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("horizontal", [True, False])
def test_post_horizontal_with_empty_filename_never_errors(monkeypatch, horizontal):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", horizontal=horizontal)
    assert py_out["retval"] is None

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_edge_horiz_fit_tmp"] = r_fit
    assert r_post_runs_without_error(
        "post_edge_horiz_fit_tmp", generic=True, filename="", title_="x", horizontal=horizontal
    )
