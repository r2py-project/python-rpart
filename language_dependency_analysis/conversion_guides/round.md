### 1. Overview of `round` in R

`round(x, digits = 0)` rounds the numeric value or vector `x` to the specified number of decimal places given by `digits`. When `digits` is positive, rounding is to that many places after the decimal point; when `digits` is zero (the default), rounding is to the nearest integer; when negative, rounding is to powers of ten to the left of the decimal point. R's `round` is fully vectorized: it accepts scalars, vectors, matrices, and arrays and returns an object of the same shape and type. R uses "round half to even" (banker's rounding) for ties (e.g., `round(0.5)` returns `0`, `round(1.5)` returns `2`).

---

### 2. Contextual Usage Analysis

Across all three files, `round` is used in three distinct roles:

**Role A — Display rounding of numeric vectors/matrices with an explicit `digits` argument (`roc.rpart.R` lines 71-75 and `summary.rpart.R` lines 106-107):**
In both places the result of `round` is immediately passed to `format()` for string formatting. The inputs are numeric vectors or single-column matrices built from division operations (ratios, proportions, model split statistics). The explicit `digits` argument is always an integer literal written with the `L` suffix (`3L`, `2L`) to signal integer type. The rounding is purely cosmetic — it controls the precision displayed to the user.

**Role B — Integer-valued parameter default computation (`rpart.control.R` line 2):**
Here `round(minsplit/3)` appears in a function signature as the default expression for `minbucket`. `minsplit` is an integer scalar (default `20L`), so `minsplit/3` is a numeric scalar. Calling `round` with no `digits` argument (defaulting to `0`) produces a numeric scalar rounded to the nearest integer, which serves as the default bucket size. This is a scalar-only context.

**Role C — Percentage rounding of a named numeric vector (`summary.rpart.R` line 26):**
`round(100 * temp/sum(temp))` normalizes variable importance weights to percentages and rounds each to the nearest integer. `temp` is a named numeric vector (`x$variable.importance`). No `digits` argument means the result is a named integer-valued numeric vector, which is then printed. This is a vectorized operation over a named vector.

Recurring patterns: (1) `round` with `digits` for display/reporting, (2) `round` without `digits` for integer computation. In all vector cases the input is either a plain numeric vector or a single-column numeric matrix.

---

### 3. Python Conversion Strategy

`numpy.round` (also accessible as `numpy.around`) is the correct primary equivalent for all usages found in this CSV. The reasons are:

- R's `round` is inherently vectorized; `numpy.round` applies element-wise over arrays of any shape and returns an array of the same shape, matching R's semantics exactly.
- For the scalar use case in `rpart.control.R`, `numpy.round` works on plain Python floats as well and returns a scalar-compatible `numpy.float64`, which can be safely cast to `int` when an integer is needed.
- The `decimals` keyword of `numpy.round` maps directly to R's `digits` argument.
- `math.round` (Python built-in) also implements banker's rounding for scalars, but cannot handle arrays. `numpy.round` handles both scalars and arrays uniformly, making it the single correct choice.
- For the percentage rounding case (`summary.rpart.R` line 26), the result should be cast to integer (`numpy.int64` or Python `int`) to exactly match R's behavior of producing integer values that are then printed without decimal points.

