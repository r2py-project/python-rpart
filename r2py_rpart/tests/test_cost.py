"""Python translation of rpart/tests/cost.R.

Original R script
-----------------
    library(rpart)
    require(survival)
    aeq <- function(x,y, ...) all.equal(as.vector(x), as.vector(y), ...)

    set.seed(10)
    #
    # Check out using costs
    #
    fit1 <- rpart(Surv(time, status) ~ age + sex + ph.ecog + ph.karno + pat.karno
                  + meal.cal + wt.loss, data=lung,
                  maxdepth=1, maxcompete=6, xval=0)

    fit2 <- rpart(Surv(time, status) ~ age + sex + ph.ecog + ph.karno + pat.karno
                  + meal.cal + wt.loss, data=lung,
                  maxdepth=1, maxcompete=6, xval=0, cost=(1+ 1:7/10))

    temp1 <- fit1$splits[1:7,]
    temp2 <- fit2$splits[1:7,]
    temp3 <- c('age', 'sex', 'ph.ecog', 'ph.karno', 'pat.karno', 'meal.cal',
               'wt.loss')
    indx1 <- match(temp3, dimnames(temp1)[[1]])
    indx2 <- match(temp3, dimnames(temp2)[[1]])
    aeq(temp1[indx1,1], temp2[indx2,1])             #same n's ?
    aeq(temp1[indx1,3], temp2[indx2,3]*(1+ 1:7/10)) #scaled importance

This test exercises rpart()'s ``cost=`` argument: fitting the same
survival tree twice, once with default (all 1) variable costs and once
with per-variable costs ``1 + 1:7/10`` (i.e. 1.1, 1.2, ..., 1.7 for age,
sex, ph.ecog, ph.karno, pat.karno, meal.cal, wt.loss respectively).  The
"improve" statistic reported by rpart for each candidate split is
divided by the variable's cost before variables are compared/ranked, so
scaling costs should scale the reported "improve" column by the same
factor, while leaving the split counts ("n's", i.e. how many
non-missing observations were available for scoring that variable's
split) unaffected -- costs affect variable *selection/ranking*, not
which/how-many observations go into a given variable's own split
statistics.

Mapping to Python
-----------------
``aeq`` -> ``numpy.allclose`` (R's ``all.equal`` with numeric vectors
performs a relative-difference numeric comparison; ``np.allclose`` with
the default tolerances mirrors this closely enough for this test, and we
additionally assert exactly on the underlying DataFrame values for
clarity).

``match(temp3, dimnames(temp1)[[1]])`` -> the Python ``splits`` DataFrame
returned by ``rpart()`` is indexed (row-labeled) by variable name exactly
like R's ``dimnames(...)[[1]]``, so the equivalent lookup is
``splits_df.index.get_indexer(temp3)`` (0-based positions; R's ``match``
returns 1-based positions, but since we then use the result purely to
*reorder* rows for comparison, the 0-based Python analogue reorders
identically).

``fit1$splits[1:7,]`` -> the R fit only splits the root node once
(``maxdepth=1``) with up to ``maxcompete=6`` recorded competitor splits
(7 rows: 1 primary + 6 competitors, one per predictor), *plus* additional
surrogate-split rows appended after them (``maxsurrogate`` defaults to 5;
here 2 surrogates -- for "ph.karno" and "pat.karno" -- are actually
found), so ``fit1$splits``/``fit2$splits`` each have 9 rows in total.
``[1:7,]`` is therefore a genuine positional slice discarding the
trailing surrogate rows, not a no-op -- the Python translation mirrors
this with ``.iloc[0:7]`` (R's 1-based ``1:7`` == Python's 0-based
``0:7``), after first asserting the full table really has 9 rows so the
slice's intent is documented rather than silently assumed.

``Surv(time, status)`` response
--------------------------------
The Python ``r2py_rpart`` package's formula parser (see
``r2py_rpart/model_frame_rpart.py::_parse_formula_terms``) only supports
plain ``response ~ terms`` formulas; it has no ``Surv()`` call-parsing
logic, and ``na_rpart``/``_build_model_frame`` assume a single-column
response. To fit a survival tree we therefore build the model frame by
hand: a DataFrame whose ``.attrs['terms']`` records ``term.labels`` for
just the 7 numeric predictors (mirroring what ``_build_model_frame``
would produce for a formula with those terms on the RHS) and whose
``.attrs['response']`` holds the (n, 2) ``[time, status]`` array. That
array is wrapped in a tiny ``_SurvArray`` ndarray subclass carrying a
``_surv = True`` flag, since ``rpart()``'s method auto-detection (see
``rpart.py``, `elif ... and getattr(Y, '_surv', False): method = "exp"`)
keys off exactly that attribute to select the exponential/survival
("exp") splitting method -- the Python equivalent of R's
``inherits(Y, "Surv")`` dispatch. This pre-built frame is then passed to
``rpart(..., model=m)``, which (per ``rpart.py``) uses a supplied
DataFrame directly instead of invoking the (Surv-unaware) formula
parser.

Row filtering (R's na.rpart): rows are dropped only if the response
(time or status) is missing, or if *every* predictor is missing for that
row (a single non-missing predictor is enough to keep the row -- rpart's
surrogate-split machinery handles remaining missing values internally,
it does not require complete cases). Neither ``time`` nor ``status`` has
any missing values in the ``lung`` dataset, and no row has all 7
predictors missing simultaneously, so (as verified against the reference
R run below) all 228 rows are retained -- no rows need dropping here, but
the filter is applied for fidelity with ``na.rpart``.

Dataset
-------
R's ``survival::lung`` dataset (NCCTG lung cancer data, 228 observations)
is not bundled with any common Python package, so it is exported once
from R (``write.csv(lung, ...)``, via
``data(lung, package = "survival")``) to
``r2py_rpart/tests/data/lung.csv`` and loaded from there with
``pandas.read_csv``. This avoids a live/runtime R dependency for the
Python test suite while using the exact same data values (row count and
per-column missing-value counts were cross-checked against the R
session: age/sex/time/status have 0 NAs, ph.ecog 1, ph.karno 1,
pat.karno 3, meal.cal 47, wt.loss 14 -- matching the "count" column
values reported by R's ``fit1$splits`` below).

set.seed(10)
-------------
``rpart()`` only consumes random draws for cross-validation grouping
(``xgroups``); since both fits use ``xval=0`` no cross-validation is
performed and no random draws actually occur, so the seed does not
affect the (deterministic) values checked in this test. It is set anyway
for exact parity with the original R script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from r2py_rpart import rpart

_LUNG_CSV = Path(__file__).parent / "data" / "lung.csv"

_PREDICTORS = ["age", "sex", "ph.ecog", "ph.karno", "pat.karno", "meal.cal", "wt.loss"]


def _load_lung() -> pd.DataFrame:
    """Load the survival::lung dataset exported from R (see module docstring)."""
    return pd.read_csv(_LUNG_CSV)


class _SurvArray(np.ndarray):
    """Minimal stand-in for R's `Surv(time, status)` object: a plain
    (n, 2) float array of [time, status] columns, tagged with `_surv =
    True` so that rpart()'s method auto-detection (see rpart.py) treats
    it like R's `inherits(Y, "Surv")` check and selects method="exp".
    """

    def __new__(cls, input_array: np.ndarray) -> "_SurvArray":
        obj = np.asarray(input_array, dtype=np.float64).view(cls)
        obj._surv = True
        return obj

    def __array_finalize__(self, obj: object) -> None:
        if obj is None:
            return
        self._surv = getattr(obj, "_surv", True)


def _build_surv_model_frame(data: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    """Python equivalent of:

        model.frame(Surv(time, status) ~ age + sex + ph.ecog + ph.karno +
                    pat.karno + meal.cal + wt.loss, data = lung)

    followed by rpart's internal na.rpart() row filtering, built by hand
    since r2py_rpart's formula parser does not parse `Surv(...)` LHS
    terms (see module docstring). Returns a DataFrame suitable for
    `rpart(model=..., ...)`.
    """
    time = data["time"].to_numpy(dtype=float)
    status = data["status"].to_numpy(dtype=float)

    # na.rpart: drop a row only if the response is missing, or if EVERY
    # predictor is missing for that row (not just some).
    resp_missing = np.isnan(time) | np.isnan(status)
    pred_missing = data[predictors].isna()
    all_pred_missing = pred_missing.sum(axis=1) == len(predictors)
    keep = ~resp_missing & ~all_pred_missing.to_numpy()

    kept = data.loc[keep]
    ## R's Surv(time, status) normalizes a numeric status of {1, 2} to
    ## internal 0/1 (censored/event) -- see survival::Surv's coding rules
    ## (verified: Surv(c(10,20,30), c(1,2,1)) -> status 0,1,0). lung's raw
    ## `status` column uses the 1=censored/2=dead convention, so subtract
    ## 1 to get the 0/1 event indicator that rpart_exp (mirroring R's
    ## rpart.exp.R, `status <- y[, ny]`) expects.
    event = kept["status"].to_numpy(dtype=float) - 1.0
    y = _SurvArray(np.column_stack([kept["time"].to_numpy(dtype=float), event]))

    cols: dict[str, object] = {"time": kept["time"], "status": kept["status"]}
    for p in predictors:
        cols[p] = kept[p]
    m = pd.DataFrame(cols, index=kept.index)

    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv(time, status)"] + predictors,
        "response": 1,
    }
    m.attrs["response"] = y
    return m


def test_cost_scales_improve_and_preserves_split_counts():
    ## set.seed(10) -- rpart only draws random numbers for xval grouping;
    ## both fits use xval=0 so no cross-validation groups are drawn and
    ## the seed has no effect on the (deterministic) values below. Set
    ## anyway for parity with the original R script.
    np.random.seed(10)

    lung = _load_lung()

    ## fit1 <- rpart(Surv(time, status) ~ age + sex + ph.ecog + ph.karno +
    ##               pat.karno + meal.cal + wt.loss, data=lung,
    ##               maxdepth=1, maxcompete=6, xval=0)
    m1 = _build_surv_model_frame(lung, _PREDICTORS)
    fit1 = rpart(
        "Surv(time, status) ~ age + sex + ph.ecog + ph.karno + pat.karno + meal.cal + wt.loss",
        model=m1,
        maxdepth=1,
        maxcompete=6,
        xval=0,
    )

    ## fit2 <- rpart(Surv(time, status) ~ ..., data=lung, maxdepth=1,
    ##               maxcompete=6, xval=0, cost=(1+ 1:7/10))
    cost = 1 + np.arange(1, 8) / 10  # 1.1, 1.2, ..., 1.7 (age .. wt.loss)
    m2 = _build_surv_model_frame(lung, _PREDICTORS)
    fit2 = rpart(
        "Surv(time, status) ~ age + sex + ph.ecog + ph.karno + pat.karno + meal.cal + wt.loss",
        model=m2,
        maxdepth=1,
        maxcompete=6,
        xval=0,
        cost=cost,
    )

    assert fit1["method"] == "exp"
    assert fit2["method"] == "exp"

    ## temp1 <- fit1$splits[1:7,]; temp2 <- fit2$splits[1:7,]
    ## maxdepth=1 -> only the root node is split; maxcompete=6 -> up to 6
    ## competitor splits are recorded for that one split, i.e. 7 primary
    ## rows (one per predictor). fit*$splits has MORE than 7 rows overall
    ## (maxsurrogate's default of 5 adds surrogate-split rows after the
    ## primary ones -- rows 8-9 here, "ph.karno"/"pat.karno" surrogates),
    ## which the original R script discards via the positional slice
    ## `[1:7,]` -- R's `1:7` is a 1-based position range, so the Python
    ## equivalent is `.iloc[0:7]`.
    assert len(fit1["splits"]) == 9  # 7 primary + 2 surrogate rows
    assert len(fit2["splits"]) == 9
    temp1 = fit1["splits"].iloc[0:7]
    temp2 = fit2["splits"].iloc[0:7]

    ## temp3 <- c('age', 'sex', 'ph.ecog', 'ph.karno', 'pat.karno',
    ##            'meal.cal', 'wt.loss')
    temp3 = _PREDICTORS

    ## indx1 <- match(temp3, dimnames(temp1)[[1]])
    ## indx2 <- match(temp3, dimnames(temp2)[[1]])
    ## `splits` is row-indexed by variable name in both R and Python, so
    ## get_indexer reorders rows in temp3's order, matching R's match().
    indx1 = temp1.index.get_indexer(temp3)
    indx2 = temp2.index.get_indexer(temp3)
    assert (indx1 >= 0).all(), "all predictors must appear in fit1$splits"
    assert (indx2 >= 0).all(), "all predictors must appear in fit2$splits"

    counts1 = temp1["count"].to_numpy()[indx1]
    counts2 = temp2["count"].to_numpy()[indx2]
    improve1 = temp1["improve"].to_numpy()[indx1]
    improve2 = temp2["improve"].to_numpy()[indx2]

    ## Cross-check against the reference R run (set.seed(10), same
    ## lung.csv data) to pin down the exact expected values, not just
    ## the relative check the original script performs.
    expected_counts = {
        "age": 228, "sex": 228, "ph.ecog": 227, "ph.karno": 227,
        "pat.karno": 225, "meal.cal": 181, "wt.loss": 214,
    }
    for name, cnt in zip(temp3, counts1):
        assert cnt == expected_counts[name]
    for name, cnt in zip(temp3, counts2):
        assert cnt == expected_counts[name]

    ## aeq(temp1[indx1,1], temp2[indx2,1])  #same n's ?
    assert np.allclose(counts1, counts2)

    ## aeq(temp1[indx1,3], temp2[indx2,3]*(1+ 1:7/10))  #scaled importance
    assert np.allclose(improve1, improve2 * cost)
