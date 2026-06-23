# Conversion Guide: `diag` in R

## 1. Overview of `diag` in R

R's `diag()` is a polymorphic function whose behaviour depends entirely on the type and shape of its argument:

| Argument type | What `diag` does |
|---|---|
| Single positive integer `n` | Creates an `n x n` identity matrix |
| Numeric vector of length `> 1` | Creates a square diagonal matrix whose diagonal entries are the vector elements |
| Matrix | Extracts the diagonal elements and returns them as a vector |
| Assignment form `diag(m) <- v` | Replaces the diagonal of matrix `m` in-place with the values in vector `v` |

All four behaviours appear in the rpart source files covered by this guide.

---

## 2. Contextual Usage Analysis

Five call sites appear across three source files. They map to three distinct behavioural modes:

### Mode A — Identity matrix creation (scalar integer argument)

Used twice in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.class.R` (lines 13 and 32). `numclass` is a single positive integer (the number of classification classes). The resulting `numclass x numclass` identity matrix is immediately used in arithmetic to build a loss matrix:

- Line 13: `matrix(rep(1, numclass^2) - diag(numclass), numclass)` — subtracts the identity from a matrix of ones to get a "ones-except-diagonal-zeros" matrix.
- Line 32: `temp2 <- 1 - diag(numclass)` — same idea, scalar `1` is broadcast over the whole identity matrix.

### Mode B — Diagonal extraction from a matrix (matrix argument)

Used once at `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.class.R` line 38:

```r
if (any(diag(temp2) != 0))
```

`temp2` is a `numclass x numclass` matrix. `diag(temp2)` extracts its diagonal as a numeric vector so the validation check can be applied.

### Mode C — Diagonal matrix creation from a vector (vector argument)

Used once at `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R` line 254:

```r
temp <- rpfit$dnode[, 4L + (1L:numclass)] %*% diag(init$parms$prior/temp)
```

`init$parms$prior/temp` is an element-wise division of two vectors of length `numclass`, producing a numeric vector. `diag()` promotes that vector into a `numclass x numclass` diagonal matrix, which is then right-multiplied against a data matrix. The effect is column-wise scaling.

### Mode D — Diagonal assignment (replacement form)

Used once at `/groups/jli9/Yufei/python-rpart/rpart/R/zzz.R` line 41:

```r
diag(desc) <- TRUE
```

`desc` is an `n x n` boolean matrix initialised to `FALSE`. The assignment form sets all `n` diagonal entries to `TRUE` in-place, marking each node as a descendant of itself.

---

## 3. Python Conversion Strategy

The chosen library is **NumPy**. R's `diag` operates on matrices (2-D arrays) and vectors (1-D arrays) in a vectorised, in-place-capable way. NumPy provides direct equivalents for all four modes:

| R mode | NumPy equivalent |
|---|---|
| `diag(n)` — identity | `numpy.eye(n)` |
| `diag(v)` — diagonal matrix from vector | `numpy.diag(v)` |
| `diag(M)` — extract diagonal from matrix | `numpy.diag(M)` |
| `diag(M) <- v` — assign diagonal in-place | `numpy.fill_diagonal(M, v)` |

`numpy.diag` is itself overloaded on rank in exactly the same way R's `diag` is overloaded on type — a 1-D array input produces a 2-D diagonal matrix, and a 2-D array input extracts the diagonal. The only mode with no direct analogue is the assignment form, which maps to `numpy.fill_diagonal` (in-place, no copy).

The identity-matrix case deserves special attention: `numpy.eye(n)` returns a `float64` array by default. For boolean contexts (Mode D) `numpy.fill_diagonal` is used directly without going through `eye`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Mode A — Identity matrix (scalar input)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class`, lines 13 and 32.

**Original R Context:**

`numclass` is a positive integer. `diag(numclass)` returns an `numclass x numclass` float matrix with ones on the diagonal and zeros elsewhere. It is immediately used in subtraction:

```r
# Line 13: inside list initialisation
loss = matrix(rep(1, numclass^2) - diag(numclass), numclass)

# Line 32: standalone assignment
temp2 <- 1 - diag(numclass)
```

Both produce a square matrix that is all-ones except for zeros on the diagonal (a classic "all classes penalise each other equally" loss matrix).

**Python Equivalent:**

```python
import numpy as np

# Line 13 equivalent
loss = np.ones((numclass, numclass)) - np.eye(numclass)

# Line 32 equivalent
temp2 = 1 - np.eye(numclass)
```

**Explanation:**

- `np.eye(numclass)` is the direct counterpart of R's `diag(numclass)`. Both produce an `n x n` identity matrix.
- R's `1 - diag(numclass)` broadcasts the scalar `1` over the whole matrix; NumPy does the same via standard broadcasting rules.
- In R, `matrix(rep(1, numclass^2) - diag(numclass), numclass)` creates a flat vector of ones, subtracts the identity (which is also flattened element-wise), then reshapes into a matrix. The NumPy version avoids that indirection by operating directly on 2-D arrays, producing an identical result.
- No import beyond `numpy` is required.

