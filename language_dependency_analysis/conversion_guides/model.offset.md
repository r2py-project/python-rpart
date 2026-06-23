# Conversion Guide: `model.offset` (R to Python)

### 1. Overview of `model.offset` in R

`model.offset` is a function from R's `stats` package that extracts the **offset component** from a model frame object. A model frame (typically produced by `stats::model.frame`) is a data structure that bundles the response variable, predictor columns, and any special components — such as observation weights, subsets, and offsets — that were specified either through an `offset()` term inside a formula or through an `offset=` argument to `model.frame`.

**Signature:**
```r
model.offset(x)
```

**Input:** `x` — a model frame object (class `data.frame` with a `"terms"` attribute), as returned by `stats::model.frame`.

**Output:** A numeric vector (unnamed) containing the aggregated offset values — one value per observation. When multiple `offset()` terms appear in the formula they are summed elementwise into a single vector. Returns `NULL` if no offset was specified in the model.

It is functionally equivalent to `model.extract(m, "offset")` but additionally validates that the result is numeric.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/rpart.R`
**Function:** `rpart`, line 30

The call on line 30 is:

```r
offset <- model.offset(m)
```

`m` is the model frame built earlier by evaluating `stats::model.frame` (line 19). The model frame contains the formula response, predictor columns, optional observation weights (`wt`), and an optional offset. The extracted `offset` is a **numeric vector of length equal to the number of observations** (`nrow(m)`), or `NULL` if the user did not specify any offset in the formula or call.

The `offset` variable is subsequently passed directly into method-specific initialization functions (`mlist$init`, `rpart.anova`, `rpart.poisson`, `rpart.class`, `rpart.exp`) as their second positional argument. This means downstream C-level splitting code receives either a numeric vector of per-observation offset adjustments or `NULL` (treated as no offset).

Key patterns:
- `offset` is always extracted from the model frame — it is never constructed manually.
- It is never indexed or sliced; it is passed whole to the init function.
- The NULL return path is a normal, expected case (most rpart calls have no offset).
- The Poisson and survival (`"exp"`) methods are the use cases where offsets are most meaningful (e.g., log-exposure offsets in count models).

---

### 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy`), with the model frame equivalent provided by **pandas** (`pandas.DataFrame`).

Rationale:
- R's model frame is most naturally represented as a `pandas.DataFrame`, where special columns (offset, weights) can be stored as named columns or passed alongside the data frame.
- The offset itself is a numeric vector of length `n_obs` — precisely a 1-D `numpy.ndarray`. NumPy is the canonical Python type for such arrays and is what downstream numerical/C extension code expects.
- When no offset is present, Python uses `None` to mirror R's `NULL`.
- There is no direct Python/pandas equivalent of R's model frame "offset slot" — the offset must be extracted explicitly from wherever it was stored (a dedicated DataFrame column, a separate array, or `None`).

---

### 4. Step-by-Step Conversion Examples

#### Usage 1: Extracting the offset from a model frame

**Locations:** `rpart/R/rpart.R`, function `rpart`, line 30.

**Original R Context:**

- `m` is a `data.frame` produced by `stats::model.frame`. It may contain a special column named `"(offset)"` if the user wrote `offset(log_exposure)` in the formula or passed `offset=log_exposure` to `model.frame`.
- Return type: a numeric vector of length `nrow(m)`, or `NULL`.

```r
# m is a model frame (data.frame with a "terms" attribute)
offset <- model.offset(m)
# offset is either a numeric vector of length nrow(m), or NULL
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

def model_offset(model_frame: pd.DataFrame):
    """
    Extract the offset component from a model frame DataFrame.

    In R, model.frame stores the offset in a column named "(offset)".
    This function mirrors that convention.

    Parameters
    ----------
    model_frame : pd.DataFrame
        A DataFrame representing the model frame. If an offset was
        specified, it is stored in a column named "(offset)".

    Returns
    -------
    np.ndarray or None
        A 1-D float64 numpy array of length n_obs, or None if no
        offset was specified.
    """
    offset_col = "(offset)"
    if offset_col not in model_frame.columns:
        return None

    offset_values = model_frame[offset_col].to_numpy(dtype=np.float64)
    return offset_values


# --- Example usage ---

# Case 1: model frame has no offset (most common rpart scenario)
df_no_offset = pd.DataFrame({
    "y": [1, 2, 3],
    "x1": [0.5, 1.5, 2.5],
})
offset = model_offset(df_no_offset)
print(offset)  # None

# Case 2: model frame has an offset (e.g. Poisson model with log-exposure)
df_with_offset = pd.DataFrame({
    "y": [10, 20, 30],
    "x1": [0.5, 1.5, 2.5],
    "(offset)": np.log([100.0, 200.0, 300.0]),
})
offset = model_offset(df_with_offset)
print(offset)  # array([4.60517..., 5.29832..., 5.70378...])

# Downstream usage mirrors R: pass offset (or None) to the init function
# init = rpart_poisson(Y, offset, parms, wt)
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `model.frame` object `m` | `pandas.DataFrame` with named columns |
| Special column `"(offset)"` in model frame | Column named `"(offset)"` in the DataFrame |
| `model.offset(m)` returning `NULL` | `None` |
| `model.offset(m)` returning a numeric vector | `numpy.ndarray` with `dtype=float64` |
| `nrow(m)` | `len(model_frame)` or `model_frame.shape[0]` |

Key nuances:
- R's model frame stores the offset under the column name `"(offset)"` (with parentheses) — this is the internal convention used by `stats::model.frame` when it encounters an `offset()` call in a formula. The Python implementation must respect the same naming convention if it constructs a model-frame-like DataFrame.
- R's `model.offset` sums multiple offset terms elementwise if more than one `offset()` appears in the formula. If multiple offset columns are possible in the Python representation (e.g. `"(offset.1)"`, `"(offset.2)"`), they should be summed: `offset_values = df[[c for c in df.columns if c.startswith("(offset")]].sum(axis=1).to_numpy(dtype=np.float64)`.
- The `NULL` / `None` distinction is critical: downstream code in both R and Python must check `if offset is None` before performing any arithmetic on the offset vector. Passing `None` where a numeric array is expected will raise an error in NumPy operations.
- No zero-indexing issues arise here since the offset is passed as a whole vector, not indexed element-by-element.
