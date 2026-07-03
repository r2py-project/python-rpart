"""Negative-path parity tests for r2py_rpart.na_rpart vs. R's
rpart:::na.rpart.

For each invalid-input scenario we:
  1. Trigger the equivalent R call via rpy2 (`rpart:::na.rpart(...)`) and
     capture the error text.
  2. Call the Python `na_rpart()` and check whether it raises.
  3. If both raise but with different wording, warn (per the test-suite
     generation protocol) rather than fail -- message text is not part of
     rpart's documented contract, only "does it raise" is.

na.rpart.R's body computes `ncol(xmiss)` (where `xmiss <- is.na(x)`, or
`is.na(x[-yvar])`) and then `xmiss %*% rep(1, ncol(xmiss))` -- for any `x`
that is not a genuine matrix/data.frame (NULL, a bare list, a plain
scalar/string), `ncol(xmiss)` is NULL, so `rep(1, NULL)` always raises
"invalid 'times' argument" in R, regardless of which particular
non-data.frame value `x` was. On the Python side, r2py_rpart.na_rpart()
does `x.attrs.get('terms')` as its very first step, so *any* non-DataFrame
`x` (None, an int, a str, a list, a dict) raises `AttributeError` at that
same point, before ever reaching the missingness logic -- both sides fail
fast on malformed input, just with different (but equally
input-content-independent) error text.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart.na_rpart import na_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    r_na_rpart_error,
    r_na_rpart_with_terms_error,
    with_response_attr,
)


# ---------------------------------------------------------------------------
# 1. x = None (R: NULL).
# ---------------------------------------------------------------------------

def test_na_rpart_none_raises_like_r():
    r_msg = r_na_rpart_error("NULL")

    with pytest.raises(Exception) as exc_info:
        na_rpart(None)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=None")


# ---------------------------------------------------------------------------
# 2. x = a plain int scalar.
# ---------------------------------------------------------------------------

def test_na_rpart_int_scalar_raises_like_r():
    r_msg = r_na_rpart_error("5")

    with pytest.raises(Exception) as exc_info:
        na_rpart(5)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=5")


# ---------------------------------------------------------------------------
# 3. x = a plain string.
# ---------------------------------------------------------------------------

def test_na_rpart_string_raises_like_r():
    r_msg = r_na_rpart_error('"hello"')

    with pytest.raises(Exception) as exc_info:
        na_rpart("hello")

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='x="hello"')


# ---------------------------------------------------------------------------
# 4. x = a plain (unnamed) list -- R's closest analogue of a bare python
#    list is `list(1, 2, 3)`.
# ---------------------------------------------------------------------------

def test_na_rpart_plain_list_raises_like_r():
    r_msg = r_na_rpart_error("list(1, 2, 3)")

    with pytest.raises(Exception) as exc_info:
        na_rpart([1, 2, 3])

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=[1, 2, 3]")


# ---------------------------------------------------------------------------
# 5. x = a plain dict -- R's closest analogue is a *named* list, which
#    (unlike the unnamed list above) DOES have a well-defined `ncol()`-free
#    `is.na()` result... but na.rpart's `ncol(xmiss)` still resolves to
#    NULL for it (ncol() is only defined for matrix-like objects), so the
#    same "invalid 'times' argument" error fires regardless.
# ---------------------------------------------------------------------------

def test_na_rpart_dict_raises_like_r():
    r_msg = r_na_rpart_error('list(a = 1, b = 2)')

    with pytest.raises(Exception) as exc_info:
        na_rpart({"a": 1, "b": 2})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x={'a': 1, 'b': 2}")


# ---------------------------------------------------------------------------
# 6. Missing required argument entirely.
# ---------------------------------------------------------------------------

def test_na_rpart_missing_argument_raises_like_r():
    r_msg = r_na_rpart_error("")

    with pytest.raises(TypeError) as exc_info:
        na_rpart()  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="na_rpart() with no arguments")


# ---------------------------------------------------------------------------
# 7. yvar (the response's column position) beyond the number of columns in
#    x -- both sides raise an out-of-bounds/subscript error, just phrased
#    differently (R: "subscript out of bounds"; python: IndexError from
#    `.iloc`).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yvar", [3, 5, 1000])
def test_na_rpart_response_index_out_of_range_raises_like_r(yvar):
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0], "x1": [1.0, np.nan, 3.0]})

    r_msg = r_na_rpart_with_terms_error(df, yvar)

    with pytest.raises(Exception) as exc_info:
        na_rpart(with_response_attr(df, yvar))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context=f"yvar={yvar} out of range")


# ---------------------------------------------------------------------------
# 8. x = a bare numpy array (not a DataFrame) -- another common "wrong
#    type" caller mistake. This is intentionally NOT tested here: R's
#    analogue is a bare (non-data.frame) numeric matrix, for which
#    `ncol()` IS defined, so R's na.rpart actually *succeeds* on it rather
#    than raising -- meaning this is not a shared-failure scenario at all,
#    but a genuine, documented R/python divergence (python raises,
#    R does not). See test_na_rpart_edge.py's
#    `test_na_rpart_bare_matrix_known_divergence` for that case, written
#    out explicitly per this project's "known divergence" convention
#    rather than forced into this file's "both must raise" pattern.
# ---------------------------------------------------------------------------
