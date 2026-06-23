# Conversion Guide: `is.numeric` in R

## 1. Overview of `is.numeric` in R

`is.numeric(x)` is a base R predicate function that tests whether an object is of a numeric type. It returns a single logical scalar `TRUE` or `FALSE`.

In R, `is.numeric()` returns `TRUE` for objects whose storage mode is `"double"` or `"integer"`, and `FALSE` for all other types including characters, logicals, factors, complex numbers, and S3/S4 objects that have had their class overridden to strip numeric inheritance. This means both plain integers (e.g., `1L`) and floating-point doubles (e.g., `1.5`) pass the test.

A key nuance: `is.numeric()` returns `FALSE` for objects of class `"factor"` even though factors have an underlying integer storage mode, because the `"factor"` class removes numeric inheritance.

**Signature:**
```r
is.numeric(x)
```

- **Input:** any R object `x`
- **Output:** a single logical scalar (`TRUE` or `FALSE`)

## 2. Contextual Usage Analysis

Across the four call sites in the rpart source, `is.numeric` is used exclusively as an **input validation guard** — it appears inside `if (!is.numeric(...))` or `if (!is.numeric(...) || ...)` conditions that raise an error when the check fails. No site uses the return value for branching into two valid code paths; all uses are defensive type assertions.

Two distinct argument types appear:

- **A vector argument (`x`):** In `formatg.R` and `rpart.matrix.R`, `is.numeric` is called on `x`, which is expected to be a numeric vector (or matrix, in the case of `formatg`). The check ensures the function receives a properly typed input before performing numeric operations such as `sprintf` formatting or coercion via `as.numeric()`.

- **A scalar argument (`shrink`):** In `rpart.exp.R` and `rpart.poisson.R`, `is.numeric` is called on `shrink`, a parameter extracted from the user-supplied `parms` list. The check is combined with a range check (`shrink < 0L`) to validate that `shrink` is a non-negative number.

The pattern is identical in both scalar cases:
```r
if (!is.numeric(shrink) || shrink < 0L)
    stop("Invalid shrinkage value")
```

## 3. Python Conversion Strategy

The appropriate Python equivalent is **`isinstance(x, (int, float, np.integer, np.floating))`** for scalar validation, and **checking the `dtype` of a NumPy array or pandas Series** for vector/array validation.

Rationale:

- Python has no single built-in function that maps directly to R's `is.numeric()`. The closest conceptual match depends on the data container in use.
- For scalar values (the `shrink` use case), a simple `isinstance` check against Python's numeric tower (`int`, `float`) and NumPy's scalar types (`np.integer`, `np.floating`) covers all realistic inputs.
- For array/vector values (the `x` use case with NumPy arrays or pandas DataFrames), checking `np.issubdtype(arr.dtype, np.number)` is the idiomatic equivalent, as it mirrors R's broad "double or integer" definition.
- `math` module functions are not appropriate here since the use cases involve type-checking (not computation), and the data involved in rpart may be arrays.

## 4. Step-by-Step Conversion Examples

### 4.1 Numeric Vector / Matrix Type Guard

**Locations:** `formatg.R` — function `formatg` (line 6); `rpart.matrix.R` — function `rpart.matrix` (line 21)

**Original R Context:**

In `formatg`, `x` is a numeric vector or numeric matrix passed by the caller. The guard fires before any formatting operation:

```r
# formatg.R, line 6
# x: numeric vector or numeric matrix (double or integer storage mode)
# Returns: character vector (or character matrix)
if (!is.numeric(x)) stop("'x' must be a numeric vector")
```

In `rpart.matrix`, `x` is one column of a model frame, tested inside a `lapply` to decide whether coercion is needed:

```r
# rpart.matrix.R, lines 18-24
# x: a single column of a data.frame (could be character, factor, logical, or numeric)
# Returns: numeric vector (coerced if necessary)
frame[] <- lapply(frame,
                  function(x) {
                      if (is.character(x)) as.numeric(factor(x))
                      else if (!is.numeric(x))  as.numeric(x)
                      else x
                  })
```

**Python Equivalent:**

For a NumPy array (the typical Python analog of an R numeric vector or matrix):

