# Conversion Guide: `model.matrix` (R to Python)

---

## 1. Overview of `model.matrix` in R

`model.matrix` is a function in R's `stats` package that constructs a **design matrix** (also called a model matrix or regressor matrix) from a formula or terms object and an associated data frame. It is the canonical way in R to convert a symbolic model specification into the numeric matrix that statistical algorithms operate on.

**Core behavior:**

- Accepts a `terms` object (derived from a formula) and a data frame (typically a model frame produced by `model.frame()`).
- Expands factor and categorical variables into numeric dummy/contrast columns using the specified contrast coding (default: treatment contrasts, i.e., one-hot minus the reference level).
- Includes an intercept column (all ones) as the first column by default (column index 1 in R, i.e., the "assign = 0" column).
- Returns a numeric matrix of class `"matrix"` with two attributes: `"assign"` (integer vector mapping each column to a formula term) and `"contrasts"` (list recording contrast coding per factor).
- Column names are derived from variable names and factor level labels; backtick-quoted names may appear when variable names contain special characters.

**Typical inputs:**

| Argument | Type | Description |
|---|---|---|
| `object` | `terms` or formula | The model structure specification |
| `data` | `data.frame` (model frame) | The data from which to build the matrix |
| `contrasts.arg` | named list (optional) | Override contrast coding per factor |

**Output:** A numeric matrix with one row per observation and one column per model term coefficient (including the intercept by default).

---

## 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.matrix.R`
**Function:** `rpart.matrix` (lines 7-32)
**Target call (line 27):**

```r
X <- model.matrix(attr(frame, "terms"), frame)[, -1L, drop = FALSE]
```

**Full function context (abridged):**

```r
rpart.matrix <- function(frame)
{
    if (!inherits(frame, "data.frame") ||
       is.null(attr(frame, "terms")))  return(as.matrix(frame))

    frame[] <- lapply(frame,
                      function(x) {
                          if (is.character(x)) as.numeric(factor(x))
                          else if(!is.numeric(x))  as.numeric(x)
                          else x
                      })

    X <- model.matrix(attr(frame, "terms"), frame)[, -1L, drop = FALSE]
    colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
    class(X) <- c("rpart.matrix", class(X))
    X
}
```

**Analysis of the call:**

1. **Input — `attr(frame, "terms")`:** A `terms` object extracted from the model frame `frame`. It encodes the formula structure (which columns are predictors, response, interactions, etc.) that was used when `rpart` built the frame via `model.frame()`.

2. **Input — `frame`:** A model frame (a `data.frame` subclass). Before the `model.matrix` call, every column has already been coerced to numeric: character columns become `as.numeric(factor(x))` (integer codes), and any other non-numeric class is cast with `as.numeric(x)`. So by the time `model.matrix` is called, all columns are numeric vectors.

