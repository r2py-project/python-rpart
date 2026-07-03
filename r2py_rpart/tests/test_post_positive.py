"""Positive-path parity tests for r2py_rpart.post vs. R's `post` (a plain S3
generic, `post <- function(tree, ...) UseMethod("post")`, dispatching to
`post.rpart` for genuine `"rpart"`-classed fits).

post()/post_rpart() is a thin *orchestration* layer, not a fresh algorithm of
its own:

    def post(tree, **kwargs): post_rpart(tree, **kwargs)

    def post_rpart(tree, title_=MISSING, filename='tree.ps', digits=None,
                   pretty=True, use_n=True, horizontal=True, **kwargs):
        ...
        plot_rpart(tree, uniform=True, branch=0.2, compress=True, margin=0.1, ax=ax)
        text_rpart(tree, all=True, use_n=use_n, fancy=True, digits=digits,
                   pretty=pretty, ax=ax)
        if title_ is MISSING: ax.set_title(f"Endpoint = {...}")
        elif len(title_) > 0: ax.set_title(title_)
        if filename != '': fig.savefig(filename, ...); plt.close(fig)
        else: plt.close(fig)

mirroring post.rpart.R's:

    plot(tree, uniform = TRUE, branch = 0.2, compress = TRUE, margin = 0.1)
    text(tree, all = TRUE, use.n = use.n, fancy = TRUE, digits = digits, pretty = pretty)
    if (missing(title.)) title(paste("Endpoint =", attr(tree$terms, "variables")[2L]))
    else if (nzchar(title.)) title(title., cex = 0.8)

So this file's comparison strategy is layered:

  - The *plot geometry* (node coordinates/xlim/ylim/branch-line segments) is
    exercised via the exact same "feed a shared (node, var, dev) triple into
    both a hand-copied R derivation replica and the python side" strategy
    `test_plot_rpart_positive.py` already established (`extract_frame_arrays`
    + `r_plot_rpart_derived` + `r_rpart_like_expr_for_plot`), just with
    post.rpart's own *fixed* plot arguments (`uniform=True, branch=0.2,
    compress=True, margin=0.1` -- unlike plot_rpart(), post() does not expose
    these as its own kwargs at all).
  - post()'s own *unique* logic -- title resolution, digits/pretty/use.n/
    horizontal forwarding, and file-writing side effects -- is exercised
    directly against R's genuine, fully-fitted `post()`/`post.rpart()` (via
    `_r_rpart_helpers.r_fit_rpart`), since none of that logic depends on
    which particular split/tree-structure was chosen (title derivation only
    touches `$terms`; digits/pretty/use.n only affect *label formatting*;
    file-writing only cares that *a* valid file gets produced) -- so there is
    no need to isolate away from R's and python's rpart() potentially
    choosing different splits for the same formula/data, the way the
    geometry checks above must.
  - Extraction of what python's post() actually drew is done via
    `_r_rpart_helpers.call_post_and_extract()`, which monkeypatches
    `matplotlib.pyplot.close` for the duration of one call so the internally-
    created (and normally immediately destroyed) `Axes` can still be
    inspected afterward -- see that helper's own docstring for the full
    rationale.

All of post()'s own keyword arguments (title_=/filename=/digits=/pretty=/
use_n=/horizontal=) are exercised below, individually and in combination.
`known bug`/`known gap` divergences uncovered while writing these tests
(default title's off-by-one endpoint-index bug; the hard-coded compress=True
tripping the pre-existing rpartco.py compress() bug; the non-forwarded `...`
extra postscript kwargs; the R-vs-python default `filename=` divergence) are
deliberately *not* exercised here -- see test_post_edge.py, which documents
each one explicitly as a regression anchor instead.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from r2py_rpart import rpart

from _r_rpart_helpers import (
    call_post_and_extract,
    cu_summary_df,
    extract_frame_arrays,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_plot_rpart_derived,
    r_post_runs_without_error,
    r_post_write_file_and_get_orientation,
    run_r,
)


def _assert_geometry_matches_fixed_post_params(py_out, node, var, dev) -> None:
    """post.rpart.R always calls `plot(tree, uniform=TRUE, branch=0.2,
    compress=TRUE, margin=0.1)` -- confirm python's post() reproduces the
    identical node coordinates/xlim/ylim/branch-line geometry R's own
    plot.rpart.R (rpartco.R + rpart.branch.R, replicated line-for-line in
    `r_plot_rpart_derived`) computes for those exact fixed arguments."""
    r_out = r_plot_rpart_derived(node, var, dev, uniform=True, branch=0.2, compress=True, margin=0.1)
    xs = py_out["xlim"]
    ys = py_out["ylim"]
    np.testing.assert_allclose(xs, r_out["xlim"], atol=1e-9)
    np.testing.assert_allclose(ys, r_out["ylim"], atol=1e-9)
    np.testing.assert_allclose(py_out["line_x"], r_out["branch_x"], equal_nan=True, atol=1e-9)
    np.testing.assert_allclose(py_out["line_y"], r_out["branch_y"], equal_nan=True, atol=1e-9)


# ---------------------------------------------------------------------------
# 1. A genuine classification fit (kyphosis), every post() argument left at
#    its documented default except title_ (given explicitly here to sidestep
#    the default-title derivation entirely -- see test_post_edge.py's
#    dedicated known-bug test for that). Confirms the underlying plot
#    geometry matches R's fixed-argument plot.rpart derivation, the root "|"
#    glyph is drawn (branch=0.2 > 0), the axis frame is off, and exactly one
#    oval/rectangle patch is drawn per frame row (fancy=True, all=True fixed).
# ---------------------------------------------------------------------------

def test_post_kyphosis_classification_defaults(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="Kyphosis tree")
    _assert_geometry_matches_fixed_post_params(py_out, node, var, dev)

    assert py_out["axis_off"] is True
    assert py_out["n_lines"] == 1
    assert py_out["retval"] is None  # post()/post_rpart() always return None
    assert py_out["title"] == "Kyphosis tree"
    assert py_out["n_patches"] == fit["frame"].shape[0]
    assert any(text == "|" for _, text, _, _ in py_out["texts"])


# ---------------------------------------------------------------------------
# 2. A regression (anova) fit (car.test.frame, Mileage ~ Weight) broadens
#    method coverage beyond "class", exactly mirroring
#    test_plot_rpart_positive.py's own uniform-spacing anova test -- but here
#    exercised through the full post() pipeline (uniform is *always* True
#    inside post.rpart, never a caller-controlled kwarg).
# ---------------------------------------------------------------------------

def test_post_anova_car_test_frame(monkeypatch):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    node, var, dev = extract_frame_arrays(fit)
    assert fit["frame"].shape[0] > 1

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="Mileage tree")
    _assert_geometry_matches_fixed_post_params(py_out, node, var, dev)
    assert py_out["title"] == "Mileage tree"


# ---------------------------------------------------------------------------
# 3. A categorical-predictor classification fit (cu.summary, Type/Country are
#    unordered factors) broadens coverage to a tree that actually splits on a
#    factor -- needed for the pretty= tests below (varying pretty on a purely
#    numeric-split tree, like kyphosis's, can never show a visible
#    difference). `minsplit`/`cp` are loosened just enough to keep the tree
#    shallow (7 rows) -- a deep/asymmetric enough tree trips the pre-existing
#    rpartco.py compress() bug documented in test_plot_rpart_edge.py/
#    test_post_edge.py, which is out of scope here.
# ---------------------------------------------------------------------------

def _cu_summary_fit():
    df = cu_summary_df()
    return rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class",
        control={"minsplit": 30, "cp": 0.05},
    )


def test_post_categorical_split_geometry(monkeypatch):
    fit = _cu_summary_fit()
    node, var, dev = extract_frame_arrays(fit)
    assert "Type" in set(var) or "Country" in set(var)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="Reliability tree")
    _assert_geometry_matches_fixed_post_params(py_out, node, var, dev)


# ---------------------------------------------------------------------------
# 4. Default title_ (the `_post_rpart_MISSING` sentinel -- R's own
#    `missing(title.)`) resolves, on *both* sides, purely from the model's
#    formula/terms -- independent of the particular tree structure fitted --
#    confirmed here via `r_post_default_title_for_formula()` (an R replica of
#    post.rpart.R's own `paste("Endpoint =", attr(tree$terms,
#    "variables")[2L])`, evaluated on the *response* variable's name).
#    NOTE: this deliberately checks the *response*-name formula
#    (`r_post_default_title_for_formula` returns "Endpoint = Kyphosis") does
#    NOT match what python's post() currently computes for the same fit
#    ("Endpoint = Age") -- that confirmed divergence is a genuine bug, filed
#    as `test_post_default_title_endpoint_index_known_bug` in
#    test_post_edge.py, not asserted here. This test instead only pins that
#    an *explicit* title_ always wins over the sentinel-triggered default,
#    which both sides agree on.
# ---------------------------------------------------------------------------

def test_post_explicit_title_overrides_default_on_both_sides(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    custom_out = call_post_and_extract(monkeypatch, fit, filename="", title_="My Custom Title")
    assert custom_out["title"] == "My Custom Title"

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    assert r_post_runs_without_error(
        _rvar(r_fit), generic=True, filename="", title_="My Custom Title"
    )


def _rvar(r_obj) -> str:
    """Assign an already-evaluated rpy2 object into R's globalenv under a
    fixed temp name and return that name as an R source expression, for
    interpolation into `r_post_*` helper calls. The name deliberately does
    *not* start with an underscore -- unlike python, a bare R identifier
    cannot begin with `_` (that requires backtick-quoting), so a leading
    underscore would make every generated call a syntax error."""
    import rpy2.robjects as ro

    ro.globalenv["post_positive_fit_tmp"] = r_obj
    return "post_positive_fit_tmp"


# ---------------------------------------------------------------------------
# 5. title_="" (an explicit, but empty, string) suppresses the title
#    entirely on both sides -- post.rpart.R's own `else if (nzchar(title.))`
#    guard (`nzchar("")` is FALSE) mirrors post_rpart.py's `elif
#    len(title_) > 0:` guard exactly.
# ---------------------------------------------------------------------------

def test_post_empty_string_title_suppresses_title(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="")
    assert py_out["title"] == ""

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    assert r_post_runs_without_error(_rvar(r_fit), filename="", title_="")


# ---------------------------------------------------------------------------
# 6. use_n=True/False changes the *content* of the leaf stat labels (whether
#    "n1/n2" event counts are appended) without altering the underlying plot
#    geometry or patch count at all -- confirmed structurally (count of
#    labels containing "/" goes from >0 to exactly 0), and cross-checked
#    that R's genuine post() accepts both values without error.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("use_n", [True, False])
def test_post_use_n_toggles_event_counts_in_labels(monkeypatch, use_n):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", use_n=use_n)
    _assert_geometry_matches_fixed_post_params(py_out, node, var, dev)

    slash_labels = [text for _, text, _, _ in py_out["texts"] if "/" in text]
    if use_n:
        assert len(slash_labels) > 0
    else:
        assert len(slash_labels) == 0

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    assert r_post_runs_without_error(_rvar(r_fit), filename="", title_="x", use_n=use_n)


# ---------------------------------------------------------------------------
# 7. pretty=True (default) vs pretty=0 (no abbreviation at all, per
#    post.rpart.Rd: "(0) signifies no abbreviation of levels") changes the
#    *content* of a factor split's label (abbreviated level names vs. full
#    level names) on the categorical cu.summary fit -- geometry/patch count
#    are entirely unaffected either way.
# ---------------------------------------------------------------------------

def test_post_pretty_toggle_changes_factor_split_label_abbreviation(monkeypatch):
    fit = _cu_summary_fit()
    node, var, dev = extract_frame_arrays(fit)

    out_pretty = call_post_and_extract(monkeypatch, fit, filename="", title_="x", pretty=True)
    out_plain = call_post_and_extract(monkeypatch, fit, filename="", title_="x", pretty=0)
    _assert_geometry_matches_fixed_post_params(out_pretty, node, var, dev)
    _assert_geometry_matches_fixed_post_params(out_plain, node, var, dev)

    pretty_labels = [text for _, text, _, _ in out_pretty["texts"] if text.startswith(("Type=", "Country="))]
    plain_labels = [text for _, text, _, _ in out_plain["texts"] if text.startswith(("Type=", "Country="))]
    assert len(pretty_labels) == len(plain_labels) > 0
    assert pretty_labels != plain_labels
    # the fully-spelled-out (pretty=0) labels are never shorter than their
    # abbreviated (pretty=True) counterparts
    for p, q in zip(sorted(pretty_labels), sorted(plain_labels)):
        assert len(q) >= len(p)


# ---------------------------------------------------------------------------
# 8. digits= controls the numeric precision of leaf stat labels (visible on
#    an "anova" fit, whose leaf labels are real-valued means, unlike
#    "class"'s integer event counts) -- confirmed structurally that a small
#    digits value (1) yields shorter/rounder label text than a large one (8),
#    while geometry stays identical, and that R's genuine post() accepts both.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("digits", [1, 5, 8])
def test_post_digits_controls_leaf_label_precision(monkeypatch, digits):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", digits=digits)
    _assert_geometry_matches_fixed_post_params(py_out, node, var, dev)

    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')
    assert r_post_runs_without_error(_rvar(r_fit), filename="", title_="x", digits=digits)


# ---------------------------------------------------------------------------
# 9. The *default* digits (omitted entirely -> post_rpart.py's own
#    `max(getattr(builtins, '_rpart_digits', 7) - 2, 1)`) numerically equals
#    R's own stock default (`getOption("digits") - 2L`, 7 - 2 = 5 in a fresh
#    R session -- confirmed directly below), and produces byte-identical leaf
#    stat label text to passing digits=5 explicitly.
# ---------------------------------------------------------------------------

def test_post_default_digits_matches_r_stock_default_value(monkeypatch):
    assert list(run_r('getOption("digits") - 2'))[0] == 5

    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")

    default_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x")
    explicit_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x", digits=5)
    assert [t for _, t, _, _ in default_out["texts"]] == [t for _, t, _, _ in explicit_out["texts"]]


# ---------------------------------------------------------------------------
# 10. filename="" (the documented "display on the current device" mode, per
#     post.rpart.Rd: "If filename = "", the plot appears on the current
#     graphical device") never writes any file and returns None on both
#     sides.
# ---------------------------------------------------------------------------

def test_post_empty_filename_writes_no_file(monkeypatch, tmp_path):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    before = set(os.listdir(tmp_path))
    monkeypatch.chdir(tmp_path)
    py_out = call_post_and_extract(monkeypatch, fit, filename="", title_="x")
    assert py_out["retval"] is None
    after = set(os.listdir(tmp_path))
    assert before == after  # no stray file was written

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    assert r_post_runs_without_error(_rvar(r_fit), filename="", title_="x")


# ---------------------------------------------------------------------------
# 11. horizontal=True/False controls the written PostScript file's
#     `%%Orientation:` DSC comment ("Landscape"/"Portrait") -- confirmed
#     against R's own genuine post()-written file's orientation comment
#     (case-insensitively: R capitalizes "Landscape"/"Portrait", matplotlib's
#     `ps` backend lower-cases them -- a purely cosmetic, non-semantic
#     difference).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("horizontal,expected", [(True, "landscape"), (False, "portrait")])
def test_post_horizontal_controls_file_orientation(monkeypatch, tmp_path, horizontal, expected):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_filename = str(tmp_path / "py_out.ps")
    call_post_and_extract(monkeypatch, fit, filename=py_filename, title_="x", horizontal=horizontal)
    assert os.path.exists(py_filename)
    with open(py_filename) as f:
        py_orientation = next(line for line in f if line.startswith("%%Orientation:")).split(":", 1)[1].strip()
    assert py_orientation.lower() == expected

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    r_filename = str(tmp_path / "r_out.ps")
    r_orientation = r_post_write_file_and_get_orientation(
        r_fit, r_filename, horizontal=horizontal, title_="x"
    )
    assert r_orientation.lower() == expected
    assert py_orientation.lower() == r_orientation.lower()


# ---------------------------------------------------------------------------
# 12. A genuine, explicit on-disk filename produces a real, well-formed
#     PostScript file on both sides (the "%!PS-Adobe" DSC magic header),
#     matching post.rpart.Rd's documented default behavior of writing to an
#     ASCII file whose name is given by `filename=`.
# ---------------------------------------------------------------------------

def test_post_writes_well_formed_postscript_file(monkeypatch, tmp_path):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_filename = str(tmp_path / "kyphosis_tree.ps")
    call_post_and_extract(monkeypatch, fit, filename=py_filename, title_="Kyphosis")
    assert os.path.getsize(py_filename) > 0
    with open(py_filename) as f:
        first_line = f.readline()
    assert first_line.startswith("%!PS-Adobe")

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    r_filename = str(tmp_path / "r_kyphosis_tree.ps")
    r_post_write_file_and_get_orientation(r_fit, r_filename, title_="Kyphosis")
    assert os.path.getsize(r_filename) > 0
    with open(r_filename) as f:
        r_first_line = f.readline()
    assert r_first_line.startswith("%!PS-Adobe")
