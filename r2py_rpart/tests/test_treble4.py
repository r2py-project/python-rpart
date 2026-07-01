"""Python translation of rpart/tests/treble4.R.

Original R script
------------------
    #
    # Treble test for class trees with 2 outcomes
    #
    # fit1 and fit1b failed equality because .7 and .3 are not easily represented
    # in binary.  Thus a complelxity param was 4e-17 (basically 0, but enough
    # to cause a split where it shouldn't be). Eric Lunde 2005-08-03
    library(rpart)
    control <- rpart.control(maxsurrogate=0, cp=1e-15, xval=0)
    set.seed(10)

    fit1 <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                  control=control,
                  parms=list(prior=c(.7,.3),
                    loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    wts <- rep(3, nrow(kyphosis))
    fit1b <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                   control=control,
                   weights=wts,
                   parms=list(prior=c(.7,.3),
                     loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    fit1b$frame$wt   <- fit1b$frame$wt/3
    fit1b$frame$dev  <- fit1b$frame$dev/3
    fit1b$frame$yval2[,2:3] <- fit1b$frame$yval2[,2:3]/3
    fit1b$splits[,3] <- fit1b$splits[,3]/3
    fit1b$variable.importance <- fit1b$variable.importance/3
    all.equal(fit1[-3], fit1b[-3])   #all but the "call"

    # Now for a set of non-equal weights
    nn <- nrow(kyphosis)
    pseudo <- double(nn)
    pseudo[1] <- pi/6
    for (i in 2:nn) pseudo[i] <- 4*pseudo[i-1]*(1-pseudo[i-1])

    wts <-  rep(1:7, length.out=nn)
    temp <- rep(1:nn, wts)             #row replicates
    xgrp <- rep(1:10, length.out=nn)[order(pseudo)]
    xgrp2<- rep(xgrp, wts)

    # The cp value stops one last split where the two predictors are
    #  completely equal in importance (perfect surrogates), but the
    #  weighted and unweighted pick a different one due to round off error
    tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0, cp=.039)
    #  Direct: replicate rows in the data set, and use unweighted
    fit2 <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis[temp,],
                   control=tempc,
                   parms=list(prior=c(.7,.3),
                              loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    #  Weighted
    tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0, cp=.039)
    fit2b <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                   control=tempc, weights=wts,
                   parms=list(prior=c(.7,.3),
                              loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))

    all.equal(fit2$frame[,-2],  fit2b$frame[,-2])  # the "n" component won't match
    all.equal(fit2$cptable, fit2b$cptable)
    all.equal(fit2$splits[,-1],fit2b$splits[,-1])
    all.equal(fit2$csplit,    fit2b$csplit)

This is the 2-class-classification analogue of ``treble.R``/``treble2.R``/
``treble3.R``'s weight-trebling tests, fit to rpart's built-in
``kyphosis`` dataset (spinal-surgery outcomes: ``Kyphosis`` present/absent
~ ``Age`` + ``Number`` + ``Start``), using the ordinary formula-string +
``data=`` + ``weights=`` + ``parms=`` code path (like ``treble2.R``/
``treble3.R``, unlike ``treble.R``'s hand-built ``Surv()`` model frame).
Every ``all.equal()`` call in the R script is a bare, unassigned
top-level expression (auto-printed, never actually checked by the R
script itself) -- all were independently re-verified against a live
``Rscript`` run of the original script (using the installed R ``rpart``
package's built-in ``kyphosis`` data) before writing the ``assert``
statements below, confirming every one does evaluate to ``TRUE``.

``kyphosis`` dataset
---------------------
Not previously exported by any earlier conversion in this batch (unlike
``cu.summary``/``mystate``/``stagec``, which were reused from
``test_testall.py``/``test_cptest.py``/``test_priors.py``'s fixtures), so
exported fresh here as ``r2py_rpart/tests/data/kyphosis.csv`` via
``Rscript -e 'library(rpart); write.csv(kyphosis, "kyphosis.csv",
row.names=FALSE)'``, following the same pattern as the pre-existing
fixtures. 81 rows, 4 columns: ``Kyphosis`` (factor, levels ``"absent"``,
``"present"`` in that order -- verified via ``str(kyphosis)`` against the
live R session used to export the fixture), ``Age``, ``Number``, ``Start``
(all integer).

R's ``parms=list(prior=c(.7,.3), loss=matrix(c(0,1,2,0),nrow=2,ncol=2))``
--------------------------------------------------------------------------
R's ``matrix(c(0,1,2,0), nrow=2, ncol=2)`` fills **column-major** (no
``byrow=TRUE``): the flat vector ``0,1,2,0`` becomes column 1 = ``(0,1)``,
column 2 = ``(2,0)``, i.e. the matrix
::
    [[0, 2],
     [1, 0]]
(row 1 = "true class 1", column 2 = "predicted class 2" costs 2; row 2 =
"true class 2", column 1 = "predicted class 1" costs 1) -- translated
directly as the Python 2-D literal ``numpy.array([[0., 2.], [1., 0.]])``,
matching ``test_priors.py``'s established handling of this exact
column-major-vs-row-major distinction (and the ``rpart.py`` fix
documented there, which Fortran/column-major-ravels any ``ndim >= 2``
``parms`` entry before handing it to the underlying C code -- this test
exercises that same code path with a small, non-symmetric loss matrix).

Part 1: fit1 (unweighted) vs. fit1b (weight=3)
------------------------------------------------
``rpart.control(maxsurrogate=0, cp=1e-15, xval=0)`` -> ``control=
{"maxsurrogate": 0, "cp": 1e-15, "xval": 0}``, a plain dict forwarded to
``rpart_control(**dict)`` exactly as R's ``rpart.control()`` return value
would be (same convention as every other conversion in this batch).

``wts <- rep(3, nrow(kyphosis))`` -> ``numpy.full(n, 3.0)``.

Undoing the trebling on ``fit1b``'s components before comparison:
``fit1b$frame$wt <- fit1b$frame$wt/3``, ``fit1b$frame$dev <-
fit1b$frame$dev/3`` -> straightforward column division on a copy of the
Python frame.

``fit1b$frame$yval2[,2:3] <- fit1b$frame$yval2[,2:3]/3`` -- verified via a
live ``Rscript`` probe (``ncol(fit1$frame$yval2)`` == 6, ``colnames``
``yval2.V1..yval2.V5, yval2.nodeprob``) that for this 2-class response,
R's ``yval2`` has exactly 6 columns in order: ``yval`` (1), the two raw
per-class weighted counts (2:3), the two per-class probabilities ("yprob",
4:5), and ``nodeprob`` (6) -- exactly mirroring ``rpart.py``'s
classification-branch ``yval2`` layout (``hstack([yval2, yprob,
nodeprob])`` with ``numclass=2``: width ``1 + 2 + 2 + 1 = 6``). So R's
1-based columns 2:3 (the two raw class-count columns, which scale
linearly with each observation's weight) are Python's 0-based columns
``1:3`` -- translated as ``yval2[:, 1:3] = yval2[:, 1:3] / 3`` on the
stacked ``yval2`` array, verified against the live R run to reproduce
``fit1$frame$yval2`` exactly after the /3 adjustment.

``fit1b$splits[,3] <- fit1b$splits[,3]/3`` -- R's ``splits`` matrix column
3 (1-based) is ``"improve"`` (columns: ``count``, ``ncat``, ``improve``,
``index``, ``adj``, matching ``test_treble3.py``'s established column
order) -- translated as dividing the ``"improve"`` column by 3 on a copy
of the Python ``splits`` DataFrame. Unlike ``treble.R``'s survival-tree
analogue (which had to conditionally divide by 1 vs. 3 depending on
whether a row was a primary or surrogate split, since ``maxsurrogate`` was
nonzero there), this test uses ``maxsurrogate=0`` so *every* row is a
primary split and the whole column scales uniformly by 3 -- verified
directly against the live R run.

``fit1b$variable.importance <- fit1b$variable.importance/3`` ->
``fit1b["variable.importance"] / 3`` (a ``pandas.Series`` keyed by
variable name, mirroring R's named numeric vector).

``all.equal(fit1[-3], fit1b[-3])`` (all top-level list components except
the 3rd, R's ``"call"``) -- since ``r2py_rpart.rpart()`` returns a plain
Python ``dict`` (not an ordered list where position 3 is reliably
"call"), this is translated as comparing every field **except** ``"call"``
by key, mirroring the task instructions' guidance for this exact case.
``r2py_rpart.rpart()``'s returned dict additionally carries several
implementation-only keys with no R analogue (``"terms"``, ``"functions"``,
``"numresp"``, ``"ordered"``, ``"_ylevels"``, ``"_rpart_class"``,
``"control"``) which are not present as top-level components of R's
``rpart()`` return value either (R stores them inside ``$terms``'s
attributes or not at all) -- these are skipped since there's nothing in
the R script's ``all.equal()`` call for them to correspond to; the
fields actually compared (``frame``, ``where``, ``cptable``, ``method``,
``parms``, ``splits``, ``variable.importance``, ``y``) are exactly the
public, R-equivalent components enumerated in ``?rpart.object``.

Part 2: replicated rows vs. weights=1:7 (fit2 vs. fit2b)
------------------------------------------------------------
Mirrors ``treble.R``/``treble2.R``'s "row replication vs. explicit
weights=" pattern, but -- per the task description -- this R script (
unlike ``treble.R``'s stagec/poisson analogue) documents **no** expected
discrepancy/toss-row list: the R comment explains the ``cp=.039`` control
value is specifically chosen to "stop one last split where the two
predictors are completely equal in importance," precisely to *avoid* the
round-off-driven divergence that would otherwise occur, so all four
``all.equal()`` calls (frame minus "n", cptable, splits minus "count",
csplit) are expected -- and live-verified -- to hold exactly.

``pseudo`` pseudo-random sequence (the logistic map, ``r=4``): ``pseudo[1]
<- pi/6; pseudo[i] <- 4*pseudo[i-1]*(1-pseudo[i-1])`` -> a literal Python
loop building a ``numpy`` array the same way (``pseudo[0] = np.pi/6``,
then ``pseudo[i] = 4*pseudo[i-1]*(1-pseudo[i-1])`` for ``i`` in
``1..nn-1``), reproducing the exact same deterministic real-valued
sequence bit-for-bit (both languages use IEEE-754 double arithmetic for
this recurrence), matching the identical idiom in ``treble.R``/
``treble2.R``.

``wts <- rep(1:7, length.out=nn)`` -> ``numpy.resize(numpy.arange(1, 8),
nn)`` (recycle-to-length idiom, same as ``treble.R``/``treble2.R``/
``treble3.R``).

``temp <- rep(1:nn, wts)`` (1-based row *numbers*, each repeated
``wts[i]`` times) -> ``numpy.repeat(numpy.arange(nn), wts)`` (0-based row
*positions*, for direct ``.iloc`` indexing), matching ``test_treble.py``/
``test_treble2.py``'s identical idiom.

``xgrp <- rep(1:10, length.out=nn)[order(pseudo)]`` -- R's ``order()``
returns the *permutation of indices* that would sort ``pseudo``
ascending (a stable sort for ties, though ``pseudo`` here has no exact
ties), used to subset/reorder the recycled ``1:10`` fold-group vector
into a "pseudo-random" shuffle -> ``numpy.resize(numpy.arange(1, 11),
nn)[numpy.argsort(pseudo, kind="stable")]`` (``numpy.argsort`` is the
direct equivalent of R's ``order()`` for a single numeric vector with no
ties, and ``kind="stable"`` matches R's stable-sort guarantee), the same
idiom used in ``treble.R``'s/``treble2.R``'s analogous ``xgrp <-
rep(...)[order(pseudo)]`` construction. Live-verified this produces the
exact same 81-element ``xgrp`` permutation as the R session used to
develop this test.

``xgrp2 <- rep(xgrp, wts)`` -> ``numpy.repeat(xgrp, wts)``.

``tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0,
cp=.039)`` / ``fit2 <- rpart(..., data=kyphosis[temp,], control=tempc,
...)`` (unweighted, on the replicated/expanded 318-row data) ->
``rpart(..., data=kyphosis.iloc[temp].reset_index(drop=True),
control=tempc, ...)``. The second ``tempc`` (``xval=xgrp``, unreplicated)
/ ``fit2b <- rpart(..., data=kyphosis, control=tempc, weights=wts, ...)``
(weighted, on the original 81-row data) -> the direct formula-string +
``data=`` + ``weights=`` translation.

``all.equal(fit2$frame[,-2], fit2b$frame[,-2])`` -- R's ``frame`` column 2
(1-based) is ``"n"`` (frame column order verified live: ``var, n, wt,
dev, yval, complexity, ncompete, nsurrogate``, then ``yval2`` appended) ->
``frame.drop(columns=["n"])`` on both sides, since the raw observation
count legitimately differs between the 318-row replicated fit and the
81-row weighted fit by construction (same reasoning as
``test_treble2.py``'s ``fit5``/``fit5b`` part 3).

``all.equal(fit2$splits[,-1], fit2b$splits[,-1])`` -- R's ``splits``
column 1 (1-based) is ``"count"`` -> ``splits.drop(columns=["count"])``
on both sides, for the same reason.

``all.equal(fit2$csplit, fit2b$csplit)`` -- ``kyphosis``'s three
predictors (``Age``, ``Number``, ``Start``) are all plain numeric/integer
columns with no categorical (factor) predictor, so **no** categorical
split ever occurs and R's ``fit2$csplit``/``fit2b$csplit`` are both
``NULL`` (live-verified: ``cat("fit2 csplit:\n"); print(fit2$csplit)``
prints ``NULL``) -- mirrored by ``r2py_rpart.rpart()``'s equivalent
``"csplit"`` dict entry, verified live to be Python ``None`` on both
fits, so the comparison is a direct ``is None`` check on each side rather
than an array comparison.

``all.equal`` -> ``numpy.allclose`` / exact equality, mirroring the
established convention across this whole batch's conversions: floating-
point columns/arrays compared with ``numpy.allclose`` (R's ``all.equal``
default relative-difference tolerance, ~1.5e-8), integer/string columns
(``var`` names, ``ncompete``/``nsurrogate``/``ncat``) compared for
bit-for-bit equality.

``set.seed(10)``
-------------------
Reproduced via ``numpy.random.seed(10)``. Part 1's ``xval=0`` (no
cross-validation) and Part 2's ``xval=`` are both explicit, deterministic
fold-group vectors, so no fit in this script actually draws random
cross-validation folds and the seed has no effect on any value checked
below -- set anyway for exact parity with the original script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart

_DATA = Path(__file__).parent / "data"
_KYPHOSIS_CSV = _DATA / "kyphosis.csv"

# R's factor(kyphosis$Kyphosis) default level order (verified against the
# R session used to export kyphosis.csv: str(kyphosis) shows
# "Factor w/ 2 levels "absent","present"").
_KYPHOSIS_LEVELS = ["absent", "present"]

_FORMULA = "Kyphosis ~ Age + Number + Start"

# parms=list(prior=c(.7,.3), loss=matrix(c(0,1,2,0),nrow=2,ncol=2))
# R's matrix(..., nrow=2, ncol=2) fills column-major: col1=(0,1), col2=(2,0).
_PRIOR = [0.7, 0.3]
_LOSS = np.array([[0.0, 2.0], [1.0, 0.0]])


def _load_kyphosis() -> pd.DataFrame:
    """Load rpart's built-in `kyphosis` dataset (81 rows), exported via
    `Rscript -e 'library(rpart); write.csv(kyphosis, "kyphosis.csv",
    row.names=FALSE)'` (see module docstring)."""
    kyph = pd.read_csv(_KYPHOSIS_CSV)
    kyph["Kyphosis"] = pd.Categorical(kyph["Kyphosis"], categories=_KYPHOSIS_LEVELS)
    return kyph


def _assert_frames_match(
    frame_a: pd.DataFrame,
    frame_b: pd.DataFrame,
    *,
    drop: list[str] | None = None,
) -> None:
    """Compare two rpart() 'frame' DataFrames column-by-column, mirroring
    R's all.equal() on a data.frame: 'var' (character) and
    'ncompete'/'nsurrogate' (integer) columns compared exactly, 'yval2'
    (list of per-row arrays) stacked and compared with numpy.allclose,
    all other numeric columns compared with numpy.allclose.
    """
    a = frame_a.drop(columns=drop) if drop else frame_a
    b = frame_b.drop(columns=drop) if drop else frame_b
    assert list(a.columns) == list(b.columns)
    assert len(a) == len(b)
    assert (a["var"].to_numpy() == b["var"].to_numpy()).all()
    for col in ["ncompete", "nsurrogate"]:
        assert (a[col].to_numpy() == b[col].to_numpy()).all(), f"frame column {col!r} mismatch"
    yval2_a = np.vstack(a["yval2"].to_numpy())
    yval2_b = np.vstack(b["yval2"].to_numpy())
    assert yval2_a.shape == yval2_b.shape
    assert np.allclose(yval2_a, yval2_b), "frame column 'yval2' mismatch"
    other_cols = [c for c in a.columns if c not in ("var", "ncompete", "nsurrogate", "yval2")]
    for col in other_cols:
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


def test_trebled_weights_class_tree_fit1_vs_fit1b() -> None:
    """control <- rpart.control(maxsurrogate=0, cp=1e-15, xval=0)
    fit1 <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                  control=control,
                  parms=list(prior=c(.7,.3),
                    loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    wts <- rep(3, nrow(kyphosis))
    fit1b <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                   control=control, weights=wts,
                   parms=list(prior=c(.7,.3),
                     loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    fit1b$frame$wt   <- fit1b$frame$wt/3
    fit1b$frame$dev  <- fit1b$frame$dev/3
    fit1b$frame$yval2[,2:3] <- fit1b$frame$yval2[,2:3]/3
    fit1b$splits[,3] <- fit1b$splits[,3]/3
    fit1b$variable.importance <- fit1b$variable.importance/3
    all.equal(fit1[-3], fit1b[-3])   #all but the "call"
    """
    np.random.seed(10)
    kyphosis = _load_kyphosis()
    n = len(kyphosis)

    control = {"maxsurrogate": 0, "cp": 1e-15, "xval": 0}
    fit1 = rpart(
        _FORMULA,
        data=kyphosis,
        control=control,
        parms={"prior": _PRIOR, "loss": _LOSS},
    )

    ## wts <- rep(3, nrow(kyphosis))
    wts = np.full(n, 3.0)
    fit1b = rpart(
        _FORMULA,
        data=kyphosis,
        control=control,
        weights=wts,
        parms={"prior": _PRIOR, "loss": _LOSS},
    )

    assert fit1["method"] == "class"
    assert fit1b["method"] == "class"

    ## fit1b$frame$wt   <- fit1b$frame$wt/3
    ## fit1b$frame$dev  <- fit1b$frame$dev/3
    frame1 = fit1["frame"]
    frame1b = fit1b["frame"].copy()
    frame1b["wt"] = frame1b["wt"] / 3
    frame1b["dev"] = frame1b["dev"] / 3

    ## fit1b$frame$yval2[,2:3] <- fit1b$frame$yval2[,2:3]/3
    ## R's 1-based yval2 columns 2:3 (the two raw per-class weighted
    ## counts, for this 2-class response) are Python's 0-based columns
    ## 1:3 (yval2 layout: col 0 = yval, cols 1:3 = per-class counts,
    ## cols 3:5 = yprob, col 5 = nodeprob -- see module docstring).
    yval2b = np.vstack(frame1b["yval2"].to_numpy())
    assert yval2b.shape == (len(frame1b), 6)
    yval2b[:, 1:3] = yval2b[:, 1:3] / 3
    frame1b["yval2"] = list(yval2b)

    ## fit1b$splits[,3] <- fit1b$splits[,3]/3
    ## R's splits column 3 (1-based) is "improve".
    splits1 = fit1["splits"]
    splits1b = fit1b["splits"].copy()
    assert list(splits1.columns) == list(splits1b.columns) == [
        "count", "ncat", "improve", "index", "adj",
    ]
    splits1b["improve"] = splits1b["improve"] / 3

    ## fit1b$variable.importance <- fit1b$variable.importance/3
    vi1 = fit1["variable.importance"]
    vi1b = fit1b["variable.importance"] / 3

    ## all.equal(fit1[-3], fit1b[-3])   #all but the "call"
    ## fit1/fit1b are plain dicts here (not R's 3rd-list-position "call"),
    ## so compare every field except "call" directly.
    _assert_frames_match(frame1, frame1b)
    assert np.array_equal(fit1["where"], fit1b["where"])
    assert list(vi1.index) == list(vi1b.index)
    assert np.allclose(vi1.to_numpy(dtype=float), vi1b.to_numpy(dtype=float))
    assert list(splits1.index) == list(splits1b.index)
    assert np.allclose(
        splits1.to_numpy(dtype=float), splits1b.to_numpy(dtype=float)
    )
    assert list(fit1["cptable"].columns) == list(fit1b["cptable"].columns)
    assert np.allclose(
        fit1["cptable"].to_numpy(dtype=float), fit1b["cptable"].to_numpy(dtype=float)
    )
    assert fit1["parms"]["prior"] == pytest.approx(fit1b["parms"]["prior"])
    assert np.array_equal(fit1["parms"]["loss"], fit1b["parms"]["loss"])
    ## fit1/fit1b's "y" component (encoded response) is unaffected by
    ## weighting, since weights only scale the *loss function*, not the
    ## observed response values themselves.
    assert np.array_equal(np.asarray(fit1["y"]), np.asarray(fit1b["y"]))


def test_replicated_rows_vs_weights_argument_match() -> None:
    """nn <- nrow(kyphosis)
    pseudo <- double(nn)
    pseudo[1] <- pi/6
    for (i in 2:nn) pseudo[i] <- 4*pseudo[i-1]*(1-pseudo[i-1])

    wts <-  rep(1:7, length.out=nn)
    temp <- rep(1:nn, wts)             #row replicates
    xgrp <- rep(1:10, length.out=nn)[order(pseudo)]
    xgrp2<- rep(xgrp, wts)

    tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0, cp=.039)
    fit2 <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis[temp,],
                   control=tempc,
                   parms=list(prior=c(.7,.3),
                              loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))
    tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0, cp=.039)
    fit2b <- rpart(Kyphosis ~ Age + Number + Start, data=kyphosis,
                   control=tempc, weights=wts,
                   parms=list(prior=c(.7,.3),
                              loss=matrix(c(0,1,2,0),nrow=2,ncol=2)))

    all.equal(fit2$frame[,-2],  fit2b$frame[,-2])  # the "n" component won't match
    all.equal(fit2$cptable, fit2b$cptable)
    all.equal(fit2$splits[,-1],fit2b$splits[,-1])
    all.equal(fit2$csplit,    fit2b$csplit)
    """
    np.random.seed(10)
    kyphosis = _load_kyphosis()
    nn = len(kyphosis)

    ## pseudo <- double(nn); pseudo[1] <- pi/6
    ## for (i in 2:nn) pseudo[i] <- 4*pseudo[i-1]*(1-pseudo[i-1])
    pseudo = np.zeros(nn)
    pseudo[0] = np.pi / 6
    for i in range(1, nn):
        pseudo[i] = 4 * pseudo[i - 1] * (1 - pseudo[i - 1])

    ## wts <-  rep(1:7, length.out=nn)
    wts = np.resize(np.arange(1, 8), nn)

    ## temp <- rep(1:nn, wts)             #row replicates
    ## (1-based row replicates in R; 0-based row positions here since
    ## they directly index kyphosis.iloc.)
    temp = np.repeat(np.arange(nn), wts)

    ## xgrp <- rep(1:10, length.out=nn)[order(pseudo)]
    xgrp = np.resize(np.arange(1, 11), nn)[np.argsort(pseudo, kind="stable")]

    ## xgrp2<- rep(xgrp, wts)
    xgrp2 = np.repeat(xgrp, wts)

    assert len(temp) == len(xgrp2) == 318

    ## tempc <- rpart.control(minsplit=2, xval=xgrp2, maxsurrogate=0, cp=.039)
    tempc_fit2 = {"minsplit": 2, "xval": xgrp2, "maxsurrogate": 0, "cp": 0.039}
    ## fit2 <- rpart(..., data=kyphosis[temp,], control=tempc, ...)
    kyphosis_rep = kyphosis.iloc[temp].reset_index(drop=True)
    fit2 = rpart(
        _FORMULA,
        data=kyphosis_rep,
        control=tempc_fit2,
        parms={"prior": _PRIOR, "loss": _LOSS},
    )

    ## tempc <- rpart.control(minsplit=2, xval=xgrp, maxsurrogate=0, cp=.039)
    tempc_fit2b = {"minsplit": 2, "xval": xgrp, "maxsurrogate": 0, "cp": 0.039}
    ## fit2b <- rpart(..., data=kyphosis, control=tempc, weights=wts, ...)
    fit2b = rpart(
        _FORMULA,
        data=kyphosis,
        control=tempc_fit2b,
        weights=wts,
        parms={"prior": _PRIOR, "loss": _LOSS},
    )

    assert fit2["method"] == "class"
    assert fit2b["method"] == "class"

    ## all.equal(fit2$frame[,-2],  fit2b$frame[,-2])  # the "n" component won't match
    ## R's frame column 2 (1-based) is "n".
    frame2 = fit2["frame"]
    frame2b = fit2b["frame"]
    assert list(frame2.columns)[1] == "n"
    assert list(frame2b.columns)[1] == "n"
    _assert_frames_match(frame2, frame2b, drop=["n"])

    ## all.equal(fit2$cptable, fit2b$cptable)
    assert list(fit2["cptable"].columns) == list(fit2b["cptable"].columns)
    assert np.allclose(
        fit2["cptable"].to_numpy(dtype=float), fit2b["cptable"].to_numpy(dtype=float)
    )

    ## all.equal(fit2$splits[,-1],fit2b$splits[,-1])
    ## R's splits column 1 (1-based) is "count".
    splits2 = fit2["splits"]
    splits2b = fit2b["splits"]
    assert list(splits2.columns)[0] == "count"
    assert list(splits2b.columns)[0] == "count"
    _assert_splits_match(splits2, splits2b, drop=["count"])

    ## all.equal(fit2$csplit,    fit2b$csplit)
    ## kyphosis's predictors (Age, Number, Start) are all numeric, so no
    ## categorical split ever occurs -- R's fit2$csplit/fit2b$csplit are
    ## both NULL (live-verified), mirrored here as both being None.
    assert fit2.get("csplit") is None
    assert fit2b.get("csplit") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
