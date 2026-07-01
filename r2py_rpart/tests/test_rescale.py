"""Python translation of rpart/tests/rescale.R.

Original R script
------------------
    #
    # Test out the rescaling done for Surv objects
    #
    library(rpart)
    require(survival)
    set.seed(10)

    aeq <- function(x,y, ...) all.equal(as.vector(x), as.vector(y), ...)
    tdata <- data.frame(time=c(1,4,3,2,5,7,8,9,4), status=c(0,1,1,0,0,1,1,0,1),
                        x=1:9)
    fit2 <- rpart.exp(Surv(tdata$time, tdata$status), NULL, wt=rep(1,9))

    #
    # Here is what it should be, in order
    #    for the intervals (0,3], (3,4], (4,7], (7,9]
    deaths <- c( 1, 2,  1, 1)
    pyears <- c(24, 6, 10, 3)
    rate   <- deaths/pyears
    cumhaz <- cumsum(c(0, rate*c(3,1,3,2)))

    aeq(fit2$y[,2], tdata$status)
    aeq(fit2$y[,1], approx(c(0,3,4,7,9), cumhaz, tdata$time)$y)

This test exercises ``rpart.exp`` -- the "rescaled exponential"
splitting method's response-preprocessing function (see
``rpart/R/rpart.exp.R``) -- directly (not through a full ``rpart()``
fit). It rescales a ``Surv(time, status)`` response so that the new
time axis has piecewise-constant hazard rate 1 within each inter-death
interval, and checks the resulting rescaled response ``fit2$y``
against a value hand-computed from the known death/person-years table
for this specific 9-observation dataset.

Mapping to Python
-----------------
``rpart.exp`` -> ``r2py_rpart.rpart_exp`` (see
``r2py_rpart/rpart_exp.py``), imported and called directly, exactly as
the R script calls ``rpart.exp`` directly (this script never calls the
top-level ``rpart()`` fitting function).

``aeq`` -> ``numpy.allclose`` (R's ``all.equal`` on numeric vectors is
a relative/absolute-tolerance numeric comparison; ``np.allclose`` with
its default tolerances mirrors this closely enough for this test).

``Surv(tdata$time, tdata$status)`` -> a plain ``(n, 2)`` NumPy array
with columns ``[time, status]``. ``rpart.exp``'s R signature is
``rpart.exp(y, offset, parms, wt)`` and only checks
``inherits(y, "Surv")`` to validate its input type; the R test's call
``rpart.exp(Surv(...), NULL, wt=rep(1,9))`` supplies ``y`` and
``offset`` positionally and ``wt`` by name, leaving ``parms`` missing
(triggering R's ``missing(parms)`` branch, which defaults to
``c(shrink=1, method=1)``). The Python ``rpart_exp(y, offset, parms,
wt)`` signature mirrors this positionally, with ``parms=None`` used as
the direct equivalent of R's "argument not supplied" (verified in
``rpart_exp.py``: a ``None`` parms takes the same
``{"shrink": 1, "method": 1}`` default branch as R's ``missing(parms)``
case). ``offset=NULL`` in R likewise maps to ``offset=None`` in Python
(the function only applies an offset rescaling when
``len(offset) == n``, which is never true for ``None``/``NULL``).

``fit2$y[,2]`` / ``fit2$y[,1]`` -> 1-based R column indices 2 and 1
become 0-based Python column indices 1 and 0
(``fit2["y"][:, 1]`` / ``fit2["y"][:, 0]``); ``rpart_exp`` returns
``y`` as a dict key (``fit2["y"]``) rather than a list element
(``fit2$y``), per the established r2py_rpart list-as-dict convention
used throughout this package (see e.g. ``fit1["splits"]`` in
``test_cost.py``).

``approx(c(0,3,4,7,9), cumhaz, tdata$time)$y`` -> R's ``approx()``
performs linear interpolation of ``cumhaz`` (the y-values) over the
knots ``c(0,3,4,7,9)`` (the x-values), evaluated at ``tdata$time``;
the direct Python equivalent is ``numpy.interp(tdata_time, [0,3,4,7,9],
cumhaz)`` (note the x/y argument order: ``np.interp(x, xp, fp)`` takes
the evaluation points first, then the knot x's, then the knot y's --
the reverse order from ``approx(x, y, xout)``). This also matches how
``rpart_exp`` itself computes ``newy`` internally via
``np.interp(time, itable, cumhaz)`` (see ``rpart_exp.py``), so this
test is effectively cross-checking that internal computation against
an independently hand-built interpolation call.

Interval table derivation
--------------------------
The dataset has death times (status==1) at t = 2 duplicate-free sorted
values {3, 4, 4, 7, 8} -> unique death times {3, 4, 7, 8}, giving
interval breakpoints ``itable = c(0, 3, 4, 7, max(time)=9)``, i.e. the
four intervals (0,3], (3,4], (4,7], (7,9] referenced in the R
comment. The hand-computed ``deaths``/``pyears``/``rate``/``cumhaz``
values in the R script (and reproduced verbatim below) are the
expected per-interval death counts, person-years of follow-up, hazard
rates, and cumulative hazard for exactly these four intervals -- they
are not derived programmatically in either the R or Python version of
this test; they encode the expected ground truth to check
``rpart_exp``'s internal ``drate2``/interval-table logic against.

No datasets/fixtures required
------------------------------
Unlike other converted tests in this suite (e.g. ``test_cost.py``,
which needs the external ``survival::lung`` dataset), this test's
input data (``tdata``) is fully inline in the R script -- 9
observations of ``time``, ``status``, and an unused ``x`` column --
so no external dataset file is needed here.

set.seed(10)
-------------
``rpart.exp`` is a deterministic function (interval construction,
person-years tabulation, and linear interpolation); it draws no random
numbers, so ``set.seed(10)`` has no effect on this test's outcome. It
is retained here (as ``np.random.seed(10)``) purely for line-by-line
parity with the original R script.
"""

