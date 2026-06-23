# Conversion Guide: `naresid` (R to Python)

---

## 1. Overview of `naresid` in R

`naresid` is a generic function in R's `stats` package whose single purpose is to **reinsert NA placeholders** into a vector, named vector, matrix, or data frame at the positions that were originally excluded due to missing values during model fitting.

When a model is fitted and the data contains `NA` rows, R's missing-value handler (typically `na.omit` or `na.exclude`) removes those rows before fitting and records the indices of the removed rows as a named integer vector. That integer vector is stored as the `"na.action"` attribute on the fitted model object, and its class (`"omit"` or `"exclude"`) determines the behavior of `naresid`.

**Signature:**
```r
naresid(omit, x, ...)
```

| Argument | Type | Description |
|---|---|---|
| `omit` | named integer vector with class `"omit"` or `"exclude"` | The `na.action` attribute from the fitted model, recording which original row indices were dropped |
| `x` | vector, matrix, or data frame | The compact result (predictions or residuals) computed over only the non-missing training rows |

**Return value:** An object of the same type as `x` but expanded to the original full-data length, with `NA` values inserted at every position identified in `omit`.

**Method dispatch:**

| Class of `omit` | Behavior |
|---|---|
| `"exclude"` | Expands `x` to original length, inserting `NA` at excluded positions. This is the active path used by `na.exclude`. |
| `"omit"` | Returns `x` unchanged (no expansion). `na.omit` already drops rows permanently. |
| default | Returns `x` unchanged. |

The critical distinction is that `na.exclude` is designed for prediction and residual workflows: it promises that the output will be aligned row-for-row with the original data frame, including rows that had missing values (which receive `NA` output). `na.omit` makes no such promise.

In the rpart package, `object$na.action` is `NULL` when no rows were excluded, so both call sites guard with `!is.null(object$na.action)` or a `missing(newdata)` check before invoking `naresid`.

---

## 2. Contextual Usage Analysis

Both usages follow the same structural pattern: a compact result array is computed over the training rows only, then `naresid` is called to expand it back to the original data length.

**Call site 1 — `predict.rpart.R`, line 43:**
- `pred` may be a named numeric vector (`type = "vector"`), a named factor (`type = "class"`), or a named numeric matrix with one row per observation (`type = "prob"` or `type = "matrix"`).
- `naresid` is called only when `newdata` is absent, meaning the caller is predicting on the original training data. The guard condition is `missing(newdata) && !is.null(object$na.action)`.
- The result of `naresid` is returned directly as the final prediction output.

**Call site 2 — `residuals.rpart.R`, line 47:**
- `resid` is always a named numeric vector (one residual per training observation). Its names are set to `names(y)` immediately before the call, where `y` is the response variable extracted from the fitted model.
- The guard is `!is.null(object$na.action)`, with `naresid` called unconditionally when `na.action` is present, and `resid` returned unchanged when it is absent.
- The same one-argument form of the ternary-like expression is used: `if (...) naresid(...) else resid`.

**Recurring pattern across both sites:**
- The `omit` argument is always `object$na.action` — the stored missing-value metadata from model fitting.
- The `x` argument is always the dense result (predictions or residuals) indexed by the training rows, which is shorter than the original data by exactly the number of excluded rows.
- The return value replaces `pred` or `resid` directly and is passed back to the caller, maintaining length alignment with the original input data.

---

## 3. Python Conversion Strategy

R's `naresid` is not a numerical function — it is a **bookkeeping / indexing utility** for restoring structural alignment after NA-row removal. The appropriate Python translation uses **`numpy`** for the array operations and **`pandas`** when named indices (equivalent to R's `names()`) need to be preserved.

The conversion strategy is:

1. Store the excluded row indices at model-fitting time (the Python equivalent of `object$na.action`).
2. After computing the compact prediction or residual array, allocate a full-length output array filled with `np.nan`.
3. Write the compact values into the non-excluded positions using NumPy integer-array indexing.

This exactly mirrors the `naresid.exclude` implementation in R's source, which:
- Allocates a full-length NA placeholder,
- Determines the "kept" indices as the complement of the omitted indices within `1:n`,
- Assigns `x` into those kept positions.

`numpy` is preferred over `math` because both `pred` and `resid` are array-like objects (vectors or matrices), and `numpy` natively handles both 1-D and 2-D expansion in a single, uniform idiom.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Usage in `predict.rpart` — Expanding Predictions

**Locations:** `rpart/R/predict.rpart.R`, function `predict.rpart`, line 43.

**Original R Context:**

```r
# pred is one of:
#   - a named numeric vector  (type = "vector" or "class")
#   - a named numeric matrix  (type = "prob" or "matrix"), shape (n_train, n_class)
# object$na.action is a named integer vector of class "exclude" or NULL

if (missing(newdata) && !is.null(object$na.action))
    pred <- naresid(object$na.action, pred)
pred
```

Input types:
- `object$na.action`: integer vector whose values are the 1-based row indices that were excluded, and whose class is `"omit"` or `"exclude"`.
- `pred`: numeric vector of length `n_train`, or numeric matrix of shape `(n_train, n_class)`.

Return type: same structure as `pred` but length/rows expanded to `n_original`, with `np.nan` at every excluded position.

**Python Equivalent:**

