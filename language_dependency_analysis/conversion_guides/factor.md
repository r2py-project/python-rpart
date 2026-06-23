# Conversion Guide: `factor` in R

---

## 1. Overview of `factor` in R

`factor()` encodes a plain vector as a categorical variable. Internally, R stores a factor as an integer vector whose values are indices into a character vector of **levels** — the set of unique, valid category labels. This two-layer representation (integer codes + levels attribute) makes factors memory-efficient and gives them well-defined semantics for modelling and display.

**Signature:**

```r
factor(x = character(), levels, labels = levels,
       exclude = NA, ordered = is.ordered(x), nmax = NA)
```

Key parameter behaviours:

| Parameter | Effect |
|-----------|--------|
| `x` | Input vector (character, numeric, or logical). |
| `levels` | Explicit universe of valid categories. Values in `x` absent from `levels` become `NA`. If omitted, defaults to `sort(unique(as.character(x)))`. |
| `labels` | Rename the levels in the output (same length as `levels`). |
| `exclude` | Values to suppress from the level set (default `NA`). |
| `ordered` | If `TRUE`, produces an ordered factor (`"ordered" "factor"` class). |

**Return value:** An object of class `"factor"` — an integer vector with a `"levels"` attribute and a `"class"` attribute.

---

## 2. Contextual Usage Analysis

Three distinct call sites appear in the rpart source, each serving a different purpose:

| File | Function | Line | Pattern |
|------|----------|------|---------|
| `predict.rpart.R` | `predict.rpart` | 33 | Reconstruct predicted class labels as an ordered factor with a fixed level set. |
| `rpart.class.R` | `rpart.class` | 8 | Create a factor over a contiguous integer range `1:numclass` to drive a `tapply` grouping aggregation. |
| `rpart.matrix.R` | `rpart.matrix` | 20 | Convert a bare character column to an integer-coded numeric via `as.numeric(factor(x))`. |

**Recurring patterns:**

- **Explicit `levels` argument** — used in two of the three call sites to pin the complete, authoritative category universe, preventing R from re-deriving it from the data alone. This is critical when the data subset may not contain every possible class.
- **Integer-range levels** (`1:numclass`) — levels are a consecutive integer sequence, making the factor a thin wrapper that guarantees `tapply` sees every class bucket even if some have zero weight.
- **Factor-to-integer pipeline** — `as.numeric(factor(x))` converts a character column to a dense integer code suitable for a numeric model matrix; the levels themselves are discarded after encoding.

---

## 3. Python Conversion Strategy

**Primary library: `pandas.Categorical`** (backed by `numpy` integer arrays).

`pandas.Categorical` is the closest structural analogue to R's factor:

- It stores data as an integer code array plus a `categories` index, mirroring R's integer-codes + levels design.
- Its `categories` parameter maps directly to R's `levels`.
- Setting `ordered=True` matches R's `ordered=TRUE`.
- Slicing a `pd.Categorical` by an integer position array (the `where` index pattern) preserves the full category set, just as R's factor subscripting does.

`numpy` is used as a secondary tool wherever the goal is a plain integer array (the `as.numeric(factor(x))` pipeline), since the Python output of that pipeline is a numeric matrix column, not a categorical column.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Reconstruct predicted class labels with a fixed level set

**Locations:** `predict.rpart.R` — `predict.rpart` (line 33)

**Original R context:**

```r
# Types:
#   ylevels  : character vector, e.g. c("setosa", "versicolor", "virginica")
#   frame$yval: integer vector — one per tree node, index into ylevels
#   where    : integer vector — maps each observation to a node index

pred <- factor(ylevels[frame$yval[where]], levels = ylevels)
names(pred) <- names(where)
```

`ylevels[frame$yval[where]]` first subscripts the integer node predictions (`frame$yval[where]`) into the character levels vector, producing a character vector of class names for each observation. `factor(..., levels = ylevels)` then wraps that character vector as a factor whose level universe is exactly `ylevels` — so even if a particular class never appears in the predictions, it still appears in the factor's level set.

**Python equivalent:**

```python
import pandas as pd
import numpy as np

# ylevels : list[str] or np.ndarray[str]  — ordered class names
# frame_yval : np.ndarray[int] (1-based R indices converted to 0-based Python)
# where : np.ndarray[int] (0-based observation-to-node mapping)

# Step 1: map each observation to its class name
predicted_labels = np.array(ylevels)[frame_yval[where] - 1]  # -1: R is 1-based

# Step 2: wrap as Categorical with the full, fixed category universe
pred = pd.Categorical(predicted_labels, categories=ylevels)

# Attach observation names as a Series if needed
pred_series = pd.Series(pred, index=obs_names)
```

