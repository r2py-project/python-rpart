# Conversion Guide: `structure` (R to Python)

---

## 1. Overview of `structure` in R

`structure(.Data, ...)` is a base R function that **returns its first argument with one or more named attributes attached**. It is a convenience wrapper around repeated `attr<-` calls: instead of setting attributes one by one after constructing an object, `structure` lets you build the object and attach metadata in a single expression.

**Signature:**
```r
structure(.Data, ...)
```

- `.Data` — any R object (vector, matrix, data frame, list, …) that will receive the attributes.
- `...` — zero or more `tag = value` pairs. Each tag becomes an attribute name on `.Data`.

**Special tag renamings** (R renames these automatically for historical reasons):

| Tag passed | Attribute stored |
|---|---|
| `.Dim` | `dim` |
| `.Dimnames` | `dimnames` |
| `.Names` | `names` |
| `.Tsp` | `tsp` |
| `.Label` | `levels` |

Setting a tag to `NULL` removes that attribute from the object.

**Return value:** the same object as `.Data`, with the requested attributes attached. The class and all other existing attributes are preserved unless explicitly overridden.

Common idiomatic uses of `structure` in R:

1. Attaching an `na.action` attribute to a filtered data frame to record which rows were dropped.
2. Attaching a `names` attribute to a freshly constructed vector.
3. Attaching `dim` to a vector to reshape it into a matrix without copying data.

---

## 2. Contextual Usage Analysis

Two distinct call sites appear in the CSV, both inside `rpart/R/`. They represent two different uses of `structure`.

### Usage A — Attaching `na.action` to a filtered data frame (`na.rpart.R`, line 22)

Inside `na.rpart`, the function filters rows from a data frame `x` by keeping only rows where at least one predictor is non-missing (boolean vector `keep`). Before returning the filtered frame it attaches the dropped-row metadata as the `na.action` attribute:

```r
structure(x[keep , , drop = FALSE], na.action = temp)
```

- `.Data` is `x[keep , , drop = FALSE]` — a data frame subset; `drop = FALSE` preserves the data frame class even when only one column remains.
- `na.action = temp` — `temp` is an integer vector of (1-based) row indices that were dropped; its `names` are the corresponding row names; its `class` is `c("na.rpart", "omit")`.
- Return type: a data frame identical in structure to `x` (minus the omitted rows) but carrying `temp` as the `"na.action"` attribute.

### Usage B — Constructing a named integer vector as an early return (`pred.rpart.R`, line 7)

Inside `pred.rpart`, when the fitted tree contains only a root node (no splits), every observation is assigned node index 1. The function returns early with:

```r
structure(rep(1, nrow(x), names = rownames(x)))
```

Note: in this call `names = rownames(x)` is passed **inside** `rep()`, not as a separate argument to `structure`. `rep(1, nrow(x))` creates a numeric vector of `1`s with length equal to the number of rows in `x`. The `names` argument inside `rep` is silently ignored by `rep` (it is not a valid `rep` argument), so the resulting vector has no names. `structure` then receives this un-named vector with **no additional tag arguments**, so it simply returns the vector unchanged. The effect is equivalent to `rep(1, nrow(x))` — a plain numeric vector of `1`s of length `nrow(x)`.

---

## 3. Python Conversion Strategy

`structure` is a **metadata-attachment** operation, not a numerical computation. Neither `numpy` nor `scipy` is the primary equivalent here.

The Python translation strategy depends on which attribute is being attached:

| R attribute | Python equivalent |
|---|---|
| `na.action` on a data frame | A companion `dict` key `"na.action"` on the dict/object representing the model frame, or an attribute on a pandas `DataFrame` via `df.attrs["na.action"]` |
| `names` on a vector | A `pandas.Series` (where the `index` carries names), or a plain `numpy` array when names are unused downstream |
| `dim` on a vector | `numpy.ndarray.reshape()` |

For the two specific usages in this codebase:

- **Usage A** (`na.action` on a filtered data frame): use `pandas.DataFrame` with `df.attrs["na.action"] = temp` (pandas `DataFrame.attrs` is a dict designed for exactly this purpose), or store the filtered frame and its `na.action` together in a plain Python `dict`.
- **Usage B** (no-op `structure` wrapping `rep`): use `numpy.ones(nrow_x, dtype=float)` directly; `structure` adds nothing here.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Attaching `na.action` to a filtered data frame

