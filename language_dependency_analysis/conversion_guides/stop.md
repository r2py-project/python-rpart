# Conversion Guide: `stop` (R to Python)

---

## 1. Overview of `stop` in R

`stop` is a base R function that halts execution of the current expression or function and signals an error condition. It accepts one or more character strings (and optionally a `call.` logical and `domain` argument) which are concatenated to form the error message. Execution is immediately aborted and control is returned to the caller, which by default prints the message prefixed with `Error in <call>:`.

Key signature:

```r
stop(..., call. = TRUE, domain = NULL)
```

- `...`: Character strings (and conditions) that form the error message.
- `call.`: Logical. If `TRUE` (the default), the call to the enclosing function is included in the error message.
- `domain`: For internationalization via `gettext`; set to `NA` to suppress translation.

A common companion is `gettextf(fmt, ...)`, which formats an error string using `sprintf`-style interpolation and passes it to `stop` for internationalized, parameterized messages.

---

## 2. Contextual Usage Analysis

Across the 79 CSV entries, `stop` is used in two structurally distinct patterns throughout the rpart R source files:

**Pattern A — Static message, type/validity guard**
The overwhelming majority of calls pass a fixed string literal directly to `stop`. These fall into several semantic sub-groups:

1. **Object class guard** — checks `inherits(x, "rpart")` and stops if the argument is not a legitimate rpart object. Appears in at least 12 files (`meanvar.rpart.R`, `path.rpart.R`, `plot.rpart.R`, `plotcp.R`, `predict.rpart.R`, `print.rpart.R`, `residuals.rpart.R`, `rsq.rpart.R`, `snip.rpart.R`, `summary.rpart.R`, `text.rpart.R`, `xpred.rpart.R`).
2. **Tree-structure guard** — checks that the fitted object is a non-trivial tree, not just a root node (`plot.rpart.R`, `text.rpart.R`).
3. **Input argument type/value guard** — validates numeric types, formula presence, lengths, sign constraints, method names, and parameter list structure. Found throughout `rpart.R`, `rpart.class.R`, `rpart.control.R`, `rpart.exp.R`, `rpart.poisson.R`, `formatg.R`, `rpartcallback.R`, `pred.rpart.R`, `residuals.rpart.R`, `predict.rpart.R`.
4. **Environment/device-state guard** — checks that a prior call to `plot()` has populated a device-parameter environment; used in `rpart.branch.R`, `rpartco.R`, `snip.rpart.mouse.R`.
5. **User-callback validation** — checks that user-supplied method lists contain the required `init`, `split`, and `eval` functions, and that their return values have valid shapes (`rpartcallback.R`).

**Pattern B — Dynamic message via `gettextf`**
Three call sites construct the error message at runtime by interpolating a variable (an unmatched argument name or parameter component name) into a format string:

```r
stop(gettextf("Argument %s not matched", names(extraArgs)[indx == 0L]), domain = NA)
stop(gettextf("'parms' component not matched: %s", names(parms)[temp == 0L]), domain = NA)
stop(gettextf("'parms' component not matched: %s", names(parms)[indx == 0L]), domain = NA)
```

These appear in `rpart.R` (line 99), `rpart.class.R` (line 20), `rpart.exp.R` (line 116), and `rpart.poisson.R` (line 21).

In all cases the argument to `stop` is a scalar character string (or a single formatted string from `gettextf`). No vectorized behavior is involved — `stop` always raises a single error immediately.

---

## 3. Python Conversion Strategy

Python's built-in exception mechanism is the direct equivalent of R's `stop`. No third-party library is required.

The idiomatic Python approach is to `raise` an exception instance. The most appropriate exception type for the patterns observed is `ValueError` for invalid argument values, types, or structures, and `TypeError` for type mismatches. Where a single generic exception type is preferred across the whole conversion, `ValueError` covers the vast majority of cases faithfully.

For the `gettextf`-based dynamic messages, Python's f-strings or `str.format()` replace the `sprintf`-style interpolation, and the `domain = NA` suppression of translation has no counterpart needed in Python (simply omit it).

There is no Python equivalent needed for `call.` — Python tracebacks already show the call stack automatically.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Object Class Guard