One important caveat: both R's `round` and Python's `numpy.round` / built-in `round` use "round half to even" (banker's rounding), so tie-breaking behavior is consistent.

---

### 4. Step-by-Step Conversion Examples

#### Pattern A1 — Display rounding of numeric vectors/matrices to 2 or 3 decimal places, wrapped in `format()`

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/roc.rpart.R`, function `roc.rpart`, lines 71-75
- `/groups/jli9/Yufei/python-rpart/rpart/R/summary.rpart.R`, function `summary.rpart`, lines 106-107

**Original R Context:**

`cutoffs` is a numeric vector (built from `sort(unique(...))`, possibly containing `NA`). `sensitivity`, `specificity`, `pospred`, `negpred` are numeric column matrices of shape `(cutoff.n, 1)`, populated by ratio computations inside a loop. `agree` and `adj` are numeric vectors extracted as columns from `x$splits`. All are rounded to a fixed number of decimal places and immediately passed to `format()`.

```r
# roc.rpart.R lines 71-75
data.frame(
    cutoffs     = format(round(cutoffs, 3L)),
    sensitivity = format(round(sensitivity, 2L)),
    specificity = format(round(specificity, 2L)),
    pospred     = format(round(pospred, 2L)),
    negpred     = format(round(negpred, 2L))
)

# summary.rpart.R lines 106-107
" agree=", format(round(agree, 3L)),
", adj=",  format(round(adj,   3L)),
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# --- roc.rpart equivalent ---
# cutoffs: 1-D numpy array (float64), may contain np.nan
# sensitivity, specificity, pospred, negpred: numpy arrays of shape (cutoff_n, 1)

cutoffs_rounded     = np.round(cutoffs, decimals=3)
sensitivity_rounded = np.round(sensitivity, decimals=2)
specificity_rounded = np.round(specificity, decimals=2)
pospred_rounded     = np.round(pospred, decimals=2)
negpred_rounded     = np.round(negpred, decimals=2)

# format() in R pads values to uniform width for display; use Python f-strings or
# numpy's format machinery when building display strings.
# For constructing a DataFrame equivalent to R's data.frame output:
result = pd.DataFrame({
    "cutoffs":     [f"{v:.3f}" if not np.isnan(v) else "NA" for v in cutoffs_rounded],
    "sensitivity": [f"{v:.2f}" for v in sensitivity_rounded.flatten()],
    "specificity": [f"{v:.2f}" for v in specificity_rounded.flatten()],
    "pospred":     [f"{v:.2f}" for v in pospred_rounded.flatten()],
    "negpred":     [f"{v:.2f}" for v in negpred_rounded.flatten()],
})

# --- summary.rpart surrogate splits equivalent ---
# agree, adj: 1-D numpy arrays (float64), extracted from splits matrix column
agree_rounded = np.round(agree, decimals=3)
adj_rounded   = np.round(adj,   decimals=3)

for s, ag, ad in zip(sname, agree_rounded, adj_rounded):
    print(f"      {s:<20} agree={ag:.3f}, adj={ad:.3f}")
```

**Explanation:**

- `round(x, nL)` in R becomes `np.round(x, decimals=n)` in Python. The `L` integer suffix in R (e.g., `3L`, `2L`) is purely a type annotation to ensure integer type; in Python the plain integer `3` or `2` is passed directly.
- R matrices of shape `(n, 1)` correspond to numpy arrays of shape `(n, 1)`; calling `.flatten()` converts them to 1-D arrays for iteration, mirroring how R drops the matrix dimension when formatting column-by-column.
- R's `format(round(...))` does two things: rounds and then pads/aligns the string representation. In Python, `f"{v:.3f}"` handles both rounding for display and fixed-width decimal formatting. When the exact column-width alignment of R's `format` is needed, `f"{v:>{width}.{decimals}f}"` can be used.
- `NA` in R numeric vectors corresponds to `np.nan` in numpy. The `np.round(np.nan)` call returns `np.nan`, which must be handled separately when building string representations.

---

#### Pattern B — Scalar integer computation as a default parameter value (no `digits` argument)

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.control.R`, function `rpart.control`, line 2

**Original R Context:**

`minsplit` is an integer scalar (default `20L`). `minbucket` is computed as the default argument expression `round(minsplit/3)`. Since `digits` defaults to `0`, the result is the numeric scalar `minsplit/3` rounded to the nearest integer. In R, dividing two integers produces a `numeric` (float), so `round` converts it back to a "round" numeric value (not strictly `integer` class, but whole-valued).

```r
rpart.control <- function(minsplit = 20L,
                          minbucket = round(minsplit / 3),
                          ...)
```

**Python Equivalent:**

```python
import numpy as np

def rpart_control(minsplit=20, minbucket=None, cp=0.01,
                  maxcompete=4, maxsurrogate=5, usesurrogate=2,
                  xval=10, surrogatestyle=0, maxdepth=30):
    # Replicate R's default: minbucket = round(minsplit / 3)
    if minbucket is None:
        minbucket = int(np.round(minsplit / 3))
    # ... rest of the function
```

**Explanation:**

- R allows default argument expressions to reference other parameters (`minbucket = round(minsplit/3)`). Python does not evaluate default expressions at call time with access to sibling parameters, so the canonical Python translation is to use `None` as the sentinel and compute the derived default inside the function body.
- `round(minsplit/3)` with no `digits` rounds to 0 decimal places (nearest integer). In Python, `np.round(minsplit / 3)` produces a `numpy.float64` whole number (e.g., `6.0` when `minsplit=20`); wrapping with `int()` converts it to a plain Python `int`, which is the most natural equivalent of R's integer-valued result and is what downstream C code expects as a count.
- Alternatively, Python's built-in `round(minsplit / 3)` works identically for this scalar case and avoids a numpy import. Both use banker's rounding. The numpy form is preferred here for consistency with the vectorized patterns above.

---

#### Pattern C — Vectorized rounding of a named numeric vector to integers for percentage display (no `digits` argument)

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/summary.rpart.R`, function `summary.rpart`, line 26

**Original R Context:**

`temp` is `x$variable.importance`, a named numeric vector whose names are predictor variable names and whose values are raw importance scores (positive numerics). The expression `100 * temp/sum(temp)` normalizes these to percentages; `round(...)` with no `digits` argument rounds each element to the nearest integer. The result is a named numeric vector of integer-valued percentages, filtered to positive values and printed.

```r
temp <- round(100 * temp / sum(temp))
if (any(temp > 0)) {
    cat("\nVariable importance\n")
    print(temp[temp > 0])
}
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# variable_importance: pandas Series with predictor names as index, float64 values
# (mirrors R's named numeric vector)

temp = variable_importance
temp = np.round(100 * temp / temp.sum()).astype(int)  # pandas Series, int dtype

positive_mask = temp > 0
if positive_mask.any():
    print("\nVariable importance")
    print(temp[positive_mask].to_string())
```

**Explanation:**

- R's named numeric vector maps naturally to a `pandas.Series` with a string index (the variable names). Arithmetic on a Series (`100 * temp / temp.sum()`) is element-wise and preserves the index, matching R's behavior.
- `np.round(series)` (or equivalently `series.round(0)`) applies banker's rounding element-wise over the Series and returns a Series of `float64` values that are whole numbers. Chaining `.astype(int)` converts to integer dtype, replicating the practical effect of R's `round(..., digits=0)` which produces numerics indistinguishable from integers.
- R's `temp[temp > 0]` logical subsetting maps to `temp[positive_mask]` with a boolean Series mask in pandas.
- R's `print` for named numeric vectors outputs names above values in an aligned grid. `Series.to_string()` produces a similar key-value listing. For exact formatting fidelity, `print(temp[positive_mask].to_string())` is the appropriate call.
