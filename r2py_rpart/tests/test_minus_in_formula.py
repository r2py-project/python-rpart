"""Python translation of rpart/tests/minus_in_formula.R.

Original R script
-----------------
    ## https://github.com/bethatkinson/rpart/issues/7

    library(rpart)
    mtcars2 <- mtcars

    mtcars2$gear <- factor(mtcars2$gear)
    mtcars2$carb <- factor(mtcars2$carb)

    set.seed(10)
    rp1 <- rpart(mpg ~ . - gear, data = mtcars2)
    set.seed(10)
    rp2 <- rpart(mpg ~ ., data = mtcars2[names(mtcars2) != "gear"])

    all.equal(rp1[setdiff(names(rp1), c("call", "terms"))],
              rp2[setdiff(names(rp2), c("call", "terms"))], check.attributes=FALSE)


    set.seed(10)
    rp3 <- rpart(mpg ~ . - gear - carb, data = mtcars2)
    set.seed(10)
    rp4 <- rpart(mpg ~ ., data = mtcars2[setdiff(names(mtcars2), c("gear", "carb"))])

    all.equal(rp3[setdiff(names(rp3), c("call", "terms"))],
              rp4[setdiff(names(rp4), c("call", "terms"))], check.attributes=FALSE)

This test (linked from https://github.com/bethatkinson/rpart/issues/7) checks
that a formula's right-hand side may combine ``.`` ("every other column of
`data`") with one or more ``- name`` exclusions -- e.g. ``mpg ~ . - gear`` --
and that fitting with such a formula produces *exactly* the same tree as
fitting ``mpg ~ .`` against a `data` frame from which the excluded column(s)
have already been dropped. It exercises this for both a single exclusion
(``. - gear``) and two exclusions (``. - gear - carb``).

Mapping to Python
-----------------
``rpart()``'s formula parser (``r2py_rpart/model_frame_rpart.py::
_parse_formula_terms``) previously supported only ``"y ~ ."`` (bare dot) or
plain ``"y ~ x1 + x2"`` term lists -- a right-hand side mixing ``.`` with a
``"- name"`` exclusion, such as ``"mpg ~ . - gear"``, was rejected (it was
treated as a single malformed term literally named ``". - gear"`` and raised
``KeyError: "variable(s) ['. - gear'] not found in data"``). This is a real
gap relative to R (whose ``terms()``/``model.frame()`` natively support
``.``/``-`` combination in formulas -- see the "If a formula contains
'. -zed' on the right hand side..." comment in ``rpart.R``), so
``_parse_formula_terms`` was extended with a small top-level ``+``/``-``
tokenizer (``_tokenize_rhs``): each token's leading sign determines whether
its expansion (``.`` -> all remaining data columns; a bare name -> that one
column) is *added to* or *removed from* the accumulated term list, exactly
mirroring R's formula ``+``/``-`` operators. ``"mpg ~ . - gear"`` and
``"mpg ~ . - gear - carb"`` are now parsed correctly and used directly below,
with no formula rewriting needed on the Python side.

``rp1[setdiff(names(rp1), c("call", "terms"))]`` -> the R fit object (a list)
minus its ``call``/``terms`` entries. The Python ``rpart()`` return value is
a dict with a directly analogous set of keys; we compare every key except
``"call"``/``"terms"`` (dropped for the same reason as in R: ``call`` records
the two formulas verbatim -- textually different even though semantically
equivalent -- and ``terms`` records formula/term metadata, not fitted
results) and except ``"functions"`` (a dict of Python closures created fresh
per-fit purely to dispatch summary/print/text formatting for the "anova"
method; comparing closure objects for equality is meaningless in Python just
as comparing R's analogous method-dispatch info would be, and R's
``all.equal`` on the raw ``rp$functions``-equivalent internal fields is not
part of what this test is probing). ``check.attributes=FALSE`` in the R call
just means R's ``all.equal`` should ignore attribute (name/dimname)
mismatches and only compare values -- the Python comparisons below already
work value-by-value (DataFrame ``.equals``/``np.allclose`` on the underlying
arrays, dict value-by-value comparison), so no extra accommodation is needed
for that flag.

``mtcars`` dataset
------------------
R's built-in ``datasets::mtcars`` (32 cars x 11 numeric columns: mpg, cyl,
disp, hp, drat, wt, qsec, vs, am, gear, carb) is not bundled with any common
Python package. It was exported once from R (via
``write.csv(mtcars, "mtcars.csv", row.names=TRUE)``, preserving the original
row names/car names as the first column, exactly matching what ``mtcars``
looks like in an R session) to ``r2py_rpart/tests/data/mtcars.csv`` and is
loaded from there with ``pandas.read_csv(..., index_col=0)``, avoiding a
live/runtime R dependency for the Python test suite while using the exact
same data values, row order, and row names as the original R script's
``mtcars``.

``factor(mtcars2$gear)`` / ``factor(mtcars2$carb)`` -> ``pandas.Categorical``:
R's ``factor()`` on a numeric column sorts the distinct values to form the
levels (ascending numeric order); ``pandas.Categorical(...)`` with no
``categories=`` argument does the same (sorted-unique-value levels), so a
direct ``pd.Categorical(mtcars2["gear"])`` assignment reproduces R's factor
coding exactly.

``mtcars2[names(mtcars2) != "gear"]`` / ``mtcars2[setdiff(names(mtcars2),
c("gear", "carb"))]`` -> column selection dropping one/two named columns
while preserving the original column order; the direct Python translation is
a list comprehension over ``mtcars2.columns`` excluding the given name(s),
used to column-index the DataFrame (``mtcars2[[c for c in mtcars2.columns if
c not in {...}]]``), which preserves order exactly like R's logical/setdiff
column subsetting here (``setdiff`` on character vectors preserves the order
of the first argument's remaining elements, matching ``names(mtcars2)``
order).

``set.seed(10)``
-----------------
``rpart()`` only consumes random draws for cross-validation grouping
(``xgroups``), and both members of each pair below are fit with rpart's
default ``xval=10``, so reproducing the exact same cross-validation folds
(hence identical ``cptable``/pruning behavior) for both fits in a pair
requires the same seed immediately before each call, exactly as the R script
does. Reproduced here via ``numpy.random.seed(10)``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from r2py_rpart import rpart

_MTCARS_CSV = Path(__file__).parent / "data" / "mtcars.csv"

# Keys present in the rpart() return dict that are excluded from the
# rp1-vs-rp2 / rp3-vs-rp4 comparison:
#  - "call"/"terms": mirrors R's `setdiff(names(rp), c("call", "terms"))`
#    (the two fits' formulas differ textually even though semantically
#    equivalent, and "terms" records formula/term metadata rather than
#    fitted results).
#  - "functions": a dict of fresh Python closures (summary/print/text
#    dispatch for the "anova" method) created independently per fit;
#    comparing closure objects is not meaningful in Python (nor would the
#    R analogue be part of what this test probes).
_EXCLUDED_KEYS = {"call", "terms", "functions"}


def _load_mtcars() -> pd.DataFrame:
    """Load the mtcars dataset exported from R (see module docstring)."""
    mtcars = pd.read_csv(_MTCARS_CSV, index_col=0)
    return mtcars


def _assert_rpart_fits_equal(fit1: dict, fit2: dict) -> None:
    """Python equivalent of:

        all.equal(fit1[setdiff(names(fit1), c("call", "terms"))],
                  fit2[setdiff(names(fit2), c("call", "terms"))],
                  check.attributes=FALSE)

    Compares every key of the two rpart() result dicts (other than the
    excluded keys above) for (near-)equality, matching the "check every
    remaining field of the fitted object" intent of the R all.equal() call.
    """
    keys1 = set(fit1.keys()) - _EXCLUDED_KEYS
    keys2 = set(fit2.keys()) - _EXCLUDED_KEYS
    assert keys1 == keys2, f"result keys differ: {keys1} vs {keys2}"

    for key in sorted(keys1):
        v1, v2 = fit1[key], fit2[key]
        if isinstance(v1, pd.DataFrame) or isinstance(v2, pd.DataFrame):
            assert isinstance(v1, pd.DataFrame) and isinstance(v2, pd.DataFrame)
            pd.testing.assert_frame_equal(v1, v2)
        elif isinstance(v1, pd.Series) or isinstance(v2, pd.Series):
            assert isinstance(v1, pd.Series) and isinstance(v2, pd.Series)
            pd.testing.assert_series_equal(v1, v2)
        elif isinstance(v1, np.ndarray) or isinstance(v2, np.ndarray):
            assert np.allclose(np.asarray(v1, dtype=float), np.asarray(v2, dtype=float)), (
                f"array mismatch for key {key!r}"
            )
        elif isinstance(v1, dict) and isinstance(v2, dict):
            assert v1 == v2, f"dict mismatch for key {key!r}: {v1} vs {v2}"
        else:
            assert v1 == v2, f"value mismatch for key {key!r}: {v1!r} vs {v2!r}"


def test_minus_in_formula_single_exclusion():
    """rp1 <- rpart(mpg ~ . - gear, data = mtcars2)
    rp2 <- rpart(mpg ~ ., data = mtcars2[names(mtcars2) != "gear"])
    all.equal(rp1[setdiff(...)], rp2[setdiff(...)], check.attributes=FALSE)
    """
    mtcars2 = _load_mtcars()
    ## mtcars2$gear <- factor(mtcars2$gear)
    ## mtcars2$carb <- factor(mtcars2$carb)
    mtcars2["gear"] = pd.Categorical(mtcars2["gear"])
    mtcars2["carb"] = pd.Categorical(mtcars2["carb"])

    ## set.seed(10)
    ## rp1 <- rpart(mpg ~ . - gear, data = mtcars2)
    np.random.seed(10)
    rp1 = rpart("mpg ~ . - gear", data=mtcars2)

    ## set.seed(10)
    ## rp2 <- rpart(mpg ~ ., data = mtcars2[names(mtcars2) != "gear"])
    np.random.seed(10)
    mtcars2_no_gear = mtcars2[[c for c in mtcars2.columns if c != "gear"]]
    rp2 = rpart("mpg ~ .", data=mtcars2_no_gear)

    ## Sanity: "gear" must not appear anywhere in either fitted tree's
    ## variable usage, since it was excluded from both formulas.
    assert "gear" not in rp1["frame"]["var"].to_numpy()
    assert "gear" not in rp2["frame"]["var"].to_numpy()

    ## all.equal(rp1[setdiff(names(rp1), c("call", "terms"))],
    ##           rp2[setdiff(names(rp2), c("call", "terms"))],
    ##           check.attributes=FALSE)
    _assert_rpart_fits_equal(rp1, rp2)


def test_minus_in_formula_double_exclusion():
    """rp3 <- rpart(mpg ~ . - gear - carb, data = mtcars2)
    rp4 <- rpart(mpg ~ ., data = mtcars2[setdiff(names(mtcars2), c("gear", "carb"))])
    all.equal(rp3[setdiff(...)], rp4[setdiff(...)], check.attributes=FALSE)
    """
    mtcars2 = _load_mtcars()
    mtcars2["gear"] = pd.Categorical(mtcars2["gear"])
    mtcars2["carb"] = pd.Categorical(mtcars2["carb"])

    ## set.seed(10)
    ## rp3 <- rpart(mpg ~ . - gear - carb, data = mtcars2)
    np.random.seed(10)
    rp3 = rpart("mpg ~ . - gear - carb", data=mtcars2)

    ## set.seed(10)
    ## rp4 <- rpart(mpg ~ ., data = mtcars2[setdiff(names(mtcars2), c("gear", "carb"))])
    np.random.seed(10)
    mtcars2_no_gear_carb = mtcars2[[c for c in mtcars2.columns if c not in ("gear", "carb")]]
    rp4 = rpart("mpg ~ .", data=mtcars2_no_gear_carb)

    ## Sanity: neither "gear" nor "carb" should appear in either fitted
    ## tree's variable usage.
    assert "gear" not in rp3["frame"]["var"].to_numpy()
    assert "carb" not in rp3["frame"]["var"].to_numpy()
    assert "gear" not in rp4["frame"]["var"].to_numpy()
    assert "carb" not in rp4["frame"]["var"].to_numpy()

    ## all.equal(rp3[setdiff(names(rp3), c("call", "terms"))],
    ##           rp4[setdiff(names(rp4), c("call", "terms"))],
    ##           check.attributes=FALSE)
    _assert_rpart_fits_equal(rp3, rp4)