**Locations:** `meanvar.rpart.R::meanvar.rpart` (line 5), `path.rpart.R::path.rpart` (line 6), `plot.rpart.R::plot.rpart` (line 5), `plotcp.R::plotcp` (line 7), `predict.rpart.R::predict.rpart` (line 5), `print.rpart.R::print.rpart` (line 4), `printcp.R::printcp` (line 4), `residuals.rpart.R::residuals.rpart` (line 5), `roc.rpart.R::roc.rpart` (line 6), `rsq.rpart.R::rsq.rpart` (line 7), `snip.rpart.R::snip.rpart` (line 6), `summary.rpart.R::summary.rpart` (line 4), `text.rpart.R::text.rpart` (line 11), `xpred.rpart.R::xpred.rpart` (line 7)

**Original R Context:**

- Input: `tree` or `x` or `object` or `fit` — expected to be an R object of class `"rpart"`. The `inherits` check tests the S3 class attribute.
- Return value of `stop`: does not return; raises an error condition.

```r
# R — parameter: tree is any R object; stops if not of class "rpart"
if (!inherits(tree, "rpart"))
    stop("Not a legitimate \"rpart\" object")
```

**Python Equivalent:**

```python
# Python — fit is expected to be an instance of the RpartTree class (or equivalent dict)
def meanvar_rpart(tree, xlab="ave(y)", ylab="ave(deviance)"):
    if not isinstance(tree, RpartTree):
        raise ValueError('Not a legitimate "rpart" object')
    # ... rest of function
```

**Explanation:**

R's `inherits(x, "rpart")` checks whether the S3 class vector of `x` contains the string `"rpart"`. In Python the equivalent is `isinstance(obj, ClassName)`, where `ClassName` is whatever Python class represents the rpart model object. `raise ValueError(...)` replaces `stop(...)` unconditionally; Python will print the traceback automatically. The escaped double-quotes in the R string become regular double quotes inside a Python single-quoted string.

---

### 4.2 Tree-Structure Guard (non-trivial tree check)

**Locations:** `plot.rpart.R::plot.rpart` (line 6), `text.rpart.R::text.rpart` (line 12)

**Original R Context:**

- Input: `x` — an rpart object whose `$frame` is a data frame; `nrow(x$frame)` returns an integer scalar.
- Return value of `stop`: does not return.

```r
# R — stops if the fit contains only a root node (no splits)
if (nrow(x$frame) <= 1L) stop("fit is not a tree, just a root")
```

**Python Equivalent:**

```python
# Python — frame is a pandas DataFrame or similar structure
def plot_rpart(x, uniform=False, branch=1, compress=False, margin=0, minbranch=0.3):
    if not isinstance(x, RpartTree):
        raise ValueError('Not a legitimate "rpart" object')
    if len(x.frame) <= 1:
        raise ValueError("fit is not a tree, just a root")
    # ... rest of function
```

**Explanation:**

`nrow(x$frame)` in R is replaced by `len(x.frame)` if `frame` is a pandas DataFrame (which returns the number of rows), or `x.frame.shape[0]` for explicit row-count access. The integer suffix `1L` in R is just a literal integer `1` in Python. `raise ValueError(...)` replaces `stop(...)`.

---

### 4.3 Input Type Guard (numeric vector check)

**Locations:** `formatg.R::formatg` (line 6)

**Original R Context:**

- Input: `x` — expected to be a numeric vector or matrix. `is.numeric(x)` returns a scalar logical.
- Return value of `stop`: does not return.

```r
# R — stops if x is not numeric
formatg <- function(x, digits = getOption("digits"),
                    format = paste0("%.", digits, "g"))
{
    if (!is.numeric(x)) stop("'x' must be a numeric vector")
    temp <- sprintf(format, x)
    if (is.matrix(x)) matrix(temp, nrow = nrow(x)) else temp
}
```

**Python Equivalent:**

```python
import numpy as np

def formatg(x, digits=None, fmt=None):
    if digits is None:
        digits = 6  # default analogous to R's getOption("digits")
    if fmt is None:
        fmt = f"%.{digits}g"
    x = np.asarray(x)
    if not np.issubdtype(x.dtype, np.number):
        raise TypeError("'x' must be a numeric vector")
    temp = np.vectorize(lambda v: fmt % v)(x)
    return temp
```

**Explanation:**

R's `is.numeric(x)` is replaced by `np.issubdtype(x.dtype, np.number)` after converting `x` to a NumPy array. `TypeError` is used here because the check is about the data type of the argument, which is more precise than `ValueError`. The `stop` message is preserved verbatim in the exception string.

---

### 4.4 Input Value Guard (scalar/range constraint)

