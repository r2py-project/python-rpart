# Conversion Guide: `quote` in R

---

## 1. Overview of `quote` in R

`quote(expr)` captures its argument as an unevaluated R language object (a `call`, `name`, or other expression object) without evaluating it. The returned object is of class `"call"` (or `"name"`, `"("`, etc.) and carries the full abstract-syntax-tree of the expression.

Key properties:

- The argument is **never evaluated**. `quote(1 + 1)` returns the call object `1 + 1`, not `2`.
- The result is a first-class R object that can be stored, inspected, modified (via `[[<-` substitution), and later evaluated with `eval()` / `eval.parent()`.
- Replacing an element of a call with `quote(some::function)` is the idiomatic way to redirect a constructed call to a different function without re-parsing text.
- When passed to `.Call(C_init_rpcallback, ...)`, a quoted block of R code becomes a deferred callback that C code can invoke via `R_tryEval`; this is an entirely R-specific mechanism with no direct C/Python analogue.

---

## 2. Contextual Usage Analysis

The CSV entries represent two distinct patterns of `quote` usage within the rpart package.

### Pattern A: Function-name substitution in a dynamically-built call

Locations: `rpart/R/rpart.R` line 18, `rpart/R/xpred.rpart.R` line 24.

Both sites build a call object from the original user call (`match.call()` / `fit$call`), strip it down to only the arguments needed for `stats::model.frame`, and then replace the first element (the function to call) with the symbol `stats::model.frame`:

```r
temp[[1L]] <- quote(stats::model.frame)
m <- eval.parent(temp)
```

The value stored is a `call` object of type `name` (specifically a namespaced symbol). The purpose is to reuse the original call's argument list while pointing it at a different function — a pattern that avoids re-parsing or hardcoding argument names.

### Pattern B: Quoting multi-statement blocks as C callback expressions

Location: `rpart/R/rpartcallback.R` lines 33, 41, 61, 70.

Four `quote({...})` calls capture entire blocks of R code as expression objects (`expr1`, `expr2`). These objects are passed directly to C via `.Call(C_init_rpcallback, rho, ..., expr1, expr2)`. The C layer stores them and later evaluates them in the environment `rho` on every callback from the tree-building algorithm. The quoted blocks contain:

- Array slicing (`yback[1:nback]`, `xback[1L:n2]`)
- Matrix reshaping (`matrix(yback[1L:(nback * numy)], ncol = numy)`)
- Calls to user-provided functions (`user.eval`, `user.split`)
- Validation checks and final numeric coercion (`as.numeric(as.vector(...))`)

The arguments and return values involved are numeric vectors and integer scalars managed in `rho`, an isolated R environment whose contents are overwritten by C on each invocation.

---

## 3. Python Conversion Strategy

`quote` is a **metaprogramming construct** with no single Python equivalent. The correct translation depends entirely on which of the two patterns is in use.

### Pattern A: Function-name substitution

In Python there is no need to quote a function name to redirect a call. Python functions are first-class objects and can be stored and called directly. The R idiom of building a call from user arguments and replacing its head with a different function translates to simply calling the target function with the same keyword arguments assembled programmatically. `functools`, plain callables, or `getattr` are the appropriate tools.

### Pattern B: Deferred code blocks for C callbacks

R's ability to pass an unevaluated block of R code to C, which then `eval`s it in a specific environment, has no direct Python equivalent. In Python, the equivalent is a **callable** (a function, lambda, or class instance with `__call__`) that closes over the relevant state. The C interface would call the Python callable directly rather than evaluating a quoted expression. `ctypes` callback types (`ctypes.CFUNCTYPE`) or `cffi` callbacks are the mechanism for passing Python callables into C code.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Pattern A — Redirecting a dynamically-built call to `stats::model.frame`

**Locations:**
- `rpart/R/rpart.R`, function `rpart`, line 18
- `rpart/R/xpred.rpart.R`, function `xpred.rpart`, line 24

**Original R Context:**

Input types: `temp` is a `call` object built from `match.call()` (in `rpart.R`) or from `fit$call` (in `xpred.rpart.R`). It holds a subset of the original call's arguments (formula, data, weights, subset, na.action). `quote(stats::model.frame)` produces a `name` object.

Return: `eval.parent(temp)` returns a `data.frame` (the model frame).

```r
# rpart.R — build a trimmed call, redirect its function, evaluate it
temp <- Call[c(1L, indx)]
temp$na.action <- na.action
temp[[1L]] <- quote(stats::model.frame)   # replace function name
m <- eval.parent(temp)                    # evaluate in parent frame
```

