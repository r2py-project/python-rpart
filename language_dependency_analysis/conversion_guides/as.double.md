# Conversion Guide: `as.double` (R to Python)

---

## 1. Overview of `as.double` in R

`as.double` is a base R function that coerces its argument to a double-precision floating-point numeric vector (i.e., R's `double` type, equivalent to IEEE 754 64-bit floats). It is an alias for `as.numeric` and belongs to the family of type-coercion primitives in R.

**Key characteristics:**

- **Input:** Any R object — numeric scalars, integer vectors, logical vectors, character strings (if parseable), matrices, data frames, lists (when used together with `unlist`), or S3/S4 objects with defined coercion methods.
- **Output:** A flat, named or unnamed atomic `double` vector. If the input is a matrix or multi-dimensional array, the result is a flat column-major (Fortran-order) vector.
- **Behaviour with matrices:** `as.double(M)` flattens a matrix in column-major order. To obtain row-major order before flattening, the pattern `as.double(t(M))` (transpose first, then flatten) is common and appears in this codebase.
- **Behaviour with lists:** `as.double(unlist(lst))` first recursively flattens the list into an atomic vector and then coerces every element to double.
- **Behaviour with `NULL`:** Returns `numeric(0)`, a zero-length double vector.
- **Machine constants:** `as.double(.Machine$double.eps)` extracts the smallest representable double precision difference from 1, analogous to Python's `sys.float_info.epsilon` or `numpy.finfo(float).eps`.
- **Primary purpose in rpart:** All `as.double` calls in rpart appear immediately before `.Call(...)` invocations, serving as explicit type guarantees required by the C interface. The C functions expect contiguous `double` arrays; `as.double` ensures no implicit integer or other type is passed.

---

## 2. Contextual Usage Analysis

Across the four source files examined, every `as.double` call falls into one of five structurally distinct scenarios:

| Scenario | Representative call | Data type converted |
|---|---|---|
| **A — Flat numeric/integer vector** | `as.double(cost)`, `as.double(cp)` | 1-D numeric or integer vector |
| **B — Matrix (column-major flatten)** | `as.double(fit$splits)` | 2-D matrix flattened column-major |
| **C — Transposed matrix (row-major flatten)** | `as.double(t(init$y))`, `as.double(t(Y))` | 2-D matrix flattened row-major |
| **D — Unlisted named list** | `as.double(unlist(init$parms))`, `as.double(unlist(controls))` | Named list of scalars → flat vector |
| **E — Machine epsilon scalar** | `as.double(.Machine$double.eps)` | Machine-precision constant |

**Recurring pattern:** In every file the converted value is passed directly as an argument to a C-level `.Call(...)`. The conversion is not about mathematical transformation; it is a type-safety cast that guarantees the C function receives a `double *` buffer rather than an integer or list pointer.

**Scalar vs. vector:** Several calls produce single-element vectors (e.g., `as.double(cp)` when `cp` is a scalar, `as.double(.Machine$double.eps)`), but because R does not distinguish between scalars and length-1 vectors, the same function handles both. In Python the equivalent must handle both shapes as well — hence `numpy` is the correct choice over `float()`.

---

## 3. Python Conversion Strategy

**Primary library: `numpy`** (`import numpy as np`).

Rationale:

1. R vectors are inherently array-like; `numpy` arrays provide the same contiguous memory layout that C interfaces expect.
2. `numpy.ndarray.astype(np.float64)` (or `np.asarray(..., dtype=np.float64)`) is the direct semantic equivalent of `as.double`: it coerces any array-like input — including scalars, lists, and existing arrays — to 64-bit floats without unnecessary copies when the source is already the correct type.
3. Matrix transposition and flattening patterns map cleanly onto `numpy` operations (`array.T.ravel()` for row-major, `array.ravel()` for column-major).
4. `math.float` or `float()` are scalar-only and would require extra branching to handle vectorized inputs; `numpy` handles both transparently.

**General mapping table:**

| R pattern | Python / numpy equivalent |
|---|---|
| `as.double(x)` — flat vector | `np.asarray(x, dtype=np.float64).ravel()` |
| `as.double(M)` — matrix, column-major | `np.asarray(M, dtype=np.float64).ravel(order='F')` |
| `as.double(t(M))` — matrix, row-major | `np.asarray(M, dtype=np.float64).ravel(order='C')` |
| `as.double(unlist(lst))` — named list | `np.asarray(list(lst.values()), dtype=np.float64).ravel()` |
| `as.double(.Machine$double.eps)` | `np.finfo(np.float64).eps` |

---

## 4. Step-by-Step Conversion Examples

### 4.1 Scenario A — Flat numeric / integer vector

**Locations:** `pred.rpart.R :: pred.rpart` (line 27), `rpart.R :: rpart` (line 171), `xpred.rpart.R :: xpred.rpart` (lines 130, 132).

**Original R context:**

```r
# x is a numeric matrix of predictors (all entries already numeric)
as.double(x)

# cost / costs is a numeric vector of per-variable costs, default rep(1, nvar)
as.double(cost)

# cp is a numeric vector of complexity parameter values
as.double(cp)
```

These are 1-D numeric vectors (or matrices treated as flat buffers). `as.double` guarantees storage mode `double` before passing to `.Call`.

**Python equivalent:**

```python
import numpy as np

# For a 1-D array or list
x_double = np.asarray(x, dtype=np.float64).ravel()

cost_double = np.asarray(cost, dtype=np.float64).ravel()

cp_double = np.asarray(cp, dtype=np.float64).ravel()
```

**Explanation:**

- `np.asarray(..., dtype=np.float64)` performs a no-copy cast when the source is already `float64`, or allocates a new array otherwise — matching R's behaviour where `as.double` is a no-op when storage mode is already `double`.
- `.ravel()` without an `order` argument defaults to `'C'` (row-major), which is correct for 1-D inputs where ordering is irrelevant.
- If the downstream C wrapper expects a flat `double *` pointer, the `.ravel()` call ensures a contiguous 1-D buffer.

---

### 4.2 Scenario B — Matrix flattened in column-major (Fortran) order

**Locations:** `pred.rpart.R :: pred.rpart` (line 24).

**Original R context:**

```r
# fit$splits is a numeric matrix with columns: count, ncat, improve, index, adj
# as.double on a matrix in R flattens column-by-column (Fortran / column-major order)
as.double(fit$splits)
```

`fit$splits` is a named numeric matrix. R stores matrices column-major internally, so `as.double(M)` reads elements down each column in turn.

**Python equivalent:**

```python
import numpy as np

# splits is a 2-D numpy array with shape (n_splits, 5)
splits_double = np.asarray(fit_splits, dtype=np.float64).ravel(order='F')
```

**Explanation:**

- `order='F'` selects Fortran (column-major) traversal, exactly matching R's default matrix storage order.
- If `fit_splits` is already a `numpy` array of shape `(n, 5)`, `.ravel(order='F')` produces a 1-D array of length `n*5` reading column-by-column: all `count` values first, then all `ncat` values, etc.
- This distinction matters when the C code indexes the buffer with Fortran-style strides.

---

### 4.3 Scenario C — Matrix transposed then flattened (row-major order)

**Locations:** `rpart.R :: rpart` (line 167), `xpred.rpart.R :: xpred.rpart` (line 114).

**Original R context:**

```r
# init$y is a numeric matrix with shape (nobs, numy)
# t() transposes it to (numy, nobs), then as.double flattens column-major,
# producing elements in the order: [y[1,1], y[2,1], ..., y[nobs,1],
#                                    y[1,2], y[2,2], ..., y[nobs,2], ...]
# which is equivalent to row-major flattening of the *original* matrix.
as.double(t(init$y))

# Y is similarly a (nobs, numy) matrix
as.double(t(Y))
```

The transpose-then-flatten idiom is R's way of producing a row-major (C-order) serialisation of a matrix, since R's native flatten is column-major.

**Python equivalent:**

```python
import numpy as np

# init_y has shape (nobs, numy) — same layout as R's init$y
y_double = np.asarray(init_y, dtype=np.float64).ravel(order='C')

# Equivalently, explicit transpose then column-major flatten:
# y_double = np.asarray(init_y, dtype=np.float64).T.ravel(order='F')
```

**Explanation:**

- In numpy, `array.ravel(order='C')` reads elements row-by-row, producing the same byte sequence as `as.double(t(M))` in R.
- The explicit `np.asarray(init_y).T.ravel(order='F')` form is semantically identical and may aid readability when porting code that uses the `t()` idiom explicitly.
- Because numpy defaults to C order, `np.asarray(init_y, dtype=np.float64).ravel()` (no order argument) also works and is idiomatic.

---

### 4.4 Scenario D — Unlisted named list coerced to double vector

**Locations:** `rpart.R :: rpart` (lines 158, 163), `xpred.rpart.R :: xpred.rpart` (lines 117, 122).

**Original R context:**

```r
# init$parms is a named list such as list(prior = c(0.5, 0.5), loss = ..., split = 1L)
# unlist() recursively flattens to a named atomic vector, then as.double coerces
temp <- as.double(unlist(init$parms))
if (!length(temp)) temp <- 0    # guard for NULL parms

# controls is the result of rpart.control(), a named list of scalars:
#   list(minsplit=20, minbucket=7, cp=0.01, ...)
as.double(unlist(controls))
```

`unlist` recursively collapses a named list of scalars (and nested vectors) into a single atomic vector; `as.double` then ensures `double` storage mode.

**Python equivalent:**

```python
import numpy as np

# parms is a Python dict, e.g. {'prior': np.array([0.5, 0.5]), 'split': 1}
def unlist_to_double(d):
    """Flatten a (possibly nested) dict/list of scalars/arrays to float64 array."""
    values = []
    for v in d.values():
        if hasattr(v, '__iter__') and not isinstance(v, str):
            values.extend(np.asarray(v, dtype=np.float64).ravel())
        else:
            values.append(float(v))
    return np.array(values, dtype=np.float64)

temp = unlist_to_double(parms) if parms else np.array([0.0])  # guard for empty parms

# controls is a flat dict of scalar control parameters
controls_double = np.asarray(list(controls.values()), dtype=np.float64)
```

**Explanation:**

- R's `unlist` handles arbitrarily nested lists; the helper above handles the common rpart case where values are scalars or short numeric arrays.
- The `if (!length(temp)) temp <- 0` guard in R maps to the `if parms else np.array([0.0])` guard in Python — both pass a dummy single-element buffer to C when no parameters are present.
- For the `controls` dict (which contains only scalar values in `rpart.control`), a simple `list(controls.values())` suffices before passing to `np.asarray`.

---

### 4.5 Scenario E — Machine epsilon constant

**Locations:** `rpart.exp.R :: rpart.exp` (line 33).

**Original R context:**

```r
# .Machine$double.eps is the smallest positive floating-point number x
# such that 1 + x != 1 in double precision (approximately 2.22e-16).
# Passed as a scalar threshold to the C routine C_rpartexp2.
temp <- .Call(C_rpartexp2, as.double(dtimes), as.double(.Machine$double.eps))
```

`.Machine$double.eps` is a scalar machine constant. The `as.double` call is technically a no-op here (it is already a `double` scalar) but makes the type explicit for the C call.

**Python equivalent:**

```python
import numpy as np

eps = np.finfo(np.float64).eps   # equivalent to .Machine$double.eps ≈ 2.220446e-16

# Or, if a length-1 numpy array is required for the C interface:
eps_array = np.array([np.finfo(np.float64).eps], dtype=np.float64)
```

**Explanation:**

- `np.finfo(np.float64).eps` returns exactly the same value as R's `.Machine$double.eps` — both are the standard IEEE 754 machine epsilon for 64-bit doubles.
- `sys.float_info.epsilon` from the standard library returns the same numeric value but as a plain Python `float`; either is acceptable when only a scalar is needed.
- If the downstream ctypes or cffi C call expects a pointer to a `double`, wrap in `np.array([...], dtype=np.float64)` to obtain a numpy scalar with a buffer address.