**Locations:** `na.rpart.R`, function `na.rpart`, line 22.

**Original R Context:**

- `x` is a data frame (rows = observations, columns = predictors + response).
- `keep` is a logical vector of length `nrow(x)`; `TRUE` means the row is retained.
- `temp` is an integer vector of 1-based row indices for the dropped rows; it has class `c("na.rpart", "omit")` and `names` equal to the original row names of the dropped rows.
- Return type: a data frame (same columns as `x`, fewer rows) with `temp` stored as the `"na.action"` attribute.

```r
# R (na.rpart.R lines 18-22)
temp <- seq(keep)[!keep]          # 1-based integer indices of dropped rows
names(temp) <- row.names(x)[!keep]
class(temp) <- c("na.rpart", "omit")
structure(x[keep , , drop = FALSE], na.action = temp)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# x        : pd.DataFrame  (rows = observations)
# keep     : np.ndarray of bool, shape (nrow(x),)

# Build temp: 0-based integer indices of dropped rows, with row-name labels
dropped_positions = np.where(~keep)[0]               # 0-based
dropped_names     = x.index[~keep].tolist()
temp = {
    "indices": dropped_positions.tolist(),           # list[int], 0-based
    "names":   dropped_names,                        # list[str]
    "class":   ("na.rpart", "omit"),
}

# Filter the data frame
x_filtered = x.loc[keep].copy()                     # drop=False equivalent: always a DataFrame

# Attach na.action metadata
x_filtered.attrs["na.action"] = temp                # pandas DataFrame.attrs dict

return x_filtered
```

**Explanation:**

- `x[keep , , drop = FALSE]` → `x.loc[keep]`. The `.loc[boolean_array]` accessor always returns a `DataFrame` (never collapses to a `Series`), matching R's `drop = FALSE` behaviour.
- `structure(..., na.action = temp)` → `df.attrs["na.action"] = temp`. `pandas.DataFrame.attrs` is a built-in per-DataFrame metadata dictionary; it does not interfere with the frame's data and is explicitly designed for this use case.
- R's 1-based `seq(keep)[!keep]` (positions of `FALSE` entries) → `np.where(~keep)[0]` (0-based). Consumers of `na.action` downstream must be aware of this index offset.
- R's `class(temp) <- c("na.rpart", "omit")` has no direct Python equivalent. The `"class"` field stored in the `temp` dict preserves the information for any downstream logic that inspects it, but no Python dispatch mechanism uses it automatically.

---

### 4.2 No-op `structure` wrapping `rep` (early return for root-only tree)

**Locations:** `pred.rpart.R`, function `pred.rpart`, line 7.

**Original R Context:**

- `x` is a numeric matrix of predictor values; `nrow(x)` is the number of new observations to predict.
- `rep(1, nrow(x), names = rownames(x))` — `names` is **not** a valid argument of `rep`; R silently ignores it. The result is a plain numeric vector of `1`s, length `nrow(x)`, with no names.
- `structure(...)` receives this vector with no additional tag arguments, so it returns the vector unchanged.
- Return type: a plain numeric vector of length `nrow(x)` (all values `1`), representing node index 1 for every observation.

```r
# R (pred.rpart.R line 7)
return(structure(rep(1, nrow(x), names = rownames(x))))
# Effective behaviour: return(rep(1, nrow(x)))
```

**Python Equivalent:**

```python
import numpy as np

# x : np.ndarray, shape (n_obs, n_features)

# Early return for root-only tree: every observation maps to node 1
return np.ones(x.shape[0], dtype=float)
```

**Explanation:**

- `rep(1, nrow(x))` → `np.ones(x.shape[0], dtype=float)`. R's `rep(scalar, n)` creates a length-`n` vector filled with the scalar; `np.ones(n)` is the direct equivalent.
- The `names = rownames(x)` argument inside R's `rep()` call is ignored at runtime (R emits no warning); it should not be translated. The caller (`pred.rpart`) assigns `rownames(x)` to `names(temp)` unconditionally on line 29, which is the correct place that names are attached. In the Python port, if named output is needed, wrap the array in a `pd.Series` with `index=pd.Index(rownames_x)` at that later step instead.
- `structure(...)` with no tag arguments is a no-op; it does not appear in the Python translation at all.