```r
# xpred.rpart.R — same pattern starting from a stored call
m <- fit$call[match(c("", "formula", "data", "weights", "subset",
                      "na.action"), names(fit$call), 0L)]
if (is.null(m$na.action)) m$na.action <- na.rpart
m[[1]] <- quote(stats::model.frame)
m <- eval.parent(m)
```

**Python Equivalent:**

In Python, `stats::model.frame` has been converted to a Python function (e.g., `model_frame` from the project's own translation layer or from `patsy`/`formulaic`). There is no call object to redirect; the function is simply called with the collected keyword arguments.

```python
import pandas as pd
from patsy import dmatrix  # or the project's own model_frame equivalent

def rpart(formula, data, weights=None, subset=None, na_action=None, ...):
    # Collect the arguments that model.frame would need
    mf_kwargs = {}
    if formula is not None:
        mf_kwargs["formula"] = formula
    if data is not None:
        mf_kwargs["data"] = data
    if weights is not None:
        mf_kwargs["weights"] = weights
    if subset is not None:
        mf_kwargs["subset"] = subset
    if na_action is not None:
        mf_kwargs["na_action"] = na_action

    # Call the Python equivalent of stats::model.frame directly —
    # no quoting or call-object manipulation is required.
    m = model_frame(**mf_kwargs)
    ...
```

**Explanation:**

R needs `quote(stats::model.frame)` because it is constructing a `call` object at runtime and must replace its first element (the function slot) with an unevaluated symbol. Python has no such construct: functions are objects that can be stored in variables and called directly. There is nothing to quote. The translation is to collect the arguments into a dict and call the target function with `**kwargs` (or positionally), making the metaprogramming step entirely unnecessary.

---

### 4.2 Pattern B — Deferred callback blocks passed to C (`numy == 1` evaluation)

**Locations:**
- `rpart/R/rpartcallback.R`, function `rpartcallback`, line 33

**Original R Context:**

Input: `user.eval` is a user-supplied R function. `yback`, `wback` are numeric vectors of length `nobs` (contents overwritten by C on each call). `nback` is a scalar integer indicating how many elements are valid. `parms` is a list of parameters. `numresp` is an integer.

Return: a numeric vector of length `1 + numresp` (deviance followed by labels).

```r
expr2 <- quote({
    temp <- user.eval(yback[1:nback], wback[1:nback], parms)
    if (length(temp$label) != numresp)
        stop("User 'eval' function returned invalid label")
    if (length(temp$deviance) != 1L)
        stop("User 'eval' function returned invalid deviance")
    as.numeric(as.vector(c(temp$deviance, temp$label)))
})
```

**Python Equivalent:**

Replace the quoted block with a Python callable (closure) that closes over the same state. The C callback mechanism uses `ctypes.CFUNCTYPE` to wrap it.

```python
import numpy as np
import ctypes

def make_eval_callback_univariate(user_eval, parms, numresp, shared_state):
    """
    shared_state is a dict with keys 'yback', 'wback', 'nback'
    whose contents are updated by C on each invocation — mirroring
    the environment `rho` in the R version.
    """
    # Python equivalent of CFUNCTYPE for a callback returning a double array.
    # Adjust the signature to match the actual C interface.
    EVAL_CALLBACK = ctypes.CFUNCTYPE(
        ctypes.POINTER(ctypes.c_double),  # return: pointer to doubles
        ctypes.c_int,                     # argument: nback
    )

    def eval_callback(nback):
        yback = shared_state["yback"]
        wback = shared_state["wback"]

        # Slice to the active portion, matching yback[1:nback] in R
        # (R is 1-indexed and inclusive; Python is 0-indexed exclusive)
        y_active = yback[:nback]
        w_active = wback[:nback]

        result = user_eval(y_active, w_active, parms)

        label = np.asarray(result["label"], dtype=np.float64)
        deviance = np.asarray(result["deviance"], dtype=np.float64)

        if len(label) != numresp:
            raise ValueError("User 'eval' function returned invalid label")
        if deviance.size != 1:
            raise ValueError("User 'eval' function returned invalid deviance")

        # Concatenate deviance and label — equivalent to c(temp$deviance, temp$label)
        output = np.concatenate([deviance.ravel(), label.ravel()])
        return output.astype(np.float64)

    return EVAL_CALLBACK(eval_callback)
```

**Explanation:**

- R's `quote({...})` captures the entire block unevaluated so that C can call `R_tryEval(expr2, rho, &err)` repeatedly. Python has no `eval`-in-environment mechanism that C can invoke the same way. The equivalent is a Python callable registered as a `ctypes` callback.
- `yback[1:nback]` in R uses 1-based inclusive indexing; the Python equivalent is `yback[:nback]` (0-based, exclusive upper bound).
- `as.numeric(as.vector(c(temp$deviance, temp$label)))` flattens and coerces to a plain numeric vector; `np.concatenate([...]).astype(np.float64)` achieves the same.

---

### 4.3 Pattern B — Deferred callback block for `split` (`numy == 1`)

**Locations:**
- `rpart/R/rpartcallback.R`, function `rpartcallback`, line 41

**Original R Context:**

Input: `user.split` is a user-supplied R function. `nback` can be negative (indicating a categorical variable, with `n2 = -nback` being the true count). `xback` is a numeric vector of predictor values. `parms` is a list.

Return: a numeric vector of `c(temp$goodness, temp$direction)`.

```r
expr1 <- quote({
    if (nback < 0L) { # categorical variable
        n2 <- -nback
        temp <- user.split(yback[1L:n2], wback[1L:n2],
                           xback[1L:n2], parms, FALSE)
        ncat <- length(unique(xback[1L:n2]))
        if (length(temp$goodness) != ncat - 1L ||
            length(temp$direction) != ncat)
            stop("Invalid return from categorical 'split' function")
    } else {
        temp <- user.split(yback[1L:nback], wback[1L:nback],
                           xback[1L:nback], parms, TRUE)
        if (length(temp$goodness) != (nback - 1L))
            stop("User 'split' function returned invalid goodness")
        if (length(temp$direction) != (nback - 1L))
            stop("User 'split' function returned invalid direction")
    }
    as.numeric(as.vector(c(temp$goodness, temp$direction)))
})
```

**Python Equivalent:**

```python
import numpy as np
import ctypes

def make_split_callback_univariate(user_split, parms, shared_state):
    """
    shared_state holds 'yback', 'wback', 'xback', 'nback'
    updated by C before each invocation.
    """
    SPLIT_CALLBACK = ctypes.CFUNCTYPE(
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,  # nback (may be negative for categorical)
    )

    def split_callback(nback):
        yback = shared_state["yback"]
        wback = shared_state["wback"]
        xback = shared_state["xback"]

        if nback < 0:
            # Categorical variable: true count is -nback
            n2 = -nback
            y_s = yback[:n2]
            w_s = wback[:n2]
            x_s = xback[:n2]
            result = user_split(y_s, w_s, x_s, parms, False)
            ncat = len(np.unique(x_s))
            if len(result["goodness"]) != ncat - 1 or len(result["direction"]) != ncat:
                raise ValueError("Invalid return from categorical 'split' function")
        else:
            y_s = yback[:nback]
            w_s = wback[:nback]
            x_s = xback[:nback]
            result = user_split(y_s, w_s, x_s, parms, True)
            if len(result["goodness"]) != nback - 1:
                raise ValueError("User 'split' function returned invalid goodness")
            if len(result["direction"]) != nback - 1:
                raise ValueError("User 'split' function returned invalid direction")

        output = np.concatenate([
            np.asarray(result["goodness"], dtype=np.float64).ravel(),
            np.asarray(result["direction"], dtype=np.float64).ravel(),
        ])
        return output

    return SPLIT_CALLBACK(split_callback)
```

**Explanation:**

- The sign of `nback` encodes the variable type. This logic is preserved verbatim in Python.
- R's `FALSE`/`TRUE` boolean literals become Python's `False`/`True`.
- `length(unique(xback[1L:n2]))` becomes `len(np.unique(x_s))`.
- The final `c(temp$goodness, temp$direction)` becomes `np.concatenate([..., ...])`.

---

### 4.4 Pattern B — Deferred callback block for `eval` (`numy > 1`, multivariate response)

**Locations:**
- `rpart/R/rpartcallback.R`, function `rpartcallback`, line 61

**Original R Context:**

Input: `yback` is a numeric vector that is logically a flattened matrix with `numy` columns and `nback` rows. `numy` is an integer column count. All other arguments are as in Pattern B above.

Return: same structure as section 4.2 — a numeric vector of length `1 + numresp`.

```r
expr2 <- quote({
    tempy <- matrix(yback[1L:(nback * numy)], ncol = numy)
    temp <- user.eval(tempy, wback[1L:nback], parms)
    if (length(temp$label) != numresp)
        stop("User 'eval' function returned invalid label")
    if (length(temp$deviance) != 1L)
        stop("User 'eval' function returned invalid deviance")
    as.numeric(as.vector(c(temp$deviance, temp$label)))
})
```

**Python Equivalent:**

```python
import numpy as np
import ctypes

def make_eval_callback_multivariate(user_eval, parms, numresp, numy, shared_state):
    EVAL_CALLBACK = ctypes.CFUNCTYPE(
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
    )

    def eval_callback(nback):
        yback = shared_state["yback"]
        wback = shared_state["wback"]

        # Reshape the flat yback vector into a (nback x numy) matrix.
        # R's matrix(yback[1:(nback*numy)], ncol=numy) fills column-major;
        # numpy default is row-major, so we reshape then transpose.
        y_flat = yback[: nback * numy]
        # R fills columns first (Fortran order), so use order='F' then transpose
        tempy = y_flat.reshape((numy, nback), order='C').T  # shape: (nback, numy)

        w_active = wback[:nback]
        result = user_eval(tempy, w_active, parms)

        label = np.asarray(result["label"], dtype=np.float64)
        deviance = np.asarray(result["deviance"], dtype=np.float64)

        if len(label) != numresp:
            raise ValueError("User 'eval' function returned invalid label")
        if deviance.size != 1:
            raise ValueError("User 'eval' function returned invalid deviance")

        output = np.concatenate([deviance.ravel(), label.ravel()])
        return output.astype(np.float64)

    return EVAL_CALLBACK(eval_callback)
```

**Explanation:**

- `matrix(yback[1L:(nback * numy)], ncol = numy)` in R fills the matrix **column-by-column** (Fortran/column-major order). The result is a matrix with `nback` rows and `numy` columns.
- In NumPy the equivalent reshape is `y_flat.reshape((numy, nback), order='C').T`, which produces an `(nback, numy)` array in the same memory layout.
- Alternatively, `np.reshape(y_flat, (nback, numy), order='F')` achieves the same result with explicit Fortran ordering and is arguably more readable.

---

### 4.5 Pattern B — Deferred callback block for `split` (`numy > 1`, multivariate response)

**Locations:**
- `rpart/R/rpartcallback.R`, function `rpartcallback`, line 70

**Original R Context:**

This is the multivariate variant of section 4.3. The same sign-of-`nback` categorical/continuous branching applies, but `yback` is first reshaped into a matrix before being passed to `user.split`.

```r
expr1 <- quote({
    if (nback < 0L) {
        n2 <- -nback
        tempy <- matrix(yback[1L:(n2 * numy)], ncol = numy)
        temp <- user.split(tempy, wback[1L:n2], xback[1L:n2], parms, FALSE)
        ncat <- length(unique(xback[1L:n2]))
        if (length(temp$goodness) != ncat - 1L ||
            length(temp$direction) != ncat)
            stop("Invalid return from categorical 'split' function")
    } else {
        tempy <- matrix(yback[1L:(nback * numy)], ncol = numy)
        temp <- user.split(tempy, wback[1:nback], xback[1L:nback], parms, TRUE)
        if (length(temp$goodness) != (nback - 1L))
            stop("User 'split' function returned invalid goodness")
        if (length(temp$direction) != (nback - 1L))
            stop("User 'split' function returned invalid direction")
    }
    as.numeric(as.vector(c(temp$goodness, temp$direction)))
})
```

**Python Equivalent:**

```python
import numpy as np
import ctypes

def make_split_callback_multivariate(user_split, parms, numy, shared_state):
    SPLIT_CALLBACK = ctypes.CFUNCTYPE(
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
    )

    def split_callback(nback):
        yback = shared_state["yback"]
        wback = shared_state["wback"]
        xback = shared_state["xback"]

        if nback < 0:
            n2 = -nback
            tempy = np.reshape(yback[: n2 * numy], (n2, numy), order='F')
            w_s = wback[:n2]
            x_s = xback[:n2]
            result = user_split(tempy, w_s, x_s, parms, False)
            ncat = len(np.unique(x_s))
            if len(result["goodness"]) != ncat - 1 or len(result["direction"]) != ncat:
                raise ValueError("Invalid return from categorical 'split' function")
        else:
            tempy = np.reshape(yback[: nback * numy], (nback, numy), order='F')
            w_s = wback[:nback]
            x_s = xback[:nback]
            result = user_split(tempy, w_s, x_s, parms, True)
            if len(result["goodness"]) != nback - 1:
                raise ValueError("User 'split' function returned invalid goodness")
            if len(result["direction"]) != nback - 1:
                raise ValueError("User 'split' function returned invalid direction")

        output = np.concatenate([
            np.asarray(result["goodness"], dtype=np.float64).ravel(),
            np.asarray(result["direction"], dtype=np.float64).ravel(),
        ])
        return output

    return SPLIT_CALLBACK(split_callback)
```

**Explanation:**

- `np.reshape(..., (n, numy), order='F')` is the clearest Python translation of R's column-major `matrix(vec, ncol = numy)`.
- All other translation notes from sections 4.2 and 4.3 apply here unchanged.
- The two branches (categorical vs. continuous) are structurally identical to section 4.3 with the addition of the `tempy` reshape before calling `user.split`.
