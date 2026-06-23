# Conversion Guide: `model.extract` (R to Python)

---

## 1. Overview of `model.extract` in R

`model.extract` is a base R function from the `stats` package with the signature:

```r
model.extract(frame, component)
```

It retrieves a named component that was stored inside a **model frame** — the structured data object produced by `model.frame()`. A model frame is essentially a data frame whose columns carry special attributes. The most commonly extracted components are:

- `"response"` — the dependent variable (the left-hand side of the formula, stored under the attribute name `"(response)"` or accessed as the first column).
- `"weights"` — per-observation weights passed via the `weights` argument to `model.frame()` or `lm()`/`rpart()`, stored under the column name `"(weights)"`.
- `"offset"` — an offset term.
- `"subset"`, `"etastart"`, `"mustart"`, and other optional components.

The function returns the extracted component as a vector (or matrix, depending on the response type), or `NULL` if the component is absent. R's documentation notes that `model.extract` exists primarily for S compatibility; the dedicated wrappers `model.response()` and `model.weights()` are the modern preferred alternatives for the two components encountered in this guide.

---

## 2. Contextual Usage Analysis

Three call sites appear in the CSV, spread across two files:

| File | Function | Line | Component extracted |
|------|----------|------|---------------------|
| `residuals.rpart.R` | `residuals.rpart` | 8 | `"response"` |
| `xpred.rpart.R` | `xpred.rpart` | 28 | `"weights"` |
| `xpred.rpart.R` | `xpred.rpart` | 31 | `"response"` |

**Pattern in `residuals.rpart.R` (line 8):**

```r
y <- object$y
if (is.null(y)) y <- model.extract(model.frame(object), "response")
```

`object$y` is the cached response vector stored on a fitted `rpart` object. When it is `NULL` (because the model was fitted without caching `y`), the response is reconstructed on the fly by re-running `model.frame(object)` and extracting the `"response"` component. The result `y` is used later as the ground-truth labels for residual computation. It can be a plain numeric vector (anova/regression), a factor-coded integer vector (classification), or a two-column matrix of `(time, events)` (survival/poisson).

**Pattern in `xpred.rpart.R` (lines 28 and 31):**

```r
if (is.null(wt)) wt <- model.extract(m, "weights")
if (is.null(Y)) {
    yflag <- TRUE
    Y <- model.extract(m, "response")
    ...
}
```

Here, `m` is an already-constructed model frame (either cached in `fit$model` or rebuilt from `fit$call`). Both extractions guard against `NULL` — weights default to a uniform vector of ones if absent (line 50: `if (length(wt) == 0) wt <- rep(1, nobs)`), and the response `Y` can again be a vector or a two-column matrix depending on the rpart method. Downstream, `Y` is passed directly to C code, so both numeric fidelity and shape must be preserved.

**Recurring patterns:**
- The model frame `m` is always a pandas-equivalent structured table with special named columns.
- Both components may legitimately be absent (`NULL`), so null-checking is part of the idiom.
- The `"response"` component can be 1-D or 2-D; the Python equivalent must handle both shapes.
- The `"weights"` component is always 1-D.

---

## 3. Python Conversion Strategy

The Python rpart port does not use R's `model.frame` machinery. Instead, the fitted model object stores pre-parsed data directly on the Python equivalent of the rpart object (e.g., `fit.y`, `fit.wt`, `fit.x`). The `model.frame` + `model.extract` pattern is therefore translated as **direct attribute access with a fallback**, mirroring the null-guard logic already present in the R source.

No external library is needed to replicate `model.extract` itself. However:

- **`numpy`** is used for array manipulation when the response is a 2-D matrix (survival/poisson case).
- **`pandas`** DataFrames serve as the Python analogue of R model frames if a model-frame concept is ever retained in Python.

The chosen strategy is:

