# Conversion Guide: `sum` in R

## 1. Overview of `sum` in R

`sum(...)` computes the sum of all values in its input. Its signature is:

```r
sum(..., na.rm = FALSE)
```

- `...`: one or more numeric, logical, complex, or raw vectors. Logical values are coerced to integers (TRUE = 1, FALSE = 0).
- `na.rm`: if `TRUE`, `NA` values are excluded before summation; defaults to `FALSE`, in which case any `NA` in the input propagates to an `NA` result.
- **Return value:** always a scalar (length-1 numeric or integer).

R's `sum` is fully vectorized over its inputs—it collapses an entire vector (or matrix, after passing as a function reference to `tapply`) to a single numeric value. It is also commonly passed as a first-class function object to higher-order functions such as `tapply`.

---

## 2. Contextual Usage Analysis

Across the CSV dataset, `sum` appears in five distinct files within the rpart package. Two overarching usage patterns are present:

**Pattern A – Direct call returning a scalar.** `sum(x)` is called on a vector or on a logical / numeric subset selected by indexing, and the result is used in a scalar arithmetic expression or comparison. This is the most frequent pattern and covers all usages in `roc.rpart.R`, `rpart.R`, `rpart.class.R`, `rpartco.R`, and `summary.rpart.R`.

**Pattern B – Function reference passed to `tapply`.** In `rpart.class.R` (line 8) and `rpart.exp.R` (lines 83, 88, 92), `sum` is passed *without parentheses* as the `FUN` argument to `tapply(x, INDEX, sum)`. `tapply` applies the function to each group defined by `INDEX` and returns a named array of group sums.

The data types involved are:
- Logical vectors (from Boolean row-selections of a matrix) — `roc.rpart.R`.
- Numeric weight vectors — `rpart.R`, `rpart.class.R`, `summary.rpart.R`.
- Numeric time/status vectors grouped by interval index — `rpart.exp.R`.
- A logical vector of leaf indicators — `rpartco.R`.

---

## 3. Python Conversion Strategy

