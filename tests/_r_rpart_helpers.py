"""Shared rpy2-based helpers for benchmarking r2py_rpart.rpart against R's
rpart::rpart.

This module is intentionally *not* named ``test_*`` so pytest does not try
to collect it directly; import from it in test_rpart_positive.py,
test_rpart_negative.py and test_rpart_edge.py instead.

All numeric comparisons should go through ``numpy.testing.assert_allclose``
(or ``math.isclose`` for scalars) rather than exact equality, to tolerate
floating point differences between R's and Python's arithmetic.
"""
from __future__ import annotations

import math
import os
import re
import warnings
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("rpy2", reason="rpy2 is required to benchmark against R's rpart::rpart")

import rpy2.robjects as ro  # noqa: E402
from rpy2.robjects import pandas2ri  # noqa: E402
from rpy2.robjects.conversion import localconverter  # noqa: E402
from rpy2.rinterface_lib.embedded import RRuntimeError  # noqa: E402
import rpy2.rinterface_lib.callbacks as _r_callbacks  # noqa: E402

try:
    from rpy2.robjects.packages import importr

    importr("rpart")
    importr("survival")
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"R packages 'rpart'/'survival' not available: {exc}", allow_module_level=True)


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ---------------------------------------------------------------------------
# Dataset loaders (mirroring the R `data(...)` sets shipped with rpart)
# ---------------------------------------------------------------------------

def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"))


def kyphosis_df() -> pd.DataFrame:
    """rpart's `kyphosis` dataset, with Kyphosis as an (unordered) 2-level factor."""
    df = load_csv("kyphosis")
    df["Kyphosis"] = pd.Categorical(df["Kyphosis"], categories=["absent", "present"])
    return df


CU_RELIABILITY_LEVELS = ["Much worse", "worse", "average", "better", "Much better"]


def cu_summary_df() -> pd.DataFrame:
    """rpart's `cu.summary` dataset: Reliability is an *ordered* factor, and
    Mileage/Reliability contain NAs -- useful for na.action + ordered-factor
    + multi-level-factor coverage simultaneously."""
    df = load_csv("cu_summary")
    df["Reliability"] = pd.Categorical(df["Reliability"], categories=CU_RELIABILITY_LEVELS, ordered=True)
    df["Country"] = pd.Categorical(df["Country"])
    df["Type"] = pd.Categorical(df["Type"])
    return df


def stagec_df() -> pd.DataFrame:
    """rpart's `stagec` dataset (prostate cancer), used for survival-flavoured
    method="poisson"/"exp" fits via Surv(pgtime, pgstat)."""
    df = load_csv("stagec")
    df["ploidy"] = pd.Categorical(df["ploidy"])
    return df


def mtcars_df() -> pd.DataFrame:
    df = load_csv("mtcars")
    df = df.rename(columns={df.columns[0]: "model"})
    return df


# ---------------------------------------------------------------------------
# R <-> Python plumbing
# ---------------------------------------------------------------------------

def to_r_dataframe(df: pd.DataFrame) -> Any:
    """Convert a pandas DataFrame to an R data.frame, preserving (ordered)
    categoricals as R factors."""
    with localconverter(ro.default_converter + pandas2ri.converter):
        return ro.conversion.py2rpy(df)


def from_r_dataframe(r_df: Any) -> pd.DataFrame:
    """Convert an R data.frame into a pandas DataFrame, preserving (ordered)
    factors as pandas Categoricals -- the mirror image of to_r_dataframe().
    ``r_df`` may be an already-evaluated rpy2 object, or an R source string
    to be evaluated first (e.g. ``"car.test.frame"`` after ``data(...)``)."""
    if isinstance(r_df, str):
        r_df = run_r(r_df)
    with localconverter(ro.default_converter + pandas2ri.converter):
        return ro.conversion.rpy2py(r_df)


def r_assign(name: str, value: Any) -> None:
    ro.globalenv[name] = value


def r_dataframe_assign(name: str, df: pd.DataFrame) -> None:
    r_assign(name, to_r_dataframe(df))


def run_r(code: str) -> Any:
    """Evaluate an R code snippet (with variables already assigned into
    R's global environment) and return the raw rpy2 object."""
    return ro.r(code)


def r_fit_rpart(formula: str, data_name: str = "df", **r_kwargs: str) -> Any:
    """Build and evaluate an R `rpart(formula, data=data_name, ...)` call.

    ``r_kwargs`` values are inserted verbatim as R source (the caller is
    responsible for producing valid R literals, e.g. via ``r_literal``).
    """
    args = [formula, f"data={data_name}"]
    args.extend(f"{k}={v}" for k, v in r_kwargs.items())
    code = "rpart(" + ", ".join(args) + ")"
    return run_r(code)


def r_literal(value: Any) -> str:
    """Render a simple Python value as an R literal for interpolation into
    an R code string (used for control=/parms=/cost=/xval= arguments)."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (float, np.floating)):
        fval = float(value)
        if math.isnan(fval):
            return "NaN"
        if math.isinf(fval):
            return "Inf" if fval > 0 else "-Inf"
        return repr(fval)
    if isinstance(value, (int, np.integer)):
        return repr(int(value))
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, dict):
        inner = ", ".join(f"{k}={r_literal(v)}" for k, v in value.items())
        return f"list({inner})"
    if isinstance(value, (list, tuple, np.ndarray)):
        inner = ", ".join(r_literal(v) for v in np.asarray(value).tolist())
        return f"c({inner})"
    raise TypeError(f"Cannot render {value!r} as an R literal")


def r_control(**kwargs: Any) -> str:
    return "rpart.control(" + ", ".join(f"{k}={r_literal(v)}" for k, v in kwargs.items()) + ")"


# ---------------------------------------------------------------------------
# rpart.control()-specific plumbing: calling R's rpart.control() directly
# (as opposed to embedding it inside a full rpart() fit) and unwrapping its
# returned list into a plain python dict, optionally also capturing any
# warning it raises without losing the (post-correction) return value.
# ---------------------------------------------------------------------------

def r_control_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert the R list returned by rpart.control() into a plain python
    dict, unwrapping length-1 vectors to scalars (longer vectors, and R
    NULL, are kept as a python list -- NULL becomes [])."""
    out: dict[str, Any] = {}
    for name in list(result.names):
        val = result.rx2(name)
        if isinstance(val, ro.rinterface.NULLType):
            out[name] = []
            continue
        vals = list(val)
        out[name] = vals[0] if len(vals) == 1 else vals
    return out


def r_rpart_control(**kwargs: Any) -> dict[str, Any]:
    """Call R's rpart.control(**kwargs) (kwargs rendered via r_literal) and
    return its result as a plain python dict via r_control_result_to_dict."""
    return r_control_result_to_dict(run_r(r_control(**kwargs)))


def r_eval_capturing_warning(code: str) -> tuple[Any, str | None]:
    """Evaluate an R expression, returning (result, first_warning_message).

    Unlike tryCatch()'s exiting warning handler (which would abandon the
    rest of the expression -- rpart.control() corrects the out-of-range
    value and returns its full list *after* signalling the warning), this
    uses withCallingHandlers()+invokeRestart("muffleWarning") so evaluation
    resumes normally after the warning is recorded, letting us verify both
    the warning text and the resulting (corrected) value in one call.
    """
    ro.globalenv["_last_warning"] = ro.NULL
    wrapped = (
        "withCallingHandlers({\n"
        f"{code}\n"
        "}, warning = function(w) {\n"
        "  assign('_last_warning', conditionMessage(w), envir=globalenv())\n"
        "  invokeRestart('muffleWarning')\n"
        "})"
    )
    result = run_r(wrapped)
    warning_obj = ro.globalenv["_last_warning"]
    warning_msg = None if isinstance(warning_obj, ro.rinterface.NULLType) else str(warning_obj[0])
    return result, warning_msg


def r_rpart_control_capturing_warning(**kwargs: Any) -> tuple[dict[str, Any], str | None]:
    """Like r_rpart_control(), but also returns the first warning message
    R's rpart.control() raised (or None), via r_eval_capturing_warning."""
    result, warning_msg = r_eval_capturing_warning(r_control(**kwargs))
    return r_control_result_to_dict(result), warning_msg


# ---------------------------------------------------------------------------
# Extraction of R fit components into plain numpy/python objects
# ---------------------------------------------------------------------------

def extract_r_fit(fit: Any) -> dict[str, Any]:
    """Pull the fields of an R `rpart` object that r2py_rpart.rpart's return
    dict also exposes, as plain numpy arrays / python scalars, avoiding
    pandas2ri's whole-data.frame conversion (which chokes on the
    matrix-valued `yval2` column of $frame)."""
    frame = fit.rx2("frame")
    out: dict[str, Any] = {
        "var": list(ro.r["as.character"](frame.rx2("var"))),
        "n": np.asarray(frame.rx2("n")),
        "wt": np.asarray(frame.rx2("wt")),
        "dev": np.asarray(frame.rx2("dev")),
        "yval": np.asarray(frame.rx2("yval")),
        "complexity": np.asarray(frame.rx2("complexity")),
        "ncompete": np.asarray(frame.rx2("ncompete")),
        "nsurrogate": np.asarray(frame.rx2("nsurrogate")),
        "frame_index": np.asarray(ro.r["row.names"](frame)).astype(str),
        "method": str(fit.rx2("method")[0]),
        "cptable": np.asarray(fit.rx2("cptable")),
        "cptable_cols": list(ro.r["colnames"](fit.rx2("cptable"))),
        "where": np.asarray(fit.rx2("where")),
    }
    splits = fit.rx2("splits")
    if not isinstance(splits, ro.rinterface.NULLType):
        out["splits"] = np.asarray(splits)
        # A root-only (or fully-pruned-to-root) fit's `$splits` is a
        # non-NULL-but-0-row matrix -- `rownames()` on a 0-row matrix is
        # itself NULL (there are no rows to name), unlike the >=1-row case
        # where rpart always sets real rownames. Guard for that so
        # extract_r_fit() doesn't blow up on such fits (e.g. prune()'d down
        # to a single leaf) -- confirmed empirically before adding this.
        splits_rownames = ro.r["rownames"](splits)
        out["splits_rownames"] = (
            [] if isinstance(splits_rownames, ro.rinterface.NULLType) else list(splits_rownames)
        )
    else:
        out["splits"] = None
    csplit = fit.rx2("csplit")
    if not isinstance(csplit, ro.rinterface.NULLType):
        out["csplit"] = np.asarray(csplit)
    else:
        out["csplit"] = None
    vimp = fit.rx2("variable.importance")
    if not isinstance(vimp, ro.rinterface.NULLType):
        # A root-only (or fully-pruned-to-root) fit's `$variable.importance`
        # is a non-NULL-but-length-0 vector (`logical(0)`) -- `names()` on a
        # length-0 vector is itself NULL, just like the 0-row-matrix
        # `rownames()` case handled above for `$splits`. Guard for that here
        # too, rather than assuming a non-NULL vector always has names.
        vimp_names = ro.r["names"](vimp)
        out["variable_importance"] = (
            {} if isinstance(vimp_names, ro.rinterface.NULLType) else dict(zip(list(vimp_names), np.asarray(vimp)))
        )
    else:
        out["variable_importance"] = None
    # `ylevels`/`xlevels` are stored as R *attributes* on the fit object
    # (attr(fit, "ylevels")), not as list elements -- rx2() only reaches
    # list elements, so attr() must be used instead.
    ylevels = ro.r["attr"](fit, "ylevels")
    if not isinstance(ylevels, ro.rinterface.NULLType):
        out["ylevels"] = list(ylevels)
    else:
        out["ylevels"] = None
    return out


def r_error_message(thunk: Callable[[], Any]) -> str | None:
    """Call a zero-arg callable that triggers R code; return the R error
    message text if it raises, else None. Suppresses R's own
    write-console error echo so it doesn't clutter test output."""
    original_warnerror = _r_callbacks.consolewrite_warnerror
    _r_callbacks.consolewrite_warnerror = lambda *_args, **_kwargs: None
    try:
        thunk()
    except RRuntimeError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return str(exc)
    finally:
        _r_callbacks.consolewrite_warnerror = original_warnerror
    return None


def assert_python_and_r_errors_agree(py_message: str, r_message: str | None, *, context: str) -> None:
    """Both R and Python must raise for a negative/edge test to pass. If
    they both raise but with different wording, warn (per the test-suite
    generation protocol) instead of failing -- error text is not part of
    rpart's documented contract."""
    assert r_message is not None, f"R did not raise for: {context}"
    if py_message.strip() not in r_message and r_message.strip() not in py_message:
        warnings.warn(
            f"Error message mismatch for {context!r}: "
            f"python={py_message!r} vs R={r_message!r}",
            UserWarning,
            stacklevel=2,
        )


# ---------------------------------------------------------------------------
# predict.rpart-specific plumbing: calling R's predict(fit, ...) (S3
# dispatch to predict.rpart) directly, and converting its return value
# (a plain numeric vector, a factor, or a matrix) into a plain python object
# directly comparable to r2py_rpart.predict_rpart()'s return value.
# ---------------------------------------------------------------------------

def r_predict(
    fit: Any,
    newdata: pd.DataFrame | None = None,
    type: str | None = None,
    na_action: str | None = None,
    newdata_var: str = "pred_newdata_tmp",
) -> Any:
    """Call R's predict(fit, ...) (S3-dispatched to predict.rpart) and return
    the raw rpy2 result object.

    ``fit`` is assigned into R's global environment under a temp name so it
    can be referenced from the generated call (this works whether ``fit``
    came from ``run_r()``/``r_fit_rpart()`` or was fetched back out of
    ``globalenv`` already). If ``newdata`` is given, it is converted via
    ``to_r_dataframe()`` (preserving (ordered) categoricals as R factors,
    exactly like ``r_dataframe_assign``) and assigned under ``newdata_var``.
    ``na_action`` (if given) is inserted verbatim as R source, e.g.
    ``"na.omit"``/``"na.fail"``/``"na.pass"``.

    Note: the temp variable names deliberately do *not* start with an
    underscore -- unlike Python, bare R identifiers cannot begin with `_`
    (that requires backtick-quoting), so `_pred_fit` would be a syntax
    error when interpolated into the generated call string.
    """
    ro.globalenv["pred_fit_tmp"] = fit
    args = ["pred_fit_tmp"]
    if newdata is not None:
        r_dataframe_assign(newdata_var, newdata)
        args.append(f"newdata={newdata_var}")
    if type is not None:
        args.append(f'type="{type}"')
    if na_action is not None:
        args.append(f"na.action={na_action}")
    return run_r("predict(" + ", ".join(args) + ")")


def r_predict_to_python(robj: Any) -> Any:
    """Convert an R predict.rpart() return value into a plain python object
    directly comparable to r2py_rpart.predict_rpart()'s return value:

    - a factor (``type="class"``)                  -> list[str] of level
      labels, via ``as.character`` (drops R's `levels` attribute, which the
      caller can check separately via ``levels(...)`` if needed).
    - a matrix (``type="matrix"``/``type="prob"``,
      or any array with a non-NULL ``dim``)         -> pandas.DataFrame
      (values + column names, if any; no column names for ``type="matrix"``,
      since R never sets ``dimnames(pred)[[2]]`` in that branch).
    - a plain numeric vector (``type="vector"``,
      or ``type="class"``'s underlying integer codes) -> 1-D numpy float
      array.
    """
    cls = list(ro.r["class"](robj))
    if "factor" in cls:
        return list(ro.r["as.character"](robj))
    dim = ro.r["dim"](robj)
    if not isinstance(dim, ro.rinterface.NULLType):
        arr = np.asarray(robj, dtype=np.float64)
        colnames_r = ro.r["colnames"](robj)
        colnames = None if isinstance(colnames_r, ro.rinterface.NULLType) else list(colnames_r)
        return pd.DataFrame(arr, columns=colnames)
    return np.asarray(robj, dtype=np.float64)


# ---------------------------------------------------------------------------
# print.rpart-specific plumbing: calling R's `rpart:::print.rpart(x, ...)`
# directly (rather than the S3-generic `print(x, ...)`) and capturing its
# console output as a list of lines, directly comparable to r2py_rpart's
# print_rpart() (which also writes its layout to stdout via builtin print()).
#
# print.rpart is called *directly* (via the triple-colon internal accessor,
# since it is registered as an S3 method -- `S3method(print, rpart)` in
# NAMESPACE -- but not itself exported) rather than through the `print()`
# generic, because print.rpart.Rd explicitly documents that "It can be
# invoked by calling print for an object of the appropriate class, or
# directly by calling print.rpart regardless of the class of x" -- the
# latter form is required for negative tests that pass in objects with no
# "rpart" class attribute at all (None, a bare list, a data.frame, ...),
# which `print()` would otherwise dispatch to print.default instead of
# print.rpart, sidestepping the `inherits(x, "rpart")` legitimacy check
# entirely.
# ---------------------------------------------------------------------------

def r_print_rpart_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for a `rpart:::print.rpart(x_expr, ...)` call.

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()").
    ``kwargs`` (minlength=/spaces=/cp=/digits=/nsmall=) are rendered via
    r_literal() and appended `name=value`; a kwarg whose value is None is
    *omitted* entirely (not passed as NULL) so that `missing(cp)` inside
    print.rpart stays TRUE when the caller doesn't care about cp -- passing
    cp=NULL explicitly would instead trigger `prune.rpart(x, cp=NULL)`.
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return "rpart:::print.rpart(" + ", ".join(args) + ")"


def r_print_rpart_lines(fit: Any, **kwargs: Any) -> list[str]:
    """Call R's `rpart:::print.rpart(fit, ...)` on an already-fitted R model
    object and return its printed console output as a list of lines (one
    per element of `capture.output()`'s returned character vector) --
    directly comparable to `capture_print_rpart_lines()`'s python-side
    return value.
    """
    ro.globalenv["print_fit_tmp"] = fit
    code = "capture.output(" + r_print_rpart_call_code("print_fit_tmp", **kwargs) + ")"
    result = run_r(code)
    return [str(s) for s in result]


