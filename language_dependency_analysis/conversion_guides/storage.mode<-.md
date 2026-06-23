# Conversion Guide: `storage.mode<-` in R

---

## 1. Overview of `storage.mode<-` in R

`storage.mode<-` is a replacement function in R that modifies the **internal storage type** of an existing object in-place without changing its structure (dimensions, names, class attributes, etc.). It is the assignment form of `storage.mode()`.

**Signature:**
```r
storage.mode(x) <- value
```

- `x`: Any R object — a vector, matrix, array, or data structure backed by an atomic type.
- `value`: A character string naming the target storage type, such as `"double"`, `"integer"`, `"logical"`, `"character"`, etc.

**Behaviour:**
- The object `x` is coerced to the specified low-level type. For `"double"`, this is equivalent to casting all elements to IEEE 754 64-bit floating-point representation.
- Unlike `as.double()`, `storage.mode<-` does **not** strip matrix dimensions or names: a 2D matrix remains a 2D matrix with all its attributes intact after the coercion.
- It operates in-place in the sense that the variable is reassigned in the calling environment — no new high-level R object is created.

**Typical inputs:** Numeric vectors, integer vectors, or matrices that need to be retyped before being passed to compiled (C/Fortran) code via `.Call` or `.C`.

**Typical outputs:** The same object, structurally unchanged, but with all elements stored as the new primitive type.

---

## 2. Contextual Usage Analysis

All three usages appear consecutively at lines 114-116 of `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`, inside the function `xpred.rpart`. They form a type-normalisation block immediately before a `.Call` to the C routine `C_xpred`:

```r
if (is.matrix(Y))  Y <- as.double(t(Y)) else storage.mode(Y) <- "double"
storage.mode(X) <- "double"
storage.mode(wt) <- "double"
```

**Data types involved:**

| Variable | Origin | Shape | Purpose |
|---|---|---|---|
| `Y` | `fit$y` or `model.extract(m, "response")` | Vector or matrix (rows = observations, cols = response columns) | Response variable |
| `X` | `fit$x` or `rpart.matrix(m)` | 2D numeric matrix (rows = observations, cols = predictor variables) | Predictor matrix |
| `wt` | `fit$wt` or `model.extract(m, "weights")`, defaulting to `rep(1, nobs)` | Numeric vector of length `nobs` | Observation weights |

**Recurring pattern:** The sole purpose of all three calls is to guarantee that the arrays are stored as 64-bit doubles before being handed off to a C function. The C routine `C_xpred` expects raw `double*` pointers, so this coercion is a safety step to avoid passing integer or logical storage where the C code assumes double.

The `Y` case is slightly different: when `Y` is already a matrix it is transposed and flattened via `as.double(t(Y))` (column-major to row-major reordering for C); when it is a plain vector `storage.mode(Y) <- "double"` is used instead to preserve its vector form.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

NumPy is the direct Python equivalent for R's vectorised numeric arrays. NumPy arrays carry an explicit `dtype` that maps directly to R's storage modes:

| R storage mode | NumPy dtype |
|---|---|
| `"double"` | `numpy.float64` |
| `"integer"` | `numpy.int32` / `numpy.int64` |
| `"logical"` | `numpy.bool_` |

The conversion is performed with `numpy.asarray(x, dtype=np.float64)` or `x.astype(np.float64)`. NumPy's `astype` and `asarray` preserve array shape (dimensions) exactly as `storage.mode<-` preserves matrix dimensions in R, making them the closest semantic equivalents.

**Why not `math` or plain Python casts?** R vectors and matrices are inherently multi-element, and `storage.mode<-` acts element-wise across the entire structure. `math.fabs` and Python's built-in `float()` only handle scalars. NumPy's element-wise casting is the correct counterpart.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Coercing a Response Vector / Matrix to double — `Y`

**Locations:** `xpred.rpart.R`, function `xpred.rpart`, line 114.

**Original R Context:**

- Input type: `Y` is either a numeric vector (length `nobs`) or a numeric matrix (`nobs` rows x `numy` columns). Its storage mode may be integer if the response was integral (e.g., class labels stored as integers).
- Return type: `Y` retains its original shape; all elements become `double`.

```r
# R — type normalisation before passing Y to C
if (is.matrix(Y))  Y <- as.double(t(Y)) else storage.mode(Y) <- "double"
```

When `Y` is a matrix, R additionally transposes it so that rows become contiguous in memory (C row-major order). When `Y` is a plain vector the transpose step is unnecessary and `storage.mode<-` alone suffices.

**Python Equivalent:**