---

### 4.2 Mode B — Extract diagonal from a matrix (matrix input)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class`, line 38.

**Original R Context:**

`temp2` is a `numclass x numclass` numeric matrix (a loss matrix supplied by the user). `diag(temp2)` returns a numeric vector of length `numclass` containing the main-diagonal entries. The result is used only for a validation check:

```r
temp2 <- matrix(temp2, ncol = numclass)   # reshape user input into matrix
if (any(diag(temp2) != 0))
    stop("Loss matrix must have zero on diagonals")
```

**Python Equivalent:**

```python
import numpy as np

temp2 = np.array(temp2).reshape(numclass, numclass)  # equivalent to matrix(temp2, ncol=numclass)
if np.any(np.diag(temp2) != 0):
    raise ValueError("Loss matrix must have zero on diagonals")
```

**Explanation:**

- When `numpy.diag` receives a 2-D array it extracts the main diagonal as a 1-D array, matching R's behaviour exactly.
- `np.any(...)` corresponds to R's `any(...)`.
- R's `matrix(temp2, ncol=numclass)` fills column-major (Fortran order); if `temp2` originated as a flat Python list or 1-D array, use `np.array(temp2).reshape(numclass, numclass, order='F')` to preserve column-major fill order. If it is already a properly shaped NumPy array, the reshape is unnecessary.

---

### 4.3 Mode C — Diagonal matrix from a vector (vector input)

**Locations:** `rpart/R/rpart.R`, function `rpart`, line 254.

**Original R Context:**

`init$parms$prior` and `temp` are both numeric vectors of length `numclass`. Their element-wise quotient is a numeric vector. `diag()` promotes that vector into a `numclass x numclass` diagonal matrix. It is right-multiplied against a data matrix to achieve column-wise scaling:

```r
temp <- pmax(1L, init$counts)
temp <- rpfit$dnode[, 4L + (1L:numclass)] %*% diag(init$parms$prior / temp)
```

The left operand `rpfit$dnode[, 4L + (1L:numclass)]` is an `N x numclass` matrix (one row per node). Right-multiplying by a diagonal matrix scales each column `j` by `prior[j] / temp[j]`.

**Python Equivalent:**

```python
import numpy as np

temp = np.maximum(1, init_counts)                    # pmax(1L, init$counts)
scale = init_parms_prior / temp                      # element-wise vector division

# Option 1: explicit diagonal matrix multiplication (direct translation)
temp_result = dnode_cols @ np.diag(scale)

# Option 2: equivalent broadcast multiply (preferred — avoids materialising the diagonal matrix)
temp_result = dnode_cols * scale                     # broadcasts scale across rows
```

**Explanation:**

- `np.diag(scale)` where `scale` is a 1-D array of length `numclass` produces a `numclass x numclass` diagonal matrix — exactly what R's `diag(vector)` does.
- Option 1 (`@ np.diag(scale)`) is the literal translation and makes the intent maximally clear.
- Option 2 (`* scale`) exploits NumPy broadcasting: multiplying an `(N, numclass)` matrix by a `(numclass,)` vector scales each column independently. The result is numerically identical but avoids allocating the `numclass x numclass` intermediate matrix, which is preferable for large `numclass`.
- `np.maximum(1, init_counts)` is the vectorised equivalent of R's `pmax(1L, init$counts)`.

---

### 4.4 Mode D — Diagonal assignment / replacement form

**Locations:** `rpart/R/zzz.R`, function `descendants`, line 41.

**Original R Context:**

`desc` is an `n x n` boolean matrix initialised to `FALSE`. The replacement form `diag(desc) <- TRUE` sets all `n` diagonal positions to `TRUE` in-place. This marks each node as a descendant of itself:

```r
n <- length(nodes)
desc <- matrix(FALSE, n, n)
if (include) diag(desc) <- TRUE
```

**Python Equivalent:**

```python
import numpy as np

n = len(nodes)
desc = np.zeros((n, n), dtype=bool)        # matrix(FALSE, n, n)
if include:
    np.fill_diagonal(desc, True)           # diag(desc) <- TRUE
```

**Explanation:**

- R's replacement form `diag(M) <- v` modifies `M` in-place; there is no direct operator overload for this in NumPy. `numpy.fill_diagonal(M, val)` is the canonical in-place equivalent — it modifies `desc` directly and returns `None`.
- `np.zeros((n, n), dtype=bool)` creates an `n x n` boolean array of `False` values, matching `matrix(FALSE, n, n)`.
- If `val` is a scalar (`True`) it is broadcast to fill all diagonal positions, just as R broadcasts `TRUE` across the diagonal.
- If `val` were a vector (e.g., `diag(desc) <- some_vector` in R), the Python call remains identical: `np.fill_diagonal(desc, some_vector)`.
