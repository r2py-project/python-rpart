# Conversion Guide: `table` (R to Python)

---

## 1. Overview of `table` in R

`table()` is a base R function that builds a contingency table of counts from one or more categorical variables (or objects coercible to factors). When given a single integer or factor vector, it returns a **named 1D integer array** whose names are the observed levels and whose values are the frequency counts for each level.

**Signature:**

```r
table(...,
      exclude = if (useNA == "no") c(NA, NaN),
      useNA = c("no", "ifany", "always"),
      dnn = list.names(...),
      deparse.level = 1)
```

Key behaviours relevant to this codebase:

- Inputs are coerced via `factor()` internally; only levels that **actually appear** in the data are represented in the output unless the input is already a `factor` with explicit levels.
- When a single vector is passed, the result is a 1D `table` (array of integers) with named elements.
- `table()` does **not** have a `levels` argument of its own. Passing `levels = 1:ngrp` through `...` treats `1:ngrp` as an additional variable to cross-classify, producing a 2D table — this is a known source of confusion in legacy rpart code (see Section 4).

---

## 2. Contextual Usage Analysis

Both calls appear inside the nested helper `drate2` in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`. The function computes per-interval hazard rates for the exponential splitting method used by `rpart.exp`.

**Common pattern.** The variable `index` (and `index2`) is produced by `unclass(cut(..., itable, include.lowest = TRUE))` and therefore holds **1-based integer interval indices** in the range `1:ngrp`. Both calls to `table` are used to count how many observations fall into each time interval so that a right-to-left cumulative sum (`rev(cumsum(rev(...)))`) can accumulate person-time correctly.

**Two distinct uses are present:**

| Line | Call | Purpose | Output shape |
|------|------|---------|--------------|
| 81 | `table(index)` | Count observations per interval. The code comment guarantees at least one observation in every interval, so no zero-filling is needed. | 1D named integer vector of length equal to the number of observed levels in `index` |
| 86 | `table(index2, levels = 1:ngrp)` | Count observations per interval for **start times**; the comment says "force the length of tab2". Because start times may not fall in every interval, some intervals can have zero counts and must still appear in the output so the downstream `cumsum` arithmetic aligns correctly with `ngrp`. | Intended: 1D named integer vector of length `ngrp`; see note below |

**Important note on line 86.** `table()` has no `levels` parameter. Passing `levels = 1:ngrp` through `...` treats it as a second cross-classifying variable, producing a **2D table** only when `length(index2) == ngrp`. In general these lengths differ, causing a runtime error. The correct intended behaviour — a 1D frequency table of length `ngrp` with zero-filled missing intervals — is achieved by pre-converting to a factor:

```r
table(factor(index2, levels = 1:ngrp))
```

This is the semantics that must be reproduced in Python.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**, specifically `numpy.bincount`.

`numpy.bincount(x, minlength)` directly replicates the semantics of R's `table()` on non-negative integer arrays:

- It counts occurrences of each integer value from `0` up to `max(x)` (or `minlength - 1`, whichever is larger).
- The `minlength` parameter zero-fills the output to at least that length — exactly what `factor(..., levels = 1:ngrp)` achieves in R.
- The result is a 1D `numpy.ndarray` of integers, analogous to R's named integer array.

Since `index` and `index2` are **1-based** in R (produced by `unclass(cut(...))`), they must be decremented by 1 before passing to `numpy.bincount` to convert to 0-based indexing.

`numpy` is preferred over `collections.Counter` or `pandas.value_counts` because:

- It returns a dense array in the correct shape for downstream vectorised arithmetic (`cumsum`, element-wise multiplication) without any further conversion.
- `minlength` provides the zero-filling equivalent of R's `factor(..., levels = ...)` in a single call.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Simple frequency count — `table(index)`

**Location:** `rpart/R/rpart.exp.R`, function `drate2`, line 81.

**Original R context.**

```r
# index: integer vector, 1-based, values in 1:ngrp
# Guaranteed to have at least one observation per interval.
tab1 <- table(index)
# tab1: named integer array of length == number of observed levels in index
# (guaranteed == ngrp by construction)
temp <- rev(cumsum(rev(tab1)))
```

- Input type: integer vector `index`, length `n`, values in `1:ngrp`.
- Output type: 1D integer array of length `ngrp`, all elements >= 1.

**Python equivalent.**

```python
import numpy as np

