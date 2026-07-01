"""Python translation of rpart/tests/xpred2.R.

Original R script
------------------
    #
    # Test out the "return.all" argument of xpred
    #  The data set has the virtue of continuous, categorical, and missings
    #
    library(rpart)
    require(survival)
    set.seed(10)

    fit1 <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
                    stagec,  method='poisson')

    xgrp <- rep(1:3, length.out=nrow(stagec))  # explicitly set the xval groups

    xfit1 <- xpred.rpart(fit1, xval=xgrp, return.all=T)
    xfit2 <- array(0, dim=dim(xfit1))
    cplist <- as.numeric(dimnames(xfit1)[[2]])

    for (i in 1:3) {
        tfit <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason +ploidy,
                    stagec,  method='poisson', subset=(xgrp !=i))
        # xvals are actually done on the absolute risk (node's risk /n), not on
        #   the rescaled risk ((node risk)/ (top node risk)) which is the basis
        #   for the printed CP.  To get the right answer we need to rescale.
        cp2 <- cplist * (fit1$frame$dev[1] / fit1$frame$n[1]) /
                        (tfit$frame$dev[1] / tfit$frame$n[1])

        for (j in 1:length(cp2)) {
            tfit2 <- prune(tfit, cp=cp2[j])
            temp <- predict(tfit2, newdata=stagec[xgrp==i,], type='matrix')
            xfit2[xgrp==i, j,] <- temp
            }
        }

    all.equal(xfit1, xfit2, check.attributes=FALSE)

This is the survival/poisson-method analogue of xpred1.R -- the same
"return.all=TRUE" cross-validation-prediction-matches-manual-refit logic,
but on `stagec` (continuous, categorical, and missing predictor values)
fit with `method='poisson'` on a `Surv(pgtime, pgstat)` response, rather
than xpred1.R's tiny inline anova-method dataset. See xpred1.R's Python
conversion (test_xpred1.py) for the general structure this mirrors; only
the poisson/Surv-specific differences are called out below.

``Surv(pgtime, pgstat)`` response
-----------------------------------
Built by hand via the same ``_SurvArray``/hand-assembled-model-frame
pattern established by test_cost.py/test_testall.py/test_treble.py (since
r2py_rpart's formula parser has no ``Surv(...)`` call-parsing logic). Row
filtering follows test_cost.py's explicit na.rpart-equivalent logic (drop
a row only if the response is missing, or if *every* predictor is
missing) even though, for `stagec`, no row actually has every one of
`age/eet/g2/grade/gleason/ploidy` missing simultaneously (`eet`, `g2`,
`gleason` each have a handful of NAs, `age`/`grade`/`ploidy` have none),
so this filtering step is a no-op here (146 of 146 rows kept, matching
test_testall.py's identically-shaped fit1 which asserts ``n == 146``) --
included anyway for a faithful, general translation of R's na.rpart
semantics.

``xgrp <- rep(1:3, length.out=nrow(stagec))`` -> ``numpy.resize(numpy.
arange(1, 4), len(stagec))``, matching xpred1.R's identical
``rep(1:3, ...)`` translation.

``xpred.rpart(fit1, xval=xgrp, return.all=T)`` -> ``xpred_rpart(fit1,
xval=xgrp, return_all=True)``. Requires ``fit1`` to be created with
``x=True`` so ``xpred_rpart`` can reuse the cached design matrix (see
xpred1.R's conversion notes; identical requirement here).

``numresp`` > 1: the code path this test actually exercises
--------------------------------------------------------------
Unlike xpred1.R's anova-method fit (``numresp == 1``, for which
``return_all`` has no effect on ``xpred_rpart``'s output shape),
``method='poisson'`` sets ``numresp = 2`` (see rpart_poisson.py:
``"numresp": 2`` -- the two responses are the node's estimated event
rate and its (shrinkage-adjusted) event count, matching ``frame$yval2``'s
2-column layout for a poisson tree). This means ``xpred_rpart``'s
``if return_all and numresp > 1:`` branch (xpred_rpart.py lines ~248-250)
*is* exercised here: the raw C output is reshaped via ``pred.reshape(
(numresp, n_cp, nrow_X), order='F')`` and then ``np.transpose(...)``
(reversing all three axes, mirroring R's ``aperm(array(pred, dim=c(
numresp, length(cp), nrow(X))))`` with no explicit permutation argument,
which also just reverses the dimension order) to produce a final shape of
``(nrow_X, n_cp, numresp)`` -- a genuinely 3-D array, unlike xpred1.R's
2-D ``(nobs, n_cp)`` result. This 3-D shape is asserted explicitly below.

Correspondingly, ``predict(tfit2, newdata=..., type='matrix')`` returns,
for this poisson tree, a proper ``(n_held_out, 2)`` matrix per fold/cp
combination (``frame$yval2`` has 2 columns for poisson, so
``predict_rpart``'s ``type='matrix'`` branch -- ``frame['yval2'][where,
:]`` -- naturally yields 2 columns per row, without any reshaping
special-casing needed), which is assigned wholesale into
``xfit2[xgrp==i, j, :]`` (R's ``xfit2[xgrp==i, j,] <- temp``, whose
trailing empty index selects "all of the 3rd/response dimension" --
exactly Python's trailing ``:`` slice).

``fit1$frame$dev[1]`` / ``fit1$frame$n[1]`` -> ``fit1["frame"]["dev"].
iloc[0]`` / ``fit1["frame"]["n"].iloc[0]`` (0-based positional first/root
row), matching xpred1.R's translation exactly.

``rpart(..., subset=(xgrp !=i))`` -> pre-filtering ``data=stagec.loc[xgrp
!= i]`` before rebuilding the hand-assembled Surv model frame (same
convention as xpred1.R / test_testall.py's ``subset=`` translations).

``prune(tfit, cp=cp2[j])`` -> ``prune(tfit, cp=cp2[j])``.

``predict(tfit2, newdata=stagec[xgrp==i,], type='matrix')`` ->
``predict_rpart(tfit2, newdata=stagec.loc[xgrp == i][predictors],
type='matrix')``; the returned ``pandas.DataFrame`` is converted to a
plain ``numpy`` array before assignment into ``xfit2``.

``xfit2[xgrp==i, j,] <- temp`` -> ``xfit2[xgrp == i, j, :] = temp_arr``.

``all.equal(xfit1, xfit2, check.attributes=FALSE)`` -> ``numpy.allclose``
plus an exact ``.shape`` check.

``cplist <- as.numeric(dimnames(xfit1)[[2]])`` -> recomputed directly
from ``fit1``'s ``cptable`` via ``xpred_rpart``'s own default-CP formula
(``cp <- sqrt(cp * c(10, cp[-length(cp)])); cp[1] <- (1 + cptable[1,1])/2``),
exactly as in xpred1.R's conversion, since r2py_rpart's ``xpred_rpart``
does not attach CP-value dimnames to its ndarray return value.

``set.seed(10)``
-----------------
As in xpred1.R: ``xval=xgrp`` is always an explicit, fully-deterministic
vector for both the main ``xpred_rpart`` call and every per-fold
``rpart()`` refit, so no assertion here actually depends on any random
draw; ``numpy.random.seed(10)`` is set anyway for parity with the R
script's ``set.seed(10)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from r2py_rpart import prune, predict_rpart, rpart, xpred_rpart

_DATA = Path(__file__).parent / "data"
_STAGEC_PLOIDY_LEVELS = ["diploid", "tetraploid", "aneuploid"]
_STAGEC_PREDICTORS = ["age", "eet", "g2", "grade", "gleason", "ploidy"]


class _SurvArray(np.ndarray):
    """Minimal stand-in for R's `Surv(pgtime, pgstat)` object: a plain
    (n, 2) float array of [time, status] columns, tagged with `_surv =
    True` so that rpart()'s method auto-detection (see rpart.py) treats
    it like R's `inherits(Y, "Surv")` check. This test always passes an
    explicit `method="poisson"`, so this tag is not load-bearing for
    method selection, but is included for consistency with the
    established pattern (test_cost.py/test_testall.py/test_treble.py).
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
    patients), exported from R via `write.csv(stagec, ...)` (see
    rpart/data/stagec.rda and rpart/man/stagec.Rd for the column
    definitions this mirrors)."""
    stagec = pd.read_csv(_DATA / "stagec.csv")
    stagec["ploidy"] = pd.Categorical(stagec["ploidy"], categories=_STAGEC_PLOIDY_LEVELS)
    return stagec


def _build_surv_model_frame(data: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    """Python equivalent of `model.frame(Surv(pgtime, pgstat) ~ age + eet +
    g2 + grade + gleason + ploidy, data = <data>)` followed by rpart's
    internal na.rpart() row filtering, built by hand since r2py_rpart's
    formula parser does not parse `Surv(...)` LHS terms (see module
    docstring and test_cost.py, which established this same pattern).
    """
    time = data["pgtime"].to_numpy(dtype=float)
    status = data["pgstat"].to_numpy(dtype=float)

    # na.rpart: drop a row only if the response is missing, or if EVERY
    # predictor is missing for that row (not just some).
    resp_missing = np.isnan(time) | np.isnan(status)
    pred_missing = data[predictors].isna()
    all_pred_missing = pred_missing.sum(axis=1) == len(predictors)
    keep = ~resp_missing & ~all_pred_missing.to_numpy()

    kept = data.loc[keep]
    y = _SurvArray(np.column_stack([kept["pgtime"].to_numpy(dtype=float),
                                     kept["pgstat"].to_numpy(dtype=float)]))

    cols: dict[str, Any] = {"pgtime": kept["pgtime"], "pgstat": kept["pgstat"]}
    for p in predictors:
        cols[p] = kept[p]
    m = pd.DataFrame(cols, index=kept.index)

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
    return m


def test_xpred_return_all_poisson_survival() -> None:
    ## set.seed(10)
    np.random.seed(10)

    stagec = _load_stagec()

    ## fit1 <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason
    ##               +ploidy, stagec,  method='poisson')
    ## x=True: cache the design matrix so xpred_rpart() below can reuse it
    ## (see xpred1.R's Python conversion, test_xpred1.py, for why this is
    ## required by r2py_rpart's xpred_rpart()).
    m1 = _build_surv_model_frame(stagec, _STAGEC_PREDICTORS)
    fit1 = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m1,
        method="poisson",
        x=True,
    )
    assert fit1["method"] == "poisson"

    ## xgrp <- rep(1:3, length.out=nrow(stagec))
    xgrp = np.resize(np.arange(1, 4), len(stagec))

    ## xfit1 <- xpred.rpart(fit1, xval=xgrp, return.all=T)
    xfit1 = xpred_rpart(fit1, xval=xgrp, return_all=True)

    ## poisson's numresp == 2, so return_all *does* affect the output
    ## shape here (unlike xpred1.R's anova/numresp==1 case): a genuinely
    ## 3-D (nobs, n_cp, numresp) array (see module docstring).
    numresp = fit1["numresp"]
    assert numresp == 2
    assert xfit1.ndim == 3
    assert xfit1.shape[0] == len(stagec)
    assert xfit1.shape[2] == numresp

    ## xfit2 <- array(0, dim=dim(xfit1))
    xfit2 = np.zeros_like(xfit1, dtype=np.float64)

    ## cplist <- as.numeric(dimnames(xfit1)[[2]])
    ## Recompute the same default CP list that xpred_rpart used internally
    ## (no explicit cp= was passed), from fit1's cptable -- see xpred1.R's
    ## conversion notes for why this exactly mirrors dimnames(xfit1)[[2]].
    cptable = fit1["cptable"]
    cp_col0 = cptable["CP"].to_numpy(dtype=float)
    cplist = np.sqrt(cp_col0 * np.concatenate([[10.0], cp_col0[:-1]]))
    cplist[0] = (1.0 + cp_col0[0]) / 2.0
    assert xfit1.shape[1] == len(cplist)

    root_risk_ratio = fit1["frame"]["dev"].iloc[0] / fit1["frame"]["n"].iloc[0]

    ## for (i in 1:3) { ... }
    for i in (1, 2, 3):
        ## tfit <- rpart(Surv(pgtime, pgstat) ~ age + eet + g2+grade+gleason
        ##               +ploidy, stagec,  method='poisson',
        ##               subset=(xgrp !=i))
        mask = xgrp != i
        m_t = _build_surv_model_frame(stagec.loc[mask], _STAGEC_PREDICTORS)
        tfit = rpart(
            "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
            model=m_t,
            method="poisson",
        )

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
            ## temp <- predict(tfit2, newdata=stagec[xgrp==i,], type='matrix')
            newdata = stagec.loc[xgrp == i, _STAGEC_PREDICTORS]
            temp = predict_rpart(tfit2, newdata=newdata, type="matrix")
            temp_arr = temp.to_numpy() if hasattr(temp, "to_numpy") else np.asarray(temp)
            ## xfit2[xgrp==i, j,] <- temp
            xfit2[xgrp == i, j, :] = temp_arr

    ## all.equal(xfit1, xfit2, check.attributes=FALSE)
    assert xfit1.shape == xfit2.shape
    assert np.allclose(xfit1, xfit2)
