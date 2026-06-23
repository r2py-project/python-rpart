# Conversion Guide: `match.arg` in R

---

## 1. Overview of `match.arg` in R

`match.arg(arg, choices, several.ok = FALSE)` is an R utility function used exclusively inside function bodies to validate and resolve a formal argument against a set of allowed string values.

When a function parameter is declared with a character vector default such as `type = c("vector", "prob", "class", "matrix")`, calling `match.arg(type)` at the start of the function body does two things:

1. **Partial matching:** If the caller supplies an abbreviated string (e.g. `"v"` for `"vector"`), `match.arg` resolves it to the full canonical value, as long as the prefix is unambiguous.
2. **Validation:** If the supplied value does not match any allowed choice (even after partial matching), `match.arg` raises an error automatically.

When called with only the argument variable and no explicit `choices` vector, `match.arg` introspects the function's own formal argument list to discover the allowed choices from the default value expression. The return value is a single scalar character string (the resolved, canonical choice), unless `several.ok = TRUE` is passed, which allows returning a character vector of multiple resolved values.

Key properties:
- Input: a scalar character string (the argument value as supplied by the caller, or the full default character vector if the argument was not supplied by the caller).
- Output: a single scalar character string containing the first matching (or only unambiguous) canonical choice.
- Side effect on error: calls `stop()` with an informative message listing valid choices.

---

## 2. Contextual Usage Analysis

All three occurrences in the rpart codebase follow the same idiomatic single-argument form `match.arg(<param>)`, where `<param>` is a function parameter declared with a character vector default. This is the most common R pattern for enumerated string arguments.

**`plotcp.R`, function `plotcp`, line 8:**
The parameter is `upper = c("size", "splits", "none")`. After `match.arg`, `upper` holds exactly one of those three strings and is immediately consumed by a `switch(upper, ...)` statement that controls which axis label style is drawn.

**`predict.rpart.R`, function `predict.rpart`, line 8:**
The parameter is `type = c("vector", "prob", "class", "matrix")`. After `match.arg`, `type` holds exactly one of those four strings. Downstream `if`/`else if` branches dispatch on this value to select the prediction format. Note that a `missing(type)` flag is captured before `match.arg` so that the default can be overridden later based on the model type.

**`residuals.rpart.R`, function `residuals.rpart`, line 10:**
The parameter is `type = c("usual", "pearson", "deviance")`. After `match.arg`, `type` holds one of those three strings and a redundant manual `match` check follows it (a defensive pattern). Downstream `switch` statements dispatch on this value to compute different residual formulas.

Recurring patterns:
- All usages are single-argument calls; no explicit `choices` vector is passed.
- The resolved value is always used immediately afterwards in a `switch` or `if`/`else if` dispatch.
- All allowed choices are plain ASCII lowercase strings with no ambiguous prefixes within the same set.

---

## 3. Python Conversion Strategy

Python has no built-in equivalent to `match.arg`, but the behaviour can be replicated cleanly using a small inline validation pattern. The two equivalent approaches are:

**Option A — Inline validation with `ValueError`** (recommended for direct translation): Accept the argument as a plain string with a documented default, validate it against a tuple of allowed values, and raise a `ValueError` if it is not found. This matches what `match.arg` does internally.

**Option B — Enum** (`enum.Enum`): Define an `Enum` for each parameter. This provides type-safety and IDE autocompletion but adds more boilerplate and changes the calling convention, making it a heavier translation than needed for a direct port.

Option A is chosen here because:
- It preserves the same calling convention (callers pass plain strings).
- The allowed-choices sets in rpart are small and stable.
- It requires no additional imports beyond the Python standard library.
- Partial matching is not idiomatic in Python; callers are expected to supply exact strings.

Note: R's `match.arg` supports partial matching (e.g., `"v"` resolves to `"vector"`). If the Python port must support partial matching for backward compatibility, the `difflib.get_close_matches` function from the standard library can be used to replicate it, as shown in the advanced example below.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 `plotcp` — Resolving `upper` against `("size", "splits", "none")`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/plotcp.R`, function `plotcp`

**Original R Context:**

- `upper` is a character scalar (or the full default vector if the caller omits the argument).
- `match.arg(upper)` resolves it to one of `"size"`, `"splits"`, or `"none"`.
- The result is consumed by `switch(upper, size = {...}, splits = {...})`.