# index is a 1-based integer numpy array (values in 1..ngrp)
# Convert to 0-based and count occurrences
tab1 = np.bincount(index - 1, minlength=ngrp)
# tab1: numpy array of shape (ngrp,), dtype int64

temp = np.cumsum(tab1[::-1])[::-1]
```

**Explanation.**

| R | Python | Notes |
|---|--------|-------|
| `table(index)` | `np.bincount(index - 1, minlength=ngrp)` | Subtract 1 for 0-based indexing; `minlength=ngrp` ensures the array always has length `ngrp` even if all values are present |
| Named elements via `names(tab1)` | Array positions `0..ngrp-1` | Names are not needed downstream; positional alignment is sufficient |
| `rev(cumsum(rev(tab1)))` | `np.cumsum(tab1[::-1])[::-1]` | `[::-1]` reverses the array; `np.cumsum` is the vectorised equivalent of R's `cumsum` |

---

### 4.2 Frequency count with forced length — `table(index2, levels = 1:ngrp)`

**Location:** `rpart/R/rpart.exp.R`, function `drate2`, line 86.

**Original R context.**

```r
# index2: integer vector, 1-based, values in 1:ngrp (some intervals may be missing)
# ngrp: integer scalar, total number of time intervals
# The call is annotated "# force the length of tab2"
tab2 <- table(index2, levels = 1:ngrp)   # legacy / intent: 1D table of length ngrp
# Correct equivalent of the author's intent:
#   tab2 <- table(factor(index2, levels = 1:ngrp))
temp <- rev(cumsum(rev(tab2)))
```

- Input type: integer vector `index2`, length `n` (generally `n != ngrp`); integer scalar `ngrp`.
- Output type (intended): 1D integer array of length exactly `ngrp`, with zeros for unobserved intervals.
- The `levels = 1:ngrp` argument does **not** control factor levels in `table()`; the correct R idiom is `table(factor(index2, levels = 1:ngrp))`. The Python translation implements the correct intent.

**Python equivalent.**

```python
import numpy as np

# index2 is a 1-based integer numpy array (values in 1..ngrp, not all values need appear)
# minlength=ngrp guarantees zero-filling for unobserved intervals
tab2 = np.bincount(index2 - 1, minlength=ngrp)
# tab2: numpy array of shape (ngrp,), dtype int64, zeros where no start-time fell

temp = np.cumsum(tab2[::-1])[::-1]
```

**Explanation.**

| R (intended) | Python | Notes |
|---|--------|-------|
| `table(factor(index2, levels = 1:ngrp))` | `np.bincount(index2 - 1, minlength=ngrp)` | `minlength=ngrp` is the direct equivalent of `factor(..., levels = 1:ngrp)` — both force the output length to `ngrp` and zero-fill absent intervals |
| `rev(cumsum(rev(tab2)))` | `np.cumsum(tab2[::-1])[::-1]` | Identical pattern to Usage 1; produces right-to-left cumulative sums |
| Implicit zero for unobserved levels | `minlength=ngrp` | The critical difference from a simple `table(index2)` / `np.bincount(index2 - 1)`: without length enforcement, downstream alignment with `ilength` (length `ngrp`) would be broken |

**Key nuance — the legacy `levels` argument.** The R call `table(index2, levels = 1:ngrp)` is a legacy construct that only avoids a runtime error if `length(index2) == ngrp` by coincidence. When translating to Python, do **not** attempt to replicate the 2D-table interpretation; implement the author's stated intent (the comment reads "force the length of tab2") using `np.bincount(..., minlength=ngrp)`.