**Locations:** `rpart.R::rpart` (lines 15, 24, 28, 59, 132, 133, 142, 143, 262), `rpart.control.R::rpart.control` (lines 15, 16), `rpart.exp.R::rpart.exp` (lines 21, 22, 122, 127), `rpart.poisson.R::rpart.poisson` (lines 11, 12, 27, 33), `rpart.class.R::rpart.class` (lines 27, 28, 29, 36, 39, 41, 43, 49), `pred.rpart.R::pred.rpart` (line 15), `residuals.rpart.R::residuals.rpart` (line 12), `predict.rpart.R::predict.rpart` (lines 32, 38), `xpred.rpart.R::xpred.rpart` (lines 83, 84)

**Original R Context:**

- Inputs are scalars or vectors of various numeric, logical, or character types. Each guard tests a specific condition and immediately halts if the condition is violated.
- Return value of `stop`: does not return.

```r
# R — representative examples of value/constraint guards
if (indx[1] == 0L) stop("a 'formula' argument is required")
if (any(attr(Terms, "order") > 1L)) stop("Trees cannot handle interaction terms")
if (any(wt < 0)) stop("negative weights not allowed")
if (is.na(method.int)) stop("Invalid method")
if (maxdepth > 30L) stop("Maximum depth is 30")
if (maxdepth < 1L) stop("Maximum depth must be at least 1")
if (length(cost) != nvar) stop("Cost vector is the wrong length")
if (any(cost <= 0)) stop("Cost vector must be positive")
if (any(y[, 1L] <= 0)) stop("Observation time must be > 0")
if (all(status == 0)) stop("No deaths in data set")
if (sum(temp) != 1) stop("Priors must sum to 1")
if (any(temp < 0)) stop("Priors must be >= 0")
if (length(temp) != numclass) stop("Wrong length for priors")
if (length(temp2) != numclass**2) stop("Wrong length for loss matrix")
if (any(diag(temp2) != 0)) stop("Loss matrix must have zero on diagonals")
if (any(temp2 < 0)) stop("Loss matrix cannot have negative elements")
if (any(rowSums(temp2) == 0)) stop("Loss matrix has a row of zeros")
if (any(is.na(vnum))) stop("Tree has variables not found in new data")
if (length(xval) == nobs): ...
else stop("Wrong length for 'xval'")
```

**Python Equivalent:**

```python
import numpy as np

# Formula presence check
if indx[0] == 0:
    raise ValueError("a 'formula' argument is required")

# Interaction terms check
if any(order > 1 for order in attr_terms_order):
    raise ValueError("Trees cannot handle interaction terms")

# Negative weights check (wt is a numpy array)
if np.any(wt < 0):
    raise ValueError("negative weights not allowed")

# Method validity check (method_int is None/NaN when pmatch fails)
if method_int is None:
    raise ValueError("Invalid method")

# Depth bounds
if maxdepth > 30:
    raise ValueError("Maximum depth is 30")
if maxdepth < 1:
    raise ValueError("Maximum depth must be at least 1")

# Cost vector checks (cost and nvar are scalars/arrays)
if len(cost) != nvar:
    raise ValueError("Cost vector is the wrong length")
if np.any(np.array(cost) <= 0):
    raise ValueError("Cost vector must be positive")

# Observation time check (y is a 2D numpy array)
if np.any(y[:, 0] <= 0):
    raise ValueError("Observation time must be > 0")
if np.all(status == 0):
    raise ValueError("No deaths in data set")

# Prior probability checks (temp is a numpy array)
if not np.isclose(np.sum(temp), 1.0):
    raise ValueError("Priors must sum to 1")
if np.any(temp < 0):
    raise ValueError("Priors must be >= 0")
if len(temp) != numclass:
    raise ValueError("Wrong length for priors")

# Loss matrix checks (temp2 is a 2D numpy array)
if temp2.size != numclass ** 2:
    raise ValueError("Wrong length for loss matrix")
if np.any(np.diag(temp2) != 0):
    raise ValueError("Loss matrix must have zero on diagonals")
if np.any(temp2 < 0):
    raise ValueError("Loss matrix cannot have negative elements")
if np.any(temp2.sum(axis=1) == 0):
    raise ValueError("Loss matrix has a row of zeros")

# Missing variable check (vnum is a numpy array with potential NaNs)
if np.any(np.isnan(vnum)):
    raise ValueError("Tree has variables not found in new data")

# xval length check
if len(xval) != nobs:
    raise ValueError("Wrong length for 'xval'")
```

