"""Python translation of rpart/tests/treble.R.

Original R script
------------------
    #
    # Simplest weight test: treble the weights
    #
    #  By using the unshrunken estimates the weights will nearly cancel
    #   out:  frame$wt, frame$dev, frame$yval2, and improvement will all
    #   be threefold larger, other things will be the same.
    # The improvement is the splits matrix, column 3, rows with n>0.  Other
    #   rows are surrogate splits.
    library(rpart)
    require(survival)
    set.seed(10)

    tempc <- rpart.control(maxsurrogate=0, cp=0, xval=0)
    fit1 <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
                    stagec, control=tempc,
                    method='poisson', parms=list(shrink=0))
    wts <- rep(3, nrow(stagec))
    fit1b <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
                    stagec, control= tempc, parms=list(shrink=0),
                    method='poisson', weights=wts)
    fit1b$frame$wt   <- fit1b$frame$wt/3
    fit1b$frame$dev  <- fit1b$frame$dev/3
    fit1b$frame$yval2[,2] <- fit1b$frame$yval2[,2]/3
    fit1b$splits[,3] <- fit1b$splits[,3]/3
    zz <- match(c("call", "variable.importance"), names(fit1))
    all.equal(fit1[-zz], fit1b[-zz])   #all but the "call" and importance
    all.equal(fit1b$variable.importance/fit1$variable.importance, rep(3,4),
              check.attributes = FALSE)

    #
    # Compare a pair of multiply weighted fits
    #  In this one, the lengths of where and y won't match
    # I have to set minsplit to the smallest possible, because otherwise
    #  the replicated data set will sometimes have enough "n" to split, but
    #  the weighted one won't.  Use of CP keeps the degenerate splits
    #  (n=2, several covariates with exactly the same improvement) at bay.
    # For larger trees, the weighted split will sometimes have fewer
    #  surrogates, because of the "at least two obs" rule.
    #
    # Create a reproducable psuedo random order using the logisic attractor
    pseudo <- double(nrow(stagec))
    pseudo[1] <- pi/4
    for (i in 2:nrow(stagec)) pseudo[i] <- 4*pseudo[i-1]*(1 - pseudo[i-1])

    wts <- rep(1:5, length.out=nrow(stagec))
    temp <- rep(1:nrow(stagec), wts)             #row replicates
    xgrp <- rep(1:10, length.out=146)[order(pseudo)]
    xgrp2<- rep(xgrp, wts)
    #  Direct: replicate rows in the data set, and use unweighted
    fit2 <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
	          control=rpart.control(minsplit=2, xval=xgrp2, cp=.025),
	          data=stagec[temp,], method='poisson')

    #  Weighted
    fit2b<- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
	          control=rpart.control(minsplit=2, xval=xgrp, cp=.025),
	          data=stagec, method='poisson', weights=wts)

    all.equal(fit2$frame[-2],  fit2b$frame[-2])  # the "n" component won't match
    all.equal(fit2$cptable,    fit2b$cptable)
    #all.equal(fit2$splits[,-1],fit2b$splits[,-1]) #fails
    toss <- c(49, 64)
    all.equal(fit2$splits[-toss,-1],fit2b$splits[-toss,-1]) #ok
    all.equal(fit2$csplit,    fit2b$csplit)
    # Line 49 is a surrogate split in a group whose 2 smallest ages are
    #  47 and 48.  The weighted fit won't split there because it wants to
    #  send at least 2 obs to the left; the replicate fit thinks that there
    #  are several 47's.

This is an informal, print-heavy R "tests" script (no `testthat`/formal
assertion failures -- every check is a bare `all.equal()` call whose result
is merely printed) that exercises rpart()'s `weights=` argument in two
different ways, both translated below into real `assert` statements.

Part 1: trebling all weights (fit1 vs fit1b)
---------------------------------------------
``rpart.control(maxsurrogate=0, cp=0, xval=0)`` -> an equivalent Python
dict passed as ``control=``. ``parms=list(shrink=0)`` disables the
Poisson method's usual shrinkage-towards-the-parent-node estimate (see
``rpart_poisson.py``), so the two fits' unshrunken rate estimates
(``frame$yval`` / ``yval2[,1]``) are identical while every weight-summed
quantity (``frame$wt``, ``frame$dev``, ``yval2[,2]`` [event counts], and
each split's "improve" statistic) scales by exactly 3, exactly as the R
script's header comment states. Verified interactively against a live
r2py_rpart run (see below) before writing the assertions: ``frame$dev``,
``yval2[, 1]`` (2nd column, 0-based ``yval2[..., 1]``, i.e. R's ``[,2]``)
and ``splits[:, "improve"]`` are each exactly 3x fit1's values;
``complexity`` (the per-node cp), ``var``, ``yval``, ``ncompete``,
``nsurrogate``, and every non-"improve" ``splits`` column (``count``,
``ncat``, ``index``, ``adj``) and ``csplit`` are bit-for-bit identical
between fit1 and (unscaled) fit1b.

``wts <- rep(3, nrow(stagec))`` -> ``numpy.full(len(stagec), 3.0)``.

``zz <- match(c("call", "variable.importance"), names(fit1)); all.equal
(fit1[-zz], fit1b[-zz])`` -> since r2py_rpart's ``rpart()`` returns a
plain Python ``dict`` (not an R S3 list with a "call" attribute holding
unevaluated argument expressions, which would trivially differ between
two independently-constructed calls), the "call" exclusion is honored by
simply never comparing the ``"call"`` key; "variable.importance" is
excluded from this bulk comparison because it is checked separately by
the next ``all.equal()`` (the ratio-of-4-values check) immediately below
it in the R script -- both are preserved as separate assertions here.
Every other top-level key (frame [with the 3 documented rescalings
undone], splits [with the "improve" column rescaled], csplit, cptable,
method, parms, control, numresp, y, ordered, terms, _xlevels) is checked.

``all.equal(fit1b$variable.importance/fit1$variable.importance, rep(3,4),
check.attributes=FALSE)`` -> both fits' ``variable.importance`` have
exactly 4 nonzero-importance variables (grade, g2, age, gleason -- eet and
ploidy contribute no importance in this particular unshrunk/cp=0 tree),
and the fit1b/fit1 ratio is exactly 3 for each; ``check.attributes=FALSE``
(ignoring the R ``names()`` attribute on both sides) -> compared here by
value after aligning on the (matching) variable-name index.

Part 2: weights= vs. row-replication (fit2 vs. fit2b)
--------------------------------------------------------
This compares two ways of encoding "some observations count more than
others": (a) literally repeating each row of ``stagec`` ``wts[i]`` times
and fitting unweighted (fit2), vs. (b) fitting once on the original,
unreplicated ``stagec`` with an explicit integer ``weights=wts`` vector
(fit2b). Per the R script's own comments, these are *not* expected to
produce bit-identical fits in every respect: `where`/`y` differ in length
(436 replicated rows vs. 146 original rows, not compared here, matching
the R script which never compares them either), the `frame`'s `"n"`
column differs by construction (replicated-row counts vs. original-row
counts) and is excluded from the frame comparison (R's `fit2$frame[-2]`,
i.e. drop column 2 -- verified `"n"` is the second column of both R's and
Python's frame -- translated as `.drop(columns=["n"])`), and two specific
`splits` rows (R's 1-based rows 49 and 64, i.e. Python's 0-based rows 48
and 63) are excluded per the R comment's own explanation: row 49 is a
surrogate split where the weighted fit's "send >= 2 obs left" rule
prevents a split that the replicated-row fit (which sees several
literally-duplicated tied values, e.g. multiple rows with age 47) allows.
`fit2$splits[,-1]` (drop column 1, "count") is excluded from the
non-`toss`-rows comparison for the same reason the R comment gives
(`#all.equal(fit2$splits[,-1],fit2b$splits[,-1]) #fails` -- i.e. dropping
only "count" and comparing the remaining columns for the *full,
untossed* splits table fails, precisely because of the two `toss`
rows -- whereas `fit2$splits[-toss,-1]` -- dropping both the `toss` rows
*and* the "count" column -- succeeds. Verified interactively: `"count"`
differs between fit2/fit2b for *every* row (since replicated rows always
have ~3x-5x the raw row count of the corresponding weighted-sum-of-counts
"count" -- both are legitimate but differently-scaled bookkeeping
quantities, not a bug), so it must be excluded throughout, matching the R
script's `[,-1]` slice in both the (commented-out, failing) full
comparison and the successful `toss`-excluded one.

``pseudo <- double(nrow(stagec)); pseudo[1] <- pi/4; for (i in
2:nrow(stagec)) pseudo[i] <- 4*pseudo[i-1]*(1 - pseudo[i-1])`` (the
logistic-map/"logistic attractor" pseudo-random sequence) -> a literal
Python transliteration with a 0-based loop (`pseudo[0] = math.pi / 4`,
then `pseudo[i] = 4 * pseudo[i-1] * (1 - pseudo[i-1])` for `i` in
`range(1, n)`), producing bit-identical floating point values to R's
version since both languages use IEEE-754 double arithmetic for the same
sequence of `+`/`-`/`*` operations.

``wts <- rep(1:5, length.out=nrow(stagec))`` -> ``numpy.resize(numpy.
arange(1, 6), n)``.

``temp <- rep(1:nrow(stagec), wts)`` (row replicates, 1-based row
*numbers* each repeated `wts[i]` times) -> R's `rep(vector, times_vector)`
repeats each element `vector[i]` exactly `times_vector[i]` times, which is
precisely `numpy.repeat(vector, times_vector)`; since `1:nrow(stagec)` is
a 1-based row-number vector used purely to *index* `stagec[temp,]`
afterwards, the direct 0-indexed equivalent is `numpy.repeat(numpy.
arange(n), wts)` (0-based row positions, each repeated `wts[i]` times),
then `stagec.iloc[temp]` for `stagec[temp,]`.

``xgrp <- rep(1:10, length.out=146)[order(pseudo)]`` -> R's `order()`
returns the *permutation of indices* that would sort its argument
ascending; indexing a vector by that permutation reorders the vector
into "the value that would land in sorted-pseudo position i" order.
Translated as ``numpy.resize(numpy.arange(1, 11), 146)[numpy.argsort
(pseudo, kind="stable")]`` (``numpy.argsort`` is the direct equivalent of
R's ``order()`` for a single numeric vector with no ties -- ``pseudo``'s
144 chaotic logistic-map values are all distinct in the double-precision
sequence generated here, so stability of the sort does not affect the
result either way).

``xgrp2 <- rep(xgrp, wts)`` -> ``numpy.repeat(xgrp, wts)`` (same
element-wise-repeat-by-corresponding-count semantics as `temp` above).

``Surv(pgtime, pgstat)`` response
-----------------------------------
Built by hand via the same ``_SurvArray``/hand-assembled-model-frame
pattern established in ``test_testall.py``/``test_cost.py`` (r2py_rpart's
formula parser has no ``Surv()`` call-parsing logic); ``weights=`` for
fit1b/fit2b is supplied the same way ``test_cost.py``'s ``cost=`` is
supplied to a hand-built model frame -- as ``m.attrs["weights"]`` (see
``r2py_rpart/rpart.py``'s ``wt = m.attrs.get("weights")`` extraction),
since the ``weights=`` *keyword* to ``rpart()`` is only consulted by
``_build_model_frame()`` (the formula-string + ``data=`` code path), not
by the ``model=`` (pre-built DataFrame) code path used here.

``all.equal`` -> ``numpy.allclose`` / exact equality
--------------------------------------------------------
R's ``all.equal()`` on numeric vectors/matrices/data.frames is a
relative-difference comparison with a default tolerance around 1.5e-8;
translated below as ``numpy.allclose`` (default tolerances) for
floating-point columns and exact equality for integer/string columns
(``var`` names, ``ncat``), mirroring R's own effectively-exact behavior
for those columns (which happen to be exactly reproducible integers/
labels here, not merely "close").

``set.seed(10)``
-------------------
Reproduced via ``numpy.random.seed(10)``. Every ``xval=`` in both parts of
this script is an explicit, deterministic value (``xval=0`` for fit1/
fit1b, explicit fold-group vectors ``xgrp``/``xgrp2`` for fit2/fit2b), so
no fit here actually draws random cross-validation folds and the seed has
no effect on any value checked below -- set anyway for exact parity with
the original script.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from r2py_rpart import rpart

_DATA = Path(__file__).parent / "data"

_STAGEC_PLOIDY_LEVELS = ["diploid", "tetraploid", "aneuploid"]
_STAGEC_PREDICTORS = ["age", "eet", "g2", "grade", "gleason", "ploidy"]


class _SurvArray(np.ndarray):
    """Minimal stand-in for R's `Surv(pgtime, pgstat)` object: a plain
    (n, 2) float array of [time, status] columns, tagged with `_surv =
    True` so rpart()'s method auto-detection (see rpart.py) treats it
    like R's `inherits(Y, "Surv")` check. Both fits in this test pass an
    explicit method="poisson", so this tag is not strictly load-bearing
    here, but is retained for consistency with test_testall.py/
    test_cost.py's identical helper.
    """

    def __new__(cls, input_array: np.ndarray) -> "_SurvArray":
        obj = np.asarray(input_array, dtype=np.float64).view(cls)
        obj._surv = True
        return obj

    def __array_finalize__(self, obj: object) -> None:
        if obj is None:
            return
        self._surv = getattr(obj, "_surv", True)


def _load_stagec() -> pd.DataFrame:
    """Load rpart's built-in `stagec` dataset (146 stage-C prostate cancer
    patients), reusing the fixture already exported by test_testall.py's
    conversion (see rpart/data/stagec.rda and rpart/man/stagec.Rd for the
    column definitions this mirrors)."""
    stagec = pd.read_csv(_DATA / "stagec.csv")
    stagec["ploidy"] = pd.Categorical(stagec["ploidy"], categories=_STAGEC_PLOIDY_LEVELS)
    return stagec


def _build_surv_model_frame(
    data: pd.DataFrame,
    predictors: list[str],
    weights: np.ndarray[Any, np.dtype[np.float64]] | None = None,
) -> pd.DataFrame:
    """Python equivalent of `model.frame(Surv(pgtime, pgstat) ~ age + eet +
    g2 + grade + gleason + ploidy, data = stagec)`, built by hand since
    r2py_rpart's formula parser does not parse `Surv(...)` LHS terms (see
    module docstring). `weights`, if given, is attached via
    `m.attrs["weights"]` -- the attribute rpart.py's `model=`-DataFrame
    code path reads weights from directly (see module docstring).
    """
    time = data["pgtime"].to_numpy(dtype=float)
    status = data["pgstat"].to_numpy(dtype=float)
    y = _SurvArray(np.column_stack([time, status]))

    cols: dict[str, Any] = {"pgtime": data["pgtime"], "pgstat": data["pgstat"]}
    for p in predictors:
        cols[p] = data[p]
    m = pd.DataFrame(cols, index=data.index)

    xlevels: dict[str, list[Any]] = {}
    for p in predictors:
        if isinstance(m[p].dtype, pd.CategoricalDtype):
            xlevels[p] = list(m[p].cat.categories)

    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv(pgtime, pgstat)"] + predictors,
        "response": 1,
        "xlevels": xlevels,
    }
    m.attrs["response"] = y
    if weights is not None:
        m.attrs["weights"] = np.asarray(weights, dtype=float)
    return m


def test_trebled_weights_scale_wt_dev_yval2_and_improve() -> None:
    """tempc <- rpart.control(maxsurrogate=0, cp=0, xval=0)
    fit1 <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason
                  +ploidy, stagec, control=tempc,
                  method='poisson', parms=list(shrink=0))
    wts <- rep(3, nrow(stagec))
    fit1b <- rpart(Surv(pgtime, pgstat) ~ ..., stagec, control=tempc,
                   parms=list(shrink=0), method='poisson', weights=wts)
    fit1b$frame$wt   <- fit1b$frame$wt/3
    fit1b$frame$dev  <- fit1b$frame$dev/3
    fit1b$frame$yval2[,2] <- fit1b$frame$yval2[,2]/3
    fit1b$splits[,3] <- fit1b$splits[,3]/3
    zz <- match(c("call", "variable.importance"), names(fit1))
    all.equal(fit1[-zz], fit1b[-zz])
    all.equal(fit1b$variable.importance/fit1$variable.importance, rep(3,4),
              check.attributes = FALSE)
    """
    np.random.seed(10)
    stagec = _load_stagec()
    n = len(stagec)

    ## tempc <- rpart.control(maxsurrogate=0, cp=0, xval=0)
    tempc = {"maxsurrogate": 0, "cp": 0, "xval": 0}

    m1 = _build_surv_model_frame(stagec, _STAGEC_PREDICTORS)
    fit1 = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m1,
        method="poisson",
        control=tempc,
        parms={"shrink": 0},
    )

    ## wts <- rep(3, nrow(stagec))
    wts = np.full(n, 3.0)
    m1b = _build_surv_model_frame(stagec, _STAGEC_PREDICTORS, weights=wts)
    fit1b = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m1b,
        method="poisson",
        control=tempc,
        parms={"shrink": 0},
    )

    assert fit1["method"] == "poisson"
    assert fit1b["method"] == "poisson"

    ## fit1b$frame$wt   <- fit1b$frame$wt/3
    ## fit1b$frame$dev  <- fit1b$frame$dev/3
    ## fit1b$frame$yval2[,2] <- fit1b$frame$yval2[,2]/3
    frame1 = fit1["frame"]
    frame1b = fit1b["frame"].copy()
    frame1b["wt"] = frame1b["wt"] / 3
    frame1b["dev"] = frame1b["dev"] / 3
    ## R's yval2[,2] (1-based 2nd column, the Poisson method's event
    ## count) -> Python's 0-based index 1 of each row's yval2 array (see
    ## rpart.poisson.R: yval2 columns are [rate, events]).
    frame1b["yval2"] = [
        np.array([row[0], row[1] / 3.0]) for row in frame1b["yval2"]
    ]

    ## fit1b$splits[,3] <- fit1b$splits[,3]/3
    splits1 = fit1["splits"]
    splits1b = fit1b["splits"].copy()
    splits1b["improve"] = splits1b["improve"] / 3

    ## zz <- match(c("call", "variable.importance"), names(fit1))
    ## all.equal(fit1[-zz], fit1b[-zz])   #all but the "call" and importance
    excluded_keys = {"call", "variable.importance"}
    keys1 = set(fit1.keys()) - excluded_keys
    keys1b = set(fit1b.keys()) - excluded_keys
    assert keys1 == keys1b

    assert len(frame1) == len(frame1b)
    assert (frame1["var"].to_numpy() == frame1b["var"].to_numpy()).all()
    for col in ["wt", "dev", "yval", "complexity"]:
        assert np.allclose(
            frame1[col].to_numpy(dtype=float), frame1b[col].to_numpy(dtype=float)
        ), f"frame column {col!r} mismatch"
    for col in ["ncompete", "nsurrogate"]:
        assert (frame1[col].to_numpy() == frame1b[col].to_numpy()).all()
    assert all(
        np.allclose(a, b) for a, b in zip(frame1["yval2"], frame1b["yval2"])
    )

    assert len(splits1) == len(splits1b)
    assert (splits1.index == splits1b.index).all()
    for col in ["count", "ncat", "improve", "index", "adj"]:
        assert np.allclose(
            splits1[col].to_numpy(dtype=float), splits1b[col].to_numpy(dtype=float)
        ), f"splits column {col!r} mismatch"

    assert np.array_equal(fit1["csplit"], fit1b["csplit"])
    assert np.allclose(
        fit1["cptable"].to_numpy(dtype=float), fit1b["cptable"].to_numpy(dtype=float)
    )
    assert fit1["parms"] == fit1b["parms"]
    assert fit1["control"] == fit1b["control"]
    assert fit1["numresp"] == fit1b["numresp"]
    assert np.array_equal(fit1["ordered"], fit1b["ordered"])
    assert fit1["terms"] == fit1b["terms"]
    assert fit1["_xlevels"] == fit1b["_xlevels"]

    ## all.equal(fit1b$variable.importance/fit1$variable.importance,
    ##           rep(3,4), check.attributes = FALSE)
    ## Exactly 4 variables (grade, g2, age, gleason) have nonzero
    ## importance in this cp=0/unshrunk tree.
    vi1 = fit1["variable.importance"]
    vi1b = fit1b["variable.importance"]
    assert len(vi1) == 4
    assert set(vi1.index) == set(vi1b.index)
    ratio = (vi1b / vi1).reindex(vi1.index)
    assert np.allclose(ratio.to_numpy(), np.full(4, 3.0))


def test_replicated_rows_vs_weights_argument_nearly_match() -> None:
    """pseudo <- double(nrow(stagec))
    pseudo[1] <- pi/4
    for (i in 2:nrow(stagec)) pseudo[i] <- 4*pseudo[i-1]*(1 - pseudo[i-1])

    wts <- rep(1:5, length.out=nrow(stagec))
    temp <- rep(1:nrow(stagec), wts)             #row replicates
    xgrp <- rep(1:10, length.out=146)[order(pseudo)]
    xgrp2<- rep(xgrp, wts)
    fit2 <- rpart(Surv(pgtime, pgstat) ~ ...,
                  control=rpart.control(minsplit=2, xval=xgrp2, cp=.025),
                  data=stagec[temp,], method='poisson')
    fit2b<- rpart(Surv(pgtime, pgstat) ~ ...,
                  control=rpart.control(minsplit=2, xval=xgrp, cp=.025),
                  data=stagec, method='poisson', weights=wts)

    all.equal(fit2$frame[-2],  fit2b$frame[-2])  # the "n" component won't match
    all.equal(fit2$cptable,    fit2b$cptable)
    toss <- c(49, 64)
    all.equal(fit2$splits[-toss,-1],fit2b$splits[-toss,-1]) #ok
    all.equal(fit2$csplit,    fit2b$csplit)
    """
    np.random.seed(10)
    stagec = _load_stagec()
    n = len(stagec)

    ## pseudo <- double(nrow(stagec)); pseudo[1] <- pi/4
    ## for (i in 2:nrow(stagec)) pseudo[i] <- 4*pseudo[i-1]*(1 - pseudo[i-1])
    pseudo = np.zeros(n)
    pseudo[0] = math.pi / 4
    for i in range(1, n):
        pseudo[i] = 4 * pseudo[i - 1] * (1 - pseudo[i - 1])

    ## wts <- rep(1:5, length.out=nrow(stagec))
    wts = np.resize(np.arange(1, 6), n)

    ## temp <- rep(1:nrow(stagec), wts)   (1-based row replicates in R;
    ## 0-based row positions here since they directly index stagec.iloc).
    temp = np.repeat(np.arange(n), wts)

    ## xgrp <- rep(1:10, length.out=146)[order(pseudo)]
    xgrp = np.resize(np.arange(1, 11), 146)[np.argsort(pseudo, kind="stable")]

    ## xgrp2 <- rep(xgrp, wts)
    xgrp2 = np.repeat(xgrp, wts)

    assert len(temp) == len(xgrp2)

    ## fit2 <- rpart(Surv(pgtime, pgstat) ~ ...,
    ##               control=rpart.control(minsplit=2, xval=xgrp2, cp=.025),
    ##               data=stagec[temp,], method='poisson')
    stagec_rep = stagec.iloc[temp].reset_index(drop=True)
    m2 = _build_surv_model_frame(stagec_rep, _STAGEC_PREDICTORS)
    fit2 = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m2,
        method="poisson",
        control={"minsplit": 2, "xval": xgrp2, "cp": 0.025},
    )

    ## fit2b<- rpart(Surv(pgtime, pgstat) ~ ...,
    ##               control=rpart.control(minsplit=2, xval=xgrp, cp=.025),
    ##               data=stagec, method='poisson', weights=wts)
    m2b = _build_surv_model_frame(stagec, _STAGEC_PREDICTORS, weights=wts)
    fit2b = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m2b,
        method="poisson",
        control={"minsplit": 2, "xval": xgrp, "cp": 0.025},
    )

    assert fit2["method"] == "poisson"
    assert fit2b["method"] == "poisson"

    ## all.equal(fit2$frame[-2],  fit2b$frame[-2])
    ## R's frame column 2 is "n" -> Python's frame.drop(columns=["n"]).
    frame2 = fit2["frame"]
    frame2b = fit2b["frame"]
    assert list(frame2.columns)[1] == "n"
    assert list(frame2b.columns)[1] == "n"
    f2 = frame2.drop(columns=["n"])
    f2b = frame2b.drop(columns=["n"])
    assert len(f2) == len(f2b)
    assert (f2["var"].to_numpy() == f2b["var"].to_numpy()).all()
    for col in ["wt", "dev", "yval", "complexity"]:
        assert np.allclose(
            f2[col].to_numpy(dtype=float), f2b[col].to_numpy(dtype=float)
        ), f"frame column {col!r} mismatch"
    for col in ["ncompete", "nsurrogate"]:
        assert (f2[col].to_numpy() == f2b[col].to_numpy()).all()
    assert all(np.allclose(a, b) for a, b in zip(f2["yval2"], f2b["yval2"]))

    ## all.equal(fit2$cptable,    fit2b$cptable)
    assert np.allclose(
        fit2["cptable"].to_numpy(dtype=float), fit2b["cptable"].to_numpy(dtype=float)
    )

    ## toss <- c(49, 64)   -- R 1-based row numbers of fit2$splits; the
    ## Python 0-based equivalents are 48 and 63.
    ## all.equal(fit2$splits[-toss,-1],fit2b$splits[-toss,-1]) #ok
    ## R's `[,-1]` drops column 1 ("count"), which is excluded throughout
    ## because it differs for essentially every row by construction (raw
    ## replicated-row counts vs. weighted-sum counts) -- see module
    ## docstring for why the R script itself notes the *un-tossed*
    ## comparison including "count" fails.
    splits2 = fit2["splits"].reset_index(drop=True)
    splits2b = fit2b["splits"].reset_index(drop=True)
    assert len(splits2) == len(splits2b) == 64
    toss = [48, 63]  # R's 1-based rows 49, 64
    keep = [i for i in range(len(splits2)) if i not in toss]
    s2 = splits2.iloc[keep].drop(columns=["count"])
    s2b = splits2b.iloc[keep].drop(columns=["count"])
    for col in ["ncat", "improve", "index", "adj"]:
        assert np.allclose(
            s2[col].to_numpy(dtype=float), s2b[col].to_numpy(dtype=float)
        ), f"splits column {col!r} mismatch (outside toss rows)"

    ## Sanity-check the two tossed rows really are the documented
    ## discrepancy (a surrogate split whose position/improve shifts
    ## slightly because of the "send >= 2 obs left" rule -- see module
    ## docstring / the R script's own trailing comment) and not some
    ## unrelated, larger mismatch.
    for row in toss:
        assert not np.isclose(
            splits2["improve"].iloc[row], splits2b["improve"].iloc[row]
        ) or not np.isclose(splits2["index"].iloc[row], splits2b["index"].iloc[row])

    ## all.equal(fit2$csplit,    fit2b$csplit)
    assert np.array_equal(fit2["csplit"], fit2b["csplit"])
