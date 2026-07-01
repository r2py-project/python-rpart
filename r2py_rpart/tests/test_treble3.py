"""Python translation of rpart/tests/treble3.R.

Original R script
------------------
    #
    # The treble test for classification trees
    #
    #
    library(rpart)
    set.seed(10)

    xgrp <- rep(1:10,length.out=nrow(cu.summary))
    carfit <- rpart(Country ~ Reliability + Price + Mileage + Type,
             method='class', data=cu.summary,
             control=rpart.control(xval=xgrp))

    carfit2 <- rpart(Country ~ Reliability + Price + Mileage + Type,
             method='class', data=cu.summary,
             weights=rep(3,nrow(cu.summary)),
             control=rpart.control(xval=xgrp))

    all.equal(carfit$frame$wt,    carfit2$frame$wt/3)
    all.equal(carfit$frame$dev,   carfit2$frame$dev/3)
    all.equal(carfit$frame[,5:7], carfit2$frame[,5:7])
    all.equal(carfit$frame$yval2[,12:21], carfit2$frame$yval2[,12:21])
    all.equal(carfit[c('where', 'csplit')],
          carfit2[c('where', 'csplit')])
    xx <- carfit2$splits
    xx[,'improve'] <- xx[,'improve'] / ifelse(xx[,5]> 0,1,3) # surrogate?
    all.equal(xx, carfit$splits)
    all.equal(as.vector(carfit$cptable),
          as.vector(carfit2$cptable%*% diag(c(1,1,1,1,sqrt(3)))))

    summary(carfit2)

This is the classification-tree analogue of ``treble.R``/``treble2.R``'s
weight-trebling tests: an informal, print-heavy R "tests" script (no
`testthat`/formal assertion failures -- every check is a bare
`all.equal()` call whose result is merely printed, never asserted, plus a
final bare `summary(carfit2)` auto-print with no check at all) that
exercises rpart()'s `weights=` argument on a **classification** (
`method='class'`) tree fit to the built-in `cu.summary` (Consumer
Reports car data) dataset, using the ordinary formula-string + `data=` +
`weights=` code path (unlike `treble.R`'s `Surv()`-response fits, which
needed a hand-built model frame). All ``all.equal()`` calls below were
verified against a live ``r2py_rpart`` run (see module-level probe used
while writing this file) to hold, and are translated into real
``assert`` statements.

``cu.summary`` dataset
------------------------
Reused verbatim from the fixture already exported by ``test_testall.py``'s
conversion (``r2py_rpart/tests/data/cu_summary.csv``, built from R's
built-in ``cu.summary`` data via ``write.csv``) per the task instructions,
rather than re-exporting it. The same ``_CU_COUNTRY_LEVELS`` (10-level
unordered factor), ``_CU_RELIABILITY_LEVELS`` (5-level *ordered* factor),
and ``_CU_TYPE_LEVELS`` (6-level unordered factor) level orders established
by ``test_testall.py`` are reproduced here via ``pandas.Categorical``.

Unlike ``test_testall.py``'s ``carfit`` (which predicts ``Reliability``),
this script's ``carfit``/``carfit2`` predict **``Country``** -- a 10-level
unordered factor -- from ``Reliability + Price + Mileage + Type``, so the
response has 10 classes (not 2 as in ``test_priors.py``'s ``stagec``
example), which matters for the ``yval2`` column-index translation below.

``xgrp <- rep(1:10,length.out=nrow(cu.summary))`` -> ``numpy.resize(numpy.
arange(1, 11), n)`` (the ``length.out=`` recycle-to-length idiom used
throughout this batch's conversions, e.g. ``test_treble2.py``).

``rpart.control(xval=xgrp)`` -> ``control={"xval": xgrp}``.

``weights=rep(3,nrow(cu.summary))`` -> ``weights=numpy.full(n, 3.0)``.

Frame-column translations (``frame[,5:7]`` and the surrogate-split
check on ``splits[,5]``)
--------------------------------------------------------------------------
``rpart.py``'s classification-method frame is built with columns, in
order: ``var``(1), ``n``(2), ``wt``(3), ``dev``(4), ``yval``(5),
``complexity``(6), ``ncompete``(7), ``nsurrogate``(8), then ``yval2``
appended -- exactly matching R's documented frame column order (see
``rpart.R``/``summary.rpart.R``). So R's 1-based ``frame[,5:7]`` is the
3-column block ``yval``, ``complexity``, ``ncompete`` -- translated below
as an explicit column-name list rather than a raw positional slice, to
make the translation self-documenting; verified this is *not* affected by
weighting (both ``yval`` -- the predicted class code, unaffected by
uniform reweighting -- and ``complexity``/``ncompete`` are identical
between carfit/carfit2).

``xx[,5]`` (R 1-based column 5 of ``splits``) -- R's ``splits`` matrix has
columns ``count``(1), ``ncat``(2), ``improve``(3), ``index``(4),
``adj``(5) (see ``rpart.R``'s ``dimnames(...) <- list(..., c("count",
"ncat", "improve", "index", "adj"))``, mirrored in ``rpart.py`` by
``columns=["count", "ncat", "improve", "index", "adj"]``), so R's
``ifelse(xx[,5] > 0, 1, 3)`` -- the comment ``# surrogate?`` -- is testing
whether the ``adj`` column (a surrogate-only "improvement over the naive
majority rule" statistic; primary splits always have ``adj == 0``) is
positive, i.e. whether the row is a *surrogate* split, in which case the
``improve`` value is left alone, vs. a primary split, whose weight-summed
``improve`` statistic scales by 3 like ``frame$wt``/``frame$dev`` do (see
``treble.R``'s header comment: "The improvement is the splits matrix,
column 3, rows with n>0[i.e. primary splits]. Other rows are surrogate
splits."). Translated as Python 0-based column ``"adj"`` (splits column
index 4), dividing ``improve`` by 1 where ``adj > 0`` (surrogate) and by 3
otherwise (primary).

``yval2`` column translation (``yval2[,12:21]``)
----------------------------------------------------
``rpart.py``'s classification branch builds ``yval2`` as ``hstack([yval2,
yprob, nodeprob])`` where the first block is ``dnode[:, 3:(4+numclass)]``
(width ``1 + numclass``: the predicted class code plus each class's raw
weighted count), the second is ``yprob`` (width ``numclass``: each class's
probability), and the third is ``nodeprob`` (width 1) -- exactly mirroring
R's ``rpart.R``: ``yval2 <- matrix(rpfit$dnode[, 4L + (0L:numclass)], ...);
frame$yval2 <- cbind(yval2, yprob, nodeprob)``. With ``Country``'s 10
classes (``numclass = 10``), the full width is ``1 + 10 + 10 + 1 = 22``
columns (0-based indices 0..21 in Python, 1-based 1..22 in R): column 0/1
= yval, columns 1-10/2-11 = per-class counts, columns 11-20/12-21 =
per-class probabilities ("yprob"), column 21/22 = nodeprob. So R's
1-based ``yval2[,12:21]`` is exactly the 10 ``yprob`` columns, translated
as Python's 0-based ``yval2[:, 11:21]`` (a half-open slice covering
indices 11 through 20 inclusive, i.e. 10 columns) -- verified to match
between carfit/carfit2 (class probabilities are a ratio and hence
unaffected by uniformly trebling every observation's weight).

``carfit[c('where', 'csplit')]``
------------------------------------
``where`` and ``csplit`` are both top-level keys of the dict returned by
``rpart()`` (see ``rpart.py``'s final ``return {...}``), translated as a
direct ``numpy.array_equal`` comparison of each (both are exact-match
integer arrays/matrices in R, unaffected by weighting, since where a
given observation lands and how a categorical split's node-index-per-
category table is encoded do not depend on the weight scale).

``cptable`` scaling (``carfit2$cptable %*% diag(c(1,1,1,1,sqrt(3)))``)
--------------------------------------------------------------------------
Matches the identical pattern in ``treble.R``/``treble2.R``: R's
``cptable`` column 5 (1-based) is ``xstd``, the Python DataFrame's 0-based
column index 4 (``_temp_labels = ["CP", "nsplit", "rel error", "xerror",
"xstd"]`` in ``rpart.py``) -- diagonal-matrix right-multiplication scales
only that column, by ``sqrt(3)``, leaving ``CP``/``nsplit``/``rel
error``/``xerror`` unchanged. Translated as scaling a copy of carfit2's
``cptable["xstd"]`` column by ``numpy.sqrt(3)`` and comparing the full
table to carfit's (unscaled) ``cptable``.

``summary(carfit2)`` (final bare call, no assertion in R)
--------------------------------------------------------------
Per the task instructions and the established convention in
``test_backticks.py``/``test_testall.py`` for bare print/summary calls
with no accompanying R assertion, this is translated into a Python
well-formedness check: the call must simply execute without raising,
confirming the returned classification-tree dict resulting from a
weighted fit is well-formed enough for ``print_rpart``/``summary_rpart``
to run to completion.

``all.equal`` -> ``numpy.allclose`` / exact equality
--------------------------------------------------------
Mirrors the established convention across this batch's conversions:
floating-point columns/arrays compared with ``numpy.allclose`` (R's
``all.equal`` default relative-difference tolerance, ~1.5e-8), integer/
categorical columns (``where``, ``csplit``, ``var`` names) compared for
bit-for-bit equality via ``numpy.array_equal``.

``set.seed(10)``
-------------------
Reproduced via ``numpy.random.seed(10)``. Both fits' ``xval=`` is the
explicit, deterministic ``xgrp`` fold-group vector, so no fit here
actually draws random cross-validation folds and the seed has no effect
on any value checked below -- set anyway for exact parity with the
original script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import print_rpart, rpart, summary_rpart

_DATA = Path(__file__).parent / "data"
_CU_SUMMARY_CSV = _DATA / "cu_summary.csv"

# Same level orders established by test_testall.py's cu.summary fixture.
_CU_COUNTRY_LEVELS = [
    "Brazil", "England", "France", "Germany", "Japan",
    "Japan/USA", "Korea", "Mexico", "Sweden", "USA",
]
_CU_RELIABILITY_LEVELS = ["Much worse", "worse", "average", "better", "Much better"]
_CU_TYPE_LEVELS = ["Compact", "Large", "Medium", "Small", "Sporty", "Van"]

_FORMULA = "Country ~ Reliability + Price + Mileage + Type"


def _load_cu_summary() -> pd.DataFrame:
    """Load rpart's built-in `cu.summary` dataset (117 cars, Consumer
    Reports April 1990), reusing the fixture already exported by
    test_testall.py's conversion verbatim (see rpart/data/cu.summary.rda
    and rpart/man/cu.summary.Rd for the column/level definitions this
    mirrors), rather than re-exporting it."""
    cu = pd.read_csv(_CU_SUMMARY_CSV)
    cu["Country"] = pd.Categorical(cu["Country"], categories=_CU_COUNTRY_LEVELS)
    cu["Reliability"] = pd.Categorical(
        cu["Reliability"], categories=_CU_RELIABILITY_LEVELS, ordered=True
    )
    cu["Type"] = pd.Categorical(cu["Type"], categories=_CU_TYPE_LEVELS)
    return cu


def test_trebled_weights_classification_carfit() -> None:
    """xgrp <- rep(1:10,length.out=nrow(cu.summary))
    carfit <- rpart(Country ~ Reliability + Price + Mileage + Type,
             method='class', data=cu.summary,
             control=rpart.control(xval=xgrp))
    carfit2 <- rpart(Country ~ Reliability + Price + Mileage + Type,
             method='class', data=cu.summary,
             weights=rep(3,nrow(cu.summary)),
             control=rpart.control(xval=xgrp))

    all.equal(carfit$frame$wt,    carfit2$frame$wt/3)
    all.equal(carfit$frame$dev,   carfit2$frame$dev/3)
    all.equal(carfit$frame[,5:7], carfit2$frame[,5:7])
    all.equal(carfit$frame$yval2[,12:21], carfit2$frame$yval2[,12:21])
    all.equal(carfit[c('where', 'csplit')],
          carfit2[c('where', 'csplit')])
    xx <- carfit2$splits
    xx[,'improve'] <- xx[,'improve'] / ifelse(xx[,5]> 0,1,3) # surrogate?
    all.equal(xx, carfit$splits)
    all.equal(as.vector(carfit$cptable),
          as.vector(carfit2$cptable%*% diag(c(1,1,1,1,sqrt(3)))))

    summary(carfit2)
    """
    np.random.seed(10)
    cu = _load_cu_summary()
    n = len(cu)

    ## xgrp <- rep(1:10,length.out=nrow(cu.summary))
    xgrp = np.resize(np.arange(1, 11), n)

    carfit = rpart(
        _FORMULA,
        data=cu,
        method="class",
        control={"xval": xgrp},
    )

    ## carfit2 <- rpart(..., weights=rep(3,nrow(cu.summary)), ...)
    carfit2 = rpart(
        _FORMULA,
        data=cu,
        method="class",
        weights=np.full(n, 3.0),
        control={"xval": xgrp},
    )

    assert carfit["method"] == "class"
    assert carfit2["method"] == "class"

    frame = carfit["frame"]
    frame2 = carfit2["frame"]
    assert len(frame) == len(frame2)
    assert (frame["var"].to_numpy() == frame2["var"].to_numpy()).all()

    ## all.equal(carfit$frame$wt,    carfit2$frame$wt/3)
    assert np.allclose(
        frame["wt"].to_numpy(dtype=float), frame2["wt"].to_numpy(dtype=float) / 3
    )

    ## all.equal(carfit$frame$dev,   carfit2$frame$dev/3)
    assert np.allclose(
        frame["dev"].to_numpy(dtype=float), frame2["dev"].to_numpy(dtype=float) / 3
    )

    ## all.equal(carfit$frame[,5:7], carfit2$frame[,5:7])
    ## R's 1-based frame columns 5:7 are "yval", "complexity", "ncompete"
    ## (frame column order: var, n, wt, dev, yval, complexity, ncompete,
    ## nsurrogate -- see module docstring), unaffected by uniform reweighting.
    for col in ["yval", "complexity", "ncompete"]:
        assert np.allclose(
            frame[col].to_numpy(dtype=float), frame2[col].to_numpy(dtype=float)
        ), f"frame column {col!r} mismatch"

    ## all.equal(carfit$frame$yval2[,12:21], carfit2$frame$yval2[,12:21])
    ## yval2 layout (Country has 10 classes): col 0 = yval, cols 1:11 =
    ## per-class counts, cols 11:21 = per-class probabilities ("yprob"),
    ## col 21 = nodeprob. R's 1-based [,12:21] is the 10 yprob columns ->
    ## Python's 0-based [:, 11:21].
    yval2 = np.vstack(frame["yval2"].to_numpy())
    yval2_2 = np.vstack(frame2["yval2"].to_numpy())
    assert yval2.shape == yval2_2.shape == (len(frame), 22)
    assert np.allclose(yval2[:, 11:21], yval2_2[:, 11:21])

    ## all.equal(carfit[c('where', 'csplit')], carfit2[c('where', 'csplit')])
    assert np.array_equal(carfit["where"], carfit2["where"])
    assert np.array_equal(carfit["csplit"], carfit2["csplit"])

    ## xx <- carfit2$splits
    ## xx[,'improve'] <- xx[,'improve'] / ifelse(xx[,5]> 0,1,3) # surrogate?
    ## all.equal(xx, carfit$splits)
    ## R's splits column 5 (1-based) is "adj" (splits columns: count, ncat,
    ## improve, index, adj) -- adj > 0 marks a surrogate split, whose
    ## "improve" is left alone; primary splits' "improve" scales by 3.
    splits = carfit["splits"]
    splits2 = carfit2["splits"]
    assert list(splits.columns) == list(splits2.columns) == [
        "count", "ncat", "improve", "index", "adj",
    ]
    assert len(splits) == len(splits2)
    assert list(splits.index) == list(splits2.index)

    xx = splits2.copy()
    adj = xx["adj"].to_numpy(dtype=float)
    divisor = np.where(adj > 0, 1.0, 3.0)
    xx["improve"] = xx["improve"].to_numpy(dtype=float) / divisor

    assert np.allclose(
        xx["improve"].to_numpy(dtype=float), splits["improve"].to_numpy(dtype=float)
    )
    for col in ["count", "ncat", "index", "adj"]:
        assert np.allclose(
            xx[col].to_numpy(dtype=float), splits[col].to_numpy(dtype=float)
        ), f"splits column {col!r} mismatch"

    ## all.equal(as.vector(carfit$cptable),
    ##           as.vector(carfit2$cptable%*% diag(c(1,1,1,1,sqrt(3)))))
    ## R's cptable column 5 (1-based) is "xstd" -> Python 0-based col 4.
    cptable = carfit["cptable"]
    cptable2 = carfit2["cptable"]
    assert list(cptable.columns) == list(cptable2.columns) == [
        "CP", "nsplit", "rel error", "xerror", "xstd",
    ]
    scaled2 = cptable2.copy()
    scaled2["xstd"] = scaled2["xstd"] * np.sqrt(3)
    assert np.allclose(
        cptable.to_numpy(dtype=float), scaled2.to_numpy(dtype=float)
    )

    ## summary(carfit2)  -- bare auto-print in R with no assertion; verify
    ## the weighted classification fit is well-formed enough for
    ## print()/summary() to run to completion (see test_backticks.py/
    ## test_testall.py's identical convention for bare print/summary calls).
    print_rpart(carfit2)
    summary_rpart(carfit2)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