**Explanation:**

Each R `if (...) stop(msg)` maps directly to a Python `if ...: raise ValueError(msg)`. For scalar comparisons the Python syntax is identical; for vector comparisons (`any`, `all` applied to vectors), the R functions `any(...)` and `all(...)` map to `np.any(...)` and `np.all(...)` when the operands are NumPy arrays. R's `sum(temp) != 1` for prior probabilities should use `np.isclose` in Python to avoid floating-point precision issues. R's 1-based column indexing `y[, 1L]` becomes 0-based `y[:, 0]` in Python/NumPy.

---

### 4.5 Named-List/Parameter Structure Guard

**Locations:** `rpart.class.R::rpart.class` (lines 17, 53), `rpart.exp.R::rpart.exp` (line 112), `rpart.poisson.R::rpart.poisson` (line 17)

**Original R Context:**

- Input: `parms` — expected to be a named R list. `is.null(names(parms))` checks whether the list has no names; `else stop("Parameter argument must be a list")` covers the case where `parms` is not a list at all.
- Return value of `stop`: does not return.

```r
# R
if (is.null(names(parms))) stop("The parms list must have names")
# ...
else stop("Parameter argument must be a list")
```

**Python Equivalent:**

```python
# parms is expected to be a dict in Python
if not isinstance(parms, dict):
    raise TypeError("Parameter argument must be a list")
if len(parms) == 0 or all(k is None for k in parms):
    raise ValueError("The parms list must have names")
```

**Explanation:**

R lists with names correspond most naturally to Python `dict` objects. `is.null(names(parms))` in R means the list has no named elements; in Python this maps to checking that the dict is empty or that keys are `None`. The "not a list" branch maps to `not isinstance(parms, dict)` and raises `TypeError` because the issue is the argument's type.

---

### 4.6 Dynamic Message via `gettextf`

**Locations:** `rpart.R::rpart` (line 99), `rpart.class.R::rpart.class` (line 20), `rpart.exp.R::rpart.exp` (line 116), `rpart.poisson.R::rpart.poisson` (line 21)

**Original R Context:**

- `gettextf` constructs a formatted string using `sprintf`-style `%s` placeholders; the result (a character scalar) is passed as the message to `stop`.
- The `domain = NA` argument tells R not to attempt translation.
- Inputs to the format string are character vectors (names of unmatched arguments or parameter components), which may have length > 1 — in R, `paste` would collapse multiple unmatched names into a single string automatically via `gettextf`.

```r
# rpart.R line 99: names(extraArgs)[indx == 0L] is a character vector
stop(gettextf("Argument %s not matched", names(extraArgs)[indx == 0L]),
     domain = NA)

# rpart.class.R line 20 / rpart.exp.R line 116 / rpart.poisson.R line 21:
stop(gettextf("'parms' component not matched: %s",
              names(parms)[temp == 0L]),
     domain = NA)
```

**Python Equivalent:**

```python
# names(extraArgs)[indx == 0] is a list of unmatched argument name strings
unmatched = [name for name, matched in zip(extra_arg_names, indx) if matched == 0]
if unmatched:
    raise ValueError(f"Argument {', '.join(unmatched)} not matched")

# names(parms)[temp == 0] is a list of unmatched parms component names
unmatched_parms = [name for name, matched in zip(parms_names, temp) if matched == 0]
if unmatched_parms:
    raise ValueError(f"'parms' component not matched: {', '.join(unmatched_parms)}")
```

**Explanation:**

R's `gettextf("format %s", value)` is replaced by a Python f-string. In R, when the `%s` value is a character vector of length > 1, only the first element is substituted (standard `sprintf` behaviour); if multiple unmatched names are expected, they should be collapsed with `paste(..., collapse = ", ")` before passing. In Python, `', '.join(list)` explicitly handles the same collapsing. The `domain = NA` argument is dropped entirely as Python has no equivalent translation-domain suppression needed here.

---

### 4.7 Device/Environment State Guard

**Locations:** `rpart.branch.R::rpart.branch` (line 10), `rpartco.R::rpartco` (line 7), `snip.rpart.mouse.R::snip.rpart.mouse` (line 9)

**Original R Context:**

- These functions check whether a plot has been previously called (and stored parameters in a per-device environment `rpart_env`). If no prior plot exists for the current device, execution stops.
- Input: side-effect check against a global/package-level environment.
- Return value of `stop`: does not return.