1. Access the pre-stored attribute directly (`fit.y`, `fit.wt`).
2. If absent (`None`), retrieve the component from the model data structure via a helper that mirrors `model.extract`.
3. For the `"response"` component, preserve the NumPy array shape (1-D vector or 2-D matrix).
4. For the `"weights"` component, return a 1-D NumPy array, defaulting to `np.ones(n)` when absent.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Extracting the Response — `residuals.rpart`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/residuals.rpart.R`, function `residuals.rpart`, line 8.

**Original R Context:**

- Input: `object` is a fitted `rpart` object. `object$y` may be `NULL`.
- `model.frame(object)` reconstructs the model frame from the original call.
- `model.extract(..., "response")` returns the response column — a numeric vector or a 2-column numeric matrix, depending on the rpart method.
- Return type: numeric vector or numeric matrix.

```r
# Generalized R snippet
y <- object$y
if (is.null(y)) y <- model.extract(model.frame(object), "response")
```

**Python Equivalent:**

```python
import numpy as np

def _extract_response(fit, model_frame=None):
    """
    Retrieve the response array from a fitted rpart-like object.
    Mirrors: model.extract(model.frame(object), "response")

    Parameters
    ----------
    fit : object
        Fitted rpart model. Expected to have a `.y` attribute (np.ndarray or None).
    model_frame : dict or None
        Pre-built model frame (Python equivalent of R's model.frame result).
        Keys are component names; "(response)" holds the response array.

    Returns
    -------
    np.ndarray
        1-D array for regression/classification, shape (n,).
        2-D array for survival/poisson, shape (n, 2).
    """
    y = getattr(fit, "y", None)
    if y is None:
        if model_frame is None:
            raise ValueError("Response is not cached and no model_frame was provided.")
        y = model_frame.get("(response)")
        if y is None:
            raise ValueError("Model frame does not contain a '(response)' component.")
        y = np.asarray(y)
    return y


# Usage in residuals_rpart equivalent
y = getattr(object, "y", None)
if y is None:
    mf = _build_model_frame(object)   # project-specific helper
    y = _extract_response(object, model_frame=mf)
```

**Explanation:**

- R's `object$y` maps to `getattr(fit, "y", None)` in Python.
- R's model frame stores the response under the column name `"(response)"` (with parentheses). In a Python dict or DataFrame, this same key is used.
- `np.asarray()` ensures the result is always a NumPy array, preserving the 2-D shape for survival/poisson responses.
- The null guard (`if y is None`) directly mirrors R's `if (is.null(y))`.

---

### 4.2 Extracting Weights — `xpred.rpart`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`, function `xpred.rpart`, line 28.

**Original R Context:**

- Input: `m` is an R model frame (a data frame with special columns). `wt` may be `NULL`.
- `model.extract(m, "weights")` returns the `"(weights)"` column as a numeric vector, or `NULL` if no weights were specified.
- The caller later replaces a zero-length result with `rep(1, nobs)`.
- Return type: numeric vector of length `n`, or `NULL`.

```r
# Generalized R snippet
wt <- fit$wt
if (is.null(wt)) wt <- model.extract(m, "weights")
if (length(wt) == 0) wt <- rep(1, nobs)
```

**Python Equivalent:**

```python
import numpy as np

def _extract_weights(fit, model_frame, n_obs):
    """
    Retrieve observation weights from a fitted rpart-like object or model frame.
    Mirrors: model.extract(m, "weights"), with the downstream default of rep(1, nobs).

    Parameters
    ----------
    fit : object
        Fitted rpart model. Expected to have a `.wt` attribute (np.ndarray or None).
    model_frame : dict or None
        Pre-built model frame. Key "(weights)" holds the weights array if present.
    n_obs : int
        Number of observations; used to construct the default uniform weight vector.

    Returns
    -------
    np.ndarray
        1-D float64 array of length n_obs.
    """
    wt = getattr(fit, "wt", None)
    if wt is None and model_frame is not None:
        wt = model_frame.get("(weights)")
        if wt is not None:
            wt = np.asarray(wt, dtype=np.float64)
    # Replicate R's: if (length(wt) == 0) wt <- rep(1, nobs)
    if wt is None or len(wt) == 0:
        wt = np.ones(n_obs, dtype=np.float64)
    return wt


# Usage in xpred_rpart equivalent
wt = getattr(fit, "wt", None)
if wt is None:
    wt = _extract_weights(fit, model_frame=m, n_obs=n_obs)
```

**Explanation:**

