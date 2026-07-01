"""Python translation of rpart/tests/xpred1.R.

Original R script
------------------
    #
    # Test out the "return.all" argument of xpred
    #   this is a very small test case for debugging
    #
    library(rpart)
    set.seed(10)

    tdata <- data.frame(y=1:12, x1= 12:1, x2=c(1,1,5,5,4,4,9,9,7,7,3,3))
    xgrp <- rep(1:3, length.out=12)

    fit1 <- rpart(y ~ x1 + x2, tdata, minsplit=6)
    xfit1 <- xpred.rpart(fit1, xval=xgrp, return.all=T)

    xfit2 <- array(0, dim=dim(xfit1))
    cplist <- as.numeric(dimnames(xfit1)[[2]])

    for (i in 1:3) {
        tfit <- rpart(y ~ x1+x2, tdata, subset=(xgrp !=i), minsplit=6)
        # xvals are actually done on the absolute risk (node's risk /n), not on
        #   the rescaled risk ((node risk)/ (top node risk)) which is the basis
        #   for the printed CP.  To get the right answer we need to rescale.
        cp2 <- cplist * (fit1$frame$dev[1] / fit1$frame$n[1]) /
                        (tfit$frame$dev[1] / tfit$frame$n[1])

        for (j in 1:length(cp2)) {
            tfit2 <- prune(tfit, cp=cp2[j])
            temp <- predict(tfit2, newdata=tdata[xgrp==i,], type='matrix')
            xfit2[xgrp==i, j] <- temp
            }
        }

    all.equal(xfit1, xfit2, check.attributes=FALSE)

This is a small, hand-computable debugging test for the ``return.all=TRUE``
argument of ``xpred.rpart``/``xpred_rpart``. It manually reimplements what
``xpred.rpart(..., return.all=TRUE)`` should be computing internally: for
each of the 3 cross-validation groups defined by ``xgrp``, fit a tree on the
subset of the data that excludes that group, rescale the "canonical" CP list
(taken from ``xfit1``'s CP dimension) from the *full*-fit's risk scale to
the *subset*-fit's absolute risk scale, prune the subset-fit's tree at each
rescaled CP, and predict (``type='matrix'``, i.e. the raw fitted value per
node -- for an anova-method single-response tree this is just the node
mean) on the held-out fold. Stacking these per-fold-per-cp predictions into
an array of the same shape as ``xfit1`` should reproduce ``xfit1`` exactly.

Data
----
``tdata`` is a tiny 12-row inline data frame (``y = 1:12``, ``x1 = 12:1``,
``x2`` an explicit vector) requiring no external fixture; it is defined
directly below exactly as in the R script. ``xgrp <- rep(1:3,
length.out=12)`` assigns cross-validation fold labels ``1,2,3,1,2,3,...``
cyclically across the 12 rows.

Mapping to Python
------------------
* ``rpart(y ~ x1+x2, tdata, minsplit=6)`` -> ``rpart("y ~ x1 + x2",
  data=tdata, minsplit=6, x=True)``. The ``x=True`` addition (not present
  in the R call) is required because R's fitted ``rpart`` object always
  retains an evaluable model frame internally (so ``xpred.rpart`` can
  reconstruct ``X``/``Y`` on demand via ``eval.parent(model.frame(...))``
  even when ``x=FALSE, y=FALSE``); the Python port instead requires the
  caller to explicitly cache the design matrix via ``x=True`` for
  ``xpred_rpart`` to have anything to reuse (see xpred_rpart.py's
  NotImplementedError when ``fit['x']`` is absent, and the identical
  ``x=True`` addition in the existing testall.R -> test_testall.py
  conversion's ``fit4`` call). ``y=True`` is unnecessary since it is
  r2py_rpart's ``rpart()`` default.
* ``xpred.rpart(fit1, xval=xgrp, return.all=T)`` ->
  ``xpred_rpart(fit1, xval=xgrp, return_all=True)``.
* ``dimnames(xfit1)[[2]]`` (the CP values used as the array's 2nd-dimension
  labels) -> r2py_rpart's ``xpred_rpart`` does not attach dimnames to its
  ndarray return value, so the same default CP list is recomputed directly
  from ``fit1``'s ``cptable`` using xpred_rpart.py's own (undocumented but
  code-visible) default-CP formula: ``cp <- sqrt(cp * c(10, cp[-length(cp)]));
  cp[1] <- (1 + cptable[1,1])/2`` (see xpred.rpart.R lines 61-65 and the
  identical logic in xpred_rpart.py's ``cp is _MISSING`` branch). Since
  ``xpred_rpart`` is called here without an explicit ``cp=`` argument (as
  in the R script), it is exactly this list that was used internally, so
  recomputing it independently and cross-checking below is a faithful,
  non-circular translation of ``dimnames(xfit1)[[2]]``.
* ``rpart(y ~ x1+x2, tdata, subset=(xgrp !=i), minsplit=6)`` -> passing a
  boolean mask directly to ``data=tdata.loc[xgrp != i]`` (r2py_rpart's
  ``rpart()`` does accept a ``subset=`` keyword taking a boolean array --
  see rpart.py / model_frame_rpart.py -- but per the existing testall.R ->
  test_testall.py conversion's established convention, pre-filtering
  ``data`` via ``.loc[mask]`` is used instead; both are equivalent here).
* ``fit1$frame$dev[1]`` / ``fit1$frame$n[1]`` (R's 1-based first row of the
  frame, i.e. the root node) -> ``fit1["frame"]["dev"].iloc[0]`` /
  ``fit1["frame"]["n"].iloc[0]`` (pandas' 0-based positional first row;
  r2py_rpart's ``frame`` DataFrame is indexed by the (1-based) rpart node
  id, so ``.iloc[0]`` -- not ``.loc[1]`` -- is the direct positional
  equivalent of R's ``[1]``, and happens to coincide with node id 1, the
  root, since the root is always the frame's first row).
* ``prune(tfit, cp=cp2[j])`` -> ``prune(tfit, cp=cp2[j])`` (r2py_rpart's
  ``prune()`` thinly dispatches to ``prune_rpart(tree, cp=...)``, mirroring
  R's ``UseMethod("prune")`` -> ``prune.rpart``).
* ``predict(tfit2, newdata=tdata[xgrp==i,], type='matrix')`` ->
  ``predict_rpart(tfit2, newdata=tdata.loc[xgrp == i], type='matrix')``.
  For this single-response ("anova") tree, ``type='matrix'`` returns one
  fitted value (the node mean) per observation, shaped ``(n_held_out, 1)``
  as a ``pandas.DataFrame``; converting to a flat ``numpy`` array before
  assigning into ``xfit2[xgrp==i, j]`` mirrors R's implicit matrix ->
  vector coercion on assignment into a numeric array slice.
* ``xfit2[xgrp==i, j] <- temp`` -> Python 0-based boolean-mask row
  indexing plus integer column indexing: ``xfit2[xgrp == i, j] = ...``.
* ``all.equal(xfit1, xfit2, check.attributes=FALSE)`` -> ``numpy.allclose``
  (ignoring attributes/dimnames on both sides, exactly as
  ``check.attributes=FALSE`` requests) plus an exact ``.shape`` check.

``xpred_rpart``'s ``return_all``/``numresp`` interaction
-----------------------------------------------------------
R's ``xpred.rpart`` only actually builds the 3-D
``array(pred, dim=c(numresp, length(cp), nrow(X)))`` / ``aperm()`` when
``return.all && numresp > 1``; the "anova" method used by this test has
``numresp == 1`` (see rpart.anova.R), so both R and r2py_rpart's
``xpred_rpart`` fall through to the plain 2-D
``(nrow(X), length(cp))``-shaped result whether or not ``return_all`` is
set. ``return.all=TRUE`` is passed here as in the original script (for
parity, and because it is literally what this test is exercising by name),
but its numeric effect on the output shape is a no-op for this
single-response method; ``xfit1.shape == (12, 3)`` is asserted explicitly
below to document this.

``set.seed(10)``
-----------------
``rpart()`` and ``xpred.rpart()`` only consume random draws to build
cross-validation groupings when ``xval`` is given as a scalar fold-count;
here ``xval=xgrp`` is always an explicit, fully-deterministic length-12
vector (both for the main ``xpred_rpart`` call and implicitly for each
``rpart()`` fit's own internal default 10-fold xval grouping, which is
computed but never consulted since ``cptable``'s ``xerror``/``xstd``
columns are not used by this test). ``numpy.random.seed(10)`` is set
anyway, mirroring the R script's ``set.seed(10)``, for exact parity/
reproducibility even though no test assertion here actually depends on it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from r2py_rpart import prune, predict_rpart, rpart, xpred_rpart


def test_xpred_return_all():
    ## set.seed(10)
    np.random.seed(10)

    ## tdata <- data.frame(y=1:12, x1= 12:1, x2=c(1,1,5,5,4,4,9,9,7,7,3,3))
    tdata = pd.DataFrame(
        {
            "y": np.arange(1, 13),
            "x1": np.arange(12, 0, -1),
            "x2": [1, 1, 5, 5, 4, 4, 9, 9, 7, 7, 3, 3],
        }
    )
    ## xgrp <- rep(1:3, length.out=12)
    xgrp = np.resize(np.arange(1, 4), 12)

    ## fit1 <- rpart(y ~ x1 + x2, tdata, minsplit=6)
    ## x=True: cache the design matrix so xpred_rpart() below can reuse it
    ## (R's fitted object always has an evaluable model frame available
    ## internally; see module docstring).
    fit1 = rpart("y ~ x1 + x2", data=tdata, minsplit=6, x=True)

    ## xfit1 <- xpred.rpart(fit1, xval=xgrp, return.all=T)
    xfit1 = xpred_rpart(fit1, xval=xgrp, return_all=True)

    ## "anova" method has numresp == 1, so return_all has no effect on the
    ## output shape here (see module docstring): (nobs, n_cp).
    assert xfit1.shape == (12, 3)

    ## xfit2 <- array(0, dim=dim(xfit1))
    xfit2 = np.zeros_like(xfit1, dtype=np.float64)

    ## cplist <- as.numeric(dimnames(xfit1)[[2]])
    ## Recompute the same default CP list that xpred_rpart used internally
    ## (no explicit cp= was passed), from fit1's cptable -- see module
    ## docstring for why this exactly mirrors dimnames(xfit1)[[2]].
    cptable = fit1["cptable"]
    cp_col0 = cptable["CP"].to_numpy(dtype=float)
    cplist = np.sqrt(cp_col0 * np.concatenate([[10.0], cp_col0[:-1]]))
    cplist[0] = (1.0 + cp_col0[0]) / 2.0

    root_risk_ratio = fit1["frame"]["dev"].iloc[0] / fit1["frame"]["n"].iloc[0]

    ## for (i in 1:3) { ... }
    for i in (1, 2, 3):
        ## tfit <- rpart(y ~ x1+x2, tdata, subset=(xgrp !=i), minsplit=6)
        mask = xgrp != i
        tfit = rpart("y ~ x1 + x2", data=tdata.loc[mask], minsplit=6)

        ## xvals are actually done on the absolute risk (node's risk / n),
        ## not on the rescaled risk ((node risk) / (top node risk)) which
        ## is the basis for the printed CP. To get the right answer we
        ## need to rescale.
        ## cp2 <- cplist * (fit1$frame$dev[1] / fit1$frame$n[1]) /
        ##                 (tfit$frame$dev[1] / tfit$frame$n[1])
        cp2 = cplist * root_risk_ratio / (tfit["frame"]["dev"].iloc[0] / tfit["frame"]["n"].iloc[0])

        ## for (j in 1:length(cp2)) { ... }
        for j in range(len(cp2)):
            ## tfit2 <- prune(tfit, cp=cp2[j])
            tfit2 = prune(tfit, cp=cp2[j])
            ## temp <- predict(tfit2, newdata=tdata[xgrp==i,], type='matrix')
            temp = predict_rpart(tfit2, newdata=tdata.loc[xgrp == i], type="matrix")
            temp_arr = temp.to_numpy() if hasattr(temp, "to_numpy") else np.asarray(temp)
            ## xfit2[xgrp==i, j] <- temp
            xfit2[xgrp == i, j] = temp_arr.ravel()

    ## all.equal(xfit1, xfit2, check.attributes=FALSE)
    assert xfit1.shape == xfit2.shape
    assert np.allclose(xfit1, xfit2)