```python
import numpy as np

# formatg equivalent guard
def formatg(x, digits=6):
    if not np.issubdtype(np.asarray(x).dtype, np.number):
        raise TypeError("'x' must be a numeric array")
    fmt = f"%.{digits}g"
    temp = np.vectorize(lambda v: f"{v:{fmt[1:]}}")(x)
    return temp

# rpart_matrix equivalent coercion logic
def coerce_column(x):
    """
    x: a pandas Series or 1-D array representing one DataFrame column.
    Returns a numeric numpy array.
    """
    import pandas as pd
    s = pd.Series(x)
    if s.dtype == object and s.apply(lambda v: isinstance(v, str)).all():
        # character -> numeric via categorical codes (mirrors as.numeric(factor(x)))
        return s.astype("category").cat.codes.to_numpy(dtype=float)
    elif not np.issubdtype(s.dtype, np.number):
        return pd.to_numeric(s, errors="coerce").to_numpy()
    else:
        return s.to_numpy()
```

**Explanation:**

- `np.issubdtype(arr.dtype, np.number)` returns `True` when the dtype is any numeric kind (integers, floats, complex), directly mirroring R's `is.numeric()` for arrays. Note that it does NOT return `True` for boolean (`np.bool_`) arrays, consistent with R's `is.numeric(TRUE)` returning `FALSE`.
- `np.asarray(x)` is used first so the check works on plain Python lists and scalars as well as NumPy arrays.
- The `rpart.matrix` coercion branch uses `pd.to_numeric(..., errors="coerce")` as the broad-catch equivalent of R's `as.numeric(x)`.

---

### 4.2 Scalar Parameter Type + Range Guard

**Locations:** `rpart.exp.R` — function `rpart.exp` (line 126); `rpart.poisson.R` — function `rpart.poisson` (line 32)

**Original R Context:**

`shrink` is extracted from the user-supplied `parms` list. It is expected to be a non-negative numeric scalar:

```r
# rpart.exp.R, line 126 (identical pattern in rpart.poisson.R, line 32)
# shrink: scalar extracted from parms list; could be any R object if user passes wrong type
# Returns: nothing — raises an error on invalid input
if (!is.numeric(shrink) || shrink < 0L)
    stop("Invalid shrinkage value")
```

**Python Equivalent:**

```python
import numbers

# shrink: value extracted from a parms dict; may be int, float, or any other type
def validate_shrink(shrink):
    """
    Raises ValueError if shrink is not a non-negative real number.
    Mirrors R: if (!is.numeric(shrink) || shrink < 0L) stop(...)
    """
    if not isinstance(shrink, (int, float)) or isinstance(shrink, bool):
        raise ValueError("Invalid shrinkage value")
    if shrink < 0:
        raise ValueError("Invalid shrinkage value")
```

Or as an inline guard (the more direct translation style used in rpart):

```python
import numpy as np

# Inline guard equivalent, suitable for use inside rpart_exp / rpart_poisson
if not isinstance(shrink, (int, float, np.integer, np.floating)) \
        or isinstance(shrink, bool) \
        or shrink < 0:
    raise ValueError("Invalid shrinkage value")
```

**Explanation:**

- R's `is.numeric(shrink)` returns `TRUE` for both integer and double scalars. In Python, the equivalent covers `int`, `float`, `np.integer`, and `np.floating`.
- `bool` must be **explicitly excluded**: in Python `isinstance(True, int)` returns `True` because `bool` is a subclass of `int`, but in R `is.numeric(TRUE)` returns `FALSE`. Excluding `bool` maintains semantic parity with R.
- The short-circuit `||` in R (which skips the range check if the type is already wrong) maps directly to Python's `or`, preserving the same left-to-right evaluation order.
- The range comparison `shrink < 0L` in R uses an integer literal `0L`, but the comparison semantics are identical to Python's `shrink < 0`.
- The `numbers.Number` abstract base class from the Python standard library is an alternative for the `isinstance` check, but it also matches `complex` numbers, which R's `is.numeric()` does not. The explicit `(int, float, np.integer, np.floating)` tuple is therefore more precise.