from __future__ import annotations

import numpy as np

from r2py_rpart import rpart_exp


def test_rescale_exp_response():
    ## set.seed(10) -- rpart.exp draws no random numbers, so this has no
    ## effect on the (fully deterministic) result; kept for parity with
    ## the original R script.
    np.random.seed(10)

    ## tdata <- data.frame(time=c(1,4,3,2,5,7,8,9,4),
    ##                      status=c(0,1,1,0,0,1,1,0,1), x=1:9)
    time = np.array([1, 4, 3, 2, 5, 7, 8, 9, 4], dtype=float)
    status = np.array([0, 1, 1, 0, 0, 1, 1, 0, 1], dtype=float)
    x = np.arange(1, 10, dtype=float)  # unused by rpart.exp, kept for parity

    ## fit2 <- rpart.exp(Surv(tdata$time, tdata$status), NULL, wt=rep(1,9))
    y = np.column_stack([time, status])
    wt = np.ones(9)
    fit2 = rpart_exp(y, None, None, wt)

    ##
    ## Here is what it should be, in order
    ##    for the intervals (0,3], (3,4], (4,7], (7,9]
    deaths = np.array([1, 2, 1, 1], dtype=float)
    pyears = np.array([24, 6, 10, 3], dtype=float)
    rate = deaths / pyears
    cumhaz = np.cumsum(np.concatenate([[0.0], rate * np.array([3, 1, 3, 2], dtype=float)]))

    ## aeq(fit2$y[,2], tdata$status)
    assert np.allclose(fit2["y"][:, 1], status)

    ## aeq(fit2$y[,1], approx(c(0,3,4,7,9), cumhaz, tdata$time)$y)
    expected_newy = np.interp(time, [0, 3, 4, 7, 9], cumhaz)
    assert np.allclose(fit2["y"][:, 0], expected_newy)
