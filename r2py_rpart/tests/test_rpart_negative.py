"""Negative-path parity tests for r2py_rpart.rpart vs. R's rpart::rpart.

For each invalid-input scenario we:
  1. Trigger the equivalent R call via rpy2 and capture the error text (or
     confirm R does *not* raise, for the one documented divergence below).
  2. Call the Python `rpart()` and confirm it raises.
  3. If both raise but with different wording, warn (per the test-suite
     generation protocol) rather than fail -- message text is not part of
     rpart's documented contract, only "does it raise" is.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    run_r,
)


def _kyphosis_r_and_py():
    df = kyphosis_df()
    r_dataframe_assign("df", df.assign(Kyphosis=df["Kyphosis"].astype(str)))
    run_r('df$Kyphosis <- factor(df$Kyphosis, levels=c("absent", "present"))')
    return df


# ---------------------------------------------------------------------------
# 1. Negative weights
# ---------------------------------------------------------------------------

def test_rpart_negative_weights_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, weights=rep(-1, nrow(df)))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, weights=-np.ones(len(df)))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="negative weights")


# ---------------------------------------------------------------------------
# 2. Invalid/unrecognized method string
# ---------------------------------------------------------------------------

def test_rpart_invalid_method_string_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="bogus")'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="bogus")

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="invalid method string")


# ---------------------------------------------------------------------------
# 3. maxdepth above the hard limit of 30
# ---------------------------------------------------------------------------

def test_rpart_maxdepth_above_30_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, control=rpart.control(maxdepth=31))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, control={"maxdepth": 31})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth > 30")


# ---------------------------------------------------------------------------
# 4. maxdepth below 1
# ---------------------------------------------------------------------------

def test_rpart_maxdepth_below_1_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, control=rpart.control(maxdepth=0))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, control={"maxdepth": 0})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth < 1")


# ---------------------------------------------------------------------------
# 5. Cost vector of the wrong length
# ---------------------------------------------------------------------------

def test_rpart_cost_vector_wrong_length_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, cost=c(1, 2))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, cost=np.array([1.0, 2.0]))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="cost vector wrong length")


# ---------------------------------------------------------------------------
# 6. Cost vector with a non-positive entry
# ---------------------------------------------------------------------------

def test_rpart_cost_vector_non_positive_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, cost=c(1, -1, 1))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, cost=np.array([1.0, -1.0, 1.0]))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="cost vector non-positive")


# ---------------------------------------------------------------------------
# 7. xval of the wrong length (neither a scalar fold-count nor len(nobs))
# ---------------------------------------------------------------------------

def test_rpart_xval_wrong_length_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, control=rpart.control(xval=c(1, 2)))'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": np.array([1, 2])})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="xval wrong length")


# ---------------------------------------------------------------------------
# 8. Unrecognized keyword argument (checked against rpart.control's formals)
# ---------------------------------------------------------------------------

def test_rpart_unmatched_kwarg_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, foobarparam=5)'))

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, foobarparam=5)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="unmatched control kwarg")


# ---------------------------------------------------------------------------
# 9. Unknown named element inside control=
# ---------------------------------------------------------------------------

def test_rpart_unknown_control_dict_key_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, control=list(bogus=1))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, control={"bogus": 1})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="unknown control dict key")


# ---------------------------------------------------------------------------
# 10. Interaction terms in the formula.
#
#     NOTE: this is a *documented divergence*, not a parity bug in the test.
#     R's rpart() builds the terms object first (which records order=2 for
#     "x1:x2"/"x1*x2"), then rpart.R explicitly checks
#     `if (any(attr(Terms, "order") > 1)) stop("Trees cannot handle
#     interaction terms")`. r2py_rpart's formula mini-parser
#     (_parse_formula_terms in model_frame_rpart.py) does not expand '*'/':'
#     into separate main-effect terms with an order flag; it instead treats
#     "x1*x2" as a single (unknown) column name, so the KeyError for a
#     missing data column fires first. Both implementations reject the
#     formula (as required), but via different exception types/messages,
#     so this is exactly the case the generation protocol asks us to
#     warn on rather than fail.
# ---------------------------------------------------------------------------

def test_rpart_interaction_terms_rejected_by_both_with_different_messages():
    rng = np.random.default_rng(0)
    n = 20
    df = pd.DataFrame({"x1": rng.standard_normal(n), "x2": rng.standard_normal(n), "y": rng.standard_normal(n)})
    r_dataframe_assign("df", df)
    r_msg = r_error_message(lambda: run_r("rpart(y ~ x1 * x2, data=df)"))

    with pytest.raises(Exception) as exc_info:
        rpart("y ~ x1 * x2", data=df)

    assert r_msg is not None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="interaction terms")
        assert len(caught) == 1, "expected a message-mismatch warning for this known divergence"


# ---------------------------------------------------------------------------
# 11. Classification parms: priors that don't sum to 1
# ---------------------------------------------------------------------------

def test_rpart_class_priors_not_summing_to_one_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=list(prior=c(0.5, 0.6)))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", parms={"prior": np.array([0.5, 0.6])})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="priors not summing to 1")


# ---------------------------------------------------------------------------
# 12. Classification parms: priors of the wrong length
# ---------------------------------------------------------------------------

def test_rpart_class_priors_wrong_length_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=list(prior=c(0.3, 0.3, 0.4)))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart(
            "Kyphosis ~ Age + Number + Start",
            data=df,
            method="class",
            parms={"prior": np.array([0.3, 0.3, 0.4])},
        )

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="priors wrong length")


# ---------------------------------------------------------------------------
# 13. Classification parms: loss matrix with a non-zero diagonal
# ---------------------------------------------------------------------------

def test_rpart_class_loss_matrix_bad_diagonal_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r(
            'rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", '
            "parms=list(loss=matrix(c(1,2,1,1), nrow=2)))"
        )
    )

    with pytest.raises(Exception) as exc_info:
        rpart(
            "Kyphosis ~ Age + Number + Start",
            data=df,
            method="class",
            parms={"loss": np.array([[1.0, 1.0], [2.0, 1.0]])},
        )

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="loss matrix bad diagonal")


# ---------------------------------------------------------------------------
# 14. Classification parms: not a list/dict at all
# ---------------------------------------------------------------------------

def test_rpart_class_parms_not_a_list_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=c(1, 2, 3))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", parms=np.array([1, 2, 3]))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="parms not a list")


# ---------------------------------------------------------------------------
# 15. Classification parms: an unmatched component name
# ---------------------------------------------------------------------------

def test_rpart_class_parms_unmatched_component_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=list(bogus=1))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", parms={"bogus": 1})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="parms unmatched component")


# ---------------------------------------------------------------------------
# 16. Classification parms: split="bogus" is a documented divergence.
#
#     R's rpart.class() does `temp3 <- pmatch(parms$split, c("gini",
#     "information")); if (is.null(temp3)) stop("Invalid splitting rule")`.
#     Because pmatch() returns NA (not NULL) on no match, `is.null(NA)` is
#     FALSE, so R's stop() is unreachable dead code here: an unrecognized
#     split string is silently accepted (parms$split becomes NA) rather
#     than rejected. r2py_rpart's rpart_class() (rpart_class.py, ~line 90)
#     deliberately implements the *intended* check instead
#     (`if split is None: raise ValueError('Invalid splitting rule')`), so
#     Python correctly rejects the bogus value while R does not. This test
#     documents that intentional improvement rather than asserting (false)
#     R/Python parity.
# ---------------------------------------------------------------------------

def test_rpart_class_invalid_split_rule_is_a_known_python_improvement_over_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=list(split="bogus"))')
    )
    assert r_msg is None, "R is expected to silently accept an unmatched split string (pmatch() NA quirk)"

    with pytest.raises(ValueError, match="Invalid splitting rule"):
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", parms={"split": "bogus"})


# ---------------------------------------------------------------------------
# 17. Missing formula/data (neither a string formula+data nor a pre-built
#     model frame).
# ---------------------------------------------------------------------------

def test_rpart_missing_formula_and_model_raises_like_r():
    r_msg = r_error_message(lambda: run_r("rpart()"))

    with pytest.raises(Exception) as exc_info:
        rpart(object(), data=pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]}))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="missing formula/model")


# ---------------------------------------------------------------------------
# 18. Empty parms dict ("no names") for classification.
# ---------------------------------------------------------------------------

def test_rpart_class_parms_without_names_raises_like_r():
    df = _kyphosis_r_and_py()
    r_msg = r_error_message(
        lambda: run_r('rpart(Kyphosis ~ Age + Number + Start, data=df, method="class", parms=list(0.5, 0.5))')
    )

    with pytest.raises(Exception) as exc_info:
        rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", parms={})

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="parms without names")
