# Conversion Guide: `is.data.frame` (R to Python)

### 1. Overview of `is.data.frame` in R

`is.data.frame(x)` is a base-R predicate function that tests whether an object `x` belongs to the class `"data.frame"`. It accepts any R object as its single argument and returns a scalar logical value — `TRUE` if the object is a data frame, `FALSE` otherwise.

A data frame in R is a rectangular, list-like structure where every column may hold a different type (numeric, character, logical, factor, etc.) and all columns share the same number of rows. It is R's primary tabular data structure, closely analogous to a pandas `DataFrame` in Python.

`is.data.frame` does not coerce or modify its input; it is a pure type-check with no side effects.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/rpart.R`
**Function:** `rpart` (lines 4–20)

The `rpart` function signature is:

```r
function(formula, data, weights, subset, na.action = na.rpart, method,
         model = FALSE, x = FALSE, y = TRUE, parms, control, cost, ...)
```

The parameter `model` has a default value of `FALSE` (a scalar logical). However, the caller is permitted to pass a pre-built model frame (a data frame) directly as `model` — a shortcut that skips the internal call to `stats::model.frame`. The guard at line 9 detects this dual-use pattern:

```r
if (is.data.frame(model)) {
    m <- model       # caller supplied a ready-made model frame
    model <- FALSE
} else {
    # build the model frame from formula + data via stats::model.frame
    indx <- match(c("formula", "data", "weights", "subset"),
                  names(Call), nomatch = 0L)
    ...
    m <- eval.parent(temp)
}
```

Key observations:
- **Input type of `model`:** Either `FALSE` (logical scalar, the default) or a `data.frame` object. No other types appear in the branch.
- **Return value of `is.data.frame`:** A scalar `TRUE`/`FALSE` used directly as an `if` condition — this is a scalar boolean guard, not a vectorized predicate.
- **Consequence:** When `TRUE`, `model` is aliased to `m` and reset to `FALSE`; when `FALSE`, the model frame is constructed from scratch using the call's `formula`, `data`, `weights`, and `subset` arguments.
- **Recurring pattern:** The check is a simple "duck-typing" dispatch — the same parameter carries two semantically different values, and the type check routes to the correct code path.

---

### 3. Python Conversion Strategy

Because the check is a **scalar type-test** (not a vectorized operation over array elements), `numpy` and `scipy` are not appropriate here. The correct Python equivalent is:

**`isinstance(model, pd.DataFrame)`** from the **`pandas`** library.

This mirrors `is.data.frame` precisely:
- R's `data.frame` maps directly to `pandas.DataFrame` — both are tabular, column-heterogeneous structures.
- `isinstance` is the idiomatic Python scalar type predicate, returning a plain `bool`, just as `is.data.frame` returns a scalar logical.
- No vectorized library is needed because the result is used as a single `if`-condition, not applied element-wise across a collection.

---

### 4. Step-by-Step Conversion Examples

#### Example 1: Pre-supplied model frame guard in `rpart`

**Locations:**
- File: `rpart/R/rpart.R`
- Function: `rpart`
- Line: 9

**Original R Context:**

`model` is a parameter typed as either `FALSE` (logical) or a `data.frame`. The check short-circuits model-frame construction when a data frame is passed directly.

```r
# model: either FALSE (logical) or a data.frame
rpart <- function(formula, data, ..., model = FALSE) {
    if (is.data.frame(model)) {
        m <- model
        model <- FALSE
    } else {
        # build m via stats::model.frame(...)
        m <- eval.parent(temp)
    }
    # m is always a data.frame from this point onward
}
```

**Python Equivalent:**

```python
import pandas as pd

def rpart(formula, data=None, model=False, **kwargs):
    if isinstance(model, pd.DataFrame):
        m = model
        model = False
    else:
        # build m via the Python equivalent of stats::model.frame
        m = build_model_frame(formula, data, **kwargs)
    # m is always a pd.DataFrame from this point onward
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `is.data.frame(model)` | `isinstance(model, pd.DataFrame)` | Both return a scalar bool; no import beyond `pandas` is needed |
| `model = FALSE` (default) | `model = False` (default) | R's `FALSE` is Python's `False`; both are falsy in a boolean context |
| `data.frame` object | `pd.DataFrame` object | The canonical tabular structure in each language |

The translation is one-to-one. `isinstance` is preferred over `type(model) is pd.DataFrame` because it correctly handles subclasses of `pd.DataFrame` (e.g., `pd.DataFrame` subclasses used by some libraries), mirroring R's class-based `is.data.frame` which also returns `TRUE` for objects whose class vector includes `"data.frame"` anywhere in its inheritance chain.