```python
import numpy as np

# Y is either a 1-D numpy array (vector) or a 2-D numpy array (matrix).
if Y.ndim == 2:
    # Transpose to row-major (C order) and flatten to a 1-D double array,
    # mirroring R's as.double(t(Y)) which lays out rows contiguously for C.
    Y = np.ascontiguousarray(Y.T, dtype=np.float64).ravel(order='F')
    # Alternatively, if the downstream C code expects a flat buffer:
    # Y = Y.astype(np.float64, order='C').ravel()
else:
    Y = np.asarray(Y, dtype=np.float64)
```

**Explanation:**
- `np.asarray(Y, dtype=np.float64)` is the direct equivalent of `storage.mode(Y) <- "double"` for a 1-D array: it returns a view (zero-copy) if `Y` is already `float64`, or a new array with the cast applied element-wise otherwise. Shape and length are preserved.
- For the matrix branch, R's `t(Y)` transposes the matrix and `as.double(...)` then reads it in column-major (Fortran) order, producing a flat C-order double buffer. The NumPy equivalent flattens the transposed array in Fortran order (`order='F'`) to replicate the same memory layout.
- `copy=False` is implicit in `np.asarray`; use `.astype(np.float64, copy=False)` to be explicit about avoiding unnecessary copies.

---

### 4.2 Coercing the Predictor Matrix to double — `X`

**Locations:** `xpred.rpart.R`, function `xpred.rpart`, line 115.

**Original R Context:**

- Input type: `X` is always a 2-D numeric matrix (shape `nobs x nvar`), produced by `rpart.matrix()` or extracted directly from `fit$x`. Some predictor columns may be integer-coded (e.g., categorical variables encoded as integers).
- Return type: `X` remains a 2-D matrix with the same dimensions and column names; all elements are stored as `double`.

```r
# R
storage.mode(X) <- "double"
```

**Python Equivalent:**

```python
import numpy as np

# X is a 2-D numpy array of shape (nobs, nvar).
X = np.asarray(X, dtype=np.float64)
```

**Explanation:**
- `np.asarray(X, dtype=np.float64)` reinterprets every element as `float64` while preserving the 2-D shape `(nobs, nvar)`, exactly as `storage.mode(X) <- "double"` preserves the matrix dimensions in R.
- If `X` originates as a pandas `DataFrame`, convert first with `X.to_numpy(dtype=np.float64)` or `np.asarray(X, dtype=np.float64)`.
- If `X` is already `float64`, `np.asarray` returns the original array without copying (zero overhead).

---

### 4.3 Coercing the Weight Vector to double — `wt`

**Locations:** `xpred.rpart.R`, function `xpred.rpart`, line 116.

**Original R Context:**

- Input type: `wt` is a 1-D numeric vector of length `nobs`, either extracted from the model frame or defaulting to `rep(1, nobs)` (an integer vector of ones when created by `rep`).
- Return type: `wt` remains a 1-D vector of length `nobs`; all elements are stored as `double`.

```r
# R
storage.mode(wt) <- "double"
```

**Python Equivalent:**

```python
import numpy as np

# wt is a 1-D numpy array of length nobs.
wt = np.asarray(wt, dtype=np.float64)
```

**Explanation:**
- Identical strategy to the `X` conversion. The only difference is that `wt` is 1-D.
- When `wt` was constructed as `np.ones(nobs, dtype=int)` (the Python counterpart of R's `rep(1, nobs)`), this call converts it to `float64` exactly as R's `storage.mode(wt) <- "double"` would.
- Using `np.ones(nobs, dtype=np.float64)` from the outset is also acceptable and avoids the coercion entirely, but the explicit `asarray` call is the direct translation of the R pattern and is safer when the origin of `wt` is not fully controlled.

---

### 4.4 Complete Normalisation Block

For convenience, the full three-line R type-normalisation block translates to:

**R (lines 114-116):**
```r
if (is.matrix(Y))  Y <- as.double(t(Y)) else storage.mode(Y) <- "double"
storage.mode(X) <- "double"
storage.mode(wt) <- "double"
```

**Python:**
```python
import numpy as np

if Y.ndim == 2:
    Y = np.ascontiguousarray(Y.T, dtype=np.float64).ravel(order='F')
else:
    Y = np.asarray(Y, dtype=np.float64)

X = np.asarray(X, dtype=np.float64)
wt = np.asarray(wt, dtype=np.float64)
```

These three lines ensure that `Y`, `X`, and `wt` are all backed by contiguous `float64` buffers, equivalent to what R guarantees before the `.Call` to `C_xpred`.