def r_print_rpart_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `rpart:::print.rpart(x_expr, ...)` for its side effect only,
    returning the R error message string if it raises (via
    r_error_message()), else None. ``x_expr`` is R source, e.g. "NULL",
    "list()", "5", or a global variable name assigned beforehand.
    """
    code = r_print_rpart_call_code(x_expr, **kwargs)
    return r_error_message(lambda: run_r(code))


def capture_print_rpart_lines(capsys: Any, fit: dict[str, Any], **kwargs: Any) -> list[str]:
    """Call r2py_rpart's print_rpart(fit, ...) and return its stdout output
    as a list of lines, directly comparable to r_print_rpart_lines()'s
    return value. ``capsys`` is pytest's built-in fixture (passed in by the
    caller); a trailing empty string caused by print()'s own trailing
    newline (print_rpart's last line is written via a bare `print(...)`,
    unlike R's `cat(z, sep="\\n")` which has no trailing newline) is
    stripped so both sides compare as the same list of content lines.
    """
    from r2py_rpart import print_rpart

    print_rpart(fit, **kwargs)
    out = capsys.readouterr().out
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


# ---------------------------------------------------------------------------
# printcp-specific plumbing: calling R's `printcp(x, ...)` directly and
# capturing both its printed console output (as a list of lines, via
# capture.output()) and its *returned* value (invisible(x$cptable), a plain
# numeric matrix) in one call.
#
# Unlike print.rpart (an S3 method registered via `S3method(print, rpart)`
# in NAMESPACE but not itself exported), printcp IS exported directly from
# the rpart NAMESPACE (`export(..., printcp, ...)`) and is a plain function
# rather than an S3 generic -- so a bare `printcp(...)` call reaches its
# `inherits(x, "rpart")` legitimacy check for any `x`, with no need for the
# `rpart:::` triple-colon internal-access trick print.rpart's helpers use.
# ---------------------------------------------------------------------------

def r_printcp_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for a `printcp(x_expr, ...)` call.

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()").
    ``kwargs`` (currently just digits=) are rendered via r_literal() and
    appended `name=value`; a kwarg whose value is None is *omitted* entirely
    (not passed as NULL) so that `missing(digits)` inside printcp stays TRUE
    and its `getOption("digits") - 2L` default resolution actually runs.
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return "printcp(" + ", ".join(args) + ")"


def r_printcp_lines_and_result(fit: Any, **kwargs: Any) -> tuple[list[str], np.ndarray, list[str]]:
    """Call R's `printcp(fit, ...)` on an already-fitted R model object and
    return a 3-tuple:

      - the printed console output as a list of lines (one per element of
        `capture.output()`'s returned character vector) -- directly
        comparable to `capture_printcp_lines_and_result()`'s python-side
        return value;
      - the *returned* `x$cptable` value (`invisible(x$cptable)`), converted
        to a plain numpy array via `as.matrix()` (printcp's return is
        already a plain numeric matrix in every case exercised here, but
        `as.matrix()` guards against decay to a bare vector for a
        single-row table);
      - that returned value's column names (e.g. ``["CP", "nsplit", "rel
        error"]``, or with ``"xerror"``/``"xstd"`` appended when
        ``xval > 0``), for cross-checking against
        `r2py_rpart.printcp`'s DataFrame column labels.
    """
    ro.globalenv["printcp_fit_tmp"] = fit
    call_code = r_printcp_call_code("printcp_fit_tmp", **kwargs)
    lines_code = f"capture.output(printcp_result_tmp <- {call_code})"
    lines_result = run_r(lines_code)
    lines = [str(s) for s in lines_result]
    mat = run_r("as.matrix(printcp_result_tmp)")
    colnames_r = ro.r["colnames"](mat)
    colnames = [] if isinstance(colnames_r, ro.rinterface.NULLType) else list(colnames_r)
    return lines, np.asarray(mat, dtype=float), colnames


def r_printcp_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `printcp(x_expr, ...)` for its side effect only, returning the R
    error message string if it raises (via r_error_message()), else None.
    ``x_expr`` is R source, e.g. "NULL", "list()", "5", or a global variable
    name assigned beforehand.
    """
    code = r_printcp_call_code(x_expr, **kwargs)
    return r_error_message(lambda: run_r(code))


def capture_printcp_lines_and_result(
    capsys: Any, fit: dict[str, Any], **kwargs: Any
) -> tuple[list[str], Any]:
    """Call r2py_rpart's printcp(fit, ...) and return a 2-tuple of (its
    stdout output as a list of lines, its return value) -- directly
    comparable to `r_printcp_lines_and_result()`'s python-side counterpart.
    ``capsys`` is pytest's built-in fixture (passed in by the caller); a
    trailing empty string caused by print()'s own trailing newline (the cp
    table's last line is written via a bare `print(...)`, unlike R's
    `cat`-based lines, which have no trailing newline of their own) is
    stripped so both sides compare as the same list of content lines.
    """
    from r2py_rpart.printcp import printcp

    retval = printcp(fit, **kwargs)
    out = capsys.readouterr().out
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, retval


def printcp_find_line(lines: list[str], prefix: str) -> int:
    """Return the index of the first line in ``lines`` starting with
    ``prefix``, raising a plain (test-failure-friendly) AssertionError if no
    such line exists."""
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            return i
    raise AssertionError(f"no line starting with {prefix!r} found in {lines!r}")


def printcp_vars_used_r(r_lines: list[str]) -> set[str] | None:
    """Extract the set of variable names from R printcp output's
    "Variables actually used in tree construction:" block, if present
    (R's `if (!is.null(used))` guard is *always* true -- see printcp.R --
    so this block is present in every R printcp call, including
    root-only/no-split trees, where it reads the literal text
    "character(0)"). The R side prints via
    `print(sort(as.character(used)), quote=FALSE)`, R's vector-print
    layout (e.g. ``[1] Country Type   ``, index-prefixed and
    column-aligned, possibly wrapped across multiple physical lines for
    longer variable lists) -- this parses that layout back into a plain
    set of names, stripping the "[k]" index prefixes.

    Returns ``None`` if no such header line is found at all (should not
    happen for well-formed R printcp output).
    """
    header = "Variables actually used in tree construction:"
    for i, line in enumerate(r_lines):
        if line.strip() == header:
            content_lines = []
            j = i + 1
            while j < len(r_lines) and r_lines[j].strip() != "":
                content_lines.append(r_lines[j])
                j += 1
            joined = " ".join(cl.strip() for cl in content_lines)
            if joined == "character(0)":
                return set()
            tokens: list[str] = []
            for cl in content_lines:
                cl = re.sub(r"^\[\d+\]\s*", "", cl)
                tokens.extend(cl.split())
            return set(tokens)
    return None


def printcp_vars_used_py(py_lines: list[str]) -> set[str] | None:
    """Extract the set of variable names from r2py_rpart.printcp's own
    "Variables actually used in tree construction:" block, if present
    (printcp.py's `if used is not None and len(used) > 0:` guard *skips*
    this block entirely for a root-only/no-split tree -- see gap 3 in
    test_printcp_positive.py's module docstring -- unlike R, which always
    prints the block). The python side prints via
    `print(sorted(str(v) for v in used))`, a literal python list repr
    (e.g. ``['Country', 'Type']``), parsed back here via `ast.literal_eval`.

    Returns ``None`` if no such header line is found (including the
    root-only-tree case, where printcp.py omits the block entirely).
    """
    import ast

    header = "Variables actually used in tree construction:"
    for i, line in enumerate(py_lines):
        if line.strip() == header:
            return set(ast.literal_eval(py_lines[i + 1].strip()))
    return None


# ---------------------------------------------------------------------------
# plotcp-specific plumbing.
#
# plotcp(x, minline=, lty=, col=, upper=, ...) is a pure-side-effect plotting
# function -- like R's, r2py_rpart's plotcp() returns None (R's own plotcp
# ends with `invisible()`, i.e. NULL). So there is no "return value" to
# compare on either side; instead:
#
#   - `r_plotcp_derived_from_cptable()` below evaluates the *exact* sequence
#     of numeric derivations plotcp.R's body performs on a `cptable` matrix
#     (xstd, xerror, nsplit, ns, the geometric-mean `cp` vector, the default
#     `ylim`, the `signif(cp, 2)` axis labels, the size/splits upper-axis
#     labels, `minpos`, and the 1SE `minline` height) -- copied line-for-line
#     from rpart/R/plotcp.R -- given a synthetic `cptable`, independent of
#     any actual rpart fit or its (RNG-dependent, R-vs-python-divergent)
#     cross-validation folds. Feeding the *same* synthetic cptable into both
#     this R replica and r2py_rpart's plotcp() (via a minimal `{"cptable":
#     ...}` fit-like dict) isolates the comparison to plotcp's own derivation
#     logic, sidestepping the fact that R's and python's rpart() draw
#     independent xval folds for the same data (already noted as
#     incomparable in test_printcp_positive.py's xerror/xstd caveat).
#
#   - `r_plotcp_error()`/`r_plotcp_runs_without_error()` call the *actual*
#     exported `plotcp(x, ...)` R function (inside a no-op `pdf(NULL)`
#     graphics device, so it never tries to open a real display in a
#     headless test environment) for its legitimacy checks (`inherits(x,
#     "rpart")`, `match.arg(upper)`, `ncol(cptable) < 5`) and general
#     side-effect-only success/failure, which the derivation replica above
#     does not exercise at all (it has no `x`-legitimacy or `upper`
#     validation of its own).
# ---------------------------------------------------------------------------

def r_matrix_literal(arr: np.ndarray) -> str:
    """Render a 2-D numpy array as an R `matrix(c(...), nrow=, ncol=)`
    literal (e.g. for a synthetic `cptable`), without needing a full rpart
    fit. Values are flattened in column-major ("F") order to match R's own
    default `matrix()` fill order."""
    arr = np.asarray(arr, dtype=float)
    nrow, ncol = arr.shape
    values = ", ".join(r_literal(v) for v in arr.flatten(order="F"))
    return f"matrix(c({values}), nrow={nrow}, ncol={ncol})"


def r_rpart_like_expr(cptable: np.ndarray) -> str:
    """Render an R expression for a minimal object satisfying `inherits(x,
    "rpart")` with only a `cptable` element -- e.g. for feeding directly
    into a genuine `plotcp(...)` R call (as opposed to the derivation
    replica, which needs no class attribute at all)."""
    return f'structure(list(cptable = {r_matrix_literal(cptable)}), class = "rpart")'


def r_plotcp_derived_from_cptable(cptable: np.ndarray) -> dict[str, Any]:
    """Evaluate rpart/R/plotcp.R's own derivation logic (copied line-for-line,
    only omitting the actual `plot()`/`axis()`/`segments()`/`abline()` graphics
    calls) on a synthetic `cptable` matrix, returning every intermediate/derived
    quantity r2py_rpart.plotcp() also computes (see module-level note above).
    ``cptable`` must be a 2-D array with >= 5 columns, in rpart's own column
    order (CP, nsplit, rel error, xerror, xstd).
    """
    code = f"""
    local({{
        p.rpart <- {r_matrix_literal(cptable)}
        xstd <- p.rpart[, 5L]
        xerror <- p.rpart[, 4L]
        nsplit <- p.rpart[, 2L]
        ns <- seq_along(nsplit)
        cp0 <- p.rpart[, 1L]
        cp <- sqrt(cp0 * c(Inf, cp0[-length(cp0)]))
        ylim <- c(min(xerror - xstd) - 0.1, max(xerror + xstd) + 0.1)
        minpos <- min(seq_along(xerror)[xerror == min(xerror)])
        list(
            xstd = xstd,
            xerror = xerror,
            nsplit = nsplit,
            ns = ns,
            cp = cp,
            ylim = ylim,
            cp_labels = as.character(signif(cp, 2L)),
            size_labels = as.character(nsplit + 1),
            splits_labels = as.character(nsplit),
            minpos = minpos,
            minline_y = (xerror + xstd)[minpos]
        )
    }})
    """
    result = run_r(code)

    def _num(name: str) -> np.ndarray:
        return np.asarray(result.rx2(name), dtype=float)

    def _str(name: str) -> list[str]:
        return [str(s) for s in result.rx2(name)]

    return {
        "xstd": _num("xstd"),
        "xerror": _num("xerror"),
        "nsplit": _num("nsplit"),
        "ns": _num("ns"),
        "cp": _num("cp"),
        "ylim": tuple(_num("ylim")),
        "cp_labels": _str("cp_labels"),
        "size_labels": _str("size_labels"),
        "splits_labels": _str("splits_labels"),
        "minpos": int(_num("minpos")[0]),
        "minline_y": float(_num("minline_y")[0]),
    }


def plotcp_cp_labels_match_modulo_known_gap(py_labels: list[str], r_labels: list[str]) -> bool:
    """Compare plotcp's bottom-axis `cp` tick labels between the two sides,
    tolerating the two known, permanent string-formatting divergences
    (documented in test_plotcp_positive.py's module docstring):

      (a) R's `as.character(signif(cp, 2))` renders positive infinity as
          "Inf"; python's `str(...)` on the equivalent float renders it as
          lowercase "inf" (cp[0] is always +Inf per plotcp.R's own `c(Inf,
          cp0[-length(cp0)])` construction, so this affects every non-empty
          cptable).
      (b) A whole-number rounded value (e.g. an exact 0): R's
          `as.character(0)` is `"0"`; python's `str(round(0.0, ...))` keeps
          a trailing ".0" (`"0.0"`) that R's character coercion drops.

    Returns True iff every label matches case-insensitively (gap a) after
    also optionally stripping a trailing ".0" from the python side (gap b).
    """
    if len(py_labels) != len(r_labels):
        return False
    for py_label, r_label in zip(py_labels, r_labels):
        if py_label.lower() == r_label.lower():
            continue
        if py_label.endswith(".0") and py_label[:-2].lower() == r_label.lower():
            continue
        return False
    return True


def plotcp_cp_labels_numerically_close(py_labels: list[str], r_labels: list[str]) -> bool:
    """A looser, purely-numeric counterpart to
    `plotcp_cp_labels_match_modulo_known_gap()`: parses each label back to a
    float (`"Inf"`/`"inf"` both parse to `float("inf")` via python's own
    `float()`) and compares element-wise with `numpy.isclose`, ignoring
    *any* string-formatting difference -- including not just gaps (a)/(b)
    documented on `plotcp_cp_labels_match_modulo_known_gap()`, but also the
    distinct "0.0003" (python) vs "3e-04" (R) scientific-notation-threshold
    divergence demonstrated explicitly in
    test_plotcp_edge.py's `test_plotcp_cp_label_scientific_notation_threshold_known_gap`
    (python's `str()` and R's `as.character()` switch to scientific
    notation at different magnitude thresholds, even though both start from
    the same `signif(cp, 2)`-rounded numeric value). Used where a test's
    focus is on the underlying *rounded value* agreeing, not its rendering.
    """
    if len(py_labels) != len(r_labels):
        return False
    py_vals = np.array([float(v) for v in py_labels])
    r_vals = np.array([float(v) for v in r_labels])
    return bool(np.allclose(py_vals, r_vals, equal_nan=True))


def r_plotcp_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for a `plotcp(x_expr, ...)` call.

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()"/
    `r_rpart_like_expr(...)`). ``kwargs`` (minline=/lty=/col=/upper=) are
    rendered via r_literal() and appended `name=value`; a kwarg whose value
    is None is omitted entirely (so R's own argument defaults apply).
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return "plotcp(" + ", ".join(args) + ")"


def _r_plotcp_in_null_device(code: str) -> None:
    """Run R source that may call plotcp() (which tries to plot on 'the
    current graphical device') inside a no-op `pdf(NULL)` device, so it
    never attempts to open a real display in a headless test environment.
    The device is always closed afterward, even if `code` raises."""
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(code)
    finally:
        run_r("grDevices::dev.off()")


def r_plotcp_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `plotcp(x_expr, ...)` (the actual R function, inside a no-op
    graphics device) for its side effect only, returning the R error message
    string if it raises (via r_error_message()), else None."""
    code = r_plotcp_call_code(x_expr, **kwargs)
    return r_error_message(lambda: _r_plotcp_in_null_device(code))


def r_plotcp_runs_without_error(x_expr: str, **kwargs: Any) -> bool:
    """Call `plotcp(x_expr, ...)` (the actual R function, inside a no-op
    graphics device) purely to sanity-check that R's *real* plotcp() accepts
    a given input/kwargs combination without raising (a complement to
    r_plotcp_error(), used in positive/edge tests to confirm the synthetic
    cptable/kwargs used for the derivation-replica comparison is one R's own
    plotcp() actually accepts, not just one the hand-copied replica accepts)."""
    return r_plotcp_error(x_expr, **kwargs) is None


# ---------------------------------------------------------------------------
# plotcp-specific plumbing, python side: r2py_rpart.plotcp() itself returns
# None (mirroring R's `invisible()`) and communicates purely by mutating the
# `matplotlib.axes.Axes` it is given (or creates) -- `call_plotcp_and_extract`
# below invokes it against a fresh figure/axes and pulls out every quantity
# plotcp.py derives/draws, in a form directly comparable to
# `r_plotcp_derived_from_cptable()`'s return dict:
#
#   - the main `ax.plot(ns, xerror, ...)` line            -> "ns"/"xerror"
#   - `ax.set_ylim(...)`                                   -> "ylim"
#   - the bottom-axis `cp` tick labels                     -> "cp_labels"
#   - the `ax.vlines(...)` error-bar segments (ymin/ymax per ns position)
#                                                           -> "xerror_minus_std"/"xerror_plus_std"
#   - the top (`ax.twiny()`) axis tick labels, if `upper != "none"`
#                                                           -> "top_labels" (else None)
#   - the `ax.axhline(...)` 1SE horizon, if `minline=True` -> "minline_y" (else None)
#
# The figure is always closed afterward (even on error) to avoid leaking
# matplotlib figures across the test session.
# ---------------------------------------------------------------------------

def call_plotcp_and_extract(fit: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Call r2py_rpart.plotcp(fit, ax=<fresh axes>, **kwargs) and return a
    dict of every quantity it plotted, pulled back out of the Axes object.
    ``kwargs`` are the same plotcp() keyword arguments (minline=/lty=/col=/
    upper=/ylim=/...) -- ``upper``/``minline`` are also inspected here (with
    their own plotcp() defaults, 'size'/True) purely to know which optional
    pieces (top axis / minline) to expect back out."""
    import matplotlib.pyplot as plt

    from r2py_rpart.plotcp import plotcp

    upper = kwargs.get("upper", "size")
    minline = kwargs.get("minline", True)
    fig, ax = plt.subplots()
    try:
        retval = plotcp(fit, ax=ax, **kwargs)

        main_line = ax.lines[0]
        ns = np.asarray(main_line.get_xdata(), dtype=float)
        xerror = np.asarray(main_line.get_ydata(), dtype=float)
        ylim = ax.get_ylim()
        cp_labels = [t.get_text() for t in ax.get_xticklabels()]

        vcoll = ax.collections[0]
        segments = vcoll.get_segments()
        xerror_minus_std = np.asarray([seg[0][1] for seg in segments], dtype=float)
        xerror_plus_std = np.asarray([seg[1][1] for seg in segments], dtype=float)

        top_labels = None
        top_xlabel = None
        if upper in ("size", "splits"):
            top_ax = fig.axes[-1]
            top_labels = [t.get_text() for t in top_ax.get_xticklabels()]
            top_xlabel = top_ax.get_xlabel()

        minline_y = None
        if minline:
            for line in ax.lines[1:]:
                ydata = np.asarray(line.get_ydata(), dtype=float)
                if len(ydata) >= 2 and np.allclose(ydata, ydata[0]):
                    minline_y = float(ydata[0])
                    break

        return {
            "retval": retval,
            "ns": ns,
            "xerror": xerror,
            "ylim": ylim,
            "cp_labels": cp_labels,
            "xerror_minus_std": xerror_minus_std,
            "xerror_plus_std": xerror_plus_std,
            "top_labels": top_labels,
            "top_xlabel": top_xlabel,
            "bottom_xlabel": ax.get_xlabel(),
            "bottom_ylabel": ax.get_ylabel(),
            "n_lines": len(ax.lines),
            "minline_y": minline_y,
        }
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot.rpart-specific plumbing.
#
# plot.rpart(x, uniform=, branch=, compress=, nspace=, margin=, minbranch=,
# branch.col=, branch.lty=, branch.lwd=, ...) is registered as an S3 method
# for the `plot` generic (`S3method(plot, rpart)` in NAMESPACE) -- so the
# *documented* calling convention is the plain generic `plot(fit, ...)` (used
# below for genuine "x really is class 'rpart'" scenarios), while its own
# internal legitimacy checks (`inherits(x, "rpart")`, `nrow(x$frame) <= 1`)
# are exercised directly via `rpart:::plot.rpart(x, ...)` for negative tests
# whose `x` deliberately has no "rpart" class at all (mirroring
# print.rpart's own `rpart:::print.rpart` convention above -- plain
# `plot(x)` on a non-"rpart"-classed `x` would dispatch to `plot.default`
# instead, never reaching plot.rpart's checks).
#
# Like plotcp, plot.rpart is a side-effect plotting function -- but unlike
# plotcp (which ends `invisible()`/NULL), plot.rpart *does* return a
# meaningful value: `invisible(list(x = xx, y = yy))`, the node coordinates
# -- directly comparable to r2py_rpart.plot_rpart()'s own `{"x":..., "y":...}`
# return dict. So both the *returned* coordinates and the *plotted* data
# (branch line segments, "|" root glyph, axis limits) pulled back out of the
# `matplotlib.axes.Axes` are compared below.
#
# `r_plot_rpart_derived()` is an R replica of rpartco.R + rpart.branch.R +
# plot.rpart.R's own coordinate/branch/xlim/ylim derivation (copied
# line-for-line, only omitting the actual `plot()`/`text()`/`lines()`
# graphics calls), run directly on a synthetic/extracted `(node, var, dev)`
# triple -- i.e. the *frame* r2py_rpart's own rpartco.py/rpart_branch.py
# consume -- rather than on a full rpart fit. This sidesteps the fact that
# R's and python's rpart() draw independent trees for the same
# formula/data in general (tree *structure* -- which var/split is chosen at
# each node -- can differ, even though this is a deterministic, non-xval
# computation unlike plotcp's RNG-driven cptable): feeding the *same*
# (node, var, dev) triple -- extracted directly from a genuine
# r2py_rpart.rpart() fit's `frame` via `extract_frame_arrays()` -- into both
# this R replica and r2py_rpart.plot_rpart() isolates the comparison to the
# coordinate-derivation logic itself.
# ---------------------------------------------------------------------------

def extract_frame_arrays(fit: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pull `node` (frame row names, as float), `var`, and `dev` straight out
    of a r2py_rpart fit's `frame` (a pandas DataFrame indexed by node id) --
    the exact three columns rpartco.py/rpart_branch.py (and their R
    originals, rpartco.R/rpart.branch.R) operate on, in frame row order."""
    frame = fit["frame"]
    node = frame.index.astype(float).to_numpy()
    var = frame["var"].astype(str).to_numpy()
    dev = frame["dev"].astype(float).to_numpy()
    return node, var, dev


def _r_num_vec(values: Any) -> str:
    return "c(" + ", ".join(r_literal(float(v)) for v in np.asarray(values, dtype=float)) + ")"


def _r_str_vec(values: Any) -> str:
    return "c(" + ", ".join(f'"{v}"' for v in values) + ")"


def r_plot_rpart_derived(
    node: np.ndarray,
    var: np.ndarray,
    dev: np.ndarray,
    *,
    uniform: bool = False,
    branch: float = 1.0,
    compress: bool = False,
    nspace: float | None = None,
    minbranch: float = 0.3,
    margin: float = 0.0,
) -> dict[str, Any]:
    """Evaluate rpartco.R + rpart.branch.R + plot.rpart.R's own
    coordinate/xlim/ylim/branch-segment derivation (copied line-for-line,
    only omitting the graphics calls themselves) on a synthetic/extracted
    `(node, var, dev)` triple, mirroring exactly the `compress`/`nspace`
    resolution plot.rpart.R itself performs (`if (compress & missing(nspace))
    nspace <- branch; if (!compress) nspace <- -1L`) -- see module-level note
    above. Returns every quantity r2py_rpart.plot_rpart() (via rpartco()/
    rpart_branch()) also computes: the node `x`/`y` coordinates, the
    `xlim`/`ylim` plot region, and the branch line segments' `x`/`y` data
    (flattened in column-major/"F" order, matching `temp['x'].ravel(order=
    'F')` on the python side -- i.e. directly comparable to what ends up in
    a single `ax.plot(...)` call's line data).
    """
    eff_nspace = branch if (compress and nspace is None) else (nspace if compress else -1.0)
    code = f"""
    local({{
      node <- {_r_num_vec(node)}
      var <- {_r_str_vec(var)}
      dev <- {_r_num_vec(dev)}
      uniform <- {"TRUE" if uniform else "FALSE"}
      branch <- {r_literal(float(branch))}
      nspace <- {r_literal(float(eff_nspace))}
      minbranch <- {r_literal(float(minbranch))}
      margin <- {r_literal(float(margin))}

      depth <- floor(log(node, base = 2) + 1e-7)
      depth <- depth - min(depth)
      is.leaf <- (var == "<leaf>")

      if (uniform) {{
        y <- (1 + max(depth) - depth) / max(depth, 4L)
      }} else {{
        y <- dev
        temp <- split(seq_along(node), depth)
        parent <- match(node %/% 2L, node)
        sibling <- match(ifelse(node %% 2L, node - 1L, node + 1L), node)
        for (i in temp[-1L]) {{
          temp2 <- dev[parent[i]] - (dev[i] + dev[sibling[i]])
          y[i] <- y[parent[i]] - temp2
        }}
        fudge <- minbranch * diff(range(y)) / max(depth)
        for (i in temp[-1L]) {{
          temp2 <- dev[parent[i]] - (dev[i] + dev[sibling[i]])
          haskids <- !(is.leaf[i] & is.leaf[sibling[i]])
          y[i] <- y[parent[i]] - ifelse(temp2 <= fudge & haskids, fudge, temp2)
        }}
        y <- y / max(y)
      }}

      x <- double(length(node))
      x[is.leaf] <- seq(sum(is.leaf))
      left.child <- match(node * 2L, node)
      right.child <- match(node * 2L + 1L, node)
      temp <- split(seq_along(node)[!is.leaf], depth[!is.leaf])
      for (i in rev(temp))
        x[i] <- 0.5 * (x[left.child[i]] + x[right.child[i]])

      if (nspace >= 0) {{
        compress_fn <- function(x, me, depth) {{
          lson <- me + 1L
          if (is.leaf[lson]) left <- list(left = x[lson], right = x[lson],
                                           depth = depth + 1L, sons = lson)
          else {{ left <- compress_fn(x, me + 1L, depth + 1L); x <- left$x }}

          rson <- me + 1L + length(left$sons)
          if (is.leaf[rson]) right <- list(left = x[rson], right = x[rson],
                                            depth = depth + 1L, sons = rson)
          else {{ right <- compress_fn(x, rson, depth + 1L); x <- right$x }}

          maxd <- max(left$depth, right$depth) - depth
          mind <- min(left$depth, right$depth) - depth
          slide <- min(right$left[1L:mind] - left$right[1L:mind]) - 1L
          if (slide > 0) {{
            x[right$sons] <- x[right$sons] - slide
            x[me] <- (x[right$sons[1L]] + x[left$sons[1L]]) / 2
          }} else slide <- 0

          if (left$depth > right$depth) {{
            templ <- left$left
            tempr <- left$right
            tempr[1L:mind] <- pmax(tempr[1L:mind], right$right - slide)
          }} else {{
            templ <- right$left - slide
            tempr <- right$right - slide
            templ[1L:mind] <- pmin(templ[1L:mind], left$left)
          }}

          list(x = x,
               left = c(x[me] - nspace * (x[me] - x[lson]), templ),
               right = c(x[me] - nspace * (x[me] - x[rson]), tempr),
               depth = maxd + depth, sons = c(me, left$sons, right$sons))
        }}
        x <- compress_fn(x, 1L, 1L)$x
      }}

      xx <- x; yy <- y
      xlim <- range(xx) + diff(range(xx)) * c(-margin, margin)
      ylim <- range(yy) + diff(range(yy)) * c(-margin, margin)

      ## rpart.branch.R
      is.left <- (node %% 2L == 0L)
      node.left <- node[is.left]
      parent2 <- match(node.left / 2L, node)
      sibling2 <- match(node.left + 1L, node)
      btemp <- (xx[sibling2] - xx[is.left]) * (1 - branch) / 2
      bx <- rbind(xx[is.left], xx[is.left] + btemp, xx[sibling2] - btemp, xx[sibling2], NA)
      by <- rbind(yy[is.left], yy[parent2], yy[parent2], yy[sibling2], NA)

      list(x = xx, y = yy, xlim = xlim, ylim = ylim,
           branch_x = as.vector(bx), branch_y = as.vector(by))
    }})
    """
    result = run_r(code)
    return {
        "x": np.asarray(result.rx2("x"), dtype=float),
        "y": np.asarray(result.rx2("y"), dtype=float),
        "xlim": tuple(np.asarray(result.rx2("xlim"), dtype=float)),
        "ylim": tuple(np.asarray(result.rx2("ylim"), dtype=float)),
        "branch_x": np.asarray(result.rx2("branch_x"), dtype=float),
        "branch_y": np.asarray(result.rx2("branch_y"), dtype=float),
    }


def r_rpart_like_expr_for_plot(node: np.ndarray, var: np.ndarray, dev: np.ndarray) -> str:
    """Render an R expression for a minimal object satisfying `inherits(x,
    "rpart")` with only a `frame` (a data.frame with `var`/`dev` columns and
    `node` as row names) -- enough for plot.rpart.R's own `nrow(x$frame)`
    check and rpartco.R/rpart.branch.R's frame access, for feeding into a
    genuine `plot(...)`/`rpart:::plot.rpart(...)` R call (as opposed to
    `r_plot_rpart_derived()`, which needs no class attribute at all)."""
    node_r = _r_num_vec(node)
    var_r = _r_str_vec(var)
    dev_r = _r_num_vec(dev)
    return (
        f"structure(list(frame = data.frame(var = {var_r}, dev = {dev_r}, "
        f"row.names = as.character({node_r}))), class = \"rpart\")"
    )


def r_plot_rpart_call_code(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str:
    """Build the R source for a `plot(x_expr, ...)` call (the documented S3
    dispatch route, `generic=True`) or a direct `rpart:::plot.rpart(x_expr,
    ...)` call (`generic=False` -- required whenever `x_expr` has no
    "rpart" class, since plain `plot()` would otherwise dispatch to
    `plot.default` and never reach plot.rpart's own legitimacy checks).
    ``kwargs`` (uniform=/branch=/compress=/nspace=/margin=/minbranch=/
    **branch.col**=/**branch.lty**=/**branch.lwd**=) are rendered via
    r_literal() and appended `name=value`; a kwarg whose value is None is
    omitted entirely so R's own argument defaults apply. Kwarg names with a
    trailing underscore (e.g. ``branch_col``) are translated to their
    R-native dotted spelling (``branch.col``).
    """
    fn = "plot" if generic else "rpart:::plot.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        r_name = k.replace("_", ".")
        args.append(f"{r_name}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def _r_plot_rpart_in_null_device(code: str) -> Any:
    """Run R source that may call plot()/plot.rpart() (which tries to plot
    on 'the current graphical device') inside a no-op `pdf(NULL)` device, so
    it never attempts to open a real display in a headless test environment.
    The device is always closed afterward, even if `code` raises. Returns
    the value of the last expression evaluated (plot.rpart's own
    `invisible(list(x=,y=))` return value survives being fetched this way --
    `invisible()` only suppresses top-level auto-print, not the value
    itself)."""
    run_r("grDevices::pdf(NULL)")
    try:
        return run_r(code)
    finally:
        run_r("grDevices::dev.off()")


def r_plot_rpart_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str | None:
    """Call `plot(x_expr, ...)`/`rpart:::plot.rpart(x_expr, ...)` (the actual
    R function, inside a no-op graphics device) for its side effect only,
    returning the R error message string if it raises (via
    r_error_message()), else None."""
    code = r_plot_rpart_call_code(x_expr, generic=generic, **kwargs)
    return r_error_message(lambda: _r_plot_rpart_in_null_device(code))


def r_plot_rpart_runs_without_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> bool:
    """Sanity-check that R's *real* plot()/plot.rpart() accepts a given
    input/kwargs combination without raising (a complement to
    r_plot_rpart_error(), used in positive/edge tests to confirm the
    synthetic node/var/dev triple + kwargs used for the derivation-replica
    comparison is one R's own plot.rpart() actually accepts)."""
    return r_plot_rpart_error(x_expr, generic=generic, **kwargs) is None


def r_plot_rpart_retval(x_expr: str, *, generic: bool = True, **kwargs: Any) -> dict[str, np.ndarray]:
    """Call the genuine R `plot(x_expr, ...)` (S3-dispatched to plot.rpart)
    inside a no-op graphics device and capture its own `invisible(list(x =
    xx, y = yy))` return value as plain numpy arrays -- directly comparable
    to r2py_rpart.plot_rpart()'s own `{"x": xx, "y": yy}` return dict, as an
    extra end-to-end cross-check alongside the `r_plot_rpart_derived()`
    replica (which recomputes the same quantities independently rather than
    capturing plot.rpart's actual return value)."""
    code = r_plot_rpart_call_code(x_expr, generic=generic, **kwargs)
    # plot.rpart's own `invisible(list(x=,y=))` return marks the value
    # invisible; a bare top-level `retval_tmp <- <code>` assignment (or even
    # the call by itself) evaluates to a NULL as seen through rpy2's ro.r(),
    # since the invisibility flag survives to the top level. Explicitly
    # re-referencing the bound name as the final expression in a `local({})`
    # block un-marks it, so it comes back as the real list.
    wrapped = f"local({{ retval_tmp <- {code}; retval_tmp }})"
    result = _r_plot_rpart_in_null_device(wrapped)
    return {
        "x": np.asarray(result.rx2("x"), dtype=float),
        "y": np.asarray(result.rx2("y"), dtype=float),
    }


def r_post_default_title_for_formula(formula: str) -> str:
    """Evaluate post.rpart.R's own title-*default* derivation --
    `temp <- attr(tree$terms, "variables")[2L]; title(paste("Endpoint =",
    temp), ...)` -- for a given model ``formula`` (R source, e.g.
    ``"Kyphosis ~ Age + Number + Start"``), independent of any particular
    fitted tree/frame (``terms()`` depends only on the formula itself, not on
    the data or the resulting split structure) -- sidestepping the fact that
    R's and python's rpart() can pick different splits for the same
    formula/data (the usual reason this test suite feeds a shared derived
    quantity into both sides rather than comparing two independent fits
    outright; here there is nothing tree-structure-dependent to begin with).

    Returns the resolved title string (e.g. ``"Endpoint = Kyphosis"``),
    directly comparable to r2py_rpart.post_rpart()'s own
    ``f"Endpoint = {tree['terms']['variables'][1]}"`` -- see
    test_post_edge.py's `test_post_default_title_endpoint_index_known_bug`
    for the confirmed off-by-one divergence this exposes (R's `variables`
    call-object indexing counts the leading `list` function symbol as
    position 1, so `[2L]` is the *response* variable; python's plain
    `variables` list has no such leading placeholder, so index `[1]` is
    instead the *first predictor*).
    """
    code = (
        f'local({{ tt <- terms({formula}); temp <- attr(tt, "variables")[2L]; '
        f'paste("Endpoint =", temp) }})'
    )
    result = run_r(code)
    return str(result[0])


def _r_post_arg_name(k: str) -> str:
    """Translate a python-side post()/post_rpart() kwarg spelling into its
    R-native dotted equivalent: a *trailing* underscore (``title_``, mirroring
    R's `title.` -- a bare trailing dot is not a legal python identifier
    suffix) becomes a trailing dot; any other underscore (``use_n`` ->
    `use.n`) is translated in place."""
    if k.endswith("_"):
        return k[:-1] + "."
    return k.replace("_", ".")


def r_post_call_code(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str:
    """Build the R source for a `post(x_expr, ...)` call (the documented S3
    dispatch route -- `post <- function(tree, ...) UseMethod("post")`,
    `generic=True`) or a direct `rpart:::post.rpart(x_expr, ...)` call
    (`generic=False`). ``kwargs`` (title_=/filename=/digits=/pretty=/use_n=/
    horizontal=) are rendered via r_literal() and appended `name=value` using
    their R-native dotted spelling (via `_r_post_arg_name`); a kwarg whose
    value is None is omitted entirely so R's own argument defaults/
    `missing()` checks apply.
    """
    fn = "post" if generic else "rpart:::post.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{_r_post_arg_name(k)}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def _r_post_in_null_device(code: str) -> Any:
    """Run R source that may call post()/post.rpart() (which, for
    `filename=""`, plots on 'the current graphical device', and otherwise
    opens its own `postscript(...)` device) inside a no-op `pdf(NULL)` device
    first, so a `filename=""` call never tries to open a real display in a
    headless test environment. The pdf(NULL) device is always closed
    afterward, even if `code` raises."""
    run_r("grDevices::pdf(NULL)")
    try:
        return run_r(code)
    finally:
        run_r("grDevices::dev.off()")


def r_post_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str | None:
    """Call `post(x_expr, ...)`/`rpart:::post.rpart(x_expr, ...)` (the actual
    R function, inside a no-op graphics device) for its side effect only,
    returning the R error message string if it raises (via
    r_error_message()), else None."""
    code = r_post_call_code(x_expr, generic=generic, **kwargs)
    return r_error_message(lambda: _r_post_in_null_device(code))


def r_post_runs_without_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> bool:
    """Sanity-check that R's *real* post()/post.rpart() accepts a given
    input/kwargs combination without raising (a complement to
    r_post_error())."""
    return r_post_error(x_expr, generic=generic, **kwargs) is None


def r_text_rpart_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `rpart:::text.rpart(x_expr, ...)` directly (bypassing the
    `text()` S3 generic's own dispatch -- exactly mirroring how
    post_rpart.py's own call to text_rpart() always reaches text_rpart's
    legitimacy checks directly, regardless of any class marker on `tree`,
    since python's post_rpart() never goes through a generic dispatcher of
    its own) inside a no-op graphics device, returning the R error message
    string if it raises, else None. ``kwargs`` (all=/use_n=/fancy=/digits=/
    pretty=/minlength=) are rendered via r_literal() with R-native dotted
    spelling, same as r_post_call_code()."""
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{_r_post_arg_name(k)}={r_literal(v)}")
    code = "rpart:::text.rpart(" + ", ".join(args) + ")"
    return r_error_message(lambda: _r_post_in_null_device(code))


# ---------------------------------------------------------------------------
# text.rpart-specific plumbing (beyond the legitimacy-check-only
# `r_text_rpart_error` above).
#
# text.rpart(x, splits=, label, FUN=text, all=, pretty=, digits=, use.n=,
# fancy=, fwidth=, fheight=, bg=par("bg"), minlength=, ...) is an S3 method
# for the `text` generic (`S3method(text, rpart)` in rpart's NAMESPACE) --
# exactly like plot.rpart, it is a pure side-effect function (its own body
# ends `invisible()`, i.e. NULL) whose `rpartco(x)` call depends on
# `rpart_env` having *already* been populated by a prior `plot(x, ...)` call
# in the very same graphics device (rpartco's own `pn <- paste0("device",
# dev.cur())` lookup) -- exactly the plot-then-annotate two-step
# text.rpart.Rd's own example demonstrates (`plot(freen.tr);
# text(freen.tr, use.n = TRUE, all = TRUE)`).
#
# Unlike plot.rpart's node coordinates (which are structurally guaranteed to
# match between an R-derivation-replica and python given the same (node,
# var, dev) triple, regardless of what underlying dataset produced them),
# text.rpart's *labels* additionally depend on `x$splits`/`x$csplit`/
# `x$frame$yval`(`2`)/`x$functions$text` -- i.e. on the *entire* fitted
# model, not just those 3 columns. So rather than hand-copying
# text.rpart.R's logic into a synthetic-object R replica (as done for
# plot.rpart/plotcp), this file instead substitutes a custom `FUN=`
# *capturing* closure -- on both sides -- into the exact same
# already-fitted model. This relies on R's and r2py_rpart's own `rpart(...)`
# choosing the *identical* tree structure for a given formula/data --
# confirmed empirically (see this file's docstring-adjacent tests) for
# every dataset used below (kyphosis/car.test.frame/cu.summary/stagec, the
# same ones already relied on throughout this test suite) -- letting
# text.rpart's real, unmodified label/position derivation logic run on both
# sides and simply recording every (x, y, labels) triple each FUN()
# invocation receives, in call order -- directly comparable call-for-call.
#
# The one remaining wrinkle: `cxy <- par("cxy")` (character width/height in
# data coordinates) is a real, device-and-font-dependent quantity with no
# reason to numerically agree between R's graphics device and matplotlib's
# font metrics -- text_rpart.py's own `cxy=` parameter exists specifically
# so callers (here, tests) can override this resolution and inject a fixed
# value instead of letting each side compute its own incompatible guess.
# `r_text_rpart_capture()` below fetches R's *actual* `par("cxy")` for the
# `pdf(NULL)` null device (deterministic across runs, for a fixed
# pointsize/device) and returns it alongside the captured calls, so callers
# feed that exact same tuple into `call_text_rpart_and_extract(fit,
# cxy=that_tuple, ...)` -- isolating the comparison to text.rpart's own
# label/position *derivation* logic, not to cxy resolution.
#
# KNOWN BUG (documented, not worked around, in test_text_rpart_edge.py):
# text_rpart.py's `fancy=True` branch mis-derives the left/right split-edge
# label selection -- it indexes `left_child`/`right_child` (computed for
# *every* frame row) by the `is_left` boolean mask (rows that are
# themselves left children) instead of by "has a left/right child at all"
# (i.e. non-leaf rows), where R's own `left.child[!is.na(left.child)]` /
# `right.child[!is.na(right.child)]` select. The two masks happen to have
# the same *cardinality* (every non-leaf node contributes exactly one left
# child and one right child, so `sum(!is.leaf) == sum(is_left) ==
# sum(is_right)`), so no shape error is raised, but the *values* silently
# differ. Only the two edge-label FUN() calls are affected -- the leaf/node
# stat-label FUN() call (always the *last* capture, regardless of
# `fancy=`) is untouched by this bug and matches R exactly.
# ---------------------------------------------------------------------------

def r_text_rpart_capture_code(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str:
    """Build the R source for a `text(x_expr, FUN=text_capture_fun_tmp, ...)`
    call (the documented S3 dispatch route, `generic=True`) or a direct
    `rpart:::text.rpart(x_expr, FUN=text_capture_fun_tmp, ...)` call
    (`generic=False`, needed whenever `x_expr` has no "rpart" class).
    ``kwargs`` (splits=/all=/pretty=/digits=/use_n=/fancy=/fwidth=/fheight=/
    bg=/minlength=/srt=) are rendered via r_literal() with R-native dotted
    spelling (via `_r_post_arg_name`, e.g. use_n -> use.n); a kwarg whose
    value is None is omitted entirely so R's own defaults/`missing()`
    checks apply. `text_capture_fun_tmp` must already be assigned into
    globalenv (see `r_text_rpart_capture`)."""
    fn = "text" if generic else "rpart:::text.rpart"
    args = [x_expr, "FUN=text_capture_fun_tmp"]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{_r_post_arg_name(k)}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def r_text_rpart_capture(
    fit: Any, *, generic: bool = True, plot_kwargs: dict[str, Any] | None = None, **kwargs: Any
) -> tuple[list[dict[str, Any]], tuple[float, float]]:
    """Call R's genuine `plot(fit, **plot_kwargs)` (to populate
    `rpart_env`'s per-device parms, mirroring the mandatory plot-then-text
    order documented in text.rpart.Rd -- see module-level note above)
    followed by `text(fit, FUN=<capturing closure>, ...)` (via
    `r_text_rpart_capture_code`), both inside the same `pdf(NULL)` null
    device, and return a 2-tuple:

      - the list of every (x, y, labels) triple text.rpart's body passed to
        FUN, in call order, as plain python dicts (`{"x": np.ndarray, "y":
        np.ndarray, "labels": list[str | None]}` -- an R `NA_character_`
        label position becomes python `None`);
      - R's actual `par("cxy")` for that null device, as a plain (width,
        height) float tuple -- feed this directly into
        `call_text_rpart_and_extract(fit, cxy=that_tuple, ...)` so both
        sides use identical label offsets (see module-level note above).
    """
    ro.globalenv["text_fit_tmp"] = fit
    run_r("grDevices::pdf(NULL)")
    try:
        plot_code = r_plot_rpart_call_code("text_fit_tmp", generic=generic, **(plot_kwargs or {}))
        run_r(plot_code)
        cxy = tuple(np.asarray(run_r('par("cxy")'), dtype=float).tolist())
        run_r(
            "text_capture_tmp <- list(); "
            "text_capture_fun_tmp <- function(x, y, labels, ...) { "
            "text_capture_tmp[[length(text_capture_tmp) + 1]] <<- "
            "list(x = as.numeric(x), y = as.numeric(y), labels = labels) }"
        )
        code = r_text_rpart_capture_code("text_fit_tmp", generic=generic, **kwargs)
        run_r(code)
    finally:
        run_r("grDevices::dev.off()")

    result = run_r("text_capture_tmp")
    calls: list[dict[str, Any]] = []
    for i in range(1, len(result) + 1):
        item = result.rx2(i)
        x_arr = np.asarray(item.rx2("x"), dtype=float)
        y_arr = np.asarray(item.rx2("y"), dtype=float)
        labels_r = item.rx2("labels")
        if isinstance(labels_r, ro.rinterface.NULLType) or len(labels_r) == 0:
            labels: list[str | None] = []
        else:
            na_mask = list(ro.r["is.na"](labels_r))
            labels = [None if na else str(v) for na, v in zip(na_mask, labels_r)]
        calls.append({"x": x_arr, "y": y_arr, "labels": labels})
    return calls, cxy


def call_text_rpart_and_extract(
    fit: dict[str, Any], *, plot_kwargs: dict[str, Any] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Call r2py_rpart's `plot_rpart(fit, **plot_kwargs)` (to populate
    `rpart_env['device1']`, mirroring the mandatory plot-then-text order --
    see module-level note above) followed by `text_rpart(fit,
    FUN=<capturing closure>, **kwargs)` on a freshly created Axes, and
    return a dict with:

      - "calls": every (x, y, labels) triple passed to FUN, in call order,
        as plain python dicts (`{"x": np.ndarray, "y": np.ndarray,
        "labels": list[str | None]}`) -- directly comparable, call-for-call,
        to `r_text_rpart_capture()`'s own return value;
      - "retval": text_rpart()'s own return value (always None);
      - "ax"/"fig": the live Axes/Figure (NOT yet closed -- caller must
        `plt.close(fig)` when done inspecting patches/texts), for tests
        that also need to inspect `ax.patches` (fancy=True ovals/rectangles)
        directly.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.plot_rpart import plot_rpart
    from r2py_rpart.text_rpart import text_rpart

    calls: list[dict[str, Any]] = []

    def capture_fun(xs: Any, ys: Any, labels: Any, **_kw: Any) -> None:
        calls.append({
            "x": np.asarray(xs, dtype=float),
            "y": np.asarray(ys, dtype=float),
            "labels": [None if (isinstance(v, float) and np.isnan(v)) else v for v in labels],
        })

    fig, ax = plt.subplots()
    plot_rpart(fit, ax=ax, **(plot_kwargs or {}))
    retval = text_rpart(fit, ax=ax, FUN=capture_fun, **kwargs)
    return {"retval": retval, "calls": calls, "n_patches": len(ax.patches), "ax": ax, "fig": fig}


def assert_text_rpart_calls_match(
    py_calls: list[dict[str, Any]], r_calls: list[dict[str, Any]], *, atol: float = 1e-6
) -> None:
    """Assert two `(x, y, labels)`-triple call lists (as returned by
    `call_text_rpart_and_extract()`/`r_text_rpart_capture()`) match exactly,
    call-for-call, position-for-position, and label-for-label (including
    `None` positions, e.g. R's `NA_character_` at a leaf's own
    `left.child`-indexed slot)."""
    assert len(py_calls) == len(r_calls), (
        f"call count mismatch: python made {len(py_calls)} FUN() calls, R made {len(r_calls)}"
    )
    for i, (py_call, r_call) in enumerate(zip(py_calls, r_calls)):
        np.testing.assert_allclose(
            py_call["x"], r_call["x"], atol=atol, err_msg=f"call {i} x mismatch"
        )
        np.testing.assert_allclose(
            py_call["y"], r_call["y"], atol=atol, err_msg=f"call {i} y mismatch"
        )
        py_labels = [None if v is None else str(v) for v in py_call["labels"]]
        assert py_labels == r_call["labels"], (
            f"call {i} labels mismatch: python={py_labels!r} vs R={r_call['labels']!r}"
        )


def r_text_rpart_generic_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str | None:
    """Like `r_text_rpart_error()`, but through the documented `text(x_expr,
    ...)` S3-generic dispatch route when ``generic=True`` (rather than
    always calling `rpart:::text.rpart` directly) -- needed for negative/
    edge tests whose ``x_expr`` genuinely has class "rpart" (so the generic
    actually reaches text.rpart) and where exercising the *documented*
    calling convention matters."""
    fn = "text" if generic else "rpart:::text.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{_r_post_arg_name(k)}={r_literal(v)}")
    code = f"{fn}(" + ", ".join(args) + ")"
    return r_error_message(lambda: _r_post_in_null_device(code))


def r_post_write_file_and_get_orientation(
    fit: Any, filename: str, *, horizontal: bool = True, **kwargs: Any
) -> str:
    """Call R's genuine `post(fit, filename=filename, horizontal=horizontal,
    ...)` (S3-dispatched to post.rpart) on an already-fitted, genuine R
    `rpart` object, writing a real PostScript file to ``filename`` via R's
    own `postscript(file=filename, horizontal=horizontal, ...)` device, and
    return the resulting file's `%%Orientation:` DSC comment value (e.g.
    "Landscape"/"Portrait") -- directly comparable (case-insensitively; R
    capitalizes, matplotlib's own `ps` backend lower-cases -- see
    test_post_positive.py) to the same comment line in
    r2py_rpart.post()'s own matplotlib-generated `.ps` output for the same
    `horizontal=` value.

    A genuine R fit (rather than a minimal synthetic frame-only object) is
    used here deliberately: this test is about post.rpart's *own* file/
    device-handling logic (title/digits/orientation), not about node-
    coordinate parity (which is exercised elsewhere via the shared
    `r_plot_rpart_derived()`/`extract_frame_arrays()` machinery on a *shared*
    node/var/dev triple) -- so there is no need to isolate away from R's and
    python's rpart() potentially picking different splits for the same
    formula/data.
    """
    ro.globalenv["post_fit_tmp"] = fit
    args = ["post_fit_tmp", f'filename="{filename}"', f"horizontal={'TRUE' if horizontal else 'FALSE'}"]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{_r_post_arg_name(k)}={r_literal(v)}")
    run_r("post(" + ", ".join(args) + ")")
    with open(filename) as f:
        for line in f:
            if line.startswith("%%Orientation:"):
                return line.split(":", 1)[1].strip()
    raise AssertionError(f"no %%Orientation: DSC comment line found in {filename!r}")


def call_post_and_extract(
    monkeypatch: Any, tree: dict[str, Any], *, filename: str = "", **kwargs: Any
) -> dict[str, Any]:
    """Call r2py_rpart.post(tree, filename=filename, **kwargs) -- the actual
    `post()` function under test, a thin `post(tree, **kwargs):
    post_rpart(tree, **kwargs)` wrapper mirroring R's own
    `post <- function(tree, ...) UseMethod("post")` -- and return a dict of
    everything it plotted onto its own internally-created
    `matplotlib.axes.Axes`.

    Unlike plot_rpart()/text_rpart() (which take an optional `ax=` and leave
    it open afterward for the caller to inspect), post()/post_rpart() always
    create their own Figure/Axes internally and unconditionally close it
    before returning (`fig.savefig(...); plt.close(fig)` when
    `filename != ""`, else just `plt.close(fig)`) -- mirroring R's own
    `on.exit(dev.off())`/`on.exit(par(oldpar))`. To inspect the Axes' final
    state before it is destroyed, this monkeypatches `matplotlib.pyplot.close`
    (the very module object post_rpart.py's own `import matplotlib.pyplot as
    plt` is bound to -- module attribute lookups are shared, so patching it
    here reaches the call inside post_rpart.py too) to record the Figure
    instead of actually closing it; the *real* `plt.close` is always restored
    and then invoked on the real figure once extraction is done (even on
    error), so no figure is ever leaked across the test session.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.post import post

    captured: dict[str, Any] = {}
    real_close = plt.close

    def fake_close(fig: Any = None) -> None:
        captured["fig"] = fig

    monkeypatch.setattr(plt, "close", fake_close)
    try:
        retval = post(tree, filename=filename, **kwargs)
    finally:
        monkeypatch.setattr(plt, "close", real_close)

    fig = captured.get("fig")
    assert fig is not None, "post() never reached plt.close(fig) -- did it raise before completing?"
    try:
        ax = fig.axes[0]
        lines = ax.lines
        line = lines[0] if lines else None
        return {
            "retval": retval,
            "title": ax.get_title(),
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "axis_off": not ax.axison,
            "line_x": np.asarray(line.get_xdata(), dtype=float) if line is not None else np.array([]),
            "line_y": np.asarray(line.get_ydata(), dtype=float) if line is not None else np.array([]),
            "n_lines": len(lines),
            "texts": [(t.get_position(), t.get_text(), t.get_ha(), t.get_va()) for t in ax.texts],
            "n_patches": len(ax.patches),
        }
    finally:
        real_close(fig)


def call_post_rpart_direct_and_extract(
    monkeypatch: Any, tree: dict[str, Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Like `call_post_and_extract`, but calls `r2py_rpart.post_rpart.post_rpart`
    directly (bypassing the `post(tree, **kwargs): post_rpart(tree, **kwargs)`
    wrapper entirely) and forwards ``*args`` positionally -- needed to
    exercise post_rpart's own real (non-generic) signature, e.g.
    `post_rpart(tree, "title", "", 5, True, True, True)`, which `post()`'s
    thin `**kwargs`-only wrapper cannot express at all (it has no positional
    parameters of its own beyond `tree`). See test_post_rpart_positive.py's
    module docstring for why this direct-entry-point distinction matters.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.post_rpart import post_rpart

    captured: dict[str, Any] = {}
    real_close = plt.close

    def fake_close(fig: Any = None) -> None:
        captured["fig"] = fig

    monkeypatch.setattr(plt, "close", fake_close)
    try:
        retval = post_rpart(tree, *args, **kwargs)
    finally:
        monkeypatch.setattr(plt, "close", real_close)

    fig = captured.get("fig")
    assert fig is not None, "post_rpart() never reached plt.close(fig) -- did it raise before completing?"
    try:
        ax = fig.axes[0]
        lines = ax.lines
        line = lines[0] if lines else None
        return {
            "retval": retval,
            "title": ax.get_title(),
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "axis_off": not ax.axison,
            "line_x": np.asarray(line.get_xdata(), dtype=float) if line is not None else np.array([]),
            "line_y": np.asarray(line.get_ydata(), dtype=float) if line is not None else np.array([]),
            "n_lines": len(lines),
            "texts": [(t.get_position(), t.get_text(), t.get_ha(), t.get_va()) for t in ax.texts],
            "n_patches": len(ax.patches),
        }
    finally:
        real_close(fig)


# ---------------------------------------------------------------------------
# prune(.rpart)-specific plumbing.
#
# Both `prune` (the S3 generic, `function(tree, ...) UseMethod("prune")`)
# and `prune.rpart` (its only method) are directly exported from the rpart
# NAMESPACE (`export(..., prune, prune.rpart, ...)`), unlike print.rpart
# (registered as an S3 method but not itself exported). So, unlike
# print.rpart's/plot.rpart's helpers above, no `rpart:::` internal-access
# trick is ever required here -- both call forms are reachable directly.
#
# Crucially, prune.rpart.R's own body (rpart/R/prune.rpart.R) has NO
# `inherits(tree, "rpart")` legitimacy check of its own (unlike
# print.rpart/plot.rpart/plotcp) -- it just does `tree$frame`,
# `tree$cptable`, etc. directly. Since R's `$` operator on a non-list atomic
# vector errors, but `$` on `NULL`/a plain `list()` (even one missing the
# expected named components) just silently returns `NULL` and keeps
# propagating through empty-vector arithmetic, `prune.rpart(tree, cp=...)`
# on a "malformed but list-shaped" `tree` frequently *succeeds* (as a no-op,
# returning `tree` unchanged) rather than erroring -- confirmed empirically
# against a live R session before any test below was written. This mirrors
# python's r2py_rpart.prune()/prune_rpart(), which likewise perform no
# `_rpart_class`/legitimacy check of their own -- but python's plain dict
# indexing (`tree['frame']`) raises immediately on `None`/`{}`/a
# component-missing dict, where R's `$` would have quietly produced `NULL`
# and sailed on. This is a genuine, confirmed behavioral gap (documented, not
# silently papered over) between the two implementations -- see
# test_prune_edge.py's dedicated "known gap" tests.
#
# So the correct comparison target for python's prune()/prune_rpart() (which
# never dispatches through any generic of their own) is R's `prune.rpart(x,
# cp=...)` called *directly* (generic=False, the default below) -- exactly
# analogous to post.rpart's/plot.rpart's own `generic=` convention above --
# with `generic=True` (the plain `prune(x, cp=...)` S3-dispatched form) used
# only where a test explicitly wants to confirm the two call forms agree.
# ---------------------------------------------------------------------------

def r_prune_call_code(x_expr: str, *, generic: bool = False, **kwargs: Any) -> str:
    """Build the R source for a `prune.rpart(x_expr, cp=...)` call
    (`generic=False`, the default -- reaching prune.rpart's body directly,
    matching python's own prune()/prune_rpart(), which never dispatch
    through a generic of their own) or a `prune(x_expr, cp=...)` call
    (`generic=True` -- the documented S3-generic entry point, `UseMethod`
    dispatching to prune.rpart for any `x` whose `class()` is `"rpart"`, and
    erroring with "no applicable method" otherwise).

    ``kwargs`` (currently just cp=) are rendered via r_literal() and
    appended `name=value`; a kwarg whose value is None is *omitted* entirely
    (not passed as `cp=NULL`) so that `missing(cp)` inside prune.rpart stays
    TRUE when the caller wants to exercise that specific error path --
    pass ``cp=None`` explicitly (which recurses into `r_literal(None) ->
    "NULL"`) instead if an *explicit* `cp=NULL` call is what's wanted (see
    test_prune_edge.py's dedicated `cp=NULL` test, which builds the R source
    for that case directly rather than through this omission convention).
    """
    fn = "prune" if generic else "prune.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def r_prune(fit: Any, *, generic: bool = False, **kwargs: Any) -> Any:
    """Call R's `prune.rpart(fit, cp=...)`/`prune(fit, cp=...)` on an
    already-fitted (or synthetic) R model object and return the raw rpy2
    result -- directly comparable, via `extract_r_fit()`, to
    r2py_rpart.prune()'s own return dict."""
    ro.globalenv["prune_fit_tmp"] = fit
    code = r_prune_call_code("prune_fit_tmp", generic=generic, **kwargs)
    return run_r(code)


def r_prune_error(x_expr: str, *, generic: bool = False, **kwargs: Any) -> str | None:
    """Call `prune.rpart(x_expr, ...)`/`prune(x_expr, ...)` (the actual R
    function) for its side effect only, returning the R error message
    string if it raises (via r_error_message()), else None. ``x_expr`` is R
    source, e.g. "NULL", "list()", "5", or a global variable name assigned
    beforehand."""
    code = r_prune_call_code(x_expr, generic=generic, **kwargs)
    return r_error_message(lambda: run_r(code))


# ---------------------------------------------------------------------------
# snip.rpart-specific plumbing: calling R's `snip.rpart(x, toss=c(...))`
# directly (it is exported straight from the rpart NAMESPACE as a plain
# function -- not an S3 generic/method pair like prune/prune.rpart -- so there
# is no `generic=`/direct-call distinction to make here: a bare
# `snip.rpart(...)` call always reaches the same body regardless of `x`'s
# class).
#
# snip.rpart(x, toss) is normally *interactive* when `toss` is omitted (or
# empty): it falls through to `snip.rpart.mouse(x)`, which calls the
# graphics-input function `identify()` -- with no graphics device/mouse
# available in a headless test session, this either errors immediately (if
# no prior `plot()` call ever stashed device parameters in `rpart_env`, which
# is always the case for a fit built directly in a fresh test) or would block
# waiting for input. Every helper below always passes `toss` explicitly and
# non-empty *except* where a test specifically wants to exercise that
# missing-parms error path (confirmed empirically to error immediately with
# "no information available on parameters from previous call to plot()"
# rather than hang -- see test_snip_rpart_negative.py).
# ---------------------------------------------------------------------------

def r_snip_call_code(x_expr: str, toss: Any = None) -> str:
    """Build the R source for a `snip.rpart(x_expr, toss=c(...))` call.
    ``toss`` (a scalar, list/tuple, or numpy array of node numbers) is
    rendered via `r_literal()`; if ``toss`` is None, the `toss=` argument is
    *omitted* entirely (so `missing(toss)` inside snip.rpart stays TRUE,
    triggering its interactive `snip.rpart.mouse()` fallback -- only used
    deliberately, for the missing-toss negative test)."""
    args = [x_expr]
    if toss is not None:
        args.append(f"toss={r_literal(np.asarray(toss).tolist())}")
    return "snip.rpart(" + ", ".join(args) + ")"


def r_snip(fit: Any, toss: Any, var_name: str = "snip_fit_tmp") -> Any:
    """Call R's `snip.rpart(fit, toss=c(...))` on an already-fitted (or
    synthetic) R model object and return the raw rpy2 result -- directly
    comparable, via `extract_r_fit()`, to r2py_rpart.snip_rpart()'s own
    return dict."""
    ro.globalenv[var_name] = fit
    code = r_snip_call_code(var_name, toss)
    return run_r(code)


def r_snip_error(x_expr: str, toss: Any = None) -> str | None:
    """Call `snip.rpart(x_expr, toss=...)` (the actual R function) for its
    side effect only, returning the R error message string if it raises (via
    r_error_message()), else None. ``x_expr`` is R source, e.g. "NULL",
    "list()", "5", or a global variable name assigned beforehand."""
    code = r_snip_call_code(x_expr, toss)
    return r_error_message(lambda: run_r(code))


def r_snip_capturing_warning(
    fit: Any, toss: Any, var_name: str = "snip_warn_fit_tmp"
) -> tuple[Any, str | None]:
    """Like `r_snip()`, but also returns the first warning message R's
    `snip.rpart()` raised (or None), via `r_eval_capturing_warning()` --
    used for the "Nodes %s are not in this tree" warning path (toss
    containing node numbers absent from the fit), which snip.rpart signals
    via `warning()` rather than `stop()`, so evaluation continues and a
    genuine (partial) result is still returned alongside the warning text."""
    ro.globalenv[var_name] = fit
    code = r_snip_call_code(var_name, toss)
    return r_eval_capturing_warning(code)


def call_plot_rpart_and_extract(fit: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Call r2py_rpart.plot_rpart(fit, ax=<fresh axes>, **kwargs) and return
    a dict of both its *returned* value and everything it plotted, pulled
    back out of the Axes object:

      - the returned `{"x":..., "y":...}` node coordinates       -> "retval"
      - `ax.set_xlim(...)`/`ax.set_ylim(...)`                    -> "xlim"/"ylim"
      - whether the axis frame/ticks were turned off (`ax.set_axis_off()`)
                                                                   -> "axis_off"
      - the single `ax.plot(...)` branch-line call's x/y data
        (NaN-separated per-branch segments, in column-major/"F" order)
                                                                   -> "line_x"/"line_y"
      - that line's color/linestyle/linewidth                    -> "line_color"/"line_style"/"line_width"
      - the root "|" glyph text, if `branch > 0`                 -> "texts" (list of
        (position, text, ha, va) tuples; empty if branch <= 0, since
        plot_rpart.py's own `if branch > 0:` guard skips it entirely)
      - how many Line2D artists were drawn (always <= 1: plot_rpart.py
        draws every branch segment via a single `ax.plot(...)` call)
                                                                   -> "n_lines"

    The figure is always closed afterward (even on error) to avoid leaking
    matplotlib figures across the test session.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.plot_rpart import plot_rpart

    fig, ax = plt.subplots()
    try:
        retval = plot_rpart(fit, ax=ax, **kwargs)
        n_lines = len(ax.lines)
        line = ax.lines[0] if n_lines else None
        line_x = np.asarray(line.get_xdata(), dtype=float) if line is not None else np.array([])
        line_y = np.asarray(line.get_ydata(), dtype=float) if line is not None else np.array([])
        texts = [(t.get_position(), t.get_text(), t.get_ha(), t.get_va()) for t in ax.texts]
        return {
            "retval": retval,
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "axis_off": not ax.axison,
            "n_lines": n_lines,
            "line_x": line_x,
            "line_y": line_y,
            "line_color": line.get_color() if line is not None else None,
            "line_style": line.get_linestyle() if line is not None else None,
            "line_width": line.get_linewidth() if line is not None else None,
            "texts": texts,
        }
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# residuals.rpart-specific plumbing.
#
# residuals.rpart(object, type = c("usual", "pearson", "deviance"), ...) is
# registered as an S3 method for the `residuals` generic
# (`S3method(residuals, rpart)` in NAMESPACE) but is not itself exported --
# so the *documented* calling convention is the plain generic
# `residuals(fit, ...)` (used below for genuine "x really is class 'rpart'"
# scenarios; `residuals()` also has its own `residuals.default` fallback for
# un-classed `x`, which does *not* reach residuals.rpart's own
# `inherits(object, "rpart")` legitimacy check at all -- confirmed
# empirically: `residuals(list(a=1))` silently returns `NULL` via
# residuals.default rather than erroring), while `rpart:::residuals.rpart`
# is used directly (mirroring print.rpart's/plot.rpart's own
# `rpart:::`-prefixed helpers elsewhere in this module) for negative tests
# whose `object` deliberately has no "rpart" class at all, so the
# `inherits()` check is actually exercised.
#
# Unlike predict.rpart, residuals.rpart operates purely on fields already
# present on the fitted object ($y, $frame, $where, $method, $parms,
# $na.action, and the "ylevels" attribute) -- it never needs `newdata` or
# reconstructs a model matrix, so no `newdata`-conversion plumbing is needed
# here (contrast with r_predict()/r_predict_to_python() above). Several edge/
# negative tests below deliberately build a *minimal* synthetic
# `structure(list(...), class = "rpart")` object directly in R (via
# `r_minimal_rpart_expr()`), rather than fitting a full tree, to isolate
# residuals.rpart's own field-access/arithmetic from tree-fitting concerns
# entirely -- mirroring the `r_rpart_like_expr()`/`r_rpart_like_expr_for_plot()`
# convention used for plotcp/plot.rpart's negative-path tests earlier in this
# module.
# ---------------------------------------------------------------------------

def r_residuals_call_code(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str:
    """Build the R source for a `residuals(x_expr, ...)` call (``generic=True``,
    the default -- the documented S3-generic entry point) or a
    `rpart:::residuals.rpart(x_expr, ...)` call (``generic=False`` -- reaching
    residuals.rpart's body directly, bypassing S3 dispatch, for un-classed
    ``x_expr``).

    ``kwargs`` (currently just type=) are rendered via r_literal() and
    appended `name=value`; a kwarg whose value is None is *omitted* entirely
    (not passed as `type=NULL`) so that `missing(type)`/match.arg's own
    default-choices resolution runs, matching residuals_rpart()'s own
    `type: str = 'usual'` default. Pass an *R-literal* explicit NULL only via
    a hand-built ``x_expr``/code string -- see test_residuals_rpart_edge.py's
    dedicated `type=NULL` test.
    """
    fn = "residuals" if generic else "rpart:::residuals.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def r_residuals(fit: Any, type: str | None = None, *, generic: bool = True) -> Any:
    """Call R's `residuals(fit, type=...)` (S3-dispatched to residuals.rpart)
    on an already-fitted (or synthetic) R model object and return the raw
    rpy2 result -- a plain (possibly named) numeric vector in every case
    residuals.rpart itself handles.

    ``fit`` is assigned into R's global environment under a temp name so it
    can be referenced from the generated call (this works whether ``fit``
    came from ``run_r()``/``r_fit_rpart()`` or was fetched back out of
    ``globalenv`` already).
    """
    ro.globalenv["resid_fit_tmp"] = fit
    kwargs: dict[str, Any] = {}
    if type is not None:
        kwargs["type"] = type
    code = r_residuals_call_code("resid_fit_tmp", generic=generic, **kwargs)
    return run_r(code)


def r_residuals_to_python(robj: Any) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Convert an R residuals.rpart() return value (a plain, possibly named,
    numeric vector -- residuals.rpart never returns a factor or matrix,
    unlike predict.rpart) into a 1-D numpy float array directly comparable
    to r2py_rpart.residuals_rpart()'s return value."""
    return np.asarray(robj, dtype=np.float64)


def r_residuals_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str | None:
    """Call `residuals(x_expr, ...)`/`rpart:::residuals.rpart(x_expr, ...)`
    for its side effect only, returning the R error message string if it
    raises (via r_error_message()), else None. ``x_expr`` is R source, e.g.
    "NULL", "list()", "5", or a global variable name assigned beforehand."""
    code = r_residuals_call_code(x_expr, generic=generic, **kwargs)
    return r_error_message(lambda: run_r(code))


def r_minimal_rpart_expr(
    *,
    y: str = "c(1, 2, 3)",
    frame_yval: str = "c(1, 2, 3)",
    where: str = "c(1, 2, 3)",
    method: str = "anova",
    yval2: str | None = None,
    ylevels: str | None = None,
    parms: str | None = None,
    na_action: str | None = None,
) -> str:
    """Render an R expression for a *minimal* synthetic object satisfying
    `inherits(x, "rpart")` with just enough fields for residuals.rpart's own
    body to run ($y, $frame (a data.frame with a $yval column, optionally
    $yval2), $where, $method, optionally $parms and $na.action, plus the
    "ylevels" attribute) -- without ever fitting a real tree. Every
    parameter is inserted *verbatim* as R source (the caller is responsible
    for producing valid R literals, e.g. via ``r_literal()``/
    ``r_matrix_literal()``), mirroring ``r_rpart_like_expr()``'s convention
    for plotcp above.

    This isolates residuals.rpart's field-access/arithmetic (the classed
    dict lookups, the `frame$yval[object$where]` indexing, the
    usual/pearson/deviance formulas) from any tree-fitting concern entirely
    -- used for edge/negative tests that need precise, hand-picked
    y/yval/yval2/where combinations (e.g. an out-of-range `where` index, a
    single-node/single-observation tree, or a hand-crafted 2-class `yval2`
    to isolate the classification pearson/deviance branch) that would be
    impractical (or RNG-dependent, or simply impossible) to coax out of an
    actual `rpart()` fit. ``yval2`` (if given) should be an R matrix literal
    (e.g. via ``r_matrix_literal()``) -- wrapped in `I(...)` so it survives
    as a matrix-valued data.frame column instead of being flattened.
    """
    frame_fields = [f"yval = {frame_yval}"]
    if yval2 is not None:
        frame_fields.append(f"yval2 = I({yval2})")
    frame_expr = "data.frame(" + ", ".join(frame_fields) + ")"

    list_fields = [f"y = {y}", f"frame = {frame_expr}", f"where = {where}", f'method = "{method}"']
    if parms is not None:
        list_fields.append(f"parms = {parms}")
    if na_action is not None:
        list_fields.append(f"na.action = {na_action}")
    expr = "structure(list(" + ", ".join(list_fields) + '), class = "rpart"'
    if ylevels is not None:
        expr += f", ylevels = {ylevels}"
    expr += ")"
    return expr


# ---------------------------------------------------------------------------
# rpart.exp-specific plumbing: calling R's internal `rpart:::rpart.exp(y=,
# offset=, parms=, wt=)` directly. Unlike print.rpart (an S3 method
# registered in NAMESPACE but not exported), rpart.exp is not registered as
# an S3 method at all -- it is called directly by rpart()'s own internal
# dispatch table for `method="exp"`/`"poisson"` -- so there is no generic to
# fall back on, and the triple-colon internal-access form is the *only* way
# to call it standalone.
#
# A few confirmed findings (verified empirically against a live R session
# before any test below was written) shaped the helpers below and the
# negative/edge tests that use them:
#
#   * `offset` has no R-side default and, unlike `parms`, is *not* guarded
#     by `missing()` inside rpart.exp.R -- the very first use,
#     `length(offset)`, forces the argument's promise. So omitting
#     `offset=` from the call entirely raises "argument \"offset\" is
#     missing, with no default", distinct from passing `offset=NULL`
#     (which takes the normal length-0/no-rescaling path). `parms`, by
#     contrast, *is* guarded by `missing(parms)`: omitting it entirely hits
#     the `parms <- c(shrink=1L, method=1L)` default branch, while passing
#     an explicit `parms=NULL` instead hits `as.list(NULL) -> list()`,
#     whose `is.null(names(list()))` is TRUE, raising "You must input a
#     named list for parms" -- a real behavioral fork R itself makes
#     between "omitted" and "explicitly NULL" that has no counterpart on
#     the python side (`parms=None` always means "use the defaults",
#     regardless of whether the caller meant "omitted" or "explicitly
#     None") -- see test_rpart_exp_negative.py's
#     `test_parms_none_python_succeeds_vs_r_explicit_null_errors_known_gap`.
#
#   * The 3-column ("counting process", `Surv(start, stop, status)`) branch
#     of `drate2`'s nested `ny == 3L` code path calls `table(index2, levels
#     = 1:ngrp)`. `table()` has no `levels=` formal of its own, so this is
#     matched by `table`'s `...`  and treated as a *second classifying
#     vector* to cross-tabulate against -- not a way to force `tab2`'s
#     length, as the adjacent source comment ("force the length of tab2")
#     clearly intends. `table(a, b)` requires `length(a) == length(b)`, so
#     this requires `length(index2) == length(1:ngrp)`, i.e. `n == ngrp`
#     (as many observations as death-time intervals) -- true only in the
#     degenerate case where *every* observation is itself an uncensored,
#     uniquely-timed death. For any realistic counting-process input (any
#     censoring at all, or any tied death time -- i.e. essentially every
#     real dataset), R's own `rpart.exp` raises "all arguments must have
#     the same length" for `ny == 3` data. Even in the narrow case where it
#     does *not* error, `table(index2, levels = 1:ngrp)` returns an
#     `ngrp`-by-`ngrp` *matrix* (index2 cross-tabulated against the literal
#     vector `1:ngrp`), not the length-`ngrp` vector the surrounding
#     arithmetic (`rev(cumsum(rev(tab2)))`, `ilength * c(0,
#     temp[-ngrp])`) assumes -- so even the "successful" case computes
#     numeric nonsense for the rescaled `y` column. Python's `drate2`
#     instead uses `np.bincount(index2, minlength=ngrp)`, which actually
#     does what the R source comment describes. So the two sides are *not*
#     expected to agree on `ny == 3` data outside the (structural,
#     R-input-independent) `cbind(newy, y[, 2L])` second column -- see
#     test_rpart_exp_negative.py's
#     `test_counting_process_ny3_realistic_data_r_table_bug_errors` and
#     test_rpart_exp_edge.py's
#     `test_counting_process_all_unique_deaths_ny3_values_diverge_known_bug`
#     for the two concrete manifestations (R erroring outright, and R
#     "succeeding" with wrong numbers).
#
#   * `wt` is accepted as a parameter by both `rpart.exp`/`rpart_exp` and
#     the nested/private `drate2`, but is never actually *read* anywhere in
#     either implementation's body, in R or in python -- a faithfully
#     ported dead parameter, not a bug introduced in translation. Varying
#     `wt` is expected to have *zero* effect on the result on both sides;
#     see test_rpart_exp_positive.py's `test_wt_is_a_faithfully_ported_no_op`.
#
#   * Python's `if not (isinstance(y, np.ndarray) and y.ndim == 2)` check is
#     a deliberate simplification of R's `if (!inherits(y, "Surv"))` --
#     python has no equivalent of an S3 class marker to check for, so *any*
#     2-D numpy array (not just one actually built via `Surv(...)`) sails
#     through this check, even if its columns bear no relationship to a
#     survival time/status encoding at all. See
#     test_rpart_exp_negative.py's
#     `test_arbitrary_2d_array_passes_python_check_but_r_requires_real_surv_known_gap`.
#
#   * Neither side validates for `NaN`/`Inf` explicitly, but they resolve
#     the *ambient* `any(y[, 1L] <= 0)` / `np.any(y[:, 0] <= 0)` checks
#     differently: R's `NA <= 0` is `NA`, and `if (any(...))` on a
#     result containing `NA` raises "missing value where TRUE/FALSE
#     needed" outright; numpy's `nan <= 0` is plain `False`, so
#     `np.any(...)` silently evaluates to `False` and a `NaN` observation
#     time sails through into `np.unique`/`np.sort`/`np.interp` untouched,
#     producing a `NaN`-contaminated (but non-raising) result instead. See
#     test_rpart_exp_edge.py's `test_nan_time_r_raises_python_silently_propagates_known_gap`
#     and `test_inf_time_r_raises_python_silently_propagates_known_gap`.
# ---------------------------------------------------------------------------

EXP_OMIT = object()


def r_surv_assign_2col(name: str, time: np.ndarray, status: np.ndarray) -> None:
    """Build a 2-column (right-censored) `survival::Surv(time, status)`
    object from plain numpy arrays and assign it into R's globalenv under
    ``name``, for feeding into `r_rpart_exp_call_code`/`r_rpart_exp`."""
    run_r(f"{name} <- survival::Surv({_r_num_vec(time)}, {_r_num_vec(status)})")


def r_surv_assign_3col(name: str, start: np.ndarray, stop: np.ndarray, status: np.ndarray) -> None:
    """Build a 3-column ("counting process") `survival::Surv(start, stop,
    status)` object from plain numpy arrays and assign it into R's
    globalenv under ``name`` -- see the module-level note above for the
    confirmed `table(index2, levels=1:ngrp)` bug this branch triggers in
    R's own rpart.exp for all but the most degenerate inputs."""
    run_r(
        f"{name} <- survival::Surv({_r_num_vec(start)}, {_r_num_vec(stop)}, {_r_num_vec(status)})"
    )


def r_rpart_exp_call_code(
    y_expr: str,
    *,
    offset: Any = EXP_OMIT,
    parms: Any = EXP_OMIT,
    wt_expr: str = "exp_wt_tmp",
) -> str:
    """Build the R source for a `rpart:::rpart.exp(y=, offset=, parms=,
    wt=)` call.

    ``offset``/``parms`` are inserted *verbatim* as R source when given
    (the caller is responsible for producing a valid R literal, e.g. via
    ``r_literal(...)`` -- which renders a python dict as a named
    `list(...)` and `None` as `"NULL"` -- or a hand-written string like
    `"list(1, 2)"` for an intentionally-unnamed parms list). The
    `EXP_OMIT` sentinel (the default for both) *omits* the argument from
    the call entirely: for `parms`, this reaches R's own `missing(parms)`
    default branch; for `offset` (which has no `missing()` guard of its
    own -- see module-level note above), this reaches the "argument ... is
    missing, with no default" error path instead.
    """
    args = [f"y={y_expr}"]
    if offset is not EXP_OMIT:
        args.append(f"offset={offset}")
    if parms is not EXP_OMIT:
        args.append(f"parms={parms}")
    args.append(f"wt={wt_expr}")
    return "rpart:::rpart.exp(" + ", ".join(args) + ")"


def r_rpart_exp(
    y_expr: str,
    wt: np.ndarray,
    *,
    offset: Any = EXP_OMIT,
    parms: Any = EXP_OMIT,
    wt_expr: str = "exp_wt_tmp",
) -> Any:
    """Assign ``wt`` into R's globalenv under ``wt_expr`` and call R's
    `rpart:::rpart.exp(y=y_expr, offset=, parms=, wt=wt_expr)` (via
    `r_rpart_exp_call_code`), returning the raw rpy2 list result."""
    ro.globalenv[wt_expr] = ro.FloatVector(np.asarray(wt, dtype=float))
    code = r_rpart_exp_call_code(y_expr, offset=offset, parms=parms, wt_expr=wt_expr)
    return run_r(code)


def r_rpart_exp_result_to_python(result: Any) -> dict[str, Any]:
    """Unpack an R `rpart.exp()` return list's `y`/`parms`/`numresp`/`numy`
    fields into plain numpy/python values directly comparable to
    r2py_rpart.rpart_exp()'s own return dict (its `summary`/`text`
    closures are handled separately below, via
    `call_r_rpart_exp_summary`/`call_r_rpart_exp_text`)."""
    y = np.asarray(result.rx2("y"), dtype=float)
    parms_r = result.rx2("parms")
    names_r = ro.r["names"](parms_r)
    parms_names = [str(s) for s in names_r]
    parms_vals = np.asarray(parms_r, dtype=float)
    parms = dict(zip(parms_names, parms_vals))
    numresp = int(np.asarray(result.rx2("numresp"), dtype=float)[0])
    numy = int(np.asarray(result.rx2("numy"), dtype=float)[0])
    return {"y": y, "parms": parms, "numresp": numresp, "numy": numy}


def call_r_rpart_exp_summary(
    result: Any, yval: np.ndarray, dev: np.ndarray, wt: np.ndarray, digits: int
) -> list[str]:
    """Call an R `rpart.exp()` return list's `$summary(yval, dev, wt,
    ylevel, digits)` closure with sample arguments (``ylevel`` is always
    passed as `NULL` -- rpart.exp's own summary closure never references
    it) and return its character-vector output as a plain list of strings,
    directly comparable to r2py_rpart.rpart_exp()'s own `summary(...)`
    closure output (also a `numpy.ndarray`/list of strings, one per row of
    ``yval``)."""
    ro.globalenv["exp_summary_fn_tmp"] = result.rx2("summary")
    code = (
        "exp_summary_fn_tmp(" + r_matrix_literal(yval) + ", " + _r_num_vec(dev) + ", "
        + _r_num_vec(wt) + f", NULL, {digits})"
    )
    return [str(s) for s in run_r(code)]


def call_r_rpart_exp_text(
    result: Any,
    yval: np.ndarray,
    dev: np.ndarray,
    wt: np.ndarray,
    digits: int,
    n: np.ndarray,
    use_n: bool,
) -> list[str]:
    """Call an R `rpart.exp()` return list's `$text(yval, dev, wt, ylevel,
    digits, n, use.n)` closure with sample arguments and return its output
    as a plain list of strings.

    NOTE (see module-level docstring on `test_rpart_exp_positive.py` for
    the full writeup): for `use_n=False` with more than one row, R's own
    `paste(formatg(yval[, 1L], digits))` does *not* collapse the vector
    into a single string -- a bare `paste(x)` call with a single vector
    argument is a no-op/identity coercion, returning a vector the same
    length as `x` (confirmed empirically: `paste(c(1.1, 2.2))` is
    `c("1.1", "2.2")`, not `"1.1 2.2"`) -- so R returns a length-`nrow(yval)`
    character vector, one element per row. r2py_rpart's `_text` instead
    does `" ".join(...)`, collapsing to a *single* string -- a genuine,
    confirmed divergence for `use_n=False` whenever `yval` has more than
    one row (a length-1 `yval` looks the same either way: a 1-element
    join and a 1-element vector are both just that one formatted value).
    """
    ro.globalenv["exp_text_fn_tmp"] = result.rx2("text")
    code = (
        "exp_text_fn_tmp(" + r_matrix_literal(yval) + ", " + _r_num_vec(dev) + ", "
        + _r_num_vec(wt) + f", NULL, {digits}, " + _r_num_vec(n) + f", {'TRUE' if use_n else 'FALSE'})"
    )
    return [str(s) for s in run_r(code)]


def r_rpart_exp_error(
    y_expr: str,
    wt: np.ndarray,
    *,
    offset: Any = EXP_OMIT,
    parms: Any = EXP_OMIT,
    wt_expr: str = "exp_wt_tmp",
) -> str | None:
    """Call `rpart:::rpart.exp(y=y_expr, offset=, parms=, wt=)` (via
    `r_rpart_exp_call_code`) for its side effect only, returning the R
    error message string if it raises (via r_error_message()), else
    None."""
    ro.globalenv[wt_expr] = ro.FloatVector(np.asarray(wt, dtype=float))
    code = r_rpart_exp_call_code(y_expr, offset=offset, parms=parms, wt_expr=wt_expr)
    return r_error_message(lambda: run_r(code))


# ---------------------------------------------------------------------------
# rsq.rpart-specific plumbing.
#
# rsq.rpart(x) is a plain, exported R function (not an S3 generic -- see
# rpart/R/rsq.rpart.R: its own body does `if (!inherits(x, "rpart")) stop(...)`
# directly, exactly like printcp/plotcp), taking only `x` (no other
# parameters) and, per rsq.rpart.Rd, producing 2 plots as a pure side
# effect: (1) R-square (apparent, and 1 - cross-validated relative error)
# vs. number of splits, and (2) cross-validated relative error +/- 1 SE vs.
# number of splits. It returns `invisible()` (NULL) on both sides
# (r2py_rpart.rsq_rpart() is annotated `-> None`).
#
# Unlike plotcp.R (which reads `x$cptable` directly), rsq.rpart.R's own
# first computational line is `p.rpart <- printcp(x)` -- i.e. it goes
# through printcp() (which reprints the whole cptable table to the console
# as a side effect, and separately re-checks `inherits(x, "rpart")`) purely
# to obtain `x$cptable` back via printcp()'s own `invisible(x$cptable)`
# return value. This means a completely minimal synthetic "rpart" object
# carrying only `cptable` + `method` (no `frame`, no `call`, no `na.action`)
# is, empirically, still accepted by R's *real*, exported `rsq.rpart()` --
# printcp()'s `frame <- x$frame; leaves <- frame$var == "<leaf>"` etc. all
# silently degrade to NULL/empty when `x$frame` is absent, printing a
# garbled-but-harmless header ("Root node error: NULL/ = ", "n= ") rather
# than raising -- confirmed empirically via a live rpy2 session before
# writing this module. So, unlike plotcp's `r_rpart_like_expr()` (used only
# for sanity-checking that a fresh, class-only cptable-carrying object is
# accepted), the same style of minimal object suffices here too, extended
# with a `method` element (`r_rsq_rpart_like_expr()` below) since
# rsq.rpart.R's `if (!method == "anova") warning(...)` reads `x$method`
# directly.
#
# r2py_rpart.rsq_rpart()'s own legitimacy check --
# `not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart')` -- mirrors
# printcp.py's `_rpart_class` check (not plotcp.py's weaker
# `'cptable' not in x` check), so -- unlike plotcp's genuine, documented
# KNOWN GAP -- a class-less dict with an otherwise-valid `cptable` IS
# rejected on both sides here, just like printcp.
# ---------------------------------------------------------------------------

def r_rsq_rpart_like_expr(cptable: np.ndarray, method: str = "anova") -> str:
    """Render an R expression for a minimal object satisfying `inherits(x,
    "rpart")`, carrying only `cptable` and `method` -- sufficient for R's
    *actual*, exported `rsq.rpart()` to run to completion (see module-level
    note above): `method` is read directly by rsq.rpart.R's own
    `if (!method == "anova") warning(...)` check, and the internal
    `printcp(x)` call degrades gracefully when `x$frame`/`x$call` are
    absent."""
    return (
        f'structure(list(cptable = {r_matrix_literal(cptable)}, '
        f'method = {r_literal(method)}), class = "rpart")'
    )


def r_rsq_rpart_derived_from_cptable(cptable: np.ndarray) -> dict[str, Any]:
    """Evaluate rpart/R/rsq.rpart.R's own derivation logic (copied
    line-for-line from the point `p.rpart <- printcp(x)` returns onward --
    i.e. treating ``cptable`` itself as `p.rpart`, since `printcp(x)`'s own
    `invisible(x$cptable)` return value is exactly `x$cptable` unrounded --
    only omitting the actual `plot()`/`par(new=TRUE)`/`legend()`/
    `segments()` graphics calls), returning every intermediate/derived
    quantity r2py_rpart.rsq_rpart() also computes/plots. ``cptable`` must be
    a 2-D array with >= 5 columns, in rpart's own column order (CP, nsplit,
    rel error, xerror, xstd) -- column 0 (CP) is never read by rsq.rpart,
    exactly as in the real R/python implementations."""
    code = f"""
    local({{
        p.rpart <- {r_matrix_literal(cptable)}
        xstd <- p.rpart[, 5L]
        xerror <- p.rpart[, 4L]
        rel.error <- p.rpart[, 3L]
        nsplit <- p.rpart[, 2L]
        ylim <- c(min(xerror - xstd) - 0.1, max(xerror + xstd) + 0.1)
        list(
            xstd = xstd,
            xerror = xerror,
            rel_error = rel.error,
            nsplit = nsplit,
            rsq_apparent = 1 - rel.error,
            rsq_xrel = 1 - xerror,
            ylim = ylim
        )
    }})
    """
    result = run_r(code)

    def _num(name: str) -> np.ndarray:
        return np.asarray(result.rx2(name), dtype=float)

    return {
        "xstd": _num("xstd"),
        "xerror": _num("xerror"),
        "rel_error": _num("rel_error"),
        "nsplit": _num("nsplit"),
        "rsq_apparent": _num("rsq_apparent"),
        "rsq_xrel": _num("rsq_xrel"),
        "ylim": tuple(_num("ylim")),
    }


def r_rsq_rpart_call_code(x_expr: str) -> str:
    """Build the R source for an `rsq.rpart(x_expr)` call -- rsq.rpart.Rd
    documents only a single `x` argument (`usage{rsq.rpart(x)}`), unlike
    plotcp/printcp which take extra keyword arguments."""
    return f"rsq.rpart({x_expr})"


def _r_rsq_rpart_in_null_device(code: str) -> None:
    """Run R source that may call rsq.rpart() (which both prints the
    cptable to the console via its internal printcp(x) call, and tries to
    plot on 'the current graphical device') inside a no-op `pdf(NULL)`
    device with its console/table output swallowed via `capture.output()`,
    so it never attempts to open a real display nor clutters test output in
    a headless test environment. The device is always closed afterward,
    even if `code` raises."""
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(f"invisible(capture.output({code}))")
    finally:
        run_r("grDevices::dev.off()")


def r_rsq_rpart_error(x_expr: str) -> str | None:
    """Call `rsq.rpart(x_expr)` (the actual R function, inside a no-op
    graphics device with its printed output swallowed) for its side effect
    only, returning the R error message string if it raises (via
    r_error_message()), else None."""
    code = r_rsq_rpart_call_code(x_expr)
    return r_error_message(lambda: _r_rsq_rpart_in_null_device(code))


def r_rsq_rpart_runs_without_error(x_expr: str) -> bool:
    """Call `rsq.rpart(x_expr)` (the actual R function, inside a no-op
    graphics device) purely to sanity-check that R's *real* rsq.rpart()
    accepts a given input without raising (a complement to
    r_rsq_rpart_error(), used in positive/edge tests to confirm the
    synthetic cptable/method used for the derivation-replica comparison is
    one R's own rsq.rpart() actually accepts, not just one the hand-copied
    replica accepts)."""
    return r_rsq_rpart_error(x_expr) is None


def r_rsq_rpart_warning(x_expr: str) -> str | None:
    """Call `rsq.rpart(x_expr)` (the actual R function, inside a no-op
    graphics device with its printed table output swallowed) and return the
    first warning message it raises (e.g. rsq.rpart.R's own
    `warning("may not be applicable for this method")` for a non-"anova"
    `method`), or None if it raises no warning. Uses
    r_eval_capturing_warning() so evaluation resumes normally after the
    warning (rsq.rpart still completes its plotting/return value)."""
    run_r("grDevices::pdf(NULL)")
    try:
        code = f"invisible(capture.output({r_rsq_rpart_call_code(x_expr)}))"
        _, warning_msg = r_eval_capturing_warning(code)
        return warning_msg
    finally:
        run_r("grDevices::dev.off()")


# ---------------------------------------------------------------------------
# rsq.rpart-specific plumbing, python side: r2py_rpart.rsq_rpart() itself
# returns None (mirroring R's `invisible()`) and communicates purely by
# mutating the `matplotlib.axes.Axes`/`Figure` it is given (or creates) --
# `call_rsq_rpart_and_extract` below invokes it against a fresh figure (or
# a caller-supplied one, exercising rsq_rpart.py's own
# `if fig is None or ax is None` branch) and pulls out every quantity
# rsq_rpart.py derives/draws, in a form directly comparable to
# `r_rsq_rpart_derived_from_cptable()`'s return dict:
#
#   Panel 1 (R-square vs. number of splits):
#     - the "Apparent" line (`ax1.plot(nsplit, 1 - rel_error, ...)`)
#                                                     -> "apparent_x"/"apparent_y"
#     - the "X Relative" line (`ax1.plot(nsplit, 1 - xerror, ...)`)
#                                                     -> "xrel_x"/"xrel_y"
#     - `ax1.set_ylim(0, 1)`                          -> "panel1_ylim"
#     - the legend labels                             -> "legend_labels"
#     - axis labels                                   -> "panel1_xlabel"/"panel1_ylabel"
#   Panel 2 (X Relative Error vs. number of splits):
#     - the main `ax2.plot(nsplit, xerror, ...)` line -> "xerror_x"/"xerror_y"
#     - `ax2.set_ylim(...)`                            -> "panel2_ylim"
#     - the `ax2.vlines(...)` error-bar segments (ymin/ymax per nsplit
#       position)                                      -> "xerror_minus_std"/"xerror_plus_std"
#     - axis labels                                   -> "panel2_xlabel"/"panel2_ylabel"
#
# When `fig`/`ax` are *both* explicitly supplied (rsq_rpart.py's `else`
# branch), both panels are drawn onto the *same* single Axes (`ax1 = ax2 =
# ax`) -- in that case the 3 plotted lines land on one Axes's `.lines` list
# in a fixed order (apparent, x-relative, then xerror), so the panel-2 main
# line is `ax.lines[2]` rather than `ax2.lines[0]`; `call_rsq_rpart_and_extract`
# below detects this (`ax1 is ax2`) and indexes accordingly. Any figure(s)
# created along the way are always closed afterward (even on error), and
# any pre-existing open figures are closed first, to avoid both leaking
# matplotlib figures across the test session and `plt.gcf()` picking up a
# stale figure from an earlier test.
# ---------------------------------------------------------------------------

def call_rsq_rpart_and_extract(
    fit: dict[str, Any], *, fig: Any = None, ax: Any = None
) -> dict[str, Any]:
    """Call r2py_rpart.rsq_rpart(fit, fig=fig, ax=ax) and return a dict of
    every quantity it plotted, pulled back out of the Axes object(s).

    If both ``fig`` and ``ax`` are omitted (the common case), rsq_rpart()
    is called with no `fig`/`ax` kwargs at all (its own default-argument
    path), and the resulting figure is retrieved via `plt.gcf()` right
    afterward (all pre-existing figures are closed first, so `plt.gcf()`
    unambiguously picks up the one rsq_rpart() itself just created). If
    both are supplied (e.g. a single pre-created `Axes`), they are passed
    through directly, exercising rsq_rpart.py's shared-single-Axes branch.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.rsq_rpart import rsq_rpart

    plt.close("all")
    try:
        if fig is not None and ax is not None:
            retval = rsq_rpart(fit, fig=fig, ax=ax)
            ax1, ax2 = ax, ax
        else:
            retval = rsq_rpart(fit, fig=fig, ax=ax)
            created_fig = plt.gcf()
            ax1, ax2 = created_fig.axes[0], created_fig.axes[1]

        apparent_line, xrel_line = ax1.lines[0], ax1.lines[1]
        legend = ax1.get_legend()
        legend_labels = [t.get_text() for t in legend.get_texts()] if legend is not None else None

        if ax1 is ax2:
            xerror_line = ax2.lines[2]
        else:
            xerror_line = ax2.lines[0]

        vcoll = ax2.collections[0]
        segments = vcoll.get_segments()
        xerror_minus_std = np.asarray([seg[0][1] for seg in segments], dtype=float)
        xerror_plus_std = np.asarray([seg[1][1] for seg in segments], dtype=float)
        vlines_x = np.asarray([seg[0][0] for seg in segments], dtype=float)

        return {
            "retval": retval,
            "apparent_x": np.asarray(apparent_line.get_xdata(), dtype=float),
            "apparent_y": np.asarray(apparent_line.get_ydata(), dtype=float),
            "xrel_x": np.asarray(xrel_line.get_xdata(), dtype=float),
            "xrel_y": np.asarray(xrel_line.get_ydata(), dtype=float),
            "panel1_ylim": ax1.get_ylim(),
            "panel1_xlabel": ax1.get_xlabel(),
            "panel1_ylabel": ax1.get_ylabel(),
            "legend_labels": legend_labels,
            "xerror_x": np.asarray(xerror_line.get_xdata(), dtype=float),
            "xerror_y": np.asarray(xerror_line.get_ydata(), dtype=float),
            "panel2_ylim": ax2.get_ylim(),
            "panel2_xlabel": ax2.get_xlabel(),
            "panel2_ylabel": ax2.get_ylabel(),
            "xerror_minus_std": xerror_minus_std,
            "xerror_plus_std": xerror_plus_std,
            "vlines_x": vlines_x,
            "n_axes": 1 if ax1 is ax2 else 2,
            "ax1_n_lines": len(ax1.lines),
        }
    finally:
        plt.close("all")


# ---------------------------------------------------------------------------
# meanvar-specific plumbing.
#
# meanvar(tree, ...) (rpart/R/meanvar.rpart.R) is a plain S3 generic defined
# *within* the rpart package itself --
#     meanvar <- function(tree, ...) UseMethod("meanvar")
# -- unlike e.g. plot.rpart/print.rpart, which extend a *base-R* generic
# (`plot`/`print`). Since "meanvar" itself has no method registered for any
# class besides "rpart" (NAMESPACE: `S3method(meanvar, rpart)`), a bare
# `meanvar(x)` call for an `x` that isn't "rpart"-classed fails inside
# UseMethod itself ("no applicable method for 'meanvar' applied to an
# object of class ...") *before* ever reaching meanvar.rpart's own
# `if (!inherits(tree, "rpart")) stop("Not a legitimate \"rpart\" object")`
# check -- so, exactly mirroring print.rpart's/plot.rpart's own established
# `rpart:::` triple-colon convention in this test suite, that check is only
# reachable (for a non-"rpart"-classed `x`) by calling
# `rpart:::meanvar.rpart(x, ...)` directly, which is what
# `r_meanvar_call_code(..., generic=False)` below does.
#
# meanvar.rpart's own transformation is a single, non-RNG-dependent
# subsetting of `tree$frame`:
#     frame <- frame[frame$var == "<leaf>", ]
#     x <- frame$yval
#     y <- frame$dev / frame$n
#     label <- row.names(frame)
#     plot(x, y, xlab = xlab, ylab = ylab, type = "n", ...)
#     text(x, y, label)
#     invisible(list(x = x, y = y, label = label))
# There is no cross-validation/xval-folds RNG divergence to sidestep here
# (unlike plotcp.R/rsq.rpart.R's cptable-based derivations) -- meanvar.rpart
# never even looks at `tree$cptable`. So both a genuine fitted tree (built
# identically by R's rpart() and r2py_rpart.rpart() from the same
# formula/data) *and* a minimal hand-built synthetic `frame` (satisfying
# `inherits(x, "rpart")` + `x$method`, exactly like rsq.rpart's own
# `r_rsq_rpart_like_expr()`) are used across the tests below -- the
# synthetic-frame route additionally exercises the internal-node filtering
# (`var == "<leaf>"`) and edge-case frame contents (NaN/Inf/n=0/negative
# values/empty) that a real fitted tree wouldn't naturally produce.
#
# KNOWN GAP (python raises, R does not): whenever the derived `y`
# (`dev/n`) -- or `x` (`yval`) -- contains a non-finite value (NaN, from a
# `0/0` node; or +-Inf), R's `plot(x, y, ..., type = "n")` still succeeds
# (confirmed empirically: R's plot.window silently tolerates non-finite
# `x`/`y` values when computing the axis range from the *other*, finite
# values) and meanvar.rpart returns its full `list(x=, y=, label=)` normally
# -- whereas r2py_rpart's `ax.set_xlim(x.min(), x.max())`/`ax.set_ylim(...)`
# calls raise `ValueError: Axis limits cannot be NaN or Inf` (matplotlib
# validates its limits strictly), so r2py_rpart.meanvar() raises before
# ever returning. See test_meanvar_edge.py's dedicated "known gap" tests.
# ---------------------------------------------------------------------------

def r_meanvar_frame_expr(var: list[str], yval: Any, dev: Any, n: Any, index: list[int]) -> str:
    """Render an R expression for a `tree$frame`-like data.frame carrying
    just the 4 columns meanvar.rpart actually reads (`var`, `yval`, `dev`,
    `n`), with `row.names` set to `index` (rendered as character strings,
    matching R's own `row.names(frame)` -- data.frame row names are always
    character, even for an all-integer node-id index)."""
    var_r = _r_str_vec(var)
    yval_r = _r_num_vec(yval)
    dev_r = _r_num_vec(dev)
    n_r = _r_num_vec(n)
    rn_r = _r_str_vec([str(i) for i in index])
    return (
        f"data.frame(var={var_r}, yval={yval_r}, dev={dev_r}, n={n_r}, "
        f"row.names={rn_r}, stringsAsFactors=FALSE)"
    )


def r_meanvar_like_expr(
    var: list[str], yval: Any, dev: Any, n: Any, index: list[int], method: str = "anova"
) -> str:
    """Render an R expression for a minimal object satisfying `inherits(x,
    "rpart")`, carrying only `frame` and `method` -- exactly the two
    elements meanvar.rpart.R's own body reads (`tree$frame`, `tree$method`)."""
    frame_expr = r_meanvar_frame_expr(var, yval, dev, n, index)
    return f'structure(list(frame = {frame_expr}, method = {r_literal(method)}), class = "rpart")'


def r_meanvar_call_code(
    x_expr: str, *, xlab: str | None = None, ylab: str | None = None, generic: bool = True
) -> str:
    """Build the R source for a `meanvar(x_expr, ...)` call (the documented
    S3-generic dispatch route -- `usage{meanvar(tree, ...)}` -- `generic=True`)
    or a direct `rpart:::meanvar.rpart(x_expr, ...)` call (`generic=False`,
    required whenever `x_expr` has no "rpart" class, since the bare generic
    would otherwise fail inside UseMethod itself and never reach
    meanvar.rpart's own legitimacy checks -- see module-level note above).
    ``xlab``/``ylab`` are omitted entirely when None, so
    `missing(xlab)`/`missing(ylab)` stays TRUE and meanvar.rpart's own
    defaults (`"ave(y)"`/`"ave(deviance)"`) apply."""
    args = [x_expr]
    if xlab is not None:
        args.append(f"xlab={r_literal(xlab)}")
    if ylab is not None:
        args.append(f"ylab={r_literal(ylab)}")
    fn = "meanvar" if generic else "rpart:::meanvar.rpart"
    return fn + "(" + ", ".join(args) + ")"


def _r_meanvar_in_null_device(code: str) -> None:
    """Run R source that may call meanvar()/meanvar.rpart() (which plots on
    'the current graphical device') inside a no-op `pdf(NULL)` device, so it
    never attempts to open a real display in a headless test environment.
    The device is always closed afterward, even if `code` raises."""
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(code)
    finally:
        run_r("grDevices::dev.off()")


def r_meanvar_result(
    x_expr: str, *, xlab: str | None = None, ylab: str | None = None, generic: bool = True
) -> dict[str, Any]:
    """Call `meanvar(x_expr, ...)` (or `rpart:::meanvar.rpart(x_expr, ...)`
    if ``generic`` is False) inside a no-op graphics device, and return its
    `invisible(list(x=, y=, label=))` return value as a plain python dict
    directly comparable to r2py_rpart.meanvar()'s own return dict.

    The call is assigned into a temp global (`meanvar_result_tmp`) and then
    fetched back out via a *separate* `run_r()` call, rather than returning
    the assignment expression's own value directly -- meanvar.rpart's
    return value is wrapped in `invisible(...)`, and rpy2's `ro.r(...)`
    empirically returns `None` (rather than the assigned value) for a
    top-level `name <- invisible(...)` expression, even though the
    assignment itself succeeds (confirmed empirically before writing this
    helper)."""
    run_r("grDevices::pdf(NULL)")
    try:
        code = r_meanvar_call_code(x_expr, xlab=xlab, ylab=ylab, generic=generic)
        run_r(f"meanvar_result_tmp <- {code}")
        result = run_r("meanvar_result_tmp")
        return {
            "x": np.asarray(result.rx2("x"), dtype=float),
            "y": np.asarray(result.rx2("y"), dtype=float),
            "label": [str(s) for s in result.rx2("label")],
        }
    finally:
        run_r("grDevices::dev.off()")


def r_meanvar_error(
    x_expr: str, *, xlab: str | None = None, ylab: str | None = None, generic: bool = True
) -> str | None:
    """Call `meanvar(x_expr, ...)`/`rpart:::meanvar.rpart(x_expr, ...)` (the
    actual R function, inside a no-op graphics device) for its side effect
    only, returning the R error message string if it raises (via
    r_error_message()), else None."""
    code = r_meanvar_call_code(x_expr, xlab=xlab, ylab=ylab, generic=generic)
    return r_error_message(lambda: _r_meanvar_in_null_device(code))


def r_meanvar_runs_without_error(
    x_expr: str, *, xlab: str | None = None, ylab: str | None = None, generic: bool = True
) -> bool:
    """Sanity-check that R's *real* meanvar()/meanvar.rpart() accepts a
    given input/kwargs combination without raising -- a complement to
    r_meanvar_error(), used in positive/edge tests to confirm the synthetic
    frame/kwargs used are genuinely within meanvar.rpart's documented
    domain, not just accepted by r2py_rpart's own (possibly divergent, see
    the KNOWN GAP note above) implementation."""
    return r_meanvar_error(x_expr, xlab=xlab, ylab=ylab, generic=generic) is None


# ---------------------------------------------------------------------------
# meanvar-specific plumbing, python side: build_meanvar_tree() constructs a
# minimal r2py_rpart-style "rpart" dict directly comparable to
# r_meanvar_like_expr()'s R-side counterpart, and
# call_meanvar_and_extract() invokes r2py_rpart.meanvar() against it,
# pulling back out both its `{"x":, "y":, "label":}` return value and the
# plotted data/labels from the `matplotlib.axes.Axes` it creates.
# ---------------------------------------------------------------------------

def build_meanvar_tree(
    var: list[str], yval: Any, dev: Any, n: Any, index: list[int], method: str = "anova"
) -> dict[str, Any]:
    """Build a minimal r2py_rpart-style "rpart" dict carrying just the
    `frame` (with `var`/`yval`/`dev`/`n` columns, indexed by `index`) and
    `method` elements -- the two elements r2py_rpart.meanvar_rpart() itself
    reads -- directly comparable to `r_meanvar_like_expr()`'s R-side
    counterpart."""
    frame = pd.DataFrame(
        {
            "var": list(var),
            "yval": np.asarray(yval, dtype=float),
            "dev": np.asarray(dev, dtype=float),
            "n": np.asarray(n, dtype=float),
        },
        index=list(index),
    )
    return {"_rpart_class": "rpart", "method": method, "frame": frame}


def call_meanvar_and_extract(tree: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Call r2py_rpart.meanvar(tree, **kwargs) and return a dict of both its
    return value (x/y/label) and the plotted data pulled back out of the
    `matplotlib.axes.Axes` it creates -- the "x"/"y"/"label" keys are
    directly comparable to `r_meanvar_result()`'s R-side counterpart, while
    "xlim"/"ylim"/"xlabel"/"ylabel"/"texts" are python-only sanity checks
    confirming meanvar_rpart.py's own plotting logic is internally
    consistent with the data it just derived.

    Any pre-existing open figures are closed first (so `plt.gcf()`
    unambiguously picks up the one meanvar() itself just created), and the
    created figure is always closed afterward, even on error, to avoid
    leaking matplotlib figures across the test session.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.meanvar_rpart import meanvar

    plt.close("all")
    try:
        retval = meanvar(tree, **kwargs)
        fig = plt.gcf()
        ax = fig.axes[0]
        texts = sorted(
            (float(t.get_position()[0]), float(t.get_position()[1]), t.get_text())
            for t in ax.texts
        )
        return {
            "retval": retval,
            "x": np.asarray(retval["x"], dtype=float),
            "y": np.asarray(retval["y"], dtype=float),
            "label": list(retval["label"]),
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "xlabel": ax.get_xlabel(),
            "ylabel": ax.get_ylabel(),
            "texts": texts,
            "n_texts": len(ax.texts),
        }
    finally:
        plt.close("all")


def call_meanvar_rpart_and_extract(tree: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Call r2py_rpart's `meanvar_rpart(tree, *args, **kwargs)` *directly*
    (importing meanvar_rpart itself, bypassing the `meanvar(tree, **kwargs)`
    generic-style wrapper entirely) and return a dict of both its return
    value (x/y/label) and the plotted data pulled back out of the
    `matplotlib.axes.Axes` it creates.

    This is the meanvar_rpart-specific counterpart to `call_meanvar_and_extract()`
    above: the latter can only ever pass xlab/ylab as *keyword* arguments
    (meanvar()'s own signature is `(tree, **kwargs)`, with no positional
    xlab/ylab slot of its own for python to bind positional arguments to),
    whereas meanvar_rpart's own concrete signature -- `(tree, xlab="ave(y)",
    ylab="ave(deviance)", **kwargs)`, mirroring R's `function(tree, xlab =
    "ave(y)", ylab = "ave(deviance)", ...)` argument order exactly -- accepts
    xlab/ylab positionally too. ``*args`` lets callers exercise that
    positional-argument-binding path directly.
    """
    import matplotlib.pyplot as plt

    from r2py_rpart.meanvar_rpart import meanvar_rpart

    plt.close("all")
    try:
        retval = meanvar_rpart(tree, *args, **kwargs)
        fig = plt.gcf()
        ax = fig.axes[0]
        return {
            "retval": retval,
            "x": np.asarray(retval["x"], dtype=float),
            "y": np.asarray(retval["y"], dtype=float),
            "label": list(retval["label"]),
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "xlabel": ax.get_xlabel(),
            "ylabel": ax.get_ylabel(),
        }
    finally:
        plt.close("all")


# ---------------------------------------------------------------------------
# summary.rpart-specific plumbing.
#
# summary.rpart(object, cp=, digits=, file, ...) is registered as an S3
# method for the `summary` generic (`S3method(summary, rpart)` in NAMESPACE)
# -- so the documented calling convention is the plain generic `summary(fit,
# ...)` (used below for genuine "x really is class 'rpart'" scenarios, via
# `r_summary_rpart_lines`), while its `inherits(object, "rpart")` legitimacy
# check is exercised directly via `rpart:::summary.rpart(x, ...)` for
# negative tests whose `x` deliberately has no "rpart" class at all
# (mirroring print.rpart's/printcp's own conventions above -- plain
# `summary(x)` on a non-"rpart"-classed `x` would dispatch to
# `summary.default` instead, never reaching summary.rpart's own check).
#
# Like print.rpart, summary.rpart's contract is almost entirely a printed
# console layout (it returns `invisible(x)`, the same object it was given --
# there is no other return value to inspect). Three sections of that layout
# are permanently unable to match R textually, for the same structural
# reasons already documented at length in test_printcp_positive.py's module
# docstring (gaps 1 and 4 there) and demonstrated again for summary.rpart in
# test_summary_rpart_positive.py's own module docstring:
#   - the "Call:" echo block (python dumps `x['call']`'s dict repr -- which
#     embeds the *entire* input DataFrame -- instead of R's short `dput()`
#     rendering of the parsed call),
#   - the cp-table block (pandas' `to_string()` vs R's column-aligned
#     `format()`),
#   - the "Variable importance" block (R prints a two-line, column-aligned
#     named-vector layout; python prints one "Name: Value" line per
#     variable).
# `summary_rpart_variable_importance_dict_r`/`_py` below parse each side's
# version of that third block back into a plain `{name: value}` dict so it
# can still be compared *semantically*. Every other line in summary.rpart's
# output (the "n=" header, and the per-node "Node number ..." blocks,
# including "Primary splits:"/"Surrogate splits:") matches R's text modulo
# only (a) incidental trailing whitespace (R's `cat(..., sep=" ")` leaves a
# trailing space here and there that python's f-strings don't) and (b)
# trailing-zero padding on formatted floats (R's `format(signif(x, digits))`
# pads every value to the same decimal width that the *hardest* case in that
# call needs; python's per-value `%g`-style formatting does not) --
# `normalize_summary_line`/`summary_lines_match` below collapse both of
# those away by re-parsing every numeric token back to a float before
# comparing, so the bulk of summary.rpart's output can be compared with
# genuine rigor despite those two purely-cosmetic gaps.
# ---------------------------------------------------------------------------

def r_summary_rpart_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for a `rpart:::summary.rpart(x_expr, ...)` call
    (bypassing S3 dispatch -- see module-level note above).

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()").
    ``kwargs`` (cp=/digits=/file=) are rendered via r_literal() and appended
    `name=value`; a kwarg whose value is None is *omitted* entirely (not
    passed as NULL) so that `missing(file)`/`missing(digits)` inside
    summary.rpart stay TRUE when the caller doesn't care about them --
    passing file=NULL explicitly would instead try (and fail) to `sink(NULL)`.
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    return "rpart:::summary.rpart(" + ", ".join(args) + ")"


def r_summary_rpart_lines(fit: Any, **kwargs: Any) -> list[str]:
    """Call R's `summary(fit, ...)` (S3-dispatched to summary.rpart, the
    documented calling convention -- summary.rpart.Rd's own usage line is
    `summary(object, cp=0, digits=getOption("digits"), file, ...)`) on an
    already-fitted R model object, and return its printed console output as
    a list of lines (one per element of `capture.output()`'s returned
    character vector) -- directly comparable to
    `capture_summary_rpart_lines()`'s python-side return value.
    """
    ro.globalenv["summary_fit_tmp"] = fit
    args = ["summary_fit_tmp"]
    for k, v in kwargs.items():
        if v is None:
            continue
        args.append(f"{k}={r_literal(v)}")
    code = "capture.output(summary(" + ", ".join(args) + "))"
    result = run_r(code)
    return [str(s) for s in result]


def r_summary_rpart_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `rpart:::summary.rpart(x_expr, ...)` for its side effect only,
    returning the R error message string if it raises (via
    r_error_message()), else None. ``x_expr`` is R source, e.g. "NULL",
    "list()", "5", or a global variable name assigned beforehand.
    """
    code = r_summary_rpart_call_code(x_expr, **kwargs)
    return r_error_message(lambda: run_r(code))


def capture_summary_rpart_lines(
    capsys: Any, fit: dict[str, Any], **kwargs: Any
) -> tuple[list[str], Any]:
    """Call r2py_rpart's summary_rpart(fit, ...) and return a 2-tuple of (its
    stdout output as a list of lines, its return value) -- directly
    comparable to `r_summary_rpart_lines()`'s python-side counterpart.
    ``capsys`` is pytest's built-in fixture (passed in by the caller); a
    trailing empty string caused by the final bare `print()` call in
    summary_rpart.py's `_do_summary()` (mirroring R's final `cat("\\n")`,
    but -- like print_rpart.py/printcp.py's own last lines -- via python's
    `print()`, which adds its own trailing newline on top of the blank line
    it's printing) is stripped so both sides compare as the same list of
    content lines.
    """
    from r2py_rpart.summary_rpart import summary_rpart

    retval = summary_rpart(fit, **kwargs)
    out = capsys.readouterr().out
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, retval


_SUMMARY_NUM_TOKEN_RE = re.compile(r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")


def _normalize_summary_number_token(tok: str) -> str:
    try:
        v = float(tok)
    except ValueError:
        return tok
    if math.isnan(v) or math.isinf(v):
        return tok
    if v == int(v):
        return str(int(v))
    # Round-trip through a fixed-precision fixed-point representation and
    # strip trailing zeros, so that differing trailing-zero *padding*
    # conventions (R's format() pads a whole column to the same decimal
    # width; python's per-value '%g' formatting does not) collapse to the
    # same text, as long as the underlying rounded value itself agrees.
    return f"{v:.6f}".rstrip("0").rstrip(".")


def normalize_summary_line(line: str) -> str:
    """Collapse the permanent, purely-cosmetic formatting gaps documented in
    the module-level note above (leading/trailing whitespace; *internal*
    whitespace-run width -- e.g. R's `paste("splits as ", ...)` inserts one
    extra space that summary_rpart.py's f-string equivalent does not, and
    column-padding widths for left-justified variable names/cut
    descriptions routinely differ by a space or two even when the content
    agrees; float trailing-zero padding) out of a single line of
    summary.rpart/summary_rpart output, so the *content* of two otherwise-
    equivalent lines can be compared for equality. Does not attempt to
    handle scientific notation produced only under the digits= extremes
    explicitly called out as KNOWN GAPs in
    test_summary_rpart_negative.py/test_summary_rpart_edge.py."""
    normalized_numbers = _SUMMARY_NUM_TOKEN_RE.sub(
        lambda m: _normalize_summary_number_token(m.group(0)), line.strip()
    )
    collapsed = re.sub(r"\s+", " ", normalized_numbers)
    # R's format() left-pads a positive number with a blank (reserving room
    # for a '-' sign that non-negative values never need) wherever it
    # appears right after "=" (e.g. "improve= 2.483921") -- summary_rpart.py
    # never inserts that padding space. Drop any whitespace immediately
    # after "=" (and before ",") so this, too, collapses to the same text.
    collapsed = re.sub(r"=\s+", "=", collapsed)
    collapsed = re.sub(r"\s+,", ",", collapsed)
    return collapsed


def summary_lines_match(py_line: str, r_line: str) -> bool:
    """True iff two summary.rpart output lines agree once
    `normalize_summary_line` has collapsed away trailing whitespace and
    float trailing-zero-padding differences."""
    return normalize_summary_line(py_line) == normalize_summary_line(r_line)


_NODE_HEADER_RE = re.compile(r"^Node number (\d+): ")


def summary_rpart_node_blocks(lines: list[str]) -> dict[int, list[str]]:
    """Split a summary.rpart/summary_rpart output's list of lines into a dict
    mapping each node id (parsed from its "Node number <id>: ..." header) to
    that node's own block of lines (from its header up to, but not
    including, the next node's header or the end of the output) -- directly
    comparable between the R and python sides regardless of what precedes
    the first node block (the Call echo / cp-table / Variable importance
    sections, all of which are handled separately -- see module-level note
    above)."""
    starts: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = _NODE_HEADER_RE.match(line)
        if m:
            starts.append((int(m.group(1)), i))
    blocks: dict[int, list[str]] = {}
    for k, (node_id, start) in enumerate(starts):
        end = starts[k + 1][1] if k + 1 < len(starts) else len(lines)
        blocks[node_id] = lines[start:end]
    return blocks


def assert_summary_node_blocks_match(py_lines: list[str], r_lines: list[str]) -> None:
    """Assert every "Node number ..." block (see `summary_rpart_node_blocks`)
    present in `r_lines` is also present in `py_lines`, with the exact same
    set of node ids, and that each corresponding pair of blocks matches
    line-for-line modulo `normalize_summary_line`'s cosmetic normalization."""
    py_blocks = summary_rpart_node_blocks(py_lines)
    r_blocks = summary_rpart_node_blocks(r_lines)
    assert set(py_blocks.keys()) == set(r_blocks.keys())
    for node_id in r_blocks:
        py_block = py_blocks[node_id]
        r_block = r_blocks[node_id]
        assert len(py_block) == len(r_block), (
            f"node {node_id}: line-count mismatch\npython={py_block!r}\nR={r_block!r}"
        )
        for py_line, r_line in zip(py_block, r_block):
            assert summary_lines_match(py_line, r_line), (
                f"node {node_id}: {py_line!r} != {r_line!r} (normalized: "
                f"{normalize_summary_line(py_line)!r} vs {normalize_summary_line(r_line)!r})"
            )


def summary_rpart_find_n_line(lines: list[str]) -> str:
    """Return the (stripped) "n=..." header line from a summary.rpart/
    summary_rpart output's list of lines -- the line printed right after the
    Call echo block (or, for a call-less object, the very first line)."""
    for line in lines:
        if line.strip().startswith("n="):
            return line.strip()
    raise AssertionError(f"no 'n=' line found in {lines!r}")


_VAR_IMPORTANCE_HEADER = "Variable importance"


def summary_rpart_variable_importance_dict_r(r_lines: list[str]) -> dict[str, int] | None:
    """Extract the {name: value} mapping from R summary.rpart's own
    "Variable importance" block, if present -- R's `print(temp[temp > 0])`
    prints a *named integer vector* via R's generic vector-print layout: one
    or more (names line, values line) pairs, each pair's columns aligned by
    width (wrapping across multiple pairs only if the full row would exceed
    the console width -- not exercised by this test suite's small predictor
    counts, but handled generically here regardless). Returns ``None`` if no
    such header line is present (a root-only/no-importance fit -- see
    module docstring)."""
    header_idx = None
    for i, line in enumerate(r_lines):
        if line.strip() == _VAR_IMPORTANCE_HEADER:
            header_idx = i
            break
    if header_idx is None:
        return None
    out: dict[str, int] = {}
    j = header_idx + 1
    while j + 1 < len(r_lines) and r_lines[j].strip() != "":
        names = r_lines[j].split()
        values = r_lines[j + 1].split()
        for name, value in zip(names, values):
            out[name] = int(round(float(value)))
        j += 2
    return out


def summary_rpart_variable_importance_dict_py(py_lines: list[str]) -> dict[str, int] | None:
    """Extract the {name: value} mapping from r2py_rpart.summary_rpart's own
    "Variable importance" block, if present. summary_rpart.py now mirrors
    R's own `print(temp[temp > 0])` named-vector layout exactly (a
    (names-line, values-line) pair, column-aligned, wrapping across
    multiple pairs only if a row would exceed console width) -- see
    `summary_rpart_variable_importance_dict_r`'s identical parsing logic,
    which this now shares in every respect but the input list. Returns
    ``None`` if no such header line is present (mirrors
    `summary_rpart_variable_importance_dict_r`'s None case)."""
    header_idx = None
    for i, line in enumerate(py_lines):
        if line.strip() == _VAR_IMPORTANCE_HEADER:
            header_idx = i
            break
    if header_idx is None:
        return None
    out: dict[str, int] = {}
    j = header_idx + 1
    while j + 1 < len(py_lines) and py_lines[j].strip() != "":
        names = py_lines[j].split()
        values = py_lines[j + 1].split()
        for name, value in zip(names, values):
            out[name] = int(round(float(value)))
        j += 2
    return out


# ---------------------------------------------------------------------------
# xpred.rpart-specific plumbing: calling R's `xpred.rpart(fit, xval=, cp=,
# return.all=)` directly and converting its return value (a 2-D matrix, or a
# 3-D array when `return.all=TRUE` *and* the fitted method's `numresp > 1`)
# into a plain numpy array directly comparable to r2py_rpart.xpred_rpart()'s
# return value.
#
# Unlike predict.rpart/print.rpart (registered S3 methods), xpred.rpart is a
# plain function exported directly from the rpart NAMESPACE -- so a bare
# `xpred.rpart(...)` call reaches its own `inherits(fit, "rpart")`
# legitimacy check directly for any `fit`, with no S3-dispatch/triple-colon
# complication needed (mirroring printcp's identical situation).
#
# `xpred.rpart(fit, xval=10)`'s *scalar*-`xval` code path draws its
# cross-validation fold assignment via R's own `sample()`, which is not
# reproducible against python's independent `numpy.random` stream (the same
# permanent, already-documented gap noted throughout this helper module and
# in test_xpred1.py/test_xpred2.py for rpart()'s own internal xval folds) --
# so value-parity tests below always pass an explicit `xval=` vector (a
# deterministic fold assignment both sides consume identically), reserving
# the scalar-`xval` path for structural-only checks.
# ---------------------------------------------------------------------------

def r_xpred_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for an `xpred.rpart(x_expr, ...)` call.

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()").
    ``kwargs`` (xval=/cp=/return_all=) are rendered via r_literal() and
    appended `name=value`, translating python's `return_all` to R's dotted
    `return.all` (R identifiers may contain literal dots; python's cannot).
    A kwarg whose value is None is *omitted* entirely (not passed as NULL)
    so that `missing(cp)` inside xpred.rpart stays TRUE when the caller
    doesn't supply an explicit `cp=` -- passing cp=NULL explicitly would
    instead be a genuine (non-missing) NULL argument, not exercising the
    same "derive cp from cptable" default code path xpred_rpart.py's own
    `cp is _MISSING` branch mirrors.
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is None:
            continue
        r_name = "return.all" if k == "return_all" else k
        args.append(f"{r_name}={r_literal(v)}")
    return "xpred.rpart(" + ", ".join(args) + ")"


def r_xpred(fit: Any, **kwargs: Any) -> Any:
    """Assign `fit` into R's global environment (as `xpred_fit_tmp`) and
    call `xpred.rpart(xpred_fit_tmp, ...)` (see r_xpred_call_code),
    returning the raw rpy2 result object -- a 2-D matrix, or a 3-D array
    when return_all=True and the method's numresp > 1."""
    ro.globalenv["xpred_fit_tmp"] = fit
    code = r_xpred_call_code("xpred_fit_tmp", **kwargs)
    return run_r(code)


def r_xpred_to_numpy(robj: Any) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Convert an R xpred.rpart() return value into a plain numpy float
    array, directly comparable to r2py_rpart.xpred_rpart()'s return value:
    both sides already agree on axis order/layout (R's `matrix(...,
    byrow=TRUE)` lays out (obs, cp) exactly like xpred_rpart.py's own
    `.reshape((nrow_X, n_cp), order='C')`, and R's `aperm()`-flipped 3-D
    `array(pred, dim=c(numresp, ncp, nobs))` lays out (obs, cp, resp)
    exactly like xpred_rpart.py's `np.transpose(...)` of the analogous
    Fortran-order reshape) -- so no further axis reordering is needed here,
    only the raw numeric conversion."""
    return np.asarray(robj, dtype=np.float64)


def r_xpred_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `xpred.rpart(x_expr, ...)` for its side effect only, returning
    the R error message string if it raises (via r_error_message()), else
    None. ``x_expr`` is R source, e.g. "NULL", "list()", "5", or a global
    variable name assigned beforehand."""
    code = r_xpred_call_code(x_expr, **kwargs)
    return r_error_message(lambda: run_r(code))


def default_xpred_cp(fit: dict[str, Any]) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Recompute xpred_rpart()'s own default (`cp is _MISSING`) complexity
    list directly from a r2py_rpart fit's `cptable`, mirroring
    xpred.rpart.R's `cp <- sqrt(cp * c(10, cp[-length(cp)])); cp[1] <- (1 +
    cptable[1,1])/2` (and xpred_rpart.py's identical `cp is _MISSING`
    branch) -- lets a test pin an explicit, R-and-python-agreeing `cp=`
    argument (e.g. to combine with an explicit `xval=` in the very same
    call) while still exercising exactly the values the *default* path
    would have produced."""
    cptable = fit["cptable"]
    cptable_arr = cptable.to_numpy() if hasattr(cptable, "to_numpy") else np.asarray(cptable)
    cp_col0 = np.asarray(cptable_arr[:, 0], dtype=np.float64)
    cp = np.sqrt(cp_col0 * np.concatenate([[10.0], cp_col0[:-1]]))
    cp[0] = (1.0 + float(cptable_arr[0, 0])) / 2.0
    return cp


# ---------------------------------------------------------------------------
# na.rpart-specific plumbing: calling R's `rpart:::na.rpart(x)` directly.
#
# na.rpart.R's own body only ever does `Terms <- attr(x, "terms")` and then
# (if non-NULL) `attr(Terms, "response")` -- so a bare R integer decorated
# with a `response` attribute is a perfectly legitimate stand-in for a real
# `terms` object (the kind `model.frame()` would normally attach) as far as
# na.rpart is concerned. `r_na_rpart()` below builds exactly that minimal
# stand-in, so na.rpart can be exercised directly without needing a full
# `model.frame()`/formula round trip. na.rpart is not exported from the
# rpart NAMESPACE (only registered as the package's default na.action), so
# it must be reached via the triple-colon internal accessor, `rpart:::`.
# ---------------------------------------------------------------------------

def r_na_rpart(df: pd.DataFrame, yvar: int | None) -> Any:
    """Assign ``df`` into R's globalenv as ``x``, optionally attaching a
    ``terms`` attribute whose own ``response`` attribute is ``yvar`` (cast
    to an R integer), then return the raw rpy2 result of
    ``rpart:::na.rpart(x)``. ``yvar=None`` leaves ``attr(x, "terms")``
    unset entirely -- na.rpart's own ``yvar <- 0L`` fallback path."""
    r_dataframe_assign("x", df)
    if yvar is not None:
        run_r(f'Terms <- 1; attr(Terms, "response") <- {int(yvar)}L; attr(x, "terms") <- Terms')
    else:
        run_r('attr(x, "terms") <- NULL')
    return run_r("rpart:::na.rpart(x)")


def r_na_action_to_dict(na_action: Any) -> dict[str, Any] | None:
    """Convert the `attr(result, "na.action")` object R's na.rpart()
    attaches (an integer vector of dropped positions, named with the
    dropped rows' original row.names, classed c("na.rpart", "omit")) into
    a plain dict directly comparable to r2py_rpart.na_rpart()'s own
    ``.attrs['na.action']`` -- {'indices': [...], 'names': [...], 'class':
    (...)}. Returns None if ``na_action`` is R's NULL (i.e. no rows were
    dropped)."""
    if isinstance(na_action, ro.rinterface.NULLType):
        return None
    indices = [int(v) for v in na_action]
    names = [str(v) for v in ro.r["names"](na_action)]
    klass = tuple(str(v) for v in ro.r["class"](na_action))
    return {"indices": indices, "names": names, "class": klass}


def r_na_rpart_result(df: pd.DataFrame, yvar: int | None) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Call r_na_rpart(df, yvar) and convert its result into a
    (filtered_dataframe, na_action_dict_or_None) pair directly comparable
    to r2py_rpart.na_rpart()'s own return value (a DataFrame, with an
    optional ``.attrs['na.action']`` dict of {'indices', 'names',
    'class'})."""
    result = r_na_rpart(df, yvar)
    out_df = from_r_dataframe(result)
    na_action = ro.r["attr"](result, "na.action")
    return out_df, r_na_action_to_dict(na_action)


def r_na_rpart_error(x_expr: str) -> str | None:
    """Call `rpart:::na.rpart(x_expr)` for its side effect only (``x_expr``
    is R source -- either a literal expression like "NULL"/"5"/'"hello"',
    or a variable name already assigned into globalenv), returning the R
    error message string if it raises (via r_error_message()), else None."""
    return r_error_message(lambda: run_r(f"rpart:::na.rpart({x_expr})"))


def r_na_rpart_with_terms_error(df: pd.DataFrame, yvar: int | None) -> str | None:
    """Like r_na_rpart_error(), but for the common "df + synthetic
    terms/response attribute" shape r_na_rpart()/r_na_rpart_result() build
    -- returns the R error message string if `rpart:::na.rpart(x)` raises
    (via r_error_message(), which also suppresses R's own write-console
    error echo), else None. Used by negative/edge tests that need to
    confirm *both* sides raise for a given (df, yvar) pair without caring
    about the (non-error) result otherwise."""
    return r_error_message(lambda: r_na_rpart(df, yvar))


# ---------------------------------------------------------------------------
# labels.rpart-specific plumbing.
#
# labels.rpart(object, digits=4, minlength=1L, pretty, collapse=TRUE, ...)
# is registered as an S3 method for the `labels` generic (`S3method(labels,
# rpart)` in rpart's NAMESPACE) -- but unlike text.rpart/plot.rpart, it is a
# *pure* function of its already-fitted `object` (frame/splits/csplit/
# xlevels): no graphics device, no RNG-driven cross-validation, no other
# side effects. So (unlike plotcp/plot.rpart's hand-copied "derivation
# replica" strategy, and unlike text.rpart's FUN=-capturing-closure
# strategy) labels.rpart can simply be called directly -- via the
# documented `labels(fit, ...)` generic dispatch -- on the *same* fitted
# model on both sides (an R fit built via `r_fit_rpart`, a python fit built
# via `rpart(...)`), relying only on R's and r2py_rpart's `rpart()` having
# chosen the identical tree structure for identical formula/data -- already
# established/relied upon throughout this test suite (see
# test_text_rpart_positive.py's module docstring) for every dataset used
# below (kyphosis/car.test.frame/cu.summary/stagec).
#
# `labels.rpart` has no `inherits(object, "rpart")` legitimacy check of its
# own (unlike print.rpart/plot.rpart/text.rpart) -- it just does `ff <-
# object$frame` directly -- exactly mirroring r2py_rpart's labels_rpart(),
# which likewise has no class check of its own and simply does `ff =
# object['frame']`. So malformed-object negative tests use `generic=False`
# below (routing to `rpart:::labels.rpart` directly, exactly like the
# print.rpart/text.rpart negative-test convention) purely to bypass the
# `labels()` *generic's own* dispatch-by-class behavior (which would
# otherwise silently fall through to `labels.default` for an unclassed `x`,
# never reaching labels.rpart's body at all -- confirmed empirically:
# `labels(NULL)` returns `character(0)` and `labels(5)` returns `"1"`,
# neither of which error).
# ---------------------------------------------------------------------------

_LABELS_OMIT = object()


def r_labels_call_code(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str:
    """Build the R source for a `labels(x_expr, ...)` call (the documented
    S3-generic dispatch route, `generic=True`) or a direct
    `rpart:::labels.rpart(x_expr, ...)` call (`generic=False`, needed
    whenever `x_expr` has no "rpart" class -- see module-level note above).

    ``kwargs`` (digits=/minlength=/pretty=/collapse=) are rendered via
    `r_literal()` and appended `name=value`. Unlike most of this file's
    other `*_call_code` helpers (where a kwarg value of plain `None` means
    "omit this argument, let R's own `missing()` resolve it"), a kwarg
    here is omitted only when its value is the sentinel `_LABELS_OMIT` --
    plain `None` is instead rendered as literal `NULL` via `r_literal`,
    since `pretty = NULL` is itself one of labels.rpart's three documented,
    distinct `pretty` values (as opposed to `pretty` not being passed at
    all, which must use `_LABELS_OMIT`)."""
    fn = "labels" if generic else "rpart:::labels.rpart"
    args = [x_expr]
    for k, v in kwargs.items():
        if v is _LABELS_OMIT:
            continue
        args.append(f"{k}={r_literal(v)}")
    return f"{fn}(" + ", ".join(args) + ")"


def r_labels(fit: Any, *, generic: bool = True, **kwargs: Any) -> Any:
    """Call R's `labels(fit, ...)` (S3-dispatched to labels.rpart, or
    direct via `generic=False`) on an already-fitted R model object (an
    rpy2 object, e.g. from `r_fit_rpart()`) and return the raw rpy2 result
    -- a character vector (`collapse=TRUE`) or a character matrix
    (`collapse=FALSE`). ``fit`` is assigned into R's globalenv under a temp
    name first; for an R expression/variable name that is *already* valid R
    source (e.g. one returned by `make_synthetic_categorical_fit()`), use
    `r_labels_result()` instead, which skips this assignment step."""
    ro.globalenv["labels_fit_tmp"] = fit
    code = r_labels_call_code("labels_fit_tmp", generic=generic, **kwargs)
    return run_r(code)


def r_labels_result(x_expr: str, *, generic: bool = True, **kwargs: Any) -> Any:
    """Like `r_labels()`, but for an R expression/variable name that is
    already valid R source (e.g. a global variable name already assigned
    via `make_synthetic_categorical_fit()`/`r_synthetic_categorical_object_code()`,
    or a literal expression like "NULL") -- unlike `r_labels()`, this does
    NOT re-assign anything into globalenv first."""
    code = r_labels_call_code(x_expr, generic=generic, **kwargs)
    return run_r(code)


def r_labels_to_python(robj: Any) -> list[str] | np.ndarray:
    """Convert an R labels.rpart() return value into a plain python object
    directly comparable to r2py_rpart.labels_rpart()'s own return value:

    - a plain character vector (`collapse=TRUE`, or the `n == 1L`
      "root"-only special case regardless of `collapse`) -> `list[str]`.
    - a character matrix (`collapse=FALSE`, `n > 1L`) -> a 2-D numpy
      `str` array, reshaped in column-major ("F") order to respect R's
      `dim` attribute (a bare `np.asarray(robj)` on an R matrix returns a
      flat 1-D array -- `dim` must be applied explicitly).
    """
    dim = ro.r["dim"](robj)
    if isinstance(dim, ro.rinterface.NULLType):
        return [str(s) for s in robj]
    nrow, ncol = int(dim[0]), int(dim[1])
    return np.asarray(robj, dtype=str).reshape((nrow, ncol), order="F")


def r_labels_error(x_expr: str, *, generic: bool = True, **kwargs: Any) -> str | None:
    """Call `labels(x_expr, ...)` (or `rpart:::labels.rpart` directly when
    `generic=False`) for its side effect only, returning the R error
    message string if it raises (via `r_error_message()`), else None.
    ``x_expr`` is R source, e.g. "NULL", "list()", "5", or a global
    variable name assigned beforehand."""
    code = r_labels_call_code(x_expr, generic=generic, **kwargs)
    return r_error_message(lambda: run_r(code))


def r_labels_capturing_warning(
    x_expr: str, *, generic: bool = True, **kwargs: Any
) -> tuple[Any, str | None]:
    """Like `r_labels()`/`r_labels_error()`, but via
    `r_eval_capturing_warning()`: returns (raw rpy2 result, first warning
    message or None) in one call -- used for labels.rpart's one documented
    warning ("more than 52 levels in a predicting factor, truncated for
    printout", raised when `minlength == 1L` and any split's `ncat > 52L`).
    ``x_expr`` must already be assigned into globalenv (e.g. via
    `r_labels()`'s own `labels_fit_tmp` convention, or
    `make_synthetic_categorical_fit()`'s returned R expression name)."""
    code = r_labels_call_code(x_expr, generic=generic, **kwargs)
    return r_eval_capturing_warning(code)


def r_synthetic_categorical_object_code(
    *, num_levels: int, left_levels: list[int], var_name: str = "X", maxcat: int | None = None
) -> str:
    """Build R source for a minimal, un-classed 3-row (root + 2 leaves)
    rpart-like list object with a single categorical primary split on a
    `num_levels`-level factor `var_name` (levels "L0".."L{num_levels-1}"),
    csplit-coded so 0-based levels in `left_levels` go left (code 1) and
    every other level goes right (code 3). If `maxcat` exceeds
    `num_levels`, `csplit` is padded with "not used" code-2 columns beyond
    the variable's own level count -- mirroring a real multi-predictor
    fit's `csplit`, which is padded out to the *largest* categorical
    predictor's level count across the whole model (see
    labels_rpart.py's own padding-handling comment). Assigns the object
    into R's globalenv as `synthetic_obj_tmp` and returns that variable
    name -- NOT classed "rpart", so must be exercised via
    `r_labels(..., generic=False)`/`r_labels_error(..., generic=False)`
    (mirroring every other malformed/synthetic-object helper in this
    file). Used to exercise labels.rpart's `minlength == 1L`-with->52-
    levels warning branch, impractical to trigger through a genuine
    data-driven `rpart()` fit."""
    maxcat = maxcat if maxcat is not None else num_levels
    codes = ["1" if i in left_levels else "3" for i in range(num_levels)]
    codes.extend("2" for _ in range(maxcat - num_levels))
    csplit_code = ", ".join(codes)
    code = f"""
    synthetic_obj_tmp <- list(
        frame = data.frame(var = c("{var_name}", "<leaf>", "<leaf>"),
                            ncompete = c(0, 0, 0), nsurrogate = c(0, 0, 0),
                            row.names = c("1", "2", "3"), stringsAsFactors = FALSE),
        splits = matrix(c(0, {num_levels}, 0, 1, 0), nrow = 1, ncol = 5),
        csplit = matrix(c({csplit_code}), nrow = 1, ncol = {maxcat})
    )
    attr(synthetic_obj_tmp, "xlevels") <- list({var_name} = paste0("L", 0:{num_levels - 1}))
    synthetic_obj_tmp
    """
    run_r(code)
    return "synthetic_obj_tmp"


def make_synthetic_categorical_fit(
    *, num_levels: int, left_levels: list[int], var_name: str = "X", maxcat: int | None = None
) -> tuple[dict[str, Any], str]:
    """Python-side counterpart to `r_synthetic_categorical_object_code()`:
    build the equivalent minimal 3-row fit dict (root categorical split +
    2 leaves), directly comparable to r2py_rpart.labels_rpart(), and also
    assign the matching R object into globalenv (via
    `r_synthetic_categorical_object_code`). Returns `(py_obj, r_expr)`,
    where `r_expr` ("synthetic_obj_tmp") is the R global variable name to
    pass into `r_labels(r_expr, generic=False, ...)` /
    `r_labels_capturing_warning(r_expr, generic=False, ...)` (it has no
    "rpart" class -- see module-level note above)."""
    maxcat = maxcat if maxcat is not None else num_levels
    frame = pd.DataFrame(
        {"var": [var_name, "<leaf>", "<leaf>"], "ncompete": [0, 0, 0], "nsurrogate": [0, 0, 0]},
        index=[1, 2, 3],
    )
    splits = np.zeros((1, 5))
    splits[0, 1] = num_levels
    splits[0, 3] = 1
    csplit = np.full((1, maxcat), 2)
    for i in range(num_levels):
        csplit[0, i] = 1 if i in left_levels else 3
    xlevels = {var_name: [f"L{i}" for i in range(num_levels)]}
    py_obj: dict[str, Any] = {"frame": frame, "splits": splits, "csplit": csplit, "_xlevels": xlevels}
    r_expr = r_synthetic_categorical_object_code(
        num_levels=num_levels, left_levels=left_levels, var_name=var_name, maxcat=maxcat
    )
    return py_obj, r_expr


# ---------------------------------------------------------------------------
# path.rpart-specific plumbing.
#
# path.rpart(tree, nodes, pretty=0, print.it=TRUE) is exported directly from
# rpart's NAMESPACE (a plain function, not an S3 generic) -- like printcp, a
# bare `path.rpart(...)` call reaches its own `inherits(tree, "rpart")`
# legitimacy check for any `tree`, with no `rpart:::` triple-colon internal-
# access trick needed.
#
# This test suite only exercises the *non-interactive* branch (`nodes`
# supplied) -- the `missing(nodes)` branch calls `rpartco(tree)` then
# `identify()` (interactive mouse-driven graphics), which
# r2py_rpart.path_rpart() itself stubs out as a no-op returning `{}` (see
# its own module docstring/comment) and which R itself cannot run
# headlessly either -- `rpartco(tree)` immediately raises "no information
# available on parameters from previous call to plot()" whenever no prior
# `plot()` call exists for the current graphics device (confirmed
# empirically), a genuine, permanent one-sided-raise gap pinned in
# test_path_rpart_negative.py/test_path_rpart_edge.py rather than exercised
# as a "real" scenario.
#
# path.rpart's return value, `invisible(path)`, is a *named list* keyed by
# node id (the corresponding frame row.names character string), each
# element a plain character vector of split labels from root to that node
# -- when every supplied node is invalid, R's `node.match()` returns a
# length-0 vector and path.rpart short-circuits to `return(invisible())`,
# i.e. plain NULL, not an empty list, whereas r2py_rpart.path_rpart()
# returns `{}` in that case (a permanent, confirmed divergence pinned as a
# KNOWN GAP in the edge-case suite rather than compared for equality).
#
# A subtlety specific to path.rpart (not shared with printcp/labels.rpart):
# evaluating `path.rpart(...)` directly as R *source text* via a bare
# `ro.r("path.rpart(...)")` call returns python `None` even on a genuine,
# non-empty result -- rpy2's `robjects.r(str)` respects R's own
# invisibility flag for a top-level call, and `invisible(path)` sets that
# flag (confirmed empirically: `ro.r["path.rpart"](...)`, the *function*-
# accessor call form, returns the real ListVector; `ro.r("path.rpart(...)")`
# returns None). `r_path_rpart()`/`r_path_rpart_result()` below sidestep
# this by assigning the call's result to a temp variable and then
# referencing that variable's bare *name* as the final statement (a bare
# symbol lookup is always visible), rather than using the function-accessor
# form directly (which does not compose as cleanly with capture.output()
# for `r_path_rpart_lines_and_result()`'s combined printed-lines-plus-
# result capture below).
# ---------------------------------------------------------------------------

_PATH_RPART_OMIT = object()
"""Sentinel meaning "omit this argument entirely" for
`r_path_rpart_call_code()`'s ``kwargs``. Unlike most of this file's other
`*_call_code` helpers (where a kwarg value of plain `None` means "omit"),
path.rpart's own `pretty=` argument treats `pretty=None` (i.e. R's
`pretty=NULL`) as one of its three documented, distinct values (-> passed
straight through to labels.rpart, `pretty=NULL` -> `minlength=1L`) --
confirmed empirically that silently omitting a python `None` `pretty=`
kwarg here (rather than rendering it as literal `NULL`) produces a
different, non-matching result. So a dedicated sentinel is used instead,
letting plain `None` render as literal `NULL` via `r_literal()`."""


def r_path_rpart_call_code(x_expr: str, **kwargs: Any) -> str:
    """Build the R source for a `path.rpart(x_expr, ...)` call.

    ``x_expr`` is inserted verbatim as R source (a variable name already
    assigned into globalenv, or a literal expression like "NULL"/"list()").
    ``kwargs`` (nodes=/pretty=/print.it=) are rendered via `r_literal()` and
    appended `name=value`; a kwarg whose value is the `_PATH_RPART_OMIT`
    sentinel is omitted entirely -- in particular, passing
    `nodes=_PATH_RPART_OMIT` keeps `nodes` unset (triggering R's own
    `missing(nodes)` interactive branch), and `pretty=_PATH_RPART_OMIT`
    lets `pretty`'s own R default (`0`) apply via `missing(pretty)`. A
    plain python `None` (e.g. `pretty=None`) is instead rendered as literal
    `NULL` -- see `_PATH_RPART_OMIT`'s own docstring above. Note `print.it`
    (an R argument name with a literal dot) must be passed as
    `kwargs={"print.it": ...}`, since `print.it` is not a legal python
    keyword-argument name.
    """
    args = [x_expr]
    for k, v in kwargs.items():
        if v is _PATH_RPART_OMIT:
            continue
        args.append(f"{k}={r_literal(v)}")
    return "path.rpart(" + ", ".join(args) + ")"


def r_path_rpart(fit: Any, **kwargs: Any) -> Any:
    """Call R's `path.rpart(fit, ...)` on an already-fitted R model object
    (an rpy2 object, e.g. from `r_fit_rpart()`) and return the raw rpy2
    result -- a `ListVector` keyed by node id, or `NULLType` when every
    supplied node is invalid (see module-level note above on why a plain
    `run_r(call_code)` would not work here). ``fit`` is assigned into R's
    globalenv under a temp name first; for an R expression/variable name
    that is already valid R source, use `r_path_rpart_result()` instead."""
    ro.globalenv["path_fit_tmp"] = fit
    call_code = r_path_rpart_call_code("path_fit_tmp", **kwargs)
    code = f"path_rpart_result_tmp <- {call_code}\npath_rpart_result_tmp"
    return run_r(code)


def r_path_rpart_result(x_expr: str, **kwargs: Any) -> Any:
    """Like `r_path_rpart()`, but for an R expression/variable name that is
    already valid R source (e.g. "NULL", "list()", "5", or a global
    variable name assigned beforehand) -- unlike `r_path_rpart()`, this does
    NOT re-assign anything into globalenv first."""
    call_code = r_path_rpart_call_code(x_expr, **kwargs)
    code = f"path_rpart_result_tmp <- {call_code}\npath_rpart_result_tmp"
    return run_r(code)


def r_path_rpart_to_python(robj: Any) -> dict[str, list[str]] | None:
    """Convert an R path.rpart() return value into a plain python object
    directly comparable to r2py_rpart.path_rpart()'s own return value:

    - a named list (the ordinary case)   -> `dict[str, list[str]]`, keyed
      by node id string, each value the list of split labels root-to-node.
    - R's plain `NULL` (every supplied node invalid, `invisible()`'s
      short-circuit return) -> python `None` -- deliberately *not*
      coerced to `{}`, so callers can distinguish R's actual NULL from
      r2py_rpart.path_rpart()'s `{}` in that same scenario (see the
      KNOWN GAP note above and test_path_rpart_edge.py).
    """
    if isinstance(robj, ro.rinterface.NULLType):
        return None
    names = robj.names
    if isinstance(names, ro.rinterface.NULLType):
        return {}
    return {str(name): [str(s) for s in robj[i]] for i, name in enumerate(names)}


def r_path_rpart_error(x_expr: str, **kwargs: Any) -> str | None:
    """Call `path.rpart(x_expr, ...)` for its side effect only, returning
    the R error message string if it raises (via `r_error_message()`), else
    None. ``x_expr`` is R source, e.g. "NULL", "list()", "5", or a global
    variable name assigned beforehand."""
    code = r_path_rpart_call_code(x_expr, **kwargs)
    return r_error_message(lambda: run_r(code))


def r_path_rpart_lines_and_result(fit: Any, **kwargs: Any) -> tuple[list[str], dict[str, list[str]] | None]:
    """Call R's `path.rpart(fit, ...)` on an already-fitted R model object
    and return a 2-tuple of (its printed console output as a list of
    lines -- one per element of `capture.output()`'s returned character
    vector, directly comparable to `capture_path_rpart_lines_and_result()`'s
    python-side return value -- and its *returned* value, converted via
    `r_path_rpart_to_python()`)."""
    ro.globalenv["path_fit_tmp"] = fit
    call_code = r_path_rpart_call_code("path_fit_tmp", **kwargs)
    lines_code = f"capture.output(path_rpart_result_tmp <- {call_code})"
    lines_result = run_r(lines_code)
    lines = [str(s) for s in lines_result]
    result = run_r("path_rpart_result_tmp")
    return lines, r_path_rpart_to_python(result)


def capture_path_rpart_lines_and_result(
    capsys: Any, tree: dict[str, Any], **kwargs: Any
) -> tuple[list[str], dict[str, list[str]]]:
    """Call r2py_rpart's path_rpart(tree, ...) and return a 2-tuple of (its
    stdout output as a list of lines, its return value) -- directly
    comparable to `r_path_rpart_lines_and_result()`'s python-side
    counterpart. ``capsys`` is pytest's built-in fixture (passed in by the
    caller); a trailing empty string caused by python's own trailing
    newline on the last `print(...)` call is stripped so both sides compare
    as the same list of content lines."""
    from r2py_rpart.path_rpart import path_rpart

    retval = path_rpart(tree, **kwargs)
    out = capsys.readouterr().out
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, retval


def with_response_attr(df: pd.DataFrame, yvar: int | None) -> pd.DataFrame:
    """Python-side mirror of r_na_rpart()'s R-side `terms`/`response`
    attribute setup: return a copy of ``df`` with ``.attrs['terms'] =
    {'response': yvar}`` set (matching the {'response': ...} dict shape
    r2py_rpart.na_rpart() itself reads via ``Terms.get('response', 0)``),
    or with no `terms` attr at all when ``yvar is None`` (na_rpart's own
    ``yvar = 0`` fallback path when ``x.attrs.get('terms')`` is None)."""
    out = df.copy()
    if yvar is not None:
        out.attrs["terms"] = {"response": yvar}
    return out