```r
plotcp <- function(x, minline = TRUE, lty = 3, col = 1,
                   upper = c("size", "splits", "none"), ...)
{
    upper <- match.arg(upper)
    # ... later ...
    switch(upper,
           size   = { axis(3L, ...); mtext("size of tree", ...) },
           splits = { axis(3L, ...); mtext("number of splits", ...) })
}
```

**Python Equivalent:**

```python
def plotcp(x, minline=True, lty=3, col=1, upper="size", **kwargs):
    _UPPER_CHOICES = ("size", "splits", "none")
    if upper not in _UPPER_CHOICES:
        raise ValueError(
            f"'upper' must be one of {_UPPER_CHOICES!r}; got {upper!r}"
        )

    # ... later ...
    if upper == "size":
        # axis(3, ...), label with nsplit + 1
        pass
    elif upper == "splits":
        # axis(3, ...), label with nsplit
        pass
```

**Explanation:**
- R's character-vector default `upper = c("size", "splits", "none")` becomes a plain string default `upper="size"` in Python (using the first element, which is the R default when the caller omits the argument).
- The `if upper not in _UPPER_CHOICES` guard replaces `match.arg`'s validation.
- R's `switch(upper, ...)` maps directly to Python `if`/`elif` branches.
- Partial matching is not replicated here because it is not idiomatic in Python; callers must pass the exact string.

---

### 4.2 `predict.rpart` — Resolving `type` against `("vector", "prob", "class", "matrix")`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/predict.rpart.R`, function `predict.rpart`

**Original R Context:**

- `type` is a character scalar or the default vector.
- `mtype = missing(type)` is captured before validation so the default can be overridden later if the model is a classifier (`nclass > 0`).
- `match.arg(type)` resolves it to one of `"vector"`, `"prob"`, `"class"`, or `"matrix"`.
- The result drives `if`/`else if` dispatch selecting the prediction output format.

```r
predict.rpart <- function(object, newdata,
     type = c("vector", "prob", "class", "matrix"),
     na.action = na.pass, ...)
{
    mtype <- missing(type)
    type  <- match.arg(type)
    # ...
    if (mtype && nclass > 0L) type <- "prob"
    if (type == "vector" || ...) { ... }
    else if (type == "matrix")   { ... }
    else if (type == "class")    { ... }
    else if (type == "prob")     { ... }
    else stop("Invalid prediction for \"rpart\" object")
}
```

**Python Equivalent:**

```python
_PREDICT_TYPE_CHOICES = ("vector", "prob", "class", "matrix")
_SENTINEL = object()  # sentinel to detect "caller did not supply type"

def predict_rpart(object, newdata=None,
                  type=_SENTINEL, na_action=None, **kwargs):
    type_missing = type is _SENTINEL
    if type is _SENTINEL:
        type = "vector"  # first element of the R default vector

    if type not in _PREDICT_TYPE_CHOICES:
        raise ValueError(
            f"'type' must be one of {_PREDICT_TYPE_CHOICES!r}; got {type!r}"
        )

    # ... compute nclass, where, frame ...

    if type_missing and nclass > 0:
        type = "prob"

    if type == "vector" or (type == "matrix" and frame_yval2 is None):
        pass  # pred = frame["yval"][where]
    elif type == "matrix":
        pass  # pred = frame["yval2"][where, :]
    elif type == "class" and nclass > 0:
        pass  # pred = factor lookup
    elif type == "prob" and nclass > 0:
        pass  # pred = probability matrix
    else:
        raise ValueError('Invalid prediction for "rpart" object')
```

**Explanation:**
- R's `missing(type)` sentinel is reproduced using a module-level `_SENTINEL = object()` and comparing `type is _SENTINEL`. This is the standard Python idiom for detecting whether a caller supplied an argument.
- The default value assigned when no argument is supplied is `"vector"`, the first element of R's default character vector (R's convention is that the first element is the default when the argument is not provided by the caller).
- The `if type not in _PREDICT_TYPE_CHOICES` guard replaces `match.arg`'s error.
- The downstream `if`/`elif` chain is a direct translation of R's `if`/`else if` dispatch.

---

### 4.3 `residuals.rpart` — Resolving `type` against `("usual", "pearson", "deviance")`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/residuals.rpart.R`, function `residuals.rpart`

