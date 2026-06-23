# Conversion Guide: `tapply` (R to Python)

---

## 1. Overview of `tapply` in R

`tapply` applies a function to subsets of a vector, where the subsets are defined by one or more grouping factors. Its signature is:

```r
tapply(X, INDEX, FUN = NULL, ..., default = NA, simplify = TRUE)
```

- `X`: An atomic vector (the data to be summarised).
- `INDEX`: A factor, or a list of factors, of the same length as `X`. Each unique combination of factor levels defines one group.
- `FUN`: The function to apply to each group's subset of `X`.
- `simplify`: When `TRUE` (the default) and `FUN` returns a scalar, the result is simplified to an array whose dimensions correspond to the levels of `INDEX`; otherwise a list is returned.

When a single factor `INDEX` is provided and `FUN` returns a scalar, `tapply` returns a **named vector** (or 1-D array in R's sense) whose names are the factor levels and whose values are the per-group results. Groups that appear in the factor's `levels` attribute but contain no observations are represented as `NA` in the output.

The closest Python equivalent for all use-cases found in the rpart source is **`pandas`**, specifically `pd.Series.groupby(...).agg(...)`, which provides the same group-keyed, labelled output. `numpy` alone cannot reproduce the named, level-preserving result that `tapply` guarantees.

---

## 2. Contextual Usage Analysis

All five call sites use `tapply` with a single `INDEX` factor and `FUN = sum`, making every case a **group-wise summation**. The details differ across the three source files:

### `importance.R` — variable importance accumulation

`tapply` at line 37 aggregates importance scores across variable names. Both `X` and `INDEX` are built by concatenating primary-split values with surrogate-split values using `c(...)` and `unlist(...)`, so both are plain numeric and character vectors respectively at call time. The index is **not** pre-coerced to a factor with explicit levels, so only the names that actually appear become group keys. The result is a named numeric vector that is subsequently sorted.

### `rpart.class.R` — class weight counts

`tapply` at line 8 sums case weights (`wt`, a numeric vector) grouped by `factor(y, levels = 1:numclass)`. The factor is constructed with **explicit levels** covering all class integers from 1 to `numclass`. This means even empty classes produce an entry (returned as `NA` by `tapply`, then replaced with 0 on line 9). The result is a named numeric vector of length `numclass`.

### `rpart.exp.R` — person-years and death counts (lines 83, 88, 92)

Inside the closure `drate2`, three `tapply` calls operate on numeric vectors indexed by `index` or `index2`, both of which are integer vectors produced by `unclass(cut(...))`. These indices are **not** explicitly coerced to a factor with declared levels before being passed. However, the context guarantees that every interval 1 through `ngrp` is populated (due to the design of `itable`), so no missing-level issue arises. All three calls sum over disjoint time-interval groups and their results are used in arithmetic immediately afterwards.

**Recurring patterns:**

| Pattern | Files | Key property |
|---|---|---|
| `tapply(numeric_vec, char/factor_index, sum)` — no explicit levels | `importance.R`, `rpart.exp.R` | Result length = number of distinct observed groups |
| `tapply(numeric_vec, factor_with_levels, sum)` — explicit levels | `rpart.class.R` | Result length = total declared levels; missing groups → `NA` |

---

## 3. Python Conversion Strategy

**Chosen library: `pandas`**

`pandas` is the right default because:

1. `pd.Series.groupby().sum()` mirrors `tapply(X, INDEX, sum)` directly: it groups by unique values of the index, sums within each group, and returns a `pd.Series` keyed by the group labels — the same shape and semantics as R's named vector output.
2. When explicit levels are needed (the `rpart.class.R` pattern), `pd.Categorical` with `categories=` and `observed=False` reproduces the behaviour of an R factor with declared levels, causing absent categories to appear in the output (as `NaN`, parallel to R's `NA`).
3. `numpy` alone (`np.bincount`, `np.add.at`) can perform group sums but loses the labelled, named-index character of `tapply`'s output, requiring extra reconstruction work.

`scipy.ndimage.sum` is an alternative for purely integer indices but also drops the labelling layer.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Variable Importance Accumulation (`importance.R`, function `importance`, line 37)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/importance.R`, function `importance`

**Original R Context:**

- `scaled.imp` — numeric vector, one value per primary split node.
- `sval` — list of numeric vectors (surrogate split importances, one sub-list per primary split node); flattened with `unlist(sval)`.
- `ff$var[fpri]` — character vector of primary-split variable names; converted to plain character with `as.character(...)`.
- `sname` — list of character vectors (surrogate variable names); flattened with `unlist(sname)`.
- The two `c(...)` calls concatenate primary and surrogate values/names into single flat vectors before the `tapply` call.
- Result: a named numeric vector (`import`) mapping each variable name to its total accumulated importance.

```r
# Generalised R snippet
X     <- c(scaled.imp, unlist(sval))       # numeric vector
INDEX <- c(as.character(ff$var[fpri]),      # character vector (becomes factor internally)
           unlist(sname))
import <- tapply(X, INDEX, sum)            # named numeric vector, one entry per unique variable
sort(c(import), decreasing = TRUE)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# X and index are already flat Python/numpy sequences at this point.
# scaled_imp: np.ndarray of shape (n_primary,)
# sval: list of np.ndarrays (one per primary split, may be empty)
# var_names: list/array of str, primary-split variable names
# sname: list of lists of str, surrogate variable names

X = np.concatenate([scaled_imp, np.concatenate(sval) if sval else np.array([])])
index = np.concatenate([np.asarray(var_names, dtype=str),
                        np.concatenate(sname) if sname else np.array([], dtype=str)])

import_scores = pd.Series(X, dtype=float).groupby(index).sum()
# import_scores is a pd.Series with variable names as the index.

# Equivalent of sort(c(import), decreasing=TRUE):
import_scores_sorted = import_scores.sort_values(ascending=False)
```

**Explanation:**

- R's `c(...)` → `np.concatenate([...])`.
- R's `unlist(sval)` → `np.concatenate(sval)` (where `sval` is a list of arrays; guard against empty list).
- `tapply(X, INDEX, sum)` → `pd.Series(X).groupby(index).sum()`. Because `INDEX` is a plain character vector (no explicit levels), only observed variable names appear — matching R behaviour.
- R's `sort(..., decreasing=TRUE)` → `.sort_values(ascending=False)`.
- The output `import_scores_sorted` is a `pd.Series` with a string index, which is the direct analogue of R's named numeric vector.

---

### 4.2 Class Weight Counts with Explicit Levels (`rpart.class.R`, function `rpart.class`, line 8)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.class.R`, function `rpart.class`

**Original R Context:**

- `wt` — numeric vector of per-observation case weights, length = number of training observations.
- `y` — integer vector of class labels in `1:numclass` (already coerced from factor on line 6).
- `numclass` — integer scalar, total number of classes.
- `factor(y, levels = 1:numclass)` — factor with all class integers declared as levels; ensures the result covers every class, even empty ones.
- Result: a named numeric vector of length `numclass`; empty classes yield `NA`, replaced with 0 on the next line.

```r
# Generalised R snippet
counts <- tapply(wt, factor(y, levels = 1:numclass), sum)
counts <- ifelse(is.na(counts), 0, counts)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# wt: np.ndarray of shape (n_obs,), float — per-observation case weights
# y:  np.ndarray of shape (n_obs,), int   — class labels in {1, ..., numclass}
# numclass: int

all_levels = np.arange(1, numclass + 1)  # mirrors 1:numclass in R

index = pd.Categorical(y, categories=all_levels)
counts = pd.Series(wt, dtype=float).groupby(index, observed=False).sum()
# counts is a pd.Series indexed by 1..numclass.
# Empty classes produce 0.0 with groupby sum (unlike tapply which produces NA).
# If NA-then-0 fidelity is required explicitly:
counts = counts.fillna(0.0)
```

**Explanation:**

- `factor(y, levels = 1:numclass)` → `pd.Categorical(y, categories=all_levels)`. Declaring `categories` explicitly is the critical step; it forces the groupby to produce a row for every declared class, just as R's factor levels force `tapply` to include all levels.
- `observed=False` in `groupby` tells pandas to include all declared categories even when no observation falls in them. With `observed=True` (the default in newer pandas), absent categories would be silently dropped — which would not match R behaviour.
- `pd.Series.groupby(...).sum()` already returns 0.0 for empty groups (rather than `NaN`), so `fillna(0.0)` is only needed if intermediate `NaN` values appear from other operations. Including it matches the intent of R's `ifelse(is.na(counts), 0, counts)`.
- The resulting `counts` is a `pd.Series` with integer index `1..numclass`, equivalent to R's named numeric vector.

---

### 4.3 Person-Years and Death Summation Over Time Intervals (`rpart.exp.R`, function `drate2`, lines 83, 88, 92)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`, inner function `drate2`

**Original R Context:**

- `itime` — numeric vector; time spent by each observation in its terminal interval (i.e., the partial width at the right end of follow-up). Length = number of observations.
- `index` — integer vector produced by `unclass(cut(time, itable, include.lowest=TRUE))`; values in `1:ngrp`. One entry per observation indicating which interval its follow-up ends in.
- `itime2` — same structure as `itime` but for start times (only present when `ny == 3`).
- `index2` — integer vector analogous to `index` but for start times.
- `status` — integer/numeric vector; 0 = censored, 1 = event. Length = number of observations.
- `ngrp` — integer scalar; total number of time intervals.
- All three calls use integer indices with no explicit factor-level declaration; every interval is guaranteed to be observed, so no missing-level issue arises.
- Results are used immediately in arithmetic (`pyears`, `py2`, `deaths`).

```r
# Generalised R snippet (lines 83, 88, 92)
pyears  <- ilength * c(temp[-1L], 0) + tapply(itime,  index,  sum)  # line 83
py2     <- ilength * c(0, temp[-ngrp]) + tapply(itime2, index2, sum) # line 88
deaths  <- tapply(status, index, sum)                                 # line 92
rate    <- deaths / pyears
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# itime:   np.ndarray shape (n_obs,), float  — partial interval time for each obs
# itime2:  np.ndarray shape (n_obs,), float  — partial interval time at start (ny==3 case)
# status:  np.ndarray shape (n_obs,), int    — event indicator (0 or 1)
# index:   np.ndarray shape (n_obs,), int    — 1-based interval index for end time
# index2:  np.ndarray shape (n_obs,), int    — 1-based interval index for start time (ny==3)
# ilength: np.ndarray shape (ngrp,),  float  — lengths of each time interval
# ngrp:    int                                — number of time intervals

# tapply(itime, index, sum)  — line 83
# np.bincount is the most efficient approach here because index is a dense integer
# vector covering 1..ngrp with no missing levels.
# np.bincount with weights produces sum per bin; minlength ensures all ngrp bins present.
itime_sum = np.bincount(index - 1, weights=itime, minlength=ngrp)   # shape (ngrp,)

tab1 = np.bincount(index - 1, minlength=ngrp)                        # count per interval
temp = np.cumsum(tab1[::-1])[::-1]                                    # right-to-left cumsum
pyears = ilength * np.append(temp[1:], 0) + itime_sum

# tapply(itime2, index2, sum) — line 88  (ny == 3 branch only)
itime2_sum = np.bincount(index2 - 1, weights=itime2, minlength=ngrp)

tab2 = np.bincount(index2 - 1, minlength=ngrp)
temp2 = np.cumsum(tab2[::-1])[::-1]
py2 = ilength * np.prepend(temp2[:-1], 0) + itime2_sum
# Note: np.prepend does not exist; use np.concatenate or np.insert:
py2 = ilength * np.concatenate([[0], temp2[:-1]]) + itime2_sum
pyears = pyears - py2

# tapply(status, index, sum) — line 92
deaths = np.bincount(index - 1, weights=status.astype(float), minlength=ngrp)

rate = deaths / pyears
```

**Explanation:**

- Because `index` and `index2` are dense integer arrays whose values cover `1..ngrp` with no gaps, `np.bincount` is the most direct and efficient equivalent. It is faster than a full pandas groupby for pure numeric summation when the index is a contiguous integer range.
- The `- 1` offset converts R's 1-based interval indices to Python's 0-based array indices, which `np.bincount` requires.
- `minlength=ngrp` ensures the output array always has exactly `ngrp` elements, matching R's guarantee that every level appears (because the factor levels span `1:ngrp`).
- `weights=itime` in `np.bincount` produces the weighted sum, which is exactly what `tapply(..., sum)` computes.
- `np.bincount(index - 1, minlength=ngrp)` (without weights) is the equivalent of R's `table(index)` used on the same lines.
- The `np.cumsum(tab[::-1])[::-1]` idiom translates R's `rev(cumsum(rev(tab1)))` — a right-to-left cumulative sum.
- `np.concatenate([[0], temp2[:-1]])` translates R's `c(0, temp[-ngrp])`.
- All output arrays are `np.ndarray` of shape `(ngrp,)`, the direct analogue of R's named numeric vector indexed by interval number.

**Alternative using pandas (for consistency with the rest of the codebase):**

```python
# If uniformity with pd.Series-based code is preferred:
itime_sum = pd.Series(itime).groupby(index - 1).sum().reindex(range(ngrp), fill_value=0.0).values
deaths    = pd.Series(status.astype(float)).groupby(index - 1).sum().reindex(range(ngrp), fill_value=0.0).values
```

The `reindex(..., fill_value=0.0)` call is the safety net for any accidentally empty bins, analogous to the `minlength` parameter of `np.bincount`.
