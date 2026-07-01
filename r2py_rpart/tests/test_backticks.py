"""Python translation of rpart/tests/backticks.R.

Original R script
------------------
    ## allow backticks in rpart.matrix: see
    ## https://stat.ethz.ch/pipermail/r-help/2012-May/314081.html

    set.seed(10)
    library(rpart)
    Iris <- iris
    names(Iris) <- sub(".", " ", names(iris), fixed=TRUE)
    rpart(Species ~ `Sepal Length`, data = Iris)

The R test exercises the fact that R formulas require backticks
(`` `Sepal Length` ``) to reference a column whose name contains a space,
and checks that ``rpart()``/``rpart.matrix()`` parse and fit such a formula
without error.  It has no explicit ``testthat``/assertion calls -- it is a
plain script under R's ``tests/`` directory, so success is defined purely
by the call completing (and printing the fitted tree) without raising an
error.

Mapping backticks -> Python
----------------------------
Python has no backtick-quoting syntax for formulas.  The Python ``rpart()``
implementation (``r2py_rpart.rpart``) accepts a plain formula *string* such
as ``"Species ~ x"`` and parses it itself (see
``r2py_rpart/model_frame_rpart.py::_parse_formula_terms``).  That parser
splits the right-hand side on ``+`` and strips a leading/trailing pair of
backticks from each term via ``_strip_backtick`` -- mirroring R's own
``sub("^`(.*)`$", "\\1", ...)`` term-label cleanup in ``rpart.R`` and
``rpart.matrix.R``.  Consequently the *exact* R syntax,
backticks-and-all -- ``"Species ~ `Sepal Length`"`` -- is valid input to the
Python ``rpart()`` too: the backticks are optional decoration that gets
stripped, and the underlying column name (including the embedded space) is
looked up directly in the DataFrame's columns.  This test exercises the
formula both with and without the backticks to demonstrate that the space
in the column name -- not the backticks themselves -- is what the original
R test was probing for, and that the Python implementation supports it
either way.

Dataset
-------
R's built-in ``iris`` data frame is standard across R installations, so no
download is required.  ``sklearn.datasets.load_iris`` bundles the same data
locally (no network access needed); we reconstruct a DataFrame with R's
canonical column names (``Sepal.Length``, ``Sepal.Width``, ``Petal.Length``,
``Petal.Width``, ``Species``) and R's canonical species-label strings
(``setosa``, ``versicolor``, ``virginica``) so the renaming logic below acts
on the same names as the original R script.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.datasets import load_iris

from r2py_rpart import rpart


def _load_r_iris() -> pd.DataFrame:
    """Build a DataFrame matching R's built-in `iris` data frame.

    R's `iris` has columns Sepal.Length, Sepal.Width, Petal.Length,
    Petal.Width (numeric) and Species (factor with levels setosa,
    versicolor, virginica). sklearn's bundled copy carries the same
    measurements/order, just under different column names/labels.
    """
    data = load_iris()
    iris = pd.DataFrame(
        data.data,
        columns=["Sepal.Length", "Sepal.Width", "Petal.Length", "Petal.Width"],
    )
    species_labels = np.asarray(data.target_names)[data.target]
    iris["Species"] = pd.Categorical(species_labels, categories=list(data.target_names))
    return iris


def test_backticks_allow_column_names_with_spaces_in_formula():
    ## set.seed(10) -- rpart uses randomness for cross-validation grouping;
    ## reproducibility only, not asserted on below.
    np.random.seed(10)

    ## Iris <- iris
    Iris = _load_r_iris()

    ## names(Iris) <- sub(".", " ", names(iris), fixed=TRUE)
    ## R's sub() (unlike gsub()) replaces only the FIRST match; fixed=TRUE
    ## treats "." literally rather than as a regex wildcard. Python's
    ## str.replace(old, new, 1) has the same "first occurrence only"
    ## semantics, and "." needs no escaping since we're not using regex.
    Iris.columns = [c.replace(".", " ", 1) for c in Iris.columns]

    assert list(Iris.columns) == [
        "Sepal Length",
        "Sepal Width",
        "Petal Length",
        "Petal Width",
        "Species",
    ]

    ## rpart(Species ~ `Sepal Length`, data = Iris)
    ## Backticks are R's syntax for quoting an identifier containing
    ## characters (like a space) that would otherwise break formula
    ## parsing. The Python rpart() formula parser strips a matching pair
    ## of leading/trailing backticks from each term (see
    ## _strip_backtick in model_frame_rpart.py), so the R formula
    ## translates verbatim into the Python formula string below.
    fit = rpart("Species ~ `Sepal Length`", data=Iris)

    ## The original R script has no explicit assertions: it is a smoke
    ## test that passes if rpart() runs (and auto-prints) without error.
    ## We assert the equivalent here -- that the call succeeded and
    ## returned a well-formed fitted-tree object.
    assert fit is not None
    assert isinstance(fit, dict)
    assert "frame" in fit
    assert isinstance(fit["frame"], pd.DataFrame)
    assert len(fit["frame"]) >= 1
    assert fit["method"] == "class"  # Species is a factor -> classification tree


def test_backticks_not_required_for_python_formula_parser():
    """Same fit, without backticks, to isolate what the R test actually
    probes: that a column name containing a space works in the formula,
    independent of the backtick quoting mechanism itself (which Python's
    parser accepts but does not require, unlike R's formula grammar).
    """
    np.random.seed(10)
    Iris = _load_r_iris()
    Iris.columns = [c.replace(".", " ", 1) for c in Iris.columns]

    fit = rpart("Species ~ Sepal Length", data=Iris)

    assert fit is not None
    assert isinstance(fit, dict)
    assert "frame" in fit
    assert isinstance(fit["frame"], pd.DataFrame)
