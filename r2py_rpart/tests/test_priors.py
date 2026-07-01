"""Python translation of rpart/tests/priors.R.

Original R script
------------------
    #
    # A hard-core test of losses and priors
    #  Simple data set where I know what the answers must be
    #
    library(rpart)
    aeq <- function(x,y, ...) all.equal(as.vector(x), as.vector(y), ...)

    dummy <- c(3,1,4,1,5,9,2,6,5,3,5,8,9,7,9)/5
    pdata <- data.frame(y=factor(rep(1:3, 5)),
                        x1 = 1:15,
                        x2 = c(1:6, 1:6, 1:3),
                        x3 = (rep(1:3, 5) + dummy)*10)

    pdata$x3[c(1,5,10)] <- NA
    pdata$y[15] <- 1     # make things unbalanced

    set.seed(10)
    pfit <- rpart(y ~ x1 + x2 + x3, pdata,
                  cp=0, xval=0, minsplit=5, maxdepth=1,
                  parms=list(prior=c(.2, .3, .5),
                             loss =matrix(c(0,2,2,2,0,6,1,1,0), 3,3,byrow=T)))

    #
    # See section 12.1 of the report for these numbers
    #

    ntot   <- c(6,5,4)
    phat   <- c(6,5,4)/15   # observed class probabilities
    prior  <- c(.2, .3, .5) # priors
    aprior <- c(4,12,5)/21  # altered priors
    lmat   <- matrix(c(0,1,2, 2,0,1, 2,6,0), ncol=3)  #loss matrix

    gini <- function(p) 1-sum(p^2)
    loss <- function(n, class)  sum(n * lmat[,class])

    phat <- function(n, ntot=c(6,5,4), prior=c(.2, .3, .5)) {
        n*prior/ntot
        }

    # Are the losses correct?
    # Class counts for the two children are (4,4,0) and (2,1,4), when
    #   using surrogates
    aeq(pfit$frame$dev/15, c(loss(prior,2), loss(phat(c(4,4,0)),2),
                                     loss(phat(c(2,1,4)),3)))
    # Node probabilities?
    aeq(pfit$frame$yval2[,8] ,
        c(1, sum(phat(c(4,4,0))), sum(phat(c(2,1,4)))))

    aeq(pfit$frame$yval2[,5:7] , rbind(prior,
                                       phat(c(4,4,0))/ sum(phat(c(4,4,0))),
                                       phat(c(2,1,4))/ sum(phat(c(2,1,4)))))

    # Now the node and class probs, under altered priors
    phat2 <- function(n, ntot=c(6,5,4), prior=aprior) {
        n*prior/ntot
        }

    # Use these to create the gini losses, base data, and for the best
    #  splits on variables 1, 2, 3
    gfun <- function(n) {  #The gini loss for a node, given the counts
        temp <- phat2(n)
        sum(temp) * gini(temp/sum(temp))
        }

    # These are in order x3, x2, x1 (best split to worst)
    # Note that for x3, missing values cause the "parent" to be viewed as
    #   having 12 obs instead of 15.
    # Each line is gini(parent) - gini(children)
    aeq(pfit$splits[1:3, 3],
        15* c(gfun(c(4,4,4)) - (gfun(c(3,4,0)) +  gfun(c(1,0,4))),
              gfun(c(6,5,4)) - (gfun(c(6,5,2)) +  gfun(c(0,0,2))),
              gfun(c(6,5,4)) - (gfun(c(4,4,4)) +  gfun(c(2,1,0)))))

This is a "hard-core" numeric check of rpart()'s classification (Gini)
splitting under a non-uniform ``prior`` and a non-symmetric ``loss``
matrix, on a small synthetic 15-row/3-class dataset where the exact
node deviances, class-probability vectors, and split-improvement values
are all known analytically and re-derived independently in the test
itself (rather than merely re-run through a second rpart() call).

Data construction
------------------
``dummy``/``pdata`` build a 15-row data frame: ``y`` cycles 1,2,3,1,2,
3,... (5 full cycles, so 5 observations per class before the manual
tweak below), ``x1`` is just the row number 1..15, ``x2`` cycles 1..6,
1..6, 1..3, and ``x3`` is ``(cycle-of-1,2,3 + dummy/5-scaled-noise) *
10``. Three ``x3`` values (rows 1, 5, 10 in R's 1-based indexing, i.e.
positions 0, 4, 9 in 0-based Python indexing) are set to ``NA``, and
the last observation's class is forced from 3 to 1 ("make things
unbalanced"), giving final class counts (6, 5, 4) for classes (1, 2,
3) -- this asymmetry is what ``ntot <- c(6,5,4)`` below encodes.

``rpart(y ~ x1 + x2 + x3, pdata, cp=0, xval=0, minsplit=5, maxdepth=1,
parms=list(prior=c(.2,.3,.5), loss=matrix(c(0,2,2,2,0,6,1,1,0), 3, 3,
byrow=TRUE)))`` -> ``r2py_rpart.rpart()`` with the equivalent
``parms={"prior": [.2, .3, .5], "loss": np.array([[0,2,2],[2,0,6],
[1,1,0]])}``. R's ``matrix(..., byrow=TRUE)`` fills row-by-row, which
is exactly the natural (row-major) layout of a Python
``numpy.array([[...], [...], [...]])`` literal written out row by row,
so no transpose/reorder is needed translating that one call -- the
resulting 3x3 loss matrix is identical element-for-element in both
languages: row i, column j is the cost of predicting class j when the
true class is i (see ``lmat`` below, which is this same matrix's
transpose, used for the independent verification arithmetic in this
test).

A real library bug surfaced by this test
------------------------------------------
This test's reference calculation (matching the R script's ``aeq``
checks against ``pfit$frame$dev`` and ``pfit$frame$yval2``) initially
FAILED against the pre-existing ``r2py_rpart.rpart()`` on the root
node's predicted class (``yval``): R predicts class 2 at the root
(``frame$yval2[1,1] == 2``, ``dev[1]/15 == 0.9``), while
``r2py_rpart.rpart()`` was predicting class 3 (``dev[1]/15 == 0.5``).
Both children's class counts/probabilities (rows 2-3 of ``yval2``)
matched R exactly, isolating the discrepancy to how the ``loss``
matrix reaches the underlying (shared, unmodified) C splitting code.

Root cause, found in ``r2py_rpart/rpart.py``: R's C entry point expects
a single flat ``parms`` vector built by ``as.double(unlist(init$parms))``,
where ``init$parms$loss`` is an R matrix -- and R matrices are *always*
stored column-major internally, so ``unlist()`` on a list containing a
matrix yields that matrix's underlying column-major storage vector
as-is. In the Python port, ``rpart_class()`` represents the same loss
matrix as a genuine 2-D ``numpy`` array (row-major storage), and
``rpart()`` flattened every ``parms`` value (prior, loss, ...) with a
plain ``.ravel()`` (row-major/`order='C'`) before handing the flat
vector to the C code. For the ``prior`` vector (1-D) this is a no-op,
but for the (non-symmetric) ``loss`` matrix, row-major-raveling
``[[0,2,2],[2,0,6],[1,1,0]]`` produces ``[0,2,2, 2,0,6, 1,1,0]``, while
R's column-major flattening of the *identical* matrix produces
``[0,2,1, 2,0,1, 2,6,0]`` -- a different vector whenever the matrix
isn't symmetric, which silently corrupts the loss values ``giniinit()``
(``rpart/src/gini.c``) reads out of ``parm[]`` for anything but a
uniform 0/1 loss matrix. This was fixed in ``rpart.py`` by raveling any
``ndim >= 2`` parms value (e.g. ``loss``) in Fortran/column-major order
(``.ravel(order='F')``) to exactly reproduce R's ``unlist()`` byte
layout, while still using ordinary (row-major, a no-op for 1-D arrays)
raveling for the ``prior`` vector and any other 1-D parms entries.
After the fix, ``r2py_rpart.rpart()``'s root-node ``yval``/``dev``/
``yval2`` match R's reference output exactly (verified against a live
``Rscript`` run of the original R test file with the installed R
``rpart`` package, in addition to the analytic recomputation this test
performs independently below), and the pre-existing test suite
(``tests/test_backticks.py``, ``test_cost.py``, ``test_cptest.py``,
``test_minus_in_formula.py``, ``test_rpart.py``) continues to pass
unaffected, since none of those exercise a non-symmetric ``parms``
matrix.

Mapping the ``aeq``/analytic checks to Python
------------------------------------------------
``aeq(x, y)`` -> ``numpy.allclose(x, y)`` (R's ``all.equal`` on numeric
vectors is a relative-difference numeric comparison; ``np.allclose``
mirrors this closely enough here, and we also compare directly against
hard reference numbers pulled from a live R run for extra precision).

``pfit$frame$dev`` -> ``pfit["frame"]["dev"]`` (a plain ``pandas``
column, one value per node/row, in the same node order as R's
``frame``: root first, then children in the order the C code emits
them -- row order is preserved end to end so no reindexing is needed).

``pfit$frame$yval2`` -> R stores ``yval2`` as one matrix column
attached to the data-frame-like ``frame`` object, with columns (for a
3-class problem) ``[yval, count_1, count_2, count_3, yprob_1, yprob_2,
yprob_3, nodeprob]`` (columns 1, 2:4, 5:7, 8 respectively, 1-based).
``r2py_rpart.rpart()`` stores the equivalent per-row data as a Python
list of 1-D ``numpy`` arrays under ``frame["yval2"]``, one array per
node, with the *same* column layout/order (``numpy`` 0-based indexing:
``arr[0]`` = yval, ``arr[1:4]`` = counts, ``arr[4:7]`` = yprob,
``arr[7]`` = nodeprob) -- so R's ``frame$yval2[,8]`` becomes stacking
the per-row arrays and indexing column 7, and R's ``frame$yval2[,5:7]``
becomes indexing columns 4:7.

``pfit$splits[1:3, 3]`` -> R's ``splits`` matrix column 3 is
``improve``; the first three rows are, by construction of this test
(``maxdepth=1`` and R's `<leaf>`-then-competitors row ordering),
the primary root split (best, on ``x3``) followed by its top two
competitor splits (on ``x2`` and ``x1``, in decreasing improvement
order) -- see the R comment "These are in order x3, x2, x1 (best split
to worst)". The Python ``splits`` ``pandas.DataFrame`` has an
``"improve"`` column and is row-indexed by variable name in the same
order the C code emits them, so ``splits.iloc[:3]["improve"]`` is the
direct equivalent (Python's ``.iloc[:3]`` selecting the first three
rows matches R's 1-based, inclusive ``[1:3, ]`` selecting the same
first three rows).

1-based vs. 0-based indexing
-------------------------------
``pdata$x3[c(1,5,10)] <- NA`` (R, 1-based row numbers 1, 5, 10) ->
``pdata.loc[[0, 4, 9], "x3"] = np.nan`` (0-based positions 0, 4, 9,
i.e. the same three physical rows). ``pdata$y[15] <- 1`` -> the last
row, 0-based position ``14`` (``len(pdata) - 1``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from r2py_rpart import rpart


def _aeq(x: np.ndarray, y: np.ndarray, rtol: float = 1.5e-8, atol: float = 0.0) -> bool:
    """Python equivalent of the R script's local ``aeq()`` helper:
    ``aeq <- function(x,y,...) all.equal(as.vector(x), as.vector(y), ...)``.
    ``all.equal()`` for numeric vectors is a relative-difference check
    with a default tolerance of about 1.5e-8, which ``numpy.allclose``
    with a matching ``rtol`` and ``atol=0`` mirrors closely enough here.
    """
    return bool(np.allclose(np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel(), rtol=rtol, atol=atol))


def _build_pdata() -> pd.DataFrame:
    ## dummy <- c(3,1,4,1,5,9,2,6,5,3,5,8,9,7,9)/5
    dummy = np.array([3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9], dtype=float) / 5

    ## pdata <- data.frame(y=factor(rep(1:3, 5)),
    ##                     x1 = 1:15,
    ##                     x2 = c(1:6, 1:6, 1:3),
    ##                     x3 = (rep(1:3, 5) + dummy)*10)
    y_cycle = np.tile(np.array([1, 2, 3]), 5)
    y = pd.Categorical(y_cycle)
    x1 = np.arange(1, 16)
    x2 = np.concatenate([np.arange(1, 7), np.arange(1, 7), np.arange(1, 4)])
    x3 = (y_cycle.astype(float) + dummy) * 10

    pdata = pd.DataFrame({"y": y, "x1": x1, "x2": x2, "x3": x3})

    ## pdata$x3[c(1,5,10)] <- NA   (R 1-based rows 1,5,10 -> 0-based 0,4,9)
    pdata.loc[[0, 4, 9], "x3"] = np.nan

    ## pdata$y[15] <- 1     # make things unbalanced (0-based row 14)
    pdata.loc[14, "y"] = 1

    return pdata


def test_priors_and_losses():
    pdata = _build_pdata()

    ## set.seed(10)
    ## pfit <- rpart(y ~ x1 + x2 + x3, pdata,
    ##               cp=0, xval=0, minsplit=5, maxdepth=1,
    ##               parms=list(prior=c(.2, .3, .5),
    ##                          loss=matrix(c(0,2,2,2,0,6,1,1,0), 3,3,byrow=T)))
    np.random.seed(10)
    loss = np.array([[0, 2, 2], [2, 0, 6], [1, 1, 0]], dtype=float)
    pfit = rpart(
        "y ~ x1 + x2 + x3",
        data=pdata,
        cp=0,
        xval=0,
        minsplit=5,
        maxdepth=1,
        parms={"prior": [0.2, 0.3, 0.5], "loss": loss},
    )

    frame = pfit["frame"]
    ## Root node splits into exactly two leaves under maxdepth=1.
    assert len(frame) == 3
    assert list(frame["var"]) == ["x3", "<leaf>", "<leaf>"]

    ## ntot   <- c(6,5,4)
    ## prior  <- c(.2, .3, .5) # priors
    ## aprior <- c(4,12,5)/21  # altered priors
    ## lmat   <- matrix(c(0,1,2, 2,0,1, 2,6,0), ncol=3)  #loss matrix
    ## R's matrix() fills column-major (no byrow=T here), so the flat
    ## literal c(0,1,2, 2,0,1, 2,6,0) becomes columns (0,1,2), (2,0,1),
    ## (2,6,0) -- i.e. rows (0,2,2), (1,0,6), (2,1,0).
    prior = np.array([0.2, 0.3, 0.5])
    aprior = np.array([4, 12, 5]) / 21
    lmat = np.array([0, 1, 2, 2, 0, 1, 2, 6, 0], dtype=float).reshape(3, 3, order="F")

    ## gini <- function(p) 1-sum(p^2)
    ## loss <- function(n, class)  sum(n * lmat[,class])
    def gini(p: np.ndarray) -> float:
        return 1 - np.sum(np.square(p))

    def loss_fn(n: np.ndarray, cls: int) -> float:
        ## R's `class` is a 1-based column index into lmat; Python's `cls`
        ## keeps that same 1-based convention and subtracts 1 when indexing.
        return float(np.sum(np.asarray(n) * lmat[:, cls - 1]))

    ## phat <- function(n, ntot=c(6,5,4), prior=c(.2, .3, .5)) { n*prior/ntot }
    def phat(n: np.ndarray, ntot: np.ndarray = np.array([6, 5, 4], dtype=float), prior_: np.ndarray = prior) -> np.ndarray:
        return np.asarray(n, dtype=float) * prior_ / ntot

    ## Are the losses correct?
    ## Class counts for the two children are (4,4,0) and (2,1,4), when
    ##   using surrogates
    ## aeq(pfit$frame$dev/15, c(loss(prior,2), loss(phat(c(4,4,0)),2),
    ##                                  loss(phat(c(2,1,4)),3)))
    dev_over_15 = frame["dev"].to_numpy(dtype=float) / 15
    expected_dev = np.array([
        loss_fn(prior, 2),
        loss_fn(phat(np.array([4, 4, 0])), 2),
        loss_fn(phat(np.array([2, 1, 4])), 3),
    ])
    assert _aeq(dev_over_15, expected_dev)
    ## Cross-checked against a live R run of the original script (see
    ## module docstring): dev/15 == (0.9, 0.26666667, 0.49333333).
    assert np.allclose(dev_over_15, [0.9, 0.266666667, 0.493333333])

    ## Node probabilities?
    ## aeq(pfit$frame$yval2[,8] ,
    ##     c(1, sum(phat(c(4,4,0))), sum(phat(c(2,1,4)))))
    yval2 = np.vstack(frame["yval2"].to_numpy())
    assert yval2.shape == (3, 8)
    nodeprob = yval2[:, 7]
    expected_nodeprob = np.array([
        1.0,
        np.sum(phat(np.array([4, 4, 0]))),
        np.sum(phat(np.array([2, 1, 4]))),
    ])
    assert _aeq(nodeprob, expected_nodeprob)

    ## aeq(pfit$frame$yval2[,5:7] , rbind(prior,
    ##                                    phat(c(4,4,0))/ sum(phat(c(4,4,0))),
    ##                                    phat(c(2,1,4))/ sum(phat(c(2,1,4)))))
    yprob = yval2[:, 4:7]
    expected_yprob = np.vstack([
        prior,
        phat(np.array([4, 4, 0])) / np.sum(phat(np.array([4, 4, 0]))),
        phat(np.array([2, 1, 4])) / np.sum(phat(np.array([2, 1, 4]))),
    ])
    assert _aeq(yprob, expected_yprob)

    ## Root node's predicted class (yval2[,1]) must be class 2, matching R
    ## exactly -- this is the value a `.ravel()` (row-major) vs.
    ## `.ravel(order='F')` (column-major) flattening bug in the `loss`
    ## matrix used to get wrong (predicting class 3 instead), see module
    ## docstring.
    assert yval2[0, 0] == 2
    assert yval2[1, 0] == 2
    assert yval2[2, 0] == 3

    ## Now the node and class probs, under altered priors
    ## phat2 <- function(n, ntot=c(6,5,4), prior=aprior) { n*prior/ntot }
    def phat2(n: np.ndarray, ntot: np.ndarray = np.array([6, 5, 4], dtype=float), prior_: np.ndarray = aprior) -> np.ndarray:
        return np.asarray(n, dtype=float) * prior_ / ntot

    ## gfun <- function(n) {  #The gini loss for a node, given the counts
    ##     temp <- phat2(n)
    ##     sum(temp) * gini(temp/sum(temp))
    ##     }
    def gfun(n: np.ndarray) -> float:
        temp = phat2(n)
        return float(np.sum(temp) * gini(temp / np.sum(temp)))

    ## These are in order x3, x2, x1 (best split to worst)
    ## Note that for x3, missing values cause the "parent" to be viewed as
    ##   having 12 obs instead of 15.
    ## Each line is gini(parent) - gini(children)
    ## aeq(pfit$splits[1:3, 3],
    ##     15* c(gfun(c(4,4,4)) - (gfun(c(3,4,0)) +  gfun(c(1,0,4))),
    ##           gfun(c(6,5,4)) - (gfun(c(6,5,2)) +  gfun(c(0,0,2))),
    ##           gfun(c(6,5,4)) - (gfun(c(4,4,4)) +  gfun(c(2,1,0)))))
    splits = pfit["splits"]
    assert list(splits.index[:3]) == ["x3", "x2", "x1"]
    improve_first3 = splits["improve"].to_numpy(dtype=float)[:3]
    expected_improve = 15 * np.array([
        gfun(np.array([4, 4, 4])) - (gfun(np.array([3, 4, 0])) + gfun(np.array([1, 0, 4]))),
        gfun(np.array([6, 5, 4])) - (gfun(np.array([6, 5, 2])) + gfun(np.array([0, 0, 2]))),
        gfun(np.array([6, 5, 4])) - (gfun(np.array([4, 4, 4])) + gfun(np.array([2, 1, 0]))),
    ])
    assert _aeq(improve_first3, expected_improve)
    ## Cross-checked against a live R run of the original script:
    ## improve[1:3] == (3.9876305, 1.9121162, 0.2904946).
    assert np.allclose(improve_first3, [3.9876305, 1.9121162, 0.2904946], rtol=1e-6)