**Original R Context:**

- `type` is a character scalar or the default vector.
- `match.arg(type)` resolves it to one of `"usual"`, `"pearson"`, or `"deviance"`.
- A redundant `is.na(match(type, c(...)))` check follows (defensive code that will never trigger after `match.arg`, but should be dropped in Python).
- The resolved value drives `switch(type, ...)` blocks inside both a `class` and a `poisson`/`exp` branch.

```r
residuals.rpart <- function(object,
    type = c("usual", "pearson", "deviance"), ...)
{
    type <- match.arg(type)
    if (is.na(match(type, c("usual", "pearson", "deviance"))))
        stop("Invalid type of residual")   # dead code after match.arg
    # ...
    switch(type,
           usual    = loss[cbind(y, yhat)],
           pearson  = (1 - yhat)/yhat,
           deviance = -2 * log(yhat))
}
```

**Python Equivalent:**

```python
import numpy as np

_RESID_TYPE_CHOICES = ("usual", "pearson", "deviance")

def residuals_rpart(object, type="usual", **kwargs):
    if type not in _RESID_TYPE_CHOICES:
        raise ValueError(
            f"'type' must be one of {_RESID_TYPE_CHOICES!r}; got {type!r}"
        )
    # The redundant is.na(match(...)) check is omitted; the guard above suffices.

    # ... extract y, frame, method ...

    if object_method == "class":
        ylevels = object["ylevels"]
        nclass  = len(ylevels)
        if type == "usual":
            yhat = frame["yval"][where]
            loss = object["parms"]["loss"]
            resid = loss[y, yhat]
        elif type == "pearson":
            yprob = frame["yval2"][where, nclass + 1: 2 * nclass + 1]
            yhat  = yprob[np.arange(len(y)), y.astype(int)]
            resid = (1 - yhat) / yhat
        elif type == "deviance":
            yprob = frame["yval2"][where, nclass + 1: 2 * nclass + 1]
            yhat  = yprob[np.arange(len(y)), y.astype(int)]
            resid = -2 * np.log(yhat)

    elif object_method in ("poisson", "exp"):
        lam    = frame["yval"][where]
        time   = y[:, 0]
        events = y[:, 1]
        expect = lam * time
        temp   = np.where(expect == 0, 0.0001, expect)
        if type == "usual":
            resid = events - expect
        elif type == "pearson":
            resid = (events - expect) / np.sqrt(temp)
        elif type == "deviance":
            resid = np.sign(events - expect) * np.sqrt(
                2 * (events * np.log(events / temp) - (events - expect))
            )
    else:
        resid = y - frame["yval"][where]

    return resid
```

**Explanation:**
- The `match.arg` call is replaced by the same `if type not in _RESID_TYPE_CHOICES` guard. The downstream redundant `is.na(match(...))` check present in the R source is omitted entirely because it is unreachable after a successful `match.arg` and serves no purpose in Python.
- `numpy` is used for vectorized array operations (`np.log`, `np.sqrt`, `np.sign`, `np.where`) because `y`, `expect`, `yhat`, and `resid` are all arrays over the observations, not scalars.
- R's `switch(type, usual = ..., pearson = ..., deviance = ...)` maps to Python `if`/`elif` branches.
- R's zero-indexed column slicing of `yval2` is adjusted for Python's zero-based indexing.

---

### 4.4 Advanced: Replicating R's Partial Matching (Optional)

If the Python port must accept abbreviated strings the way R does (e.g., `"u"` for `"usual"`), use `difflib.get_close_matches` with a cutoff of `0` to implement unambiguous prefix matching:

```python
from difflib import get_close_matches

def _match_arg(value, choices):
    """Replicate R's match.arg partial-matching behaviour."""
    if value in choices:
        return value
    # Try prefix match
    prefix_matches = [c for c in choices if c.startswith(value)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise ValueError(
            f"'arg' should be one of {choices!r}; "
            f"{value!r} is ambiguous (matches {prefix_matches!r})"
        )
    raise ValueError(
        f"'arg' should be one of {choices!r}; got {value!r}"
    )

# Usage:
type = _match_arg(type, ("usual", "pearson", "deviance"))
```

This helper can be placed in a shared utility module and reused across all converted functions that originally called `match.arg`.