```python
import numpy as np

def naresid(na_action, x):
    """
    Reinsert NA placeholders at excluded positions.

    Parameters
    ----------
    na_action : dict or None
        A dict with keys:
          "indices"  -- 0-based integer array of excluded row positions
                        (equivalent to R's object$na.action values minus 1)
          "n_total"  -- int, total number of rows in the original data
        If None, x is returned unchanged (mirrors naresid.default / na.omit).
    x : np.ndarray
        1-D array of length n_train, or 2-D array of shape (n_train, n_cols).

    Returns
    -------
    np.ndarray
        Same dtype as x, but length/rows = n_total, with np.nan at excluded
        positions.
    """
    if na_action is None:
        return x

    excl_idx = np.asarray(na_action["indices"])   # 0-based excluded positions
    n_total  = na_action["n_total"]
    n_train  = x.shape[0]

    # Build the kept (non-excluded) position list
    all_idx  = np.arange(n_total)
    kept_idx = np.setdiff1d(all_idx, excl_idx, assume_unique=True)

    if x.ndim == 1:
        out = np.full(n_total, np.nan, dtype=float)
        out[kept_idx] = x
    else:  # 2-D matrix (e.g. prob predictions)
        out = np.full((n_total, x.shape[1]), np.nan, dtype=float)
        out[kept_idx, :] = x

    return out


# --- Caller site (predict_rpart equivalent) ---
# predict_on_training = (newdata is None)
# na_action stores the excluded-row metadata recorded during fit()

if predict_on_training and na_action is not None:
    pred = naresid(na_action, pred)
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `object$na.action` (integer vector, 1-based) | `na_action["indices"]` (0-based int array) | R uses 1-based indexing; subtract 1 when recording during fit |
| `naresid(omit, pred)` | `naresid(na_action, pred)` | Same dispatch logic re-implemented as a plain function |
| `NA` scalar / row | `np.nan` | `np.nan` propagates through arithmetic, matching R's NA behaviour for numeric types |
| `drop=FALSE` for matrices | `out[kept_idx, :]` | NumPy preserves 2-D shape when indexing a 2-D array with a 1-D index array |
| `names(pred)` | `pd.Series` index or a separate `names` array | If row labels must be preserved, wrap `out` in a `pd.Series` (1-D) or `pd.DataFrame` (2-D) |

The `na.omit` case (class `"omit"`) maps to `na_action is None` or a sentinel flag: `na.omit` drops rows permanently and does not expect them to be reinserted, so the compact array is returned as-is.

---

### 4.2 Usage in `residuals.rpart` — Expanding Residuals

**Locations:** `rpart/R/residuals.rpart.R`, function `residuals.rpart`, line 47.

**Original R Context:**

```r
# resid is a named numeric vector of length n_train
# names(resid) <- names(y)  # set immediately before this line

if (!is.null(object$na.action)) naresid(object$na.action, resid) else resid
```

Input types:
- `object$na.action`: same metadata as above.
- `resid`: numeric vector of length `n_train`, with names matching the response variable `y`.

Return type: numeric vector of length `n_original`, with `np.nan` at excluded positions. When returned to the caller, the vector is aligned row-for-row with the original input data.

**Python Equivalent:**

```python
import numpy as np

# resid is a 1-D np.ndarray of shape (n_train,)
# na_action is the dict defined in Example 4.1, or None

resid_expanded = naresid(na_action, resid) if na_action is not None else resid
return resid_expanded
```

Because `resid` is always a 1-D array in `residuals.rpart`, only the `x.ndim == 1` branch of `naresid` is exercised here. The same `naresid` helper from Example 4.1 handles this case without modification.

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `names(resid) <- names(y)` | `resid` as `pd.Series` with `y`'s index, or a separate `names` array | If names must round-trip, use `pd.Series`; for pure numerical pipelines, a plain `np.ndarray` suffices |
| `if (!is.null(...)) naresid(...) else resid` | `naresid(na_action, resid) if na_action is not None else resid` | Direct Python ternary; `None` stands in for R's `NULL` |
| Inline ternary result returned | `return resid_expanded` | No intermediate variable needed |

---

### 4.3 Recording `na_action` During Model Fitting

Because Python does not automatically track excluded rows the way R does, the `na_action` dict must be populated explicitly during the rpart fitting phase. The pattern to follow is:

```python
import numpy as np

def record_na_action(y_original):
    """
    Identify rows with NA/NaN in the response or predictors before fitting.
    Call this before dropping NA rows, and store the result on the fitted model.

    Returns
    -------
    dict with keys "indices" (0-based) and "n_total", or None if no NAs.
    """
    na_mask = np.isnan(y_original.astype(float))  # adapt for your data type
    excl_idx = np.where(na_mask)[0]
    if len(excl_idx) == 0:
        return None
    return {"indices": excl_idx, "n_total": len(y_original)}


# During fit:
na_action = record_na_action(y)
if na_action is not None:
    keep = np.setdiff1d(np.arange(na_action["n_total"]), na_action["indices"])
    X_train, y_train = X[keep], y[keep]
else:
    X_train, y_train = X, y

model.fit(X_train, y_train)
model.na_action = na_action   # store on the fitted object, mirroring object$na.action
```

This mirrors R's `na.exclude` contract: the excluded indices are stored once at fit time and then consumed by `naresid` at predict/residual time.
