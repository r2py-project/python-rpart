# Conversion Guide: `names<-` (R to Python)

---

### 1. Overview of `names<-` in R

`names<-` is R's assignment form of the `names()` generic. It sets the `names` attribute of any R object — most commonly a named vector or list. The idiom:

```r
names(x) <- value
```

is syntactic sugar for the internal call `x <- "names<-"(x, value)`. It attaches a character vector `value` as element-level labels to `x`, making subsequent element access by name possible (e.g., `x["foo"]`).

- **Input — object (`x`):** Any R vector, list, or similar object whose names attribute can be set.
- **Input — value:** A character vector whose length is less than or equal to `length(x)`. If shorter, R extends it with `NA` characters. Passing `NULL` removes all names.
- **Output:** The same object `x` with its `names` attribute updated in place (R's copy-on-modify semantics make this appear in-place).

In the rpart package the particular form used is:

```r
names(temp) <- row.names(x)[!keep]
```

where `temp` is an integer vector produced by `seq(keep)[!keep]` and the right-hand side is a character vector of row-names corresponding to dropped rows.

---

### 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/na.rpart.R`  
**Function:** `na.rpart` (lines 1–24)  
**Target line:** 19

```r
na.rpart <- function(x) {
    ...
    if (all(keep)) x
    else {
        temp <- seq(keep)[!keep]            # line 18: integer indices of dropped rows
        names(temp) <- row.names(x)[!keep] # line 19: attach dropped row-names as names
        class(temp) <- c("na.rpart", "omit")
        structure(x[keep , , drop = FALSE], na.action = temp)
    }
}
```

**Data types involved:**

| Expression | R type | Description |
|---|---|---|
| `temp` | integer vector | Positional indices (1-based) of rows that were removed due to NAs |
| `row.names(x)[!keep]` | character vector | Row-name strings for those removed rows |
| `names(temp) <- ...` | (side-effect) | Pairs each index with its corresponding row-name string |

**Pattern:** This is a one-shot name assignment — a single integer vector receives a character vector of the same length as its names attribute. There is no partial assignment, no recycling, and no `NULL` reset. The named vector is then stored as the `na.action` metadata attached to the cleaned data frame.

---

### 3. Python Conversion Strategy

The closest Python equivalent is a **`dict`** or, when a pandas-aware structure is preferred, a **`pandas.Series` with a string index**.

- A Python `dict` directly models the R named vector: keys are the character names, values are the integer indices.
- A `pandas.Series` with an explicit string index is the stronger structural match when the result must interoperate with pandas DataFrames (as it does here, since the `na.action` equivalent will be attached to a DataFrame).

**Why not numpy?** `numpy` arrays do not natively support string-keyed element labels. A structured array with named fields is semantically different (it names *columns*, not *rows*). Therefore `numpy` is not the right tool for this particular pattern.

**Chosen strategy:** `pandas.Series` with a string index, mirroring R's named integer vector. Where a lightweight dict suffices (no DataFrame interop needed), a plain `dict` is also shown.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Assigning row-name strings as the index of a dropped-row index vector

**Locations:** `na.rpart.R` — function `na.rpart`

**Original R Context**

```
temp       : integer vector  — 1-based positional indices of dropped rows
row.names  : character vector — row-name strings of dropped rows
(same length as temp)
```

```r
# R generalized snippet
temp <- seq(keep)[!keep]            # e.g. c(2L, 5L, 7L)
names(temp) <- row.names(x)[!keep] # e.g. c("row2", "row5", "row7")
# Result: named integer vector
# row2 row5 row7
#    2    5    7
```

**Python Equivalent — pandas.Series (recommended)**

```python
import numpy as np
import pandas as pd

# keep is a boolean array (True = row is retained)
# x is the pandas DataFrame equivalent of the R data frame

# Replicate seq(keep)[!keep]: 1-based integer positions of dropped rows
dropped_positions = np.where(~keep)[0] + 1          # convert 0-based to 1-based

# Replicate row.names(x)[!keep]: string row labels of dropped rows
dropped_row_names = x.index[~keep].astype(str)

# Replicate names(temp) <- row.names(x)[!keep]
temp = pd.Series(dropped_positions, index=dropped_row_names, dtype=int)
# Result: a Series with string index
# row2    2
# row5    5
# row7    7
# dtype: int64
```

**Python Equivalent — plain dict (lightweight alternative)**

```python
import numpy as np

dropped_positions = (np.where(~keep)[0] + 1).tolist()
dropped_row_names = x.index[~keep].astype(str).tolist()

temp = dict(zip(dropped_row_names, dropped_positions))
# Result: {'row2': 2, 'row5': 5, 'row7': 7}
```

**Explanation**

| R construct | Python equivalent | Notes |
|---|---|---|
| `seq(keep)[!keep]` | `np.where(~keep)[0] + 1` | `np.where` returns 0-based indices; `+1` converts to R's 1-based convention |
| `row.names(x)[!keep]` | `x.index[~keep].astype(str)` | pandas `.index` is the direct analogue of R's `row.names`; `.astype(str)` ensures character type |
| `names(temp) <- ...` | `pd.Series(..., index=...)` | In pandas, setting the index at construction time is equivalent to assigning R names post-hoc; there is no separate "assign names after construction" step needed |
| Named integer vector | `pd.Series(dtype=int)` with string index | The Series preserves both the integer values and their string labels, matching R's named vector semantics |
| `class(temp) <- c("na.rpart", "omit")` | custom class or metadata attribute | Outside the scope of `names<-`; handled separately in the `na.rpart` Python conversion |

Zero-indexing note: R's `seq(keep)` produces 1-based integers. When translating to Python, add `1` to `np.where(~keep)[0]` if the downstream code (e.g., re-indexing into the DataFrame) expects 1-based positions. If the Python code uses 0-based indexing throughout, omit the `+1` and adjust callers accordingly.