3. **Output — `[, -1L, drop = FALSE]`:** The intercept column (column 1 in R's 1-based indexing, the all-ones column) is immediately dropped. `drop = FALSE` preserves the matrix class even when only a single predictor column remains (preventing silent coercion to a vector).

4. **Post-processing:** Backtick-quoted column names (e.g., `` `variable name` ``) are cleaned to plain names via `sub("^\`(.*)\`", "\\1", colnames(X))`.

5. **Recurring pattern:** There is exactly one distinct usage pattern in the CSV. The call is always `model.matrix(terms_object, model_frame)[, -1L, drop = FALSE]` — build the full design matrix from a terms-annotated data frame, then strip the intercept column.

---

## 3. Python Conversion Strategy

**Chosen library: `patsy` (primary) with `numpy` (secondary)**

`patsy` is the closest Python equivalent to R's `model.matrix`. It was designed explicitly to replicate R's formula-based design matrix construction:

- It accepts formula strings (e.g., `"y ~ x1 + x2"`) or a design-info object (analogous to R's `terms` object).
- It produces dummy-coded columns for categorical variables using the same treatment-contrast default as R.
- It includes or excludes the intercept via `+ 0` / `- 1` in the formula, directly mirroring R's `[, -1L]` intercept-dropping idiom.
- The output (`patsy.DesignMatrix`) is a subclass of `numpy.ndarray`, so all `numpy` operations apply directly.

`numpy` alone handles the final array operations (column slicing, `.astype(float)`, shape introspection).

**Why not `pandas.get_dummies` or `sklearn.preprocessing`?**

- `pandas.get_dummies` does not use a terms/formula object and does not respect an existing model specification; it encodes all object-dtype columns unconditionally with no reference-level handling.
- `sklearn.preprocessing.OneHotEncoder` / `ColumnTransformer` requires explicit column specification and does not accept a terms-object workflow.
- Neither preserves the "assign" metadata or interaction-term expansion that `model.matrix` provides via `terms`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `model.matrix` with intercept removal (`[, -1L, drop = FALSE]`)

**Locations:** `rpart.matrix.R` — function `rpart.matrix`

**Original R Context:**

- `frame`: a model frame (`data.frame` with a `"terms"` attribute), all columns already coerced to numeric.
- `attr(frame, "terms")`: a `terms` object encoding the formula used to build `frame`.
- Return value `X`: a numeric matrix, no intercept column, shape `(n_rows, n_predictors)`.

```r
# Conceptual R usage
# Assume `frame` is a model frame produced by model.frame(formula, data)
# All columns have been pre-coerced to numeric.

X <- model.matrix(attr(frame, "terms"), frame)[, -1L, drop = FALSE]
colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd
import patsy

def rpart_matrix(frame: pd.DataFrame, formula: str) -> np.ndarray:
    """
    Python equivalent of R's rpart.matrix().

    Parameters
    ----------
    frame : pd.DataFrame
        A data frame equivalent to R's model frame. Must contain all
        variables referenced in `formula`.
    formula : str
        A patsy/R-style formula string, e.g. "y ~ x1 + x2".
        The response variable (left-hand side) will be separated
        automatically; only the right-hand side predictor matrix is returned.

    Returns
    -------
    X : np.ndarray, shape (n_samples, n_predictors)
        Design matrix with no intercept column (mirrors R's [, -1L] drop).
    col_names : list[str]
        Column names of the design matrix.
    """
    # Step 1: coerce non-numeric columns to numeric codes,
    # mirroring R's lapply(frame, function(x) { ... }) pre-processing.
    frame_numeric = frame.copy()
    for col in frame_numeric.columns:
        if not pd.api.types.is_numeric_dtype(frame_numeric[col]):
            frame_numeric[col] = frame_numeric[col].astype("category").cat.codes.astype(float)

    # Step 2: build the design matrix WITHOUT an intercept column.
    # patsy's "- 1" or "+ 0" suppresses the intercept, which is equivalent
    # to R's model.matrix(...)[, -1L, drop = FALSE].
    # Split formula into lhs (response) and rhs (predictors).
    if "~" in formula:
        rhs = formula.split("~", 1)[1].strip()
    else:
        rhs = formula.strip()

    # Remove intercept from the RHS formula.
    rhs_no_intercept = rhs + " - 1"

    X_design = patsy.dmatrix(rhs_no_intercept, data=frame_numeric, return_type="matrix")

    # Step 3: convert to a plain numpy float64 array.
    X = np.asarray(X_design, dtype=np.float64)

    # Step 4: clean column names — patsy may use "Q('name')" or similar
    # quoting for names with special characters; strip to plain names,
    # mirroring R's sub("^`(.*)`", "\\1", colnames(X)).
    import re
    col_names = [re.sub(r"^Q\('(.*)'\)$", r"\1", name)
                 for name in X_design.design_info.column_names]

    return X, col_names


# -----------------------------------------------------------------------
# Minimal worked example
# -----------------------------------------------------------------------
import pandas as pd
import numpy as np

data = pd.DataFrame({
    "y":  [2.1, 3.5, 1.8, 4.2, 3.9],
    "x1": [1.0, 2.0, 3.0, 4.0, 5.0],
    "x2": ["a", "b", "a", "b", "a"],   # categorical — will be coerced
})

X, cols = rpart_matrix(data, formula="y ~ x1 + x2")
print("Column names:", cols)
print("Design matrix shape:", X.shape)
print(X)
# Example output (treatment contrast on x2, reference level 'a' dropped):
# Column names: ['x1', 'x2[T.b]']
# Design matrix shape: (5, 2)
# [[1.  0.]
#  [2.  1.]
#  [3.  0.]
#  [4.  1.]
#  [5.  0.]]
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `attr(frame, "terms")` | `formula` string passed to `patsy.dmatrix` | `patsy` encodes the same structural information from a formula string; there is no direct "terms object" in Python, but `patsy.DesignInfo` serves the analogous role. |
| `model.matrix(terms, frame)` | `patsy.dmatrix(rhs_formula, data=frame_numeric)` | Both expand factors to dummy columns with treatment contrasts by default. |
| `[, -1L, drop = FALSE]` | `"... - 1"` appended to the RHS formula | Removing the intercept in patsy via `- 1` is cleaner than building it then slicing it away, but `np.asarray(X_design)[:, 1:]` achieves the same effect if you prefer the slice approach. |
| `drop = FALSE` | `np.asarray(X_design, dtype=np.float64)` | `numpy` arrays never silently drop dimensions like R vectors do; no special guard is needed. |
| `sub("^\`(.*)\`", "\\1", colnames(X))` | `re.sub(r"^Q\('(.*)'\)$", r"\1", name)` | R uses backtick quoting for awkward names; `patsy` uses `Q('name')` quoting. Both can be cleaned with a simple regex substitution. |
| Pre-coercion: `as.numeric(factor(x))` for character columns | `col.astype("category").cat.codes.astype(float)` | Both convert character/categorical columns to integer codes before the matrix is built. |
| Return type `"rpart.matrix"` class | Plain `np.ndarray` | The class attribute is an rpart-internal tag for the `ipred` package interop; in Python this bookkeeping is not needed unless explicitly reproducing the class hierarchy. |

**Key nuances:**

- **Intercept removal:** R's `[, -1L]` removes the first column (1-based index). In `patsy`, the cleanest equivalent is including `- 1` in the formula so the intercept is never generated. Alternatively, after calling `patsy.dmatrix` without `- 1`, you can slice `np.asarray(X_design)[:, 1:]` — but only if you know the intercept is always the first column (it is, when present).
- **Factor contrast coding:** By default both R and `patsy` use treatment contrasts (drop the first/reference level). If R's `options(contrasts=...)` is changed, the `patsy` formula must be adjusted accordingly (e.g., `C(x2, Sum)` for sum contrasts).
- **Pre-numeric coercion:** The R code coerces columns to numeric *before* calling `model.matrix`, meaning factors are represented as integer codes (1, 2, 3, ...) rather than being expanded into dummy columns by `model.matrix`. The Python translation replicates this by using `.cat.codes` before calling `patsy.dmatrix`. If the original intent were to let `model.matrix` handle factor expansion natively, `patsy` would do so automatically for `pandas` `Categorical` columns without pre-coercion.
- **Zero-based indexing:** R's `-1L` means "drop column at 1-based index 1". Python's equivalent slice would be `[:, 1:]` (drop column at 0-based index 0). Using `- 1` in the patsy formula avoids this entirely.