```r
# R
pn <- paste0("device", dev.cur())
if (!exists(pn, envir = rpart_env, inherits = FALSE))
    stop("no information available on parameters from previous call to plot()")
parms <- get(pn, envir = rpart_env, inherits = FALSE)
```

**Python Equivalent:**

```python
# rpart_env is a module-level dict mapping device_id -> parms
device_key = f"device{dev_cur()}"
if device_key not in rpart_env:
    raise RuntimeError(
        "no information available on parameters from previous call to plot()"
    )
parms = rpart_env[device_key]
```

**Explanation:**

R's package-level environment `rpart_env` used with `exists` and `get` maps to a Python module-level `dict`. The `exists(..., envir = rpart_env)` check becomes a `key in dict` membership test. `RuntimeError` is used here rather than `ValueError` because the issue is a missing prerequisite state (a prior `plot()` call), not an invalid argument value. `dev.cur()` would be replaced by whatever Python graphics backend function returns the current device/figure identifier.

---

### 4.8 User-Callback Validation

**Locations:** `rpartcallback.R::rpartcallback` (lines 7, 9, 11, 13, 36, 38, 49, 54, 56, 65, 67, 79, 85, 87)

**Original R Context:**

- `mlist` is a user-supplied list of functions. The code checks structural requirements (minimum 3 elements, presence of `init`, `split`, `eval` functions) and runtime return value shapes (lengths of `label`, `deviance`, `goodness`, `direction` fields).
- Inputs are R lists and function objects; lengths and types are checked.
- Return value of `stop`: does not return.

```r
# R — structural checks
if (length(mlist) < 3L)
    stop("User written methods must have 3 functions")
if (!is.function(mlist$init))
    stop("User written method does not contain an 'init' function")
if (!is.function(mlist$split))
    stop("User written method does not contain a 'split' function")
if (!is.function(mlist$eval))
    stop("User written method does not contain an 'eval' function")

# R — runtime return-value checks (inside quoted expressions)
if (length(temp$label) != numresp)
    stop("User 'eval' function returned invalid label")
if (length(temp$deviance) != 1L)
    stop("User 'eval' function returned invalid deviance")
if (length(temp$goodness) != ncat - 1L || length(temp$direction) != ncat)
    stop("Invalid return from categorical 'split' function")
if (length(temp$goodness) != (nback - 1L))
    stop("User 'split' function returned invalid goodness")
if (length(temp$direction) != (nback - 1L))
    stop("User 'split' function returned invalid direction")
```

**Python Equivalent:**

```python
import callable as _callable  # callable is a Python builtin

def rpartcallback(mlist, nobs, init):
    # mlist is a dict with keys 'init', 'split', 'eval' (and optionally others)
    if len(mlist) < 3:
        raise ValueError("User written methods must have 3 functions")
    if not callable(mlist.get("init")):
        raise ValueError("User written method does not contain an 'init' function")
    if not callable(mlist.get("split")):
        raise ValueError("User written method does not contain a 'split' function")
    if not callable(mlist.get("eval")):
        raise ValueError("User written method does not contain an 'eval' function")

    # ... setup ...

    # Runtime return-value checks (within callback/evaluation logic)
    def check_eval_result(temp, numresp):
        if len(temp["label"]) != numresp:
            raise ValueError("User 'eval' function returned invalid label")
        if not hasattr(temp["deviance"], "__len__") or len(temp["deviance"]) != 1:
            raise ValueError("User 'eval' function returned invalid deviance")

    def check_split_result_categorical(temp, ncat):
        if len(temp["goodness"]) != ncat - 1 or len(temp["direction"]) != ncat:
            raise ValueError("Invalid return from categorical 'split' function")

    def check_split_result_continuous(temp, nback):
        if len(temp["goodness"]) != nback - 1:
            raise ValueError("User 'split' function returned invalid goodness")
        if len(temp["direction"]) != nback - 1:
            raise ValueError("User 'split' function returned invalid direction")
```

**Explanation:**

R's `is.function(x)` maps to Python's built-in `callable(x)`. R's `length(x)` on a list or vector maps to Python's `len(x)` for sequences. The `mlist$init` member access maps to `mlist.get("init")` on a Python dict (or `mlist["init"]` if the key is guaranteed present). R lists with named elements map to Python dicts. The integer literal suffix `1L` is simply `1` in Python. `raise ValueError(...)` replaces all `stop(...)` calls.