`numpy` is the primary equivalent. It provides `numpy.sum()`, which:
- Accepts arrays of any dimensionality and dtype.
- Handles logical (boolean) arrays exactly as R does (True = 1, False = 0).
- Accepts an `axis` argument to collapse along a specific dimension (equivalent to R's `rowSums` / `colSums`), and omits the argument to get a global scalar sum exactly like R's `sum`.

For Pattern B (`tapply(..., sum)`), the idiomatic Python equivalent uses `numpy` together with `pandas.Series.groupby(...).sum()` or `numpy`-based grouping via `numpy.bincount` / `pandas`. `pandas.Series.groupby` is the closest structural match to `tapply` and is used in the examples below.

`math.sum` / `math.fsum` are **not** suitable here because R's usage is inherently over vectors, not single scalars.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Row-sum guard check on a boolean matrix (`roc.rpart.R`, lines 17 and 23)

**Locations:** `roc.rpart.R` — function `roc.rpart`

**Original R Context:**

```r
# pred.np is a boolean matrix of shape [cutoff_n, n_endnodes]
# last.r is the number of rows
last.r <- dim(pred.np)[1L]
last.c <- dim(pred.np)[2L]
if (sum(pred.np[1L, ]) > 0L) {
    pred.np <- rbind(matrix(FALSE, nrow = 1L, ncol = last.c), pred.np)
    cutoffs <- c(NA, cutoffs)
}
last.r <- dim(pred.np)[1L]
last.c <- dim(pred.np)[2L]
if (sum(pred.np[last.r, ]) < last.c) {
    pred.np <- rbind(pred.np, matrix(TRUE, nrow = 1L, ncol = last.c))
    cutoffs <- c(cutoffs, NA)
}
```

`pred.np[1L, ]` selects the first row (a boolean vector); `sum` counts the number of `TRUE` values. The results are scalars compared against integer constants.

**Python Equivalent:**

```python
import numpy as np

# pred_np: 2-D boolean numpy array of shape (cutoff_n, n_endnodes)
# cutoffs: 1-D numpy array

last_r, last_c = pred_np.shape

if np.sum(pred_np[0, :]) > 0:          # row 0 in Python == row 1L in R
    pred_np = np.vstack([
        np.zeros((1, last_c), dtype=bool),
        pred_np
    ])
    cutoffs = np.concatenate([[np.nan], cutoffs])

last_r, last_c = pred_np.shape

if np.sum(pred_np[last_r - 1, :]) < last_c:   # last row
    pred_np = np.vstack([
        pred_np,
        np.ones((1, last_c), dtype=bool)
    ])
    cutoffs = np.concatenate([cutoffs, [np.nan]])
```

**Explanation:** R's 1-based row index `pred.np[1L, ]` becomes `pred_np[0, :]` in Python. `np.sum` on a boolean array counts `True` elements, matching R's coercion of logical to integer before summing. `np.vstack` replaces `rbind`.

---

### 4.2 Grouped sums over boolean row-selections for confusion-matrix construction (`roc.rpart.R`, lines 43–46)

**Locations:** `roc.rpart.R` — function `roc.rpart`

**Original R Context:**

```r
# truth: numeric matrix of shape [n_endnodes, 2], columns = class counts
# pred.np[i, ]: boolean vector of length n_endnodes (which nodes are predicted positive)
ss.table[1L, 1L] <- sum(truth[pred.np[i, ], 1L])
ss.table[2L, 1L] <- sum(truth[!pred.np[i, ], 1L])
ss.table[1L, 2L] <- sum(truth[pred.np[i, ], 2L])
ss.table[2L, 2L] <- sum(truth[!pred.np[i, ], 2L])
```

`pred.np[i, ]` is a boolean vector used as a row mask. `sum` collapses the masked column to a scalar.

**Python Equivalent:**

```python
import numpy as np

# truth: 2-D numpy array of shape (n_endnodes, 2), dtype float or int
# pred_np: 2-D boolean numpy array of shape (cutoff_n, n_endnodes)

for i in range(cutoff_n):
    mask = pred_np[i, :]                    # boolean vector

    ss_table = np.zeros((2, 2))
    ss_table[0, 0] = np.sum(truth[mask, 0])       # R column 1L -> Python index 0
    ss_table[1, 0] = np.sum(truth[~mask, 0])
    ss_table[0, 1] = np.sum(truth[mask, 1])       # R column 2L -> Python index 1
    ss_table[1, 1] = np.sum(truth[~mask, 1])
```

**Explanation:** R's logical negation `!pred.np[i, ]` becomes `~mask` in numpy. R's 1-based column indices `1L` and `2L` become Python 0-based indices `0` and `1`. Boolean fancy-indexing in numpy works identically to R's logical subsetting.

---

### 4.3 Scalar sum of a numeric weight vector (`rpart.R`, line 252)

**Locations:** `rpart.R` — function `rpart`

**Original R Context:**

```r
# wt: numeric vector of case weights (length = number of training observations)
nodeprob <- rpfit$dnode[, numclass + 5L] / sum(wt)
```

`sum(wt)` produces a single numeric scalar — the total weight of all observations — used as a normalizing denominator.

**Python Equivalent:**

```python
import numpy as np

# wt: 1-D numpy array of case weights
nodeprob = rpfit_dnode[:, numclass + 4] / np.sum(wt)   # column index shifted by 1
```

**Explanation:** A straightforward drop-in: `np.sum` over a 1-D array returns a scalar. The column index shifts from `numclass + 5L` (1-based) to `numclass + 4` (0-based).

---

### 4.4 `sum` passed as a function reference to `tapply` — weighted class counts (`rpart.class.R`, lines 8, 12, 24, 27)

**Locations:** `rpart.class.R` — function `rpart.class`

**Original R Context:**

```r
# wt: numeric weight vector; y: integer class-label vector (1-based)
counts <- tapply(wt, factor(y, levels = 1:numclass), sum)
counts <- ifelse(is.na(counts), 0, counts)

# Usage 1: normalize to get priors
parms <- list(prior = counts / sum(counts), ...)

# Usage 2: normalize inside branch (parms supplied as list)
if (is.null(parms$prior)) temp <- c(counts / sum(counts))
else {
    temp <- parms$prior
    if (sum(temp) != 1) stop("Priors must sum to 1")
    ...
}
```

`tapply(wt, factor(...), sum)` groups the weight vector by class label and sums each group, producing a named numeric array of length `numclass`. The subsequent `sum(counts)` and `sum(temp)` are then scalar sums over those result arrays.

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# wt: 1-D numpy array of case weights
# y: 1-D numpy integer array, 1-based class labels

numclass = int(np.max(y[~np.isnan(y)]))

# tapply(wt, factor(y, levels=1:numclass), sum)
wt_series = pd.Series(wt)
y_cat = pd.Categorical(y, categories=range(1, numclass + 1))
counts = wt_series.groupby(y_cat).sum().to_numpy()
counts = np.where(np.isnan(counts), 0.0, counts)

# sum(counts) — scalar total weight
prior = counts / np.sum(counts)

# Validation: sum(temp) != 1
temp = prior   # or user-supplied prior
if abs(np.sum(temp) - 1.0) > 1e-10:
    raise ValueError("Priors must sum to 1")
```

**Explanation:** `pd.Series.groupby(pd.Categorical(...)).sum()` replicates `tapply` with explicit level ordering (including empty groups, which produce 0 in R after `ifelse(is.na(...), 0, ...)`). `np.sum` then collapses the resulting array to a scalar for normalization and validation.

---

### 4.5 `sum` as `FUN` in `tapply` for grouped time-interval sums — survival data (`rpart.exp.R`, lines 83, 88, 92)

**Locations:** `rpart.exp.R` — function `drate2` (nested inside `rpart.exp`)

**Original R Context:**

```r
# itime: numeric vector — time spent in the final interval per observation
# index: integer vector — interval index for each observation
# itime2: numeric vector — time before "start" per observation (ny==3 case)
# index2: integer vector — interval index for start times
# status: binary integer vector (0=censored, 1=death)

pyears <- ilength * c(temp[-1L], 0) + tapply(itime, index, sum)
# (ny == 3 case)
py2 <- ilength * c(0, temp[-ngrp]) + tapply(itime2, index2, sum)
deaths <- tapply(status, index, sum)
rate <- deaths / pyears
```

All three `tapply(..., sum)` calls group a numeric or binary vector by an integer interval index and compute the group total. Each returns a numeric vector of length `ngrp` (one value per time interval).

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# itime, itime2, status: 1-D numpy arrays
# index, index2: 1-D numpy integer arrays (1-based interval labels)
# ilength: 1-D numpy array of interval lengths, length ngrp
# temp: cumulative counts array (see rev/cumsum logic)

ngrp = len(ilength)

# tapply(itime, index, sum) — sum of itime per interval group
itime_series = pd.Series(itime)
index_cat = pd.Categorical(index, categories=range(1, ngrp + 1))
tapply_itime = itime_series.groupby(index_cat).sum().to_numpy()

pyears = ilength * np.concatenate([temp[1:], [0]]) + tapply_itime

# ny == 3 case
itime2_series = pd.Series(itime2)
index2_cat = pd.Categorical(index2, categories=range(1, ngrp + 1))
tapply_itime2 = itime2_series.groupby(index2_cat).sum().to_numpy()

py2 = ilength * np.concatenate([[0], temp[:-1]]) + tapply_itime2
pyears = pyears - py2

# tapply(status, index, sum) — death counts per interval
status_series = pd.Series(status)
deaths = status_series.groupby(index_cat).sum().to_numpy()

rate = deaths / pyears
```

**Explanation:** `pd.Series.groupby(pd.Categorical(..., categories=...)).sum()` enforces that every interval group appears in the output — including empty intervals — exactly as R's `tapply` does when the grouping factor has explicit levels. Without the explicit `categories`, empty groups would be silently dropped, giving a shorter array and breaking the element-wise arithmetic with `ilength`. The `.to_numpy()` call converts back to a plain numpy array for subsequent vectorized operations.

---

### 4.6 Scalar sum over a logical vector of leaf indicators (`rpartco.R`, line 55)

**Locations:** `rpartco.R` — function `rpartco`

**Original R Context:**

```r
# is.leaf: logical vector (TRUE where a tree node is a leaf)
x[is.leaf] <- seq(sum(is.leaf))
```

`sum(is.leaf)` counts the number of `TRUE` entries, producing a scalar integer used as the argument to `seq` to generate the sequence `1, 2, ..., n_leaves`.

**Python Equivalent:**

```python
import numpy as np

# is_leaf: 1-D boolean numpy array
n_leaves = int(np.sum(is_leaf))          # count of True entries
x[is_leaf] = np.arange(1, n_leaves + 1) # R's seq(n) = 1..n; Python is 0-based
```

**Explanation:** `np.sum` on a boolean array counts `True` values. R's `seq(n)` produces `1:n` (inclusive); the Python equivalent is `np.arange(1, n + 1)`.

---

### 4.7 Scalar sum to normalize variable importance (`summary.rpart.R`, line 26)

**Locations:** `summary.rpart.R` — function `summary.rpart`

**Original R Context:**

```r
# temp: numeric named vector of variable importance scores
temp <- round(100 * temp / sum(temp))
```

`sum(temp)` produces the total importance mass as a scalar, used to convert raw scores to percentages.

**Python Equivalent:**

```python
import numpy as np

# temp: 1-D numpy array of variable importance scores (or pandas Series)
temp = np.round(100 * temp / np.sum(temp)).astype(int)
```

**Explanation:** A direct replacement: `np.sum` over a 1-D array returns a scalar. `np.round` followed by `.astype(int)` reproduces R's `round()` which returns integers in this context. If `temp` is a `pandas.Series` (to preserve variable names), `temp.sum()` is equally valid and returns a scalar.
