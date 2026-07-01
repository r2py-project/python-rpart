"""Python translation of rpart/tests/usersplits.R.

Original R script
------------------
    # Any necessary setup
    library(rpart)
    options(na.action="na.omit")
    options(digits=4) # to match earlier output
    set.seed(1234)

    mystate <- data.frame(state.x77, region=factor(state.region))
    names(mystate) <- c("population","income" , "illiteracy","life" ,
           "murder", "hs.grad", "frost",     "area",      "region")
    #
    # Test out the "user mode" functions, with an anova variant
    #

    # The 'evaluation' function.  Called once per node.
    #  Produce a label (1 or more elements long) for labeling each node,
    #  and a deviance.  The latter is
    #	- of length 1
    #       - equal to 0 if the node is "pure" in some sense (unsplittable)
    #       - does not need to be a deviance: any measure that gets larger
    #            as the node is less acceptable is fine.
    #       - the measure underlies cost-complexity pruning, however
    temp1 <- function(y, wt, parms) {
        wmean <- sum(y*wt)/sum(wt)
        rss <- sum(wt*(y-wmean)^2)
        list(label= wmean, deviance=rss)
        }

    # The split function, where most of the work occurs.
    #   Called once per split variable per node.
    # If continuous=T
    #   The actual x variable is ordered
    #   y is supplied in the sort order of x, with no missings,
    #   return two vectors of length (n-1):
    #      goodness = goodness of the split, larger numbers are better.
    #                 0 = couldn't find any worthwhile split
    #        the ith value of goodness evaluates splitting obs 1:i vs (i+1):n
    #      direction= -1 = send "y< cutpoint" to the left side of the tree
    #                  1 = send "y< cutpoint" to the right
    #         this is not a big deal, but making larger "mean y's" move towards
    #         the right of the tree, as we do here, seems to make it easier to
    #         read
    # If continuos=F, x is a set of integers defining the groups for an
    #   unordered predictor.  In this case:
    #       direction = a vector of length m= "# groups".  It asserts that the
    #           best split can be found by lining the groups up in this order
    #           and going from left to right, so that only m-1 splits need to
    #           be evaluated rather than 2^(m-1)
    #       goodness = m-1 values, as before.
    #
    # The reason for returning a vector of goodness is that the C routine
    #   enforces the "minbucket" constraint. It selects the best return value
    #   that is not too close to an edge.
    temp2 <- function(y, wt, x, parms, continuous) {
        # Center y
        n <- length(y)
        y <- y- sum(y*wt)/sum(wt)

        if (continuous) {
    	# continuous x variable
    	temp <- cumsum(y*wt)[-n]

    	left.wt  <- cumsum(wt)[-n]
    	right.wt <- sum(wt) - left.wt
    	lmean <- temp/left.wt
    	rmean <- -temp/right.wt
    	goodness <- (left.wt*lmean^2 + right.wt*rmean^2)/sum(wt*y^2)
    	list(goodness= goodness, direction=sign(lmean))
    	}
        else {
    	# Categorical X variable
    	ux <- sort(unique(x))
    	wtsum <- tapply(wt, x, sum)
    	ysum  <- tapply(y*wt, x, sum)
    	means <- ysum/wtsum

    	# For anova splits, we can order the categories by their means
    	#  then use the same code as for a non-categorical
    	ord <- order(means)
    	n <- length(ord)
    	temp <- cumsum(ysum[ord])[-n]
    	left.wt  <- cumsum(wtsum[ord])[-n]
    	right.wt <- sum(wt) - left.wt
    	lmean <- temp/left.wt
    	rmean <- -temp/right.wt
    	list(goodness= (left.wt*lmean^2 + right.wt*rmean^2)/sum(wt*y^2),
    	     direction = ux[ord])
    	}
        }

    # The init function:
    #   fix up y to deal with offsets
    #   return a dummy parms list
    #   numresp is the number of values produced by the eval routine's "label"
    #   numy is the number of columns for y
    #   summary is a function used to print one line in summary.rpart
    # In general, this function would also check for bad data, see rpart.poisson
    #   for instace.
    temp3 <- function(y, offset, parms, wt) {
        if (!is.null(offset)) y <- y-offset
        list(y=y, parms=0, numresp=1, numy=1,
    	      summary= function(yval, dev, wt, ylevel, digits ) {
    		  paste("  mean=", format(signif(yval, digits)),
    			", MSE=" , format(signif(dev/wt, digits)),
    			sep='')
    	     })
        }


    alist <- list(eval=temp1, split=temp2, init=temp3)

    fit1 <- rpart(income ~population +illiteracy  + murder + hs.grad + region,
    	     mystate, control=rpart.control(minsplit=10, xval=0),
    	     method=alist)

    fit2 <- rpart(income ~population +illiteracy + murder + hs.grad + region,
    	     mystate, control=rpart.control(minsplit=10, xval=0),
    	      method='anova')

    # Other than their call statement, and a longer "functions" component in
    #  fit1, fit1 and fit2 should be identical.
    all.equal(fit1$frame, fit2$frame)
    all.equal(fit1$splits, fit2$splits)
    all.equal(fit1$csplit, fit2$csplit)
    all.equal(fit1$where, fit2$where)
    all.equal(fit1$cptable, fit2$cptable)

    # Now try xpred on it
    xvtemp <- rep(1:5, length.out=50)
    xp1 <- xpred.rpart(fit1, xval=xvtemp)
    xp2 <- xpred.rpart(fit2, xval=xvtemp)
    aeq <- function(x,y) all.equal(as.vector(x), as.vector(y))
    aeq(xp1, xp2)

    fit3 <- rpart(income ~population +illiteracy + murder + hs.grad + region,
    	     mystate, control=rpart.control(minsplit=10, xval=xvtemp),
    	      method='anova')
    zz <- apply((mystate$income - xp1)^2,2, sum)
    aeq(zz/fit1$frame$dev[1], fit3$cptable[,4])  #reproduce xerror

    zz2 <- sweep((mystate$income-xp1)^2,2, zz/nrow(xp1))
    zz2 <- sqrt(apply(zz2^2, 2, sum))/ fit1$frame$dev[1]
    aeq(zz2, fit3$cptable[,5])          #reproduce se(xerror)

This test exercises rpart()'s "user-defined split method" feature
(``method=list(eval=..., split=..., init=...)``): three R closures
(``temp1``/``temp2``/``temp3``) reimplement the built-in ``anova``
splitting rule completely from scratch using only the primitives that
rpart's C code hands back to a user callback (per-node ``y``/``wt``
vectors for ``eval``, per-variable sorted ``y``/``wt``/``x`` vectors for
``split``, and the raw response/offset/weights for ``init``), and the
resulting tree (``fit1``) is checked to be identical -- structurally and
numerically -- to the tree grown by the built-in ``method='anova'``
(``fit2``). It then cross-checks ``xpred.rpart`` (leave-some-out
cross-validated fitted values) between the two methods, and finally
reproduces R's own ``cptable`` cross-validation error/std-error columns
by hand from those xpred values, closing the loop between the
user-supplied splitting rule and rpart's internal cross-validation
machinery.

Mapping to Python
-----------------
``method=alist`` where ``alist=list(eval=temp1, split=temp2,
init=temp3)`` -> a Python ``dict`` ``{"eval": ..., "split": ...,
"init": ...}`` passed as ``method=`` to ``r2py_rpart.rpart()``. Per
``rpart.py`` (search "method=4 (user-defined splits)"), a ``dict``
value for ``method`` is detected via ``isinstance(method, dict)`` and
routed to ``rpartcallback()`` (``rpartcallback.py``), which wires the
three Python callables into the C splitting engine via cffi -- the
direct Python analogue of R's C-callback ``.Call`` mechanism for
user-written splitting rules (``src/rpart.c`` / ``usercode.c``).

Callback signatures (verified against ``rpart/R/rpart.R`` -- the
``mlist$init(...)``/``rpartcallback.py``'s ``eval1``/``eval2`` call
sites -- rather than assumed):

* ``temp1(y, wt, parms) -> list(label=wmean, deviance=rss)`` translates
  directly to ``eval(y, wt, parms) -> {"label": np.ndarray, "deviance":
  scalar}``.  ``rpartcallback.py``'s ``eval2()`` calls
  ``user_eval(yback[:nback], wback[:nback], parms)`` and requires
  ``len(temp["label"]) == numresp`` (so ``label`` must be a length-1
  array-like here, since ``temp3`` declares ``numresp=1``) and
  ``np.asarray(temp["deviance"]).size == 1``.

* ``temp2(y, wt, x, parms, continuous) -> list(goodness=..., direction=...)``
  translates directly to ``split(y, wt, x, parms, continuous) ->
  {"goodness": np.ndarray, "direction": np.ndarray}``.
  ``rpartcallback.py``'s ``eval1()`` calls
  ``user_split(yback[:n], wback[:n], xback[:n], parms, continuous)``
  with ``continuous`` as a Python ``bool`` (``True``/``False`` mirror
  R's ``continuous=TRUE``/``FALSE`` exactly, so the R body's
  ``if (continuous) ... else ...`` translates unchanged to
  ``if continuous: ... else: ...``).  For the categorical branch, R's
  ``x`` here already comes pre-encoded as the 1-based integer factor
  codes rpart's C engine uses internally (see ``rpart_matrix.py``,
  which encodes categorical predictors via ``as.numeric(factor(...))``
  exactly like R does) -- ``temp2`` never assumes any particular integer
  values, only that ``sort(unique(x))`` enumerates the distinct groups
  and ``tapply(..., x, sum)`` groups by them, so the Python translation
  (``np.unique``/boolean-mask grouping) works identically regardless of
  the exact codes.

* ``temp3(y, offset, parms, wt) -> list(y=..., parms=0, numresp=1,
  numy=1, summary=function(...))`` translates directly to
  ``init(y, offset, parms, wt) -> {"y": ..., "parms": 0, "numresp": 1,
  "numy": 1, "summary": callable}`` -- matching the key names/shapes
  ``rpart.py`` and ``rpart_anova.py`` (the built-in anova method's own
  ``init``, used here as the reference implementation of this exact
  contract) actually consume: ``init["y"]``, ``init["parms"]``,
  ``init["numresp"]``, ``init["numy"]``, ``init["summary"]``.
  One necessary, non-logic-changing signature adaptation: R calls
  ``mlist$init(Y, offset, wt=wt)`` (see ``rpart/R/rpart.R``, the
  ``if (missing(parms)) mlist$init(Y, offset, wt=wt)`` branch) whenever
  ``rpart()`` itself is not given a ``parms=`` argument -- omitting the
  positional ``parms`` argument entirely. R permits this because
  ``parms`` is a plain (defaultless) formal that ``temp3``'s body never
  references, and R's lazy/promise argument evaluation never forces an
  unused, unsupplied argument, so no error occurs. ``rpart.py`` reproduces
  this exact call shape verbatim (``mlist["init"](Y, offset, wt=wt)``
  when ``parms`` is not supplied to ``rpart()``, which is the case in
  this test), but Python has no lazy-evaluation equivalent: a Python
  function positionally/keyword-called without one of its required
  parameters raises ``TypeError`` immediately, regardless of whether the
  body uses that parameter. ``temp3`` is therefore translated with
  ``parms=None`` as a default value (never triggered by any read of
  ``parms`` inside the function body -- it stays semantically identical
  to R's "never supplied" for every computation ``temp3`` performs) so
  the Python callable can be invoked the same way.  ``temp3``'s
  ``summary`` closure returns a plain Python ``str`` (rather than R's
  ``paste(...)`` string) since it is exercised only informally by
  ``summary.rpart``-style printing in the original R script (not
  asserted on) and is not exercised at all by this Python test.

A genuine library bug found and fixed by this test (``xpred_rpart.py``):
``xpred_rpart()``'s parms-flattening code (mirroring
``rpart.py``'s own ``as.double(unlist(init$parms))`` step) special-cased
only ``dict``-valued and ``None``-valued ``parms``, falling back to
``list(parms)`` for everything else -- which raises
``TypeError: 'int' object is not iterable`` whenever ``parms`` is a bare
scalar, exactly what ``temp3`` above returns (``parms=0``). R's
``unlist(0)`` has no such restriction: it accepts a bare atomic value
and returns it unchanged as a length-1 vector. ``rpart.py`` itself
already has the correct three-way ``None`` / ``dict`` / scalar-or-array
branch (via ``np.asarray(init["parms"]).ravel()`` for the scalar/array
case), so ``xpred_rpart.py``'s parms-flattening block has been changed
to mirror that exact same three-way branch, fixing the crash without
altering behavior for any dict/None ``parms`` value (verified: the full
existing test suite -- 34 tests before this file existed -- still passes
unchanged after the fix).

``all.equal(fit1$frame, fit2$frame)`` / ``...$splits`` / ``...$csplit``
/ ``...$where`` / ``...$cptable`` -> since ``r2py_rpart``'s ``rpart()``
returns these as a ``dict`` of ``pandas.DataFrame``/``numpy.ndarray``
values (rather than R's single S3-classed list), each comparison is
translated to an explicit column-by-column / element-wise numeric
equality assertion (``np.allclose`` for numeric columns, exact equality
for the string ``var`` column and integer ``where``/``csplit`` arrays)
instead of a single blanket ``DataFrame.equals()`` call -- the two
frames were independently verified to be numerically identical in every
column via this element-by-element check (a blanket ``.equals()`` spuriously
reports ``False`` here purely from an incidental dtype-object
representation difference in the ``var`` column, not from any actual
value mismatch, so per-column checks are both more faithful to what
``all.equal()`` actually verifies -- value equality -- and more
informative on failure).

``xpred.rpart(fit1, xval=xvtemp)`` / ``xpred.rpart(fit2, xval=xvtemp)``
-> ``xpred_rpart(fit1, xval=xvtemp)`` / ``xpred_rpart(fit2, xval=xvtemp)``
(the r2py_rpart port of ``xpred.rpart``, see ``xpred_rpart.py``). Unlike
R -- which can always re-derive a fresh model frame internally via
``eval.parent(model.frame(...))`` when a fit was not created with
``x=TRUE``/``y=TRUE`` -- the Python port cannot re-evaluate a model
frame from a stored R-style call/environment, so both ``fit1`` and
``fit2`` are fitted here with ``x=True`` (``y`` is cached by ``rpart()``
by default already) so that ``xpred_rpart`` can reuse the cached
predictor matrix directly; this mirrors the same adaptation used by
``test_testall.py``'s ``fit4``/``xpred_rpart`` case. This does not change
any tested value: R's own ``xpred.rpart`` would derive the exact same
model frame either way, since ``mystate``/the formula are unchanged
between the two calls.

``aeq <- function(x,y) all.equal(as.vector(x), as.vector(y))`` ->
``numpy.allclose`` on the flattened (or directly 2-D, since shapes
already match) arrays -- R's ``all.equal`` on numeric data is a
relative/absolute-tolerance comparison that ``np.allclose``'s default
tolerances mirror closely enough for this test.

``zz <- apply((mystate$income - xp1)^2, 2, sum)`` -> ``xp1`` is an
``(n, ncp)`` matrix (rows = observations, columns = cp values, exactly
matching R's ``xpred.rpart`` return shape) and R's ``mystate$income -
xp1`` broadcasts the length-``n`` vector against each column; the direct
Python translation broadcasts ``income`` as a column vector
(``income[:, None]``) against the ``(n, ncp)`` array, then
``apply(..., 2, sum)`` (column sums) becomes ``.sum(axis=0)``.

``aeq(zz/fit1$frame$dev[1], fit3$cptable[,4])`` -> R's ``fit1$frame$dev[1]``
(1-based first row = root node) becomes ``fit1["frame"]["dev"].iloc[0]``
(0-based first row, same root node); R's ``fit3$cptable[,4]`` (1-based
4th column = ``xerror``, per the cptable column order ``CP, nsplit, rel
error, xerror, xstd``) becomes ``fit3["cptable"]["xerror"]`` (looked up
by name rather than a hard-coded 0-based column index 3, which is both
equivalent and clearer).

``zz2 <- sweep((mystate$income-xp1)^2, 2, zz/nrow(xp1))`` -> R's
``sweep(A, 2, v)`` subtracts vector ``v`` from each column of matrix
``A`` (the default ``sweep`` operation is ``"-"``); the direct Python
translation is ``(income[:, None] - xp1)**2 - (zz / xp1.shape[0])``,
relying on the same column-broadcasting as above (``zz / nrow(xp1)`` is
a length-``ncp`` vector, broadcasting against each row of the ``(n,
ncp)`` squared-residual matrix exactly like R's ``sweep(..., 2, ...)``
does). ``fit3$cptable[,5]`` (1-based 5th column = ``xstd``) becomes
``fit3["cptable"]["xstd"]`` by the same by-name-lookup reasoning as
above.

``options(na.action="na.omit")`` / ``options(digits=4)`` -> these R
session options affect only NA-handling defaults (irrelevant here: the
``mystate`` fixture has no missing values) and print-formatting
precision (irrelevant to a non-printing, assertion-based Python test),
so neither has a Python equivalent needed for this test's assertions.

``mystate`` dataset
--------------------
Loaded from the shared ``r2py_rpart/tests/data/mystate.csv`` fixture
(state.x77 + state.region, exported from R; see ``test_cptest.py``'s
docstring for the full provenance/derivation notes), exactly as done by
``test_cptest.py``/``test_testall.py``. The ``region`` column is
restored to a ``pandas.Categorical`` with the exact R factor level order
(``Northeast, South, North Central, West``) so ``rpart_matrix()``
encodes it identically to R's ``as.numeric(factor(state.region))``.

set.seed(1234)
---------------
Both ``fit1``/``fit2`` use ``xval=0`` (no cross-validation, hence no
random fold assignment), and ``fit3``/the two ``xpred.rpart`` calls use
an explicit, fully deterministic ``xvtemp = rep(1:5, length.out=50)``
fold vector (not a random draw) -- so ``set.seed(1234)`` has no effect
on any value computed or asserted by this script. It is set anyway
(as ``np.random.seed(1234)``) purely for line-by-line parity with the
original R script.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from r2py_rpart import rpart, xpred_rpart

_DATA = Path(__file__).parent / "data"

# R's factor(state.region) level order (first-appearance-in-sorted-levels
# order used by R for the built-in `state.region` factor; verified against
# the R session used to export mystate.csv -- see test_cptest.py).
_REGION_LEVELS = ["Northeast", "South", "North Central", "West"]

_FORMULA = "income ~ population + illiteracy + murder + hs.grad + region"


def _load_mystate() -> pd.DataFrame:
    """Load the state.x77/state.region-derived dataset exported from R
    (see test_cptest.py, which established this same fixture/pattern)."""
    mystate = pd.read_csv(_DATA / "mystate.csv")
    mystate["region"] = pd.Categorical(mystate["region"], categories=_REGION_LEVELS)
    return mystate


## temp1 <- function(y, wt, parms) {
##     wmean <- sum(y*wt)/sum(wt)
##     rss <- sum(wt*(y-wmean)^2)
##     list(label= wmean, deviance=rss)
##     }
def temp1(y: np.ndarray, wt: np.ndarray, parms: Any) -> dict[str, Any]:
    wmean = np.sum(y * wt) / np.sum(wt)
    rss = np.sum(wt * (y - wmean) ** 2)
    return {"label": np.array([wmean]), "deviance": rss}


## temp2 <- function(y, wt, x, parms, continuous) {
##     n <- length(y)
##     y <- y- sum(y*wt)/sum(wt)
##     if (continuous) { ... }
##     else { ... }
##     }
def temp2(y: np.ndarray, wt: np.ndarray, x: np.ndarray, parms: Any, continuous: bool) -> dict[str, Any]:
    ## Center y
    n = len(y)
    y = y - np.sum(y * wt) / np.sum(wt)

    if continuous:
        ## continuous x variable
        ## temp <- cumsum(y*wt)[-n]
        temp = np.cumsum(y * wt)[:-1]

        left_wt = np.cumsum(wt)[:-1]
        right_wt = np.sum(wt) - left_wt
        lmean = temp / left_wt
        rmean = -temp / right_wt
        goodness = (left_wt * lmean**2 + right_wt * rmean**2) / np.sum(wt * y**2)
        return {"goodness": goodness, "direction": np.sign(lmean)}
    else:
        ## Categorical X variable
        ## ux <- sort(unique(x))
        ux = np.sort(np.unique(x))
        ## wtsum <- tapply(wt, x, sum); ysum <- tapply(y*wt, x, sum)
        wtsum = np.array([wt[x == v].sum() for v in ux])
        ysum = np.array([(y * wt)[x == v].sum() for v in ux])
        means = ysum / wtsum

        ## For anova splits, we can order the categories by their means
        ##  then use the same code as for a non-categorical
        ## ord <- order(means)
        ord_idx = np.argsort(means, kind="stable")
        n2 = len(ord_idx)
        temp = np.cumsum(ysum[ord_idx])[:-1]
        left_wt = np.cumsum(wtsum[ord_idx])[:-1]
        right_wt = np.sum(wt) - left_wt
        lmean = temp / left_wt
        rmean = -temp / right_wt
        goodness = (left_wt * lmean**2 + right_wt * rmean**2) / np.sum(wt * y**2)
        direction = ux[ord_idx]
        return {"goodness": goodness, "direction": direction}


## temp3 <- function(y, offset, parms, wt) {
##     if (!is.null(offset)) y <- y-offset
##     list(y=y, parms=0, numresp=1, numy=1,
## 	      summary= function(yval, dev, wt, ylevel, digits ) {
## 		  paste("  mean=", format(signif(yval, digits)),
## 			", MSE=" , format(signif(dev/wt, digits)),
## 			sep='')
## 	     })
##     }
##
## Note: `parms` is given a default of None here (R's `temp3` formal has
## no default) purely so this callable can be invoked the same way
## `rpart.py` invokes it -- `mlist["init"](Y, offset, wt=wt)`, omitting
## `parms` entirely -- whenever `rpart()` itself receives no `parms=`
## argument (see module docstring, "Callback signatures" section, for the
## full R-lazy-evaluation-vs-Python explanation). `parms` is never read
## inside this function body, so the default is never actually exercised
## by any computation.
def temp3(y: np.ndarray, offset: np.ndarray | None, parms: Any = None, wt: np.ndarray | None = None) -> dict[str, Any]:
    if offset is not None:
        y = y - offset

    def summary(yval: Any, dev: Any, wt: Any, ylevel: Any, digits: int) -> str:
        return f"  mean={yval}, MSE={dev / wt}"

    return {"y": y, "parms": 0, "numresp": 1, "numy": 1, "summary": summary}


def _fit_user_and_anova(mystate: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    alist = {"eval": temp1, "split": temp2, "init": temp3}

    ## fit1 <- rpart(income ~population +illiteracy  + murder + hs.grad + region,
    ##              mystate, control=rpart.control(minsplit=10, xval=0),
    ##              method=alist)
    ## x=True is required so xpred_rpart() below can reuse the cached
    ## predictor matrix (R always has an evaluable model frame available
    ## internally; the Python port only caches $x when x=True is passed --
    ## see test_testall.py's fit4 for the identical adaptation).
    fit1 = rpart(
        _FORMULA,
        data=mystate,
        control={"minsplit": 10, "xval": 0},
        method=alist,
        x=True,
    )

    ## fit2 <- rpart(income ~population +illiteracy + murder + hs.grad + region,
    ##              mystate, control=rpart.control(minsplit=10, xval=0),
    ##               method='anova')
    fit2 = rpart(
        _FORMULA,
        data=mystate,
        control={"minsplit": 10, "xval": 0},
        method="anova",
        x=True,
    )
    return fit1, fit2


def test_user_split_matches_builtin_anova_fit():
    ## set.seed(1234) -- both fits use xval=0 (no cross-validation), so no
    ## random draws occur; set anyway for parity with the original script.
    np.random.seed(1234)

    mystate = _load_mystate()
    fit1, fit2 = _fit_user_and_anova(mystate)

    ## Other than their call statement, and a longer "functions" component
    ##  in fit1, fit1 and fit2 should be identical.

    ## all.equal(fit1$frame, fit2$frame)
    frame1, frame2 = fit1["frame"], fit2["frame"]
    assert list(frame1["var"]) == list(frame2["var"])
    for col in ("n", "wt", "dev", "yval", "complexity", "ncompete", "nsurrogate"):
        assert np.allclose(
            frame1[col].to_numpy(dtype=float), frame2[col].to_numpy(dtype=float)
        ), f"frame column {col!r} differs"
    assert list(frame1.index) == list(frame2.index)

    ## all.equal(fit1$splits, fit2$splits)
    assert np.allclose(
        fit1["splits"].to_numpy(dtype=float), fit2["splits"].to_numpy(dtype=float)
    )
    assert list(fit1["splits"].index) == list(fit2["splits"].index)

    ## all.equal(fit1$csplit, fit2$csplit)
    assert np.array_equal(fit1["csplit"], fit2["csplit"])

    ## all.equal(fit1$where, fit2$where)
    assert np.array_equal(fit1["where"], fit2["where"])

    ## all.equal(fit1$cptable, fit2$cptable)
    assert np.allclose(
        fit1["cptable"].to_numpy(dtype=float), fit2["cptable"].to_numpy(dtype=float)
    )


def test_user_split_xpred_matches_builtin_anova():
    np.random.seed(1234)

    mystate = _load_mystate()
    fit1, fit2 = _fit_user_and_anova(mystate)
    n = len(mystate)

    ## xvtemp <- rep(1:5, length.out=50)
    xvtemp = np.resize(np.arange(1, 6), n)

    ## xp1 <- xpred.rpart(fit1, xval=xvtemp)
    ## xp2 <- xpred.rpart(fit2, xval=xvtemp)
    xp1 = xpred_rpart(fit1, xval=xvtemp)
    xp2 = xpred_rpart(fit2, xval=xvtemp)

    ## aeq <- function(x,y) all.equal(as.vector(x), as.vector(y))
    ## aeq(xp1, xp2)
    assert np.allclose(np.asarray(xp1).ravel(), np.asarray(xp2).ravel())

    ## fit3 <- rpart(income ~population +illiteracy + murder + hs.grad + region,
    ##              mystate, control=rpart.control(minsplit=10, xval=xvtemp),
    ##               method='anova')
    fit3 = rpart(
        _FORMULA,
        data=mystate,
        control={"minsplit": 10, "xval": xvtemp},
        method="anova",
    )

    ## zz <- apply((mystate$income - xp1)^2,2, sum)
    income = mystate["income"].to_numpy(dtype=float)
    zz = np.sum((income[:, None] - xp1) ** 2, axis=0)

    ## aeq(zz/fit1$frame$dev[1], fit3$cptable[,4])  #reproduce xerror
    dev_root = fit1["frame"]["dev"].iloc[0]
    assert np.allclose(zz / dev_root, fit3["cptable"]["xerror"].to_numpy())

    ## zz2 <- sweep((mystate$income-xp1)^2,2, zz/nrow(xp1))
    ## zz2 <- sqrt(apply(zz2^2, 2, sum))/ fit1$frame$dev[1]
    zz2 = (income[:, None] - xp1) ** 2 - (zz / xp1.shape[0])
    zz2 = np.sqrt(np.sum(zz2**2, axis=0)) / dev_root

    ## aeq(zz2, fit3$cptable[,5])          #reproduce se(xerror)
    assert np.allclose(zz2, fit3["cptable"]["xstd"].to_numpy())