**Explanation:**

- R's `ylevels[frame$yval[where]]` uses 1-based indexing; the Python equivalent subtracts 1 before indexing into the numpy array.
- `pd.Categorical(..., categories=ylevels)` pins the full level universe, so classes absent from the predictions still appear in `pred.categories` — exactly mirroring `factor(..., levels = ylevels)`.
- `pd.Series` with an `index` replaces `names(pred) <- names(where)`.

---

### 4.2 Integer-range factor for `tapply` grouping

**Locations:** `rpart.class.R` — `rpart.class` (line 8)

**Original R context:**

```r
# Types:
#   y        : integer vector of class codes, values in 1..numclass
#   wt       : numeric vector of observation weights (same length as y)
#   numclass : integer scalar — total number of classes

counts <- tapply(wt, factor(y, levels = 1:numclass), sum)
counts <- ifelse(is.na(counts), 0, counts)   # fill zero for empty classes
```

`factor(y, levels = 1:numclass)` forces the grouping variable to have exactly `numclass` buckets labelled `1, 2, …, numclass`. Without the explicit `levels`, any class absent from `y` would not appear in the `tapply` result, causing a length mismatch downstream. The `ifelse` guard handles the rare remaining `NA`s.

**Python equivalent:**

```python
import numpy as np
import pandas as pd

# y        : np.ndarray[int], 1-based class codes
# wt       : np.ndarray[float], observation weights
# numclass : int

# Use pd.Categorical to force all class buckets to appear
y_cat = pd.Categorical(y, categories=np.arange(1, numclass + 1))
counts_series = pd.Series(wt).groupby(y_cat).sum()

# Fill any missing (empty-class) buckets with 0
counts = counts_series.reindex(np.arange(1, numclass + 1), fill_value=0.0).to_numpy()
```

**Explanation:**

- `pd.Categorical(y, categories=np.arange(1, numclass + 1))` mirrors `factor(y, levels = 1:numclass)`: every integer bucket from 1 to `numclass` is guaranteed to appear in the groupby result even when no observation belongs to that class.
- `groupby(...).sum()` replicates `tapply(wt, ..., sum)`.
- `.reindex(..., fill_value=0.0)` makes the `ifelse(is.na(counts), 0, counts)` step explicit and avoids silent `NaN` values propagating downstream.
- The final `.to_numpy()` yields a plain `float64` array matching R's named numeric vector output.

---

### 4.3 Character column to integer codes for numeric matrix construction

**Locations:** `rpart.matrix.R` — `rpart.matrix` (line 20)

**Original R context:**

```r
# Types:
#   x : character vector (a data-frame column)
#   Return value used as a numeric column inside model.matrix

frame[] <- lapply(frame, function(x) {
    if (is.character(x)) as.numeric(factor(x))
    else if (!is.numeric(x)) as.numeric(x)
    else x
})
```

`factor(x)` — with no explicit `levels` — derives the level set from `sort(unique(x))`, creating a lexicographically-ordered category universe. `as.numeric(...)` then extracts the 1-based integer codes, converting the character column into a dense numeric column that `model.matrix` can include in the design matrix.

**Python equivalent:**

```python
import numpy as np
import pandas as pd

def encode_column(col):
    """
    Replicates rpart.matrix's per-column encoding logic.

    col : pd.Series with any dtype
    Returns a pd.Series of float64 integer codes (1-based).
    """
    if pd.api.types.is_string_dtype(col) or pd.api.types.is_object_dtype(col):
        # factor(x) with default levels = sort(unique(x))
        cat = pd.Categorical(col, categories=sorted(col.dropna().unique()))
        # as.numeric(factor(x)) — R codes are 1-based
        return pd.Series(cat.codes + 1, index=col.index, dtype=float)
    elif not pd.api.types.is_numeric_dtype(col):
        # as.numeric(x) for non-numeric, non-character columns
        return col.astype(float)
    else:
        return col

# Apply across all columns of a DataFrame (mirrors lapply over frame)
frame = frame.apply(encode_column)
```

**Explanation:**

- `pd.Categorical(col, categories=sorted(...))` reproduces `factor(x)` with its default `levels = sort(unique(as.character(x)))` behaviour.
- `cat.codes` is 0-based in pandas; adding 1 restores R's 1-based integer codes, keeping numerical equivalence with the original output fed into `model.matrix`.
- `dtype=float` matches `as.numeric(...)` which returns a double vector in R.
- The `apply(encode_column)` pattern replicates the `lapply(frame, function(x) ...)` idiom, operating column-by-column across the data frame.