- R's `"(weights)"` column name maps directly to the `"(weights)"` key in a Python model-frame dict or DataFrame.
- `np.ones(n_obs, dtype=np.float64)` replicates R's `rep(1, nobs)` — a uniform weight vector.
- The `dtype=np.float64` matches R's `storage.mode(wt) <- "double"` coercion that occurs at line 116 of `xpred.rpart.R` before the `.Call` to C code.
- A zero-length array (`len(wt) == 0`) is treated identically to `None`, matching R's `length(wt) == 0` check.

---

### 4.3 Extracting the Response — `xpred.rpart`

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`, function `xpred.rpart`, line 31.

**Original R Context:**

- Same model frame `m` as in 4.2.
- `model.extract(m, "response")` retrieves the raw response before any rpart method-specific transformation.
- After extraction, the response is passed to an `init` function (e.g., `rpart.anova`, `rpart.poisson`, `rpart.class`) that may transform `Y` and return `init$y`.
- Return type: numeric vector or 2-column numeric matrix.

```r
# Generalized R snippet
Y <- fit$y
if (is.null(Y)) {
    yflag <- TRUE
    Y <- model.extract(m, "response")
    offset <- attr(Terms, "offset")
    if (method != "user") {
        init <- get(paste("rpart", method, sep = "."))(Y, offset, NULL)
        Y <- init$y
        numy <- if (is.matrix(Y)) ncol(Y) else 1L
    }
}
```

**Python Equivalent:**

```python
import numpy as np

# Assumed available: method-specific init functions in a dispatch dict
RPART_INIT_FUNCTIONS = {
    "anova":   rpart_anova_init,
    "poisson": rpart_poisson_init,
    "class":   rpart_class_init,
    "exp":     rpart_poisson_init,  # "exp" maps to poisson (line 11 of xpred.rpart.R)
}

def _extract_and_init_response(fit, model_frame, terms, method):
    """
    Retrieve and optionally transform the response, mirroring the R block:
        Y <- model.extract(m, "response")
        init <- rpart.<method>(Y, offset, NULL)
        Y <- init$y

    Parameters
    ----------
    fit : object
        Fitted rpart model with optional `.y` attribute.
    model_frame : dict
        Pre-built model frame. Key "(response)" holds the raw response.
    terms : object
        Model terms object; `.offset` attribute gives the offset column index or None.
    method : str
        One of "anova", "poisson", "class", "exp", "user".

    Returns
    -------
    Y : np.ndarray
        Possibly transformed response; 1-D or 2-D depending on method.
    numy : int
        Number of response columns (1 for vectors, ncol for matrices).
    yflag : bool
        True when Y was freshly extracted (not cached), signalling that init was called.
    """
    Y = getattr(fit, "y", None)
    if Y is not None:
        yflag = False
        numy = Y.shape[1] if Y.ndim == 2 else 1
        return Y, numy, yflag

    yflag = True
    raw_y = model_frame.get("(response)")
    if raw_y is None:
        raise ValueError("Model frame does not contain a '(response)' component.")
    Y = np.asarray(raw_y)

    offset = getattr(terms, "offset", None)

    if method != "user":
        init_fn = RPART_INIT_FUNCTIONS[method]
        init = init_fn(Y, offset, parms=None)
        Y = init["y"]

    numy = Y.shape[1] if Y.ndim == 2 else 1
    return Y, numy, yflag


# Usage in xpred_rpart equivalent
Y, numy, yflag = _extract_and_init_response(fit, model_frame=m, terms=Terms, method=method)
```

**Explanation:**

- The `yflag` boolean directly mirrors R's `yflag <- TRUE/FALSE`, used later to decide whether to call `init` again for `method == "user"`.
- `"exp"` is remapped to `"poisson"` in the Python dispatch dict, matching R's `if (method.int == 5L) method.int <- 2L` on line 11 of `xpred.rpart.R`.
- `numy = Y.shape[1] if Y.ndim == 2 else 1` directly translates R's `numy <- if (is.matrix(Y)) ncol(Y) else 1L`.
- The `offset` is retrieved from the `terms` object rather than from `attr(Terms, "offset")`, as Python model terms objects store this as an attribute.
- `np.asarray()` is used without forcing a dtype here because the type coercion (`storage.mode(Y) <- "double"`) happens later in the R code (line 114), and the Python equivalent of that coercion (`Y.astype(np.float64)`) should similarly be deferred to the point just before the C call.
