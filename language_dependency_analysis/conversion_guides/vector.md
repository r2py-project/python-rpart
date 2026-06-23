# Conversion Guide: `vector` in R (rpart package)

---

## 1. Overview of `vector` in R

`vector(mode, length)` is a base R function that creates an atomic or generic vector of a specified mode and length, with all elements initialized to the mode's default "empty" value.

**Signature:**
```r
vector(mode = "logical", length = 0)
```

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `mode` | A character string naming an R type: `"logical"`, `"integer"`, `"double"`, `"complex"`, `"character"`, `"raw"`, or `"list"`. |
| `length` | A non-negative integer giving the number of elements. |

**Initialization defaults by mode:**

| Mode | Default element value |
|------|-----------------------|
| `"logical"` | `FALSE` |
| `"integer"` | `0L` |
| `"double"` | `0` |
| `"character"` | `""` |
| `"list"` | `NULL` |

When called as `vector("list", n)`, the result is a list of length `n` where every slot holds `NULL`. This is R's idiomatic way to pre-allocate a container that will later hold heterogeneous objects — analogous to allocating a Python list of `None` values before filling it in a loop.

---

## 2. Contextual Usage Analysis

**File:** `rpart/R/importance.R`
**Function:** `importance`
**Line:** 16

```r
sname <- vector("list", length(fpri))
sval  <- sname
```

**Context summary:**

- `fpri` is an integer index vector produced by `which(ff$var != "<leaf>")`. Its length equals the number of non-leaf nodes in the rpart decision tree frame — a runtime-determined integer scalar.
- `vector("list", length(fpri))` creates a list of that many `NULL` slots. The purpose is **pre-allocation**: reserving a slot for each primary split so that the subsequent `for` loop can fill `sname[[i]]` and `sval[[i]]` selectively (only when `nsurr[i] > 0`).
- `sval <- sname` is an immediate copy — both start as identically-sized all-`NULL` lists.
- Elements of `sname` are later assigned character vectors (surrogate variable names); elements of `sval` are assigned numeric vectors (scaled importance scores).
- At the end, `unlist(sval)` and `unlist(sname)` flatten these list containers back to plain vectors for the `tapply` aggregation step.

**Pattern:** This is a single, consistent usage pattern: **pre-allocating a generic list container of a runtime-determined length**, with `NULL` as the sentinel "not yet filled" value for slots where no surrogates exist.

---

## 3. Python Conversion Strategy

**Chosen library: built-in Python list**

Because `vector("list", n)` with mode `"list"` creates a heterogeneous container (not a numeric array), `numpy` is not appropriate here. The elements stored later are themselves sequences of varying length (character vectors and numeric vectors). The direct Python equivalent is a plain Python `list` pre-populated with `None`.

- `[None] * n` allocates a list of `n` `None` values — exactly mirroring R's `vector("list", n)`.
- `None` is Python's direct counterpart to R's `NULL`.
- Slot assignment `sname[i] = ...` matches R's `sname[[i]] <- ...` (with zero-based index adjustment).
- `[x for sublist in sname if sublist is not None for x in sublist]` or `itertools.chain` equivalently replaces `unlist()`.

For modes other than `"list"` (e.g., `"double"`, `"integer"`), `numpy.zeros(n)` or `numpy.empty(n)` would be the preferred equivalent since those produce fixed-type numeric arrays — but that case does not appear in this CSV.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `vector("list", length(fpri))` — Pre-allocating a generic list

**Locations:** `importance.R` — function `importance`, lines 16–17.

**Original R Context:**

```r
# fpri: integer vector, length = number of non-leaf nodes (runtime value)
# Both sname and sval are initialized as all-NULL lists of that length.
sname <- vector("list", length(fpri))
sval  <- sname

# Later, slots are conditionally filled inside a for-loop:
for (i in seq_along(fpri)) {
    if (nsurr[i] > 0L) {
        sname[[i]] <- sdim[indx]                               # character vector
        sval[[i]]  <- scaled.imp[i] * fit$splits[indx, "adj"] # numeric vector
    }
    # Slots where nsurr[i] == 0 remain NULL
}

# Finally flattened:
unlist(sval)
unlist(sname)
```

- Input types: `length(fpri)` is an integer scalar.
- Return type of `vector("list", n)`: a list of length `n`, every element `NULL`.
- Elements assigned later: character vectors (`sname`) and numeric vectors (`sval`).

**Python Equivalent:**

```python
import numpy as np
import itertools

# fpri is a 1-D numpy array of integer indices (non-leaf node positions)
n = len(fpri)

# Pre-allocate — direct translation of vector("list", length(fpri))
sname = [None] * n
sval  = [None] * n

# Conditional fill inside the loop (0-based indexing in Python)
for i in range(n):
    if nsurr[i] > 0:
        indx = spri[i] + ff_ncompete[fpri[i]] + np.arange(1, nsurr[i] + 1)
        sname[i] = sdim[indx]                              # numpy array of str
        sval[i]  = scaled_imp[i] * fit_splits_adj[indx]   # numpy array of float

# Flatten — equivalent to unlist()
sval_flat  = np.array(list(itertools.chain.from_iterable(
                 v for v in sval  if v is not None)))
sname_flat = np.array(list(itertools.chain.from_iterable(
                 v for v in sname if v is not None)))
```

**Explanation:**

| R construct | Python equivalent | Notes |
|-------------|-------------------|-------|
| `vector("list", n)` | `[None] * n` | Pre-allocates a list; `None` mirrors R's `NULL`. |
| `sval <- sname` | `sval = [None] * n` | In Python, `sval = sname` would create an alias (shared reference), not a copy. Use a separate `[None] * n` to get an independent list. |
| `sname[[i]] <- ...` | `sname[i] = ...` | R uses 1-based indexing; Python uses 0-based. The loop variable `i` runs `seq_along(fpri)` (1 to n) in R and `range(n)` (0 to n-1) in Python. |
| `unlist(sval)` | `np.array(list(itertools.chain.from_iterable(...)))` | `itertools.chain.from_iterable` flattens a list of arrays/lists, filtering `None` slots explicitly. The result is cast to a numpy array to restore vectorized numeric behavior. |
| Slots left as `NULL` | Slots left as `None` | Both serve as "not filled" sentinels; both are skipped during flattening. |

**Key nuance — copy semantics:** In R, `sval <- sname` produces an independent copy due to R's copy-on-modify semantics. In Python, `sval = sname` would make both names point to the same list object. To match R's behavior, always initialize `sval` independently with its own `[None] * n` expression.
