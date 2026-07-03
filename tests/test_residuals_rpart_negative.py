"""Negative-path parity tests for r2py_rpart.residuals_rpart vs. R's
residuals.rpart (rpart:::residuals.rpart, S3-dispatched via residuals()).

Each test triggers an error condition on both sides and asserts that *both*
raise. If both raise but with differently-worded messages,
`assert_python_and_r_errors_agree` warns rather than fails (error text is
not part of rpart's documented contract) -- see tests/_r_rpart_helpers.py.

residuals.rpart is registered as an S3 method for the `residuals` generic
(`S3method(residuals, rpart)` in NAMESPACE) but is not itself exported.
Confirmed empirically: the plain generic `residuals(list(a=1))` does *not*
reach residuals.rpart's own `inherits(object, "rpart")` legitimacy check at
all -- it dispatches to `residuals.default`, which just returns `NULL`
silently for an object with no "residuals" component. So, exactly as for
print.rpart/plot.rpart elsewhere in this test suite, the "object is not a
legitimate rpart object" checks below call `rpart:::residuals.rpart(...)`
directly (`generic=False`) to actually exercise that check; every other
negative test here uses a genuinely `"rpart"`-classed (or fitted) object, so
the documented `residuals(fit, ...)` generic entry point (`generic=True`,
the default) is used instead.

Both explicit `raise` branches inside residuals_rpart.py are exercised here:
  - `object` is not a legitimate "rpart" object                -> ValueError
  - `type=` doesn't match/partially-match any valid type         -> ValueError
Plus two further error paths implied by direct dict/attribute access that
have no explicit `raise` of their own:
  - missing the required `object` positional argument            -> TypeError
  - `object` missing the `method` key entirely                   -> KeyError
    (R: `object$method == "class"` on a NULL `$method` is
    `logical(0)`, and `if (logical(0))` itself raises -- both sides
    error, albeit with unrelated wording)
"""
from __future__ import annotations

import pandas as pd
import pytest

from r2py_rpart import residuals_rpart, rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_residuals,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. `object` is not a legitimate rpart object (plain dict/list/scalar/None).
#    Every one of these fails python's own `isinstance(object, dict) and
#    'frame' in object` check identically, and every one of these also fails
#    R's `inherits(object, "rpart")` check identically -- so a single fixed
#    R reference call suffices for all parametrized variants (mirroring
#    test_predict_rpart_negative.py's own `bad_object` parametrization).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_object", ["not a dict", 123, [1, 2, 3], {"no_frame_key": 1}, None])
def test_residuals_invalid_object_raises(bad_object):
    with pytest.raises(Exception) as exc_info:
        residuals_rpart(bad_object)
    r_message = r_error_message(lambda: run_r("rpart:::residuals.rpart(list(a=1))"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid object {bad_object!r}")


# ---------------------------------------------------------------------------
# 2. Missing the required `object` positional argument entirely.
# ---------------------------------------------------------------------------

def test_residuals_missing_object_argument_raises():
    with pytest.raises(TypeError) as exc_info:
        residuals_rpart()
    r_message = r_error_message(lambda: run_r("rpart:::residuals.rpart()"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="missing object argument")


# ---------------------------------------------------------------------------
# 3. `type=` is a string that neither exactly nor partially matches any of
#    "usual"/"pearson"/"deviance".
# ---------------------------------------------------------------------------

def test_residuals_invalid_type_string_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        residuals_rpart(py_fit, type="bogus")

    r_message = r_error_message(lambda: r_residuals(r_fit, type="bogus"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type='bogus'")


# ---------------------------------------------------------------------------
# 4. `type=` an empty string: no valid type starts with "", but match.arg()
#    still requires a unique match, so R errors just like an unmatched type.
# ---------------------------------------------------------------------------

def test_residuals_empty_type_string_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        residuals_rpart(py_fit, type="")

    r_message = r_error_message(lambda: r_residuals(r_fit, type=""))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type=''")


# ---------------------------------------------------------------------------
# 5. `type=` a non-string (R's match.arg requires a character vector; python's
#    `str.startswith` requires a str first-argument).
# ---------------------------------------------------------------------------

def test_residuals_non_string_type_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        residuals_rpart(py_fit, type=123)

    r_message = r_error_message(lambda: r_residuals(r_fit, type=123))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type=123 (non-string)")


# ---------------------------------------------------------------------------
# 6. `object` missing the `method` key/component entirely: python's plain
#    `object['method']` dict lookup raises KeyError; R's `object$method ==
#    "class"` on a NULL `$method` produces `logical(0)`, and `if
#    (logical(0))` itself raises "argument is of length zero" -- confirmed
#    directly via rpy2 before writing this test. Uses a minimal synthetic
#    object (via r_minimal_rpart_expr()'s underlying R-source convention,
#    built by hand here since `method` must be *omitted*, not merely set to
#    a bogus value) rather than a genuine fit, isolating this from any
#    tree-fitting concern.
# ---------------------------------------------------------------------------

def test_residuals_object_missing_method_key_raises():
    r_expr = 'structure(list(y = c(1, 2, 3), frame = data.frame(yval = c(1, 2, 3)), where = c(1, 2, 3)), class = "rpart")'
    r_message = r_error_message(lambda: run_r(f"residuals({r_expr})"))

    py_fit = {
        "y": [1.0, 2.0, 3.0],
        "frame": pd.DataFrame({"yval": [1.0, 2.0, 3.0]}, index=[1, 2, 3]),
        "where": [1, 2, 3],
    }
    with pytest.raises(KeyError) as exc_info:
        residuals_rpart(py_fit)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="object missing 'method' key")
