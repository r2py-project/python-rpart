"""Python translation of rpart/tests/treble2.R.

Original R script
------------------
    #
    # Test weights in a regression problem
    #
    library(rpart)
    set.seed(10)

    mystate <- data.frame(state.x77, region=factor(state.region))
    names(mystate) <- c("population","income" , "illiteracy","life" ,
           "murder", "hs.grad", "frost",     "area",      "region")

    xgrp <- rep(1:10,5)
    fit4 <- rpart(income ~ population + region + illiteracy +life + murder +
                            hs.grad + frost , mystate,
                       control=rpart.control(minsplit=10, xval=xgrp))
    wts <- rep(3, nrow(mystate))
    fit4b <-  rpart(income ~ population + region + illiteracy +life + murder +
                            hs.grad + frost , mystate,
                       control=rpart.control(minsplit=10, xval=xgrp), weights=wts)
    fit4b$frame$wt   <- fit4b$frame$wt/3
    fit4b$frame$dev  <- fit4b$frame$dev/3
    fit4b$cptable[,5] <- fit4b$cptable[,5] * sqrt(3)
    temp <- c('frame', 'where', 'splits', 'csplit', 'cptable')
    all.equal(fit4[temp], fit4b[temp])


    # Next is a very simple case, but worth keeping
    dummy <- data.frame(y=1:10, x1=c(10:4, 1:3), x2=c(1,3,5,7,9,2,4,6,8,0))

    xx1 <- rpart(y ~ x1 + x2, dummy, minsplit=4, xval=0)
    xx2 <- rpart(y ~ x1 + x2, dummy, weights=rep(2,10), minsplit=4, xval=0)

    all.equal(xx1$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2))
    all.equal(xx2$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2)*2)

    # Now for a set of non-equal weights
    #  We need to set maxcompete=3 because there just happens to be, in one
    #  of the lower nodes, an exact tie between variables "life" and "murder".
    #  Round off error causes fit5 to choose one and fit5b the other.
    # Later -- cut it back to maxdepth=3 for the same reason (a tie).
    #
    nn <- nrow(mystate)
    wts <- rep(1:5, length.out=nn)
    temp <- rep(1:nn, wts)             #row replicates
    xgrp <- rep(1:10, length.out=nn)
    xgrp2<- rep(xgrp, wts)
    tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0,
    		       maxcompete=3, maxdepth=3)
    #  Direct: replicate rows in the data set, and use unweighted
    fit5 <-  rpart(income ~ population + region + illiteracy +life + murder +
                            hs.grad + frost , data=mystate[temp,], control=tempc)
    #  Weighted
    tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0,
    		       maxcompete=3, maxdepth=3)
    fit5b <-  rpart(income ~ population + region + illiteracy +life + murder +
                            hs.grad + frost , data=mystate, control=tempc,
                            weights=wts)
    all.equal(fit5$frame[-2],  fit5b$frame[-2])  # the "n" component won't match
    all.equal(fit5$cptable,    fit5b$cptable)
    all.equal(fit5$splits[,-1],fit5b$splits[,-1])
    all.equal(fit5$csplit,    fit5b$csplit)

This is an informal, print-heavy R "tests" script (no `testthat`/formal
assertion failures -- every check is a bare `all.equal()` call whose result
is merely printed, never asserted) that exercises rpart()'s `weights=`
argument on an "anova"-method (plain regression) tree fit to the
`mystate` dataset, translated below into real `assert` statements. All
three parts were additionally cross-checked against a live R session
(`Rscript`, same `rpart` package, same `set.seed(10)`) before writing the
assertions, confirming every one of the R script's bare `all.equal()`
calls does in fact evaluate to `TRUE` (not merely "printed and ignored" --
the values genuinely match to R's default `all.equal` tolerance, including
the full, un-relaxed `fit5$frame[-2]`/`fit5$cptable`/`fit5$splits[,-1]`/
`fit5$csplit` comparisons in part 3).

``mystate`` dataset
--------------------
Reused verbatim from the fixture already exported by
``test_cptest.py``'s conversion (``r2py_rpart/tests/data/mystate.csv``,
built from R's built-in ``state.x77``/``state.region`` datasets) rather
than re-exporting it, per the task instructions. The same
``_REGION_LEVELS = ["Northeast", "South", "North Central", "West"]``
level order (R's ``factor(state.region)`` default level ordering) is
reproduced via ``pandas.Categorical(..., categories=_REGION_LEVELS)``, and
the same set of 7 predictors used by ``test_cptest.py`` are used here too,
plus ``life`` (life expectancy), which ``cptest.R`` did not use but
``treble2.R`` does.

Part 1: trebled weights (fit4 vs fit4b), using formula-string + data=
-----------------------------------------------------------------------
Unlike ``treble.R`` (which had to hand-build a model frame for its
``Surv()`` response), this part uses the ordinary formula-string +
``data=`` code path, with ``weights=wts`` passed as a keyword to
``rpart()`` directly -- ``r2py_rpart``'s ``rpart()`` forwards this
straight to ``_build_model_frame()`` (see ``model_frame_rpart.py``),
exactly mirroring R's ``model.frame()`` weights handling.

``rpart.control(minsplit=10, xval=xgrp)`` -> ``control={"minsplit": 10,
"xval": xgrp}`` (a plain dict), since ``rpart()``'s ``control=`` parameter
accepts a dict and forwards it to ``rpart_control(**dict)`` (see
``rpart.py``), exactly as R's ``rpart.control()`` return value would be.

``xgrp <- rep(1:10,5)`` (a length-50 explicit cross-validation fold-group
vector, values 1..10 each repeated 5 times in a contiguous block, *not*
interleaved) -> ``numpy.repeat(numpy.arange(1, 11), 5)`` (R's
``rep(vector, 5)`` with a scalar second argument repeats the *entire
vector* 5 times end-to-end -- i.e. ``1,2,...,10,1,2,...,10,...`` -- which
is actually ``numpy.tile``, not ``numpy.repeat``; verified against R
directly: ``rep(1:10, 5)`` produces ``1 2 3 4 5 6 7 8 9 10 1 2 3 ...``, the
tile pattern, so the correct translation is ``numpy.tile(numpy.arange(1,
11), 5)``).

``wts <- rep(3, nrow(mystate))`` -> ``numpy.full(len(mystate), 3.0)``.

``fit4b$frame$wt <- fit4b$frame$wt/3``, ``fit4b$frame$dev <-
fit4b$frame$dev/3``, ``fit4b$cptable[,5] <- fit4b$cptable[,5] *
sqrt(3)`` -> undone/applied on copies of the Python frame/cptable
(``frame["wt"] / 3``, ``frame["dev"] / 3``, ``cptable["xstd"] *
sqrt(3)`` -- R's cptable column 5, 1-based, is ``xstd``, the Python
DataFrame's 0-based column index 4 per ``rpart.py``'s ``_temp_labels =
["CP", "nsplit", "rel error", "xerror", "xstd"]``, matching the task
description).

``temp <- c('frame', 'where', 'splits', 'csplit', 'cptable'); all.equal
(fit4[temp], fit4b[temp])`` -> each of these five components is compared
directly (frame column-by-column after undoing the 3x/sqrt(3) rescalings
above; ``where`` and ``cptable``'s other 4 columns and ``splits``/
``csplit`` compared as-is, since the R script's own live-verified
``all.equal`` result shows they are *exactly* unchanged by weighting other
than through the two frame columns and the one cptable column explicitly
rescaled).

Part 2: tiny 10-row dummy dataset (xx1 vs xx2), exact `frame$dev` values
--------------------------------------------------------------------------
``dummy <- data.frame(y=1:10, x1=c(10:4, 1:3), x2=c(1,3,5,7,9,2,4,6,8,0))``
-> a literal ``pandas.DataFrame`` built the same way: ``y = 1..10``,
``x1 = [10,9,8,7,6,5,4] + [1,2,3]`` (R's ``10:4`` counts *down* from 10 to
4 inclusive -- 7 values -- concatenated with ``1:3``), ``x2`` a literal
list.

``xx1 <- rpart(y ~ x1 + x2, dummy, minsplit=4, xval=0)`` /
``xx2 <- rpart(y ~ x1 + x2, dummy, weights=rep(2,10), minsplit=4,
xval=0)`` -> direct formula-string + ``data=`` calls, ``minsplit``/
``xval`` passed as top-level ``rpart()`` kwargs (validated against
``rpart_control``'s formals by ``rpart.py``, then forwarded), exactly
mirroring the R call signature; ``weights=rep(2,10)`` ->
``weights=numpy.full(10, 2.0)``.

``all.equal(xx1$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2))`` /
``all.equal(xx2$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2)*2)`` -> both
verified against a live R run to indeed hold exactly (``[1] TRUE`` for
both), translated as ``numpy.allclose`` against the same literal 7-value
arrays (the second scaled by 2, per the unequal-weights-double-the-total-
deviance identity that motivates this whole test file).

Part 3: replicated rows vs. weights=1:5 (fit5 vs fit5b)
-----------------------------------------------------------
Mirrors ``treble.R``'s second test (row-replication vs. explicit
``weights=`` on the same data) but on ``mystate``/anova instead of
``stagec``/poisson, with ``rpart.control(minsplit=2, maxsurrogate=0,
maxcompete=3, maxdepth=3)`` -- the R comment explains ``maxcompete=3``
(and later ``maxdepth=3``) is needed because of a documented near-tie
between the "life" and "murder" variables in a lower node that round-off
error can resolve differently between the replicated and weighted fits;
``maxdepth=3`` keeps the tree shallow enough that this potential
tie-breaking divergence never actually manifests. Live-verified against R:
with these controls, *all four* ``all.equal`` calls (frame minus "n",
cptable, splits minus "count", csplit) evaluate to exactly ``TRUE`` -- no
approximation or excluded rows/columns beyond what the R script itself
already excludes (unlike ``treble.R``'s stagec/poisson analogue, which
needed a hand-verified 2-row "toss" list because of an actual, expected
discrepancy).

``nn <- nrow(mystate); wts <- rep(1:5, length.out=nn)`` -> ``n =
len(mystate); wts = numpy.resize(numpy.arange(1, 6), n)`` (``rep(vector,
length.out=n)`` recycles ``vector`` to exactly length ``n``, which is
precisely ``numpy.resize``'s semantics -- same idiom used in
``test_treble.py``).

``temp <- rep(1:nn, wts)`` (1-based row *numbers*, each repeated
``wts[i]`` times) -> ``numpy.repeat(numpy.arange(n), wts)`` (0-based row
*positions*, for direct ``.iloc`` indexing), matching ``test_treble.py``'s
identical idiom for ``stagec[temp,]`` -> ``stagec.iloc[temp]``.

``xgrp <- rep(1:10, length.out=nn)`` -> ``numpy.resize(numpy.arange(1,
11), n)``. ``xgrp2 <- rep(xgrp, wts)`` -> ``numpy.repeat(xgrp, wts)``.

``fit5 <- rpart(..., data=mystate[temp,], control=tempc)`` (unweighted,
on the replicated/expanded data) -> ``rpart(..., data=mystate.iloc[temp]
.reset_index(drop=True), control=tempc)``. ``fit5b <- rpart(..., data=
mystate, control=tempc, weights=wts)`` (weighted, on the original data)
-> the direct formula-string + ``data=`` + ``weights=`` translation.

``all.equal(fit5$frame[-2], fit5b$frame[-2])`` -- R's ``frame`` column 2
(1-based) is ``"n"`` (verified: ``var, n, wt, dev, yval, complexity,
ncompete, nsurrogate`` -- same order as the Python frame built by
``rpart.py``) -> ``frame.drop(columns=["n"])`` on both sides, since the
"n" (raw observation count backing each node) legitimately differs
between the 150-row replicated fit and the 50-row weighted fit by
construction, exactly as the R comment states.

``all.equal(fit5$splits[,-1], fit5b$splits[,-1])`` -- R's ``splits``
column 1 is ``"count"`` -> ``splits.drop(columns=["count"])`` on both
sides, for the same reason "n" is dropped from frame (the "count" column
records the same raw-vs-weighted-sum discrepancy at the split level).
Live-verified this drop is *sufficient* here (unlike ``treble.R``'s
stagec/poisson analogue, no additional rows need excluding) because the
``maxcompete=3``/``maxdepth=3`` controls specifically prevent the
documented "life"/"murder" round-off tie from manifesting.

``all.equal`` -> ``numpy.allclose`` / exact equality, mirroring
``test_treble.py``'s / ``test_cptest.py``'s established convention:
floating point columns compared with ``numpy.allclose`` (R's
``all.equal`` default relative-difference tolerance, ~1.5e-8), integer/
string columns (``var`` names, ``ncat``) compared for bit-for-bit
equality.

``set.seed(10)``
-------------------
Reproduced via ``numpy.random.seed(10)``. Every ``xval=`` in this script
is an explicit, deterministic fold-group vector (``xgrp``/``xgrp2`` for
all three fits, ``xval=0`` for the dummy dataset's xx1/xx2), so no fit
here actually draws random cross-validation folds and the seed has no
effect on any value checked below -- set anyway for exact parity with the
original script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart

_DATA = Path(__file__).parent / "data"
_MYSTATE_CSV = _DATA / "mystate.csv"

# R's factor(state.region) level order (verified against the R session
# used to export mystate.csv; same order used by test_cptest.py).
_REGION_LEVELS = ["Northeast", "South", "North Central", "West"]

_PREDICTORS = [
    "population",
    "region",
    "illiteracy",
    "life",
    "murder",
    "hs.grad",
    "frost",
]
_FORMULA = "income ~ population + region + illiteracy + life + murder + hs.grad + frost"


def _load_mystate() -> pd.DataFrame:
    """Load the state.x77/state.region-derived dataset exported from R
    (reused verbatim from test_cptest.py's fixture, per the task
    instructions -- see module docstring)."""
    mystate = pd.read_csv(_MYSTATE_CSV)
    mystate["region"] = pd.Categorical(mystate["region"], categories=_REGION_LEVELS)
    return mystate


def _assert_frames_match(
    frame_a: pd.DataFrame,
    frame_b: pd.DataFrame,
    *,
    drop: list[str] | None = None,
) -> None:
    """Compare two rpart() 'frame' DataFrames column-by-column, mirroring
    R's all.equal() on a data.frame: 'var' (character) and 'ncompete'/
    'nsurrogate' (integer) columns compared exactly, all other (numeric)
    columns compared with numpy.allclose. No 'yval2' column is present
    for the anova method (single response), matching R.
    """
    a = frame_a.drop(columns=drop) if drop else frame_a
    b = frame_b.drop(columns=drop) if drop else frame_b
    assert list(a.columns) == list(b.columns)
    assert len(a) == len(b)
    assert (a["var"].to_numpy() == b["var"].to_numpy()).all()
    for col in ["ncompete", "nsurrogate"]:
        assert (a[col].to_numpy() == b[col].to_numpy()).all(), f"frame column {col!r} mismatch"
    for col in [c for c in a.columns if c not in ("var", "ncompete", "nsurrogate")]:
        assert np.allclose(
            a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float)
        ), f"frame column {col!r} mismatch"


def _assert_splits_match(
    splits_a: pd.DataFrame,
    splits_b: pd.DataFrame,
    *,
    drop: list[str] | None = None,
) -> None:
    """Compare two rpart() 'splits' DataFrames, mirroring R's
    all.equal(): row (variable) names compared exactly, all remaining
    (numeric) columns compared with numpy.allclose.
    """
    a = splits_a.drop(columns=drop) if drop else splits_a
    b = splits_b.drop(columns=drop) if drop else splits_b
    assert list(a.columns) == list(b.columns)
    assert len(a) == len(b)
    assert list(a.index) == list(b.index)
    assert np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float))


def test_trebled_weights_scale_wt_dev_and_xstd() -> None:
    """xgrp <- rep(1:10,5)
    fit4 <- rpart(income ~ population + region + illiteracy +life + murder +
                          hs.grad + frost , mystate,
                     control=rpart.control(minsplit=10, xval=xgrp))
    wts <- rep(3, nrow(mystate))
    fit4b <-  rpart(income ~ ..., mystate,
                     control=rpart.control(minsplit=10, xval=xgrp), weights=wts)
    fit4b$frame$wt   <- fit4b$frame$wt/3
    fit4b$frame$dev  <- fit4b$frame$dev/3
    fit4b$cptable[,5] <- fit4b$cptable[,5] * sqrt(3)
    temp <- c('frame', 'where', 'splits', 'csplit', 'cptable')
    all.equal(fit4[temp], fit4b[temp])
    """
    np.random.seed(10)
    mystate = _load_mystate()
    n = len(mystate)

    ## xgrp <- rep(1:10,5)  -- R's rep(vector, scalar) TILES the whole
    ## vector `scalar` times (1,2,...,10,1,2,...,10,...), not element-wise
    ## repeat -- verified directly against R.
    xgrp = np.tile(np.arange(1, 11), 5)
    assert len(xgrp) == n == 50

    control4 = {"minsplit": 10, "xval": xgrp}
    fit4 = rpart(_FORMULA, data=mystate, control=control4)

    ## wts <- rep(3, nrow(mystate))
    wts = np.full(n, 3.0)
    fit4b = rpart(_FORMULA, data=mystate, control=control4, weights=wts)

    assert fit4["method"] == "anova"
    assert fit4b["method"] == "anova"

    ## fit4b$frame$wt   <- fit4b$frame$wt/3
    ## fit4b$frame$dev  <- fit4b$frame$dev/3
    frame4 = fit4["frame"]
    frame4b = fit4b["frame"].copy()
    frame4b["wt"] = frame4b["wt"] / 3
    frame4b["dev"] = frame4b["dev"] / 3

    ## fit4b$cptable[,5] <- fit4b$cptable[,5] * sqrt(3)
    ## R's cptable column 5 (1-based) is "xstd" -> Python 0-based col 4,
    ## matching rpart.py's _temp_labels = ["CP","nsplit","rel error",
    ## "xerror","xstd"].
    cptable4 = fit4["cptable"]
    cptable4b = fit4b["cptable"].copy()
    assert list(cptable4.columns)[4] == "xstd"
    assert list(cptable4b.columns)[4] == "xstd"
    cptable4b["xstd"] = cptable4b["xstd"] * np.sqrt(3)

    ## temp <- c('frame', 'where', 'splits', 'csplit', 'cptable')
    ## all.equal(fit4[temp], fit4b[temp])
    _assert_frames_match(frame4, frame4b)
    assert np.array_equal(fit4["where"], fit4b["where"])
    _assert_splits_match(fit4["splits"], fit4b["splits"])
    assert np.array_equal(fit4["csplit"], fit4b["csplit"])
    assert np.allclose(
        cptable4.to_numpy(dtype=float), cptable4b.to_numpy(dtype=float)
    )


def test_dummy_dataset_frame_dev_weighted_vs_unweighted() -> None:
    """dummy <- data.frame(y=1:10, x1=c(10:4, 1:3), x2=c(1,3,5,7,9,2,4,6,8,0))
    xx1 <- rpart(y ~ x1 + x2, dummy, minsplit=4, xval=0)
    xx2 <- rpart(y ~ x1 + x2, dummy, weights=rep(2,10), minsplit=4, xval=0)
    all.equal(xx1$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2))
    all.equal(xx2$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2)*2)
    """
    ## dummy <- data.frame(y=1:10, x1=c(10:4, 1:3), x2=c(1,3,5,7,9,2,4,6,8,0))
    ## R's 10:4 counts DOWN from 10 to 4 inclusive (7 values).
    dummy = pd.DataFrame(
        {
            "y": np.arange(1, 11),
            "x1": np.concatenate([np.arange(10, 3, -1), np.arange(1, 4)]),
            "x2": [1, 3, 5, 7, 9, 2, 4, 6, 8, 0],
        }
    )

    xx1 = rpart("y ~ x1 + x2", data=dummy, minsplit=4, xval=0)
    xx2 = rpart(
        "y ~ x1 + x2", data=dummy, weights=np.full(10, 2.0), minsplit=4, xval=0
    )

    expected = np.array([82.5, 10, 2, 0.5, 10, 0.5, 2])

    ## all.equal(xx1$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2))
    dev1 = xx1["frame"]["dev"].to_numpy(dtype=float)
    assert len(dev1) == len(expected)
    assert np.allclose(dev1, expected)

    ## all.equal(xx2$frame$dev, c(82.5, 10, 2, .5, 10, .5, 2)*2)
    dev2 = xx2["frame"]["dev"].to_numpy(dtype=float)
    assert len(dev2) == len(expected)
    assert np.allclose(dev2, expected * 2)


def test_replicated_rows_vs_weights_argument_match() -> None:
    """nn <- nrow(mystate)
    wts <- rep(1:5, length.out=nn)
    temp <- rep(1:nn, wts)             #row replicates
    xgrp <- rep(1:10, length.out=nn)
    xgrp2<- rep(xgrp, wts)
    tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0,
                            maxcompete=3, maxdepth=3)
    fit5 <-  rpart(income ~ ..., data=mystate[temp,], control=tempc)
    tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0,
                            maxcompete=3, maxdepth=3)
    fit5b <-  rpart(income ~ ..., data=mystate, control=tempc, weights=wts)
    all.equal(fit5$frame[-2],  fit5b$frame[-2])  # the "n" component won't match
    all.equal(fit5$cptable,    fit5b$cptable)
    all.equal(fit5$splits[,-1],fit5b$splits[,-1])
    all.equal(fit5$csplit,    fit5b$csplit)
    """
    np.random.seed(10)
    mystate = _load_mystate()
    nn = len(mystate)

    ## wts <- rep(1:5, length.out=nn)
    wts = np.resize(np.arange(1, 6), nn)

    ## temp <- rep(1:nn, wts)  (1-based row replicates in R; 0-based row
    ## positions here since they directly index mystate.iloc).
    temp = np.repeat(np.arange(nn), wts)

    ## xgrp <- rep(1:10, length.out=nn)
    xgrp = np.resize(np.arange(1, 11), nn)

    ## xgrp2<- rep(xgrp, wts)
    xgrp2 = np.repeat(xgrp, wts)

    assert len(temp) == len(xgrp2)

    ## tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0,
    ##                         maxcompete=3, maxdepth=3)
    tempc_fit5 = {
        "minsplit": 2,
        "xval": xgrp2,
        "maxsurrogate": 0,
        "maxcompete": 3,
        "maxdepth": 3,
    }
    ## fit5 <-  rpart(income ~ ..., data=mystate[temp,], control=tempc)
    mystate_rep = mystate.iloc[temp].reset_index(drop=True)
    fit5 = rpart(_FORMULA, data=mystate_rep, control=tempc_fit5)

    ## tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0,
    ##                         maxcompete=3, maxdepth=3)
    tempc_fit5b = {
        "minsplit": 2,
        "xval": xgrp,
        "maxsurrogate": 0,
        "maxcompete": 3,
        "maxdepth": 3,
    }
    ## fit5b <-  rpart(income ~ ..., data=mystate, control=tempc, weights=wts)
    fit5b = rpart(_FORMULA, data=mystate, control=tempc_fit5b, weights=wts)

    assert fit5["method"] == "anova"
    assert fit5b["method"] == "anova"

    ## all.equal(fit5$frame[-2],  fit5b$frame[-2])
    ## R's frame column 2 (1-based) is "n".
    frame5 = fit5["frame"]
    frame5b = fit5b["frame"]
    assert list(frame5.columns)[1] == "n"
    assert list(frame5b.columns)[1] == "n"
    _assert_frames_match(frame5, frame5b, drop=["n"])

    ## all.equal(fit5$cptable,    fit5b$cptable)
    assert list(fit5["cptable"].columns) == list(fit5b["cptable"].columns)
    assert np.allclose(
        fit5["cptable"].to_numpy(dtype=float), fit5b["cptable"].to_numpy(dtype=float)
    )

    ## all.equal(fit5$splits[,-1],fit5b$splits[,-1])
    ## R's splits column 1 (1-based) is "count".
    splits5 = fit5["splits"]
    splits5b = fit5b["splits"]
    assert list(splits5.columns)[0] == "count"
    assert list(splits5b.columns)[0] == "count"
    _assert_splits_match(splits5, splits5b, drop=["count"])

    ## all.equal(fit5$csplit,    fit5b$csplit)
    assert np.array_equal(fit5["csplit"], fit5b["csplit"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
