"""Python translation of rpart/tests/cptest.R.

Original R script
-----------------
    library(rpart)
    mystate <- data.frame(state.x77, region=factor(state.region))
    names(mystate) <- c("population","income" , "illiteracy","life" ,
           "murder", "hs.grad", "frost",     "area",      "region")
    #
    # This little test came out of a query that cp did not scale
    #  with the data size.  It does
    #
    # tdata = 20 copies of "mystate"
    # trees with tdata and trees with mystate should be the same (they are)
    #  except for the n's
    set.seed(10)

    tdata <- rbind(mystate, mystate, mystate, mystate, mystate)
    tdata <- rbind(tdata, tdata, tdata, tdata)
    tfit1 <- rpart(income ~ population + illiteracy + murder + hs.grad + region,
                   data = mystate, method = "anova", xval=0, cp=.089)
    tfit2 <- rpart(income ~ population + illiteracy + murder + hs.grad + region,
                   data = tdata, method='anova', xval=0, cp=.089,
                   minsplit=400, minbucket=140)

    all.equal(tfit1$splits[,-1], tfit2$splits[,-1])

This test checks that rpart()'s complexity parameter (``cp``) is scaled
relative to the data size rather than being an absolute quantity: fitting
the same model on a dataset ("mystate") and on 20 verbatim copies of it
stacked together ("tdata", built as 5 copies stacked via `rbind`, then
that result stacked 4 times -- 5*4 = 20 copies total, so every row count
in tdata is exactly 20x the corresponding count in mystate) should
produce identical trees, splits, and improvement statistics -- with the
sole difference being the raw observation counts ("n's") backing each
split, which scale by the same 20x factor. `minsplit=400,
minbucket=140` on the 20x-replicated fit are exactly 20x the (rpart
default) `minsplit=20, minbucket=7` used implicitly by the un-replicated
fit, so both fits make identical splitting *decisions* despite tdata
having 20x as many rows.

Mapping to Python
-----------------
``all.equal(tfit1$splits[,-1], tfit2$splits[,-1])`` -> the R ``splits``
matrix has columns ``count, ncat, improve, index, adj`` (in that order);
``[,-1]`` drops the first column (``count``), which is expected to
differ (scaled by 20x) between the two fits, and compares the remaining
four columns (``ncat, improve, index, adj``) for equality. The Python
``rpart()`` return value's ``"splits"`` entry is a ``pandas.DataFrame``
with the same five columns in the same order, so the equivalent
translation drops the ``"count"`` column (``.drop(columns=["count"])``)
and compares the rest with ``numpy.allclose`` (R's ``all.equal`` on
numeric data performs a relative-difference numeric comparison, which
``np.allclose`` mirrors closely enough here). We additionally assert
that the ``count`` columns themselves are related by the expected 20x
factor, since that is precisely the behavior ("cp does not scale with
data size... it does") that motivated this test, even though the
original R script's final expression only prints/checks the `[,-1]`
sub-matrix.

``state.x77`` / ``state.region`` datasets
------------------------------------------
R's built-in ``datasets::state.x77`` (a 50x8 numeric matrix: population,
income, illiteracy, life expectancy, murder rate, percent high-school
graduates, mean number of days with frost, land area -- one row per US
state) and ``datasets::state.region`` (a parallel length-50 factor
classifying each state into one of 4 regions: Northeast, South, North
Central, West) are not bundled with any common Python package. They are
exported once from R (via
``data(state); mystate <- data.frame(state.x77, region=factor(state.region))``,
mirroring the first 4 lines of the original script, plus a ``state``
column recording the row name/state name) to
``r2py_rpart/tests/data/mystate.csv`` and loaded from there with
``pandas.read_csv``, avoiding a live/runtime R dependency for the Python
test suite while using the exact same data values. The exported factor
level order (``Northeast, South, North Central, West`` -- R's
``factor(state.region)`` default alphabetical-of-appearance level
ordering, verified directly against the R session) is reproduced via an
explicit ``pandas.Categorical(..., categories=[...])`` so that the
``region`` dummy/indicator coding used internally by ``rpart_matrix``
matches R's factor coding exactly.

``rbind`` replication -> ``pandas.concat``
--------------------------------------------
``tdata <- rbind(mystate, mystate, mystate, mystate, mystate)`` (5
copies) followed by ``tdata <- rbind(tdata, tdata, tdata, tdata)`` (4
copies of the 5-copy block, i.e. 20 copies of mystate total) translates
directly to ``pandas.concat([mystate] * 5, ignore_index=True)`` followed
by ``pandas.concat([tdata] * 4, ignore_index=True)``. ``ignore_index=True``
mirrors R's ``rbind`` producing fresh sequential row names/indices
(rather than repeating the original 50 row labels 20 times over), which
matters here only in that it keeps the DataFrame index simple; no test
logic depends on specific row labels.

set.seed(10)
------------
``rpart()`` only consumes random draws for cross-validation grouping
(``xgroups``); since both fits use ``xval=0`` no cross-validation is
performed and no random draws actually occur, so the seed does not
affect the (deterministic) values checked in this test. It is set anyway
(via ``numpy.random.seed``) for exact parity with the original R script.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from r2py_rpart import rpart

_MYSTATE_CSV = Path(__file__).parent / "data" / "mystate.csv"

# R's factor(state.region) level order (first-appearance-in-sorted-levels
# order used by R for the built-in `state.region` factor; verified against
# the R session used to export mystate.csv).
_REGION_LEVELS = ["Northeast", "South", "North Central", "West"]

_PREDICTORS = ["population", "illiteracy", "murder", "hs.grad", "region"]


def _load_mystate() -> pd.DataFrame:
    """Load the state.x77/state.region-derived dataset exported from R
    (see module docstring)."""
    mystate = pd.read_csv(_MYSTATE_CSV)
    mystate["region"] = pd.Categorical(mystate["region"], categories=_REGION_LEVELS)
    return mystate


def test_cp_scales_with_data_size():
    ## set.seed(10) -- rpart only draws random numbers for xval grouping;
    ## both fits use xval=0 so no cross-validation groups are drawn and
    ## the seed has no effect on the (deterministic) values below. Set
    ## anyway for parity with the original R script.
    np.random.seed(10)

    mystate = _load_mystate()

    ## tdata <- rbind(mystate, mystate, mystate, mystate, mystate)
    ## tdata <- rbind(tdata, tdata, tdata, tdata)
    ## -> 5 * 4 = 20 verbatim copies of mystate stacked together.
    tdata = pd.concat([mystate] * 5, ignore_index=True)
    tdata = pd.concat([tdata] * 4, ignore_index=True)
    assert len(tdata) == 20 * len(mystate)

    ## tfit1 <- rpart(income ~ population + illiteracy + murder + hs.grad +
    ##                region, data = mystate, method = "anova", xval=0,
    ##                cp=.089)
    tfit1 = rpart(
        "income ~ population + illiteracy + murder + hs.grad + region",
        data=mystate,
        method="anova",
        xval=0,
        cp=0.089,
    )

    ## tfit2 <- rpart(income ~ population + illiteracy + murder + hs.grad +
    ##                region, data = tdata, method='anova', xval=0, cp=.089,
    ##                minsplit=400, minbucket=140)
    ## minsplit=400/minbucket=140 are exactly 20x rpart's defaults
    ## (minsplit=20, minbucket=7), matching the 20x replication of tdata
    ## so that both fits make identical splitting decisions.
    tfit2 = rpart(
        "income ~ population + illiteracy + murder + hs.grad + region",
        data=tdata,
        method="anova",
        xval=0,
        cp=0.089,
        minsplit=400,
        minbucket=140,
    )

    splits1 = tfit1["splits"]
    splits2 = tfit2["splits"]

    ## Same split structure (same variables, in the same order, same
    ## number of split rows) for both fits.
    assert list(splits1.index) == list(splits2.index)
    assert len(splits1) == len(splits2) == 15

    ## all.equal(tfit1$splits[,-1], tfit2$splits[,-1])
    ## R's `[,-1]` drops the first ("count") column and compares the rest
    ## (ncat, improve, index, adj) for (near-)equality.
    other_cols = ["ncat", "improve", "index", "adj"]
    assert np.allclose(
        splits1[other_cols].to_numpy(dtype=float),
        splits2[other_cols].to_numpy(dtype=float),
    )

    ## Cross-check against the reference R run (set.seed(10), same
    ## mystate data) to pin down the exact expected values, not just
    ## the relative check the original script performs.
    expected = pd.DataFrame(
        {
            "count": [50, 50, 50, 50, 50, 0, 0, 0, 40, 40, 40, 40, 40, 0, 0],
            "ncat": [-1, 1, 4, 1, -1, 1, 1, 4, -1, -1, -1, -1, 4, -1, -1],
            "improve": [
                0.428308799, 0.324905806, 0.228488159, 0.124288833, 0.083809134,
                0.900000000, 0.880000000, 0.880000000,
                0.167925662, 0.123477318, 0.115183167, 0.064725011, 0.008926168,
                0.900000000, 0.825000000,
            ],
            "index": [
                44.30, 1.55, 1.00, 11.40, 5627.50,
                1.55, 11.55, 2.00,
                10.00, 60.95, 0.75, 2980.50, 3.00,
                7805.00, 64.55,
            ],
            "adj": [
                0.000, 0.000, 0.000, 0.000, 0.000,
                0.500, 0.400, 0.400,
                0.000, 0.000, 0.000, 0.000, 0.000,
                0.500, 0.125,
            ],
        },
        index=[
            "hs.grad", "illiteracy", "region", "murder", "population",
            "illiteracy", "murder", "region",
            "murder", "hs.grad", "illiteracy", "population", "region",
            "population", "hs.grad",
        ],
    )
    assert np.allclose(splits1["count"].to_numpy(dtype=float), expected["count"].to_numpy(dtype=float))
    assert np.allclose(splits1[other_cols].to_numpy(dtype=float), expected[other_cols].to_numpy(dtype=float))

    ## "tdata = 20 copies of mystate... trees... should be the same
    ## except for the n's": the count column should scale by exactly
    ## 20x, in addition to the `[,-1]` columns already checked above.
    assert np.allclose(splits2["count"].to_numpy(dtype=float), 20 * splits1["count"].to_numpy(dtype=float))

    ## Both fits should also produce trees of the same size (same number
    ## of nodes) given the matching splitting decisions.
    assert len(tfit1["frame"]) == len(tfit2["frame"])
