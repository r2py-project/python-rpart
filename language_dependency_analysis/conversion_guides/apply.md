# Conversion Guide: `apply` (R to Python)

---

## 1. Overview of `apply` in R

`apply` is a base-R function that applies a function over the margins (rows or columns) of a matrix or array.

**Signature:**

```r
apply(X, MARGIN, FUN, ...)
```

**Parameters:**

- `X`: A matrix or array.
- `MARGIN`: An integer specifying the dimension over which to apply `FUN`. `1L` means rows; `2L` means columns.
- `FUN`: The function to apply to each row or column slice.
- `...`: Additional arguments passed to `FUN`.

**Return value:**

When `FUN` returns a scalar for each slice, `apply` returns a vector of the same length as the chosen margin (one value per row when `MARGIN = 1L`). When `FUN` returns a character string per row (as in all usages here), the result is a character vector whose length equals the number of rows of `X`.

---

## 2. Contextual Usage Analysis

All three occurrences appear inside the `rpart.class` function in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.class.R` (lines 85-88 and 105-106). They share the same structural pattern:

```r
apply(matrix(temp, ncol = nclass), 1L, paste, collapse = "<sep>")
```

**Data flow:**

1. `temp` starts as the result of `formatg(...)`, which formats a matrix of numeric values into character strings. `formatg` returns a character vector (a flattened, column-major representation of the matrix).
2. `matrix(temp, ncol = nclass)` reshapes this character vector back into a matrix with `nclass` columns. The number of rows equals the number of tree nodes being processed.
3. `apply(..., 1L, paste, collapse = "<sep>")` iterates over rows. For each row it calls `paste(..., collapse = "<sep>")`, which concatenates the `nclass` character elements of that row into a single string.

The two separator variants are:

- `" "` (space): used in the `summary` sub-function (lines 85-88) for counts and probabilities.
- `"/"` (slash): used in the `text` sub-function (line 105-106) for counts.

The result in every case is a **character vector** of length equal to the number of rows (tree nodes), where each element is the space- or slash-joined string of class-level formatted values for that node.

---

## 3. Python Conversion Strategy

The preferred Python equivalent is **NumPy** combined with a vectorized string join. The pattern in R combines two operations:

1. Reshape a flat array into a 2-D matrix (`matrix(..., ncol = nclass)`).
2. Join each row's elements into a single string (`apply(..., 1L, paste, collapse = sep)`).

In Python/NumPy:

- Step 1 maps to `np.array(temp).reshape(-1, nclass)` with Fortran (column-major) order, matching R's column-major matrix fill.
- Step 2 maps to a list comprehension or `np.apply_along_axis` over rows, calling `sep.join(row)` on each row.

Because `formatg` output is already string-typed, no numeric conversion is needed. Pure Python string operations (`sep.join`) are idiomatic and efficient here; there is no benefit to a `numpy` ufunc for string joining. However, `numpy` is still required for the reshape step.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Space-separated join of counts (line 85-88)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class` (inner `summary` closure), lines 85-88.

**Original R context:**

```r
# temp1 is a character vector produced by formatg(counts, format = "%5g")
# counts is a numeric matrix with shape [n_nodes, nclass]
# After formatg, temp1 is a character vector of length n_nodes * nclass (column-major)
# nclass is an integer >= 2 (the branch is only entered when nclass > 1)

temp1 <- apply(matrix(temp1, ncol = nclass), 1L,
               paste, collapse = " ")
# Result: character vector of length n_nodes
# Each element: nclass count strings joined by a single space
# e.g. "  123   45    6"
```

Input types: character vector (`temp1`), integer scalar (`nclass`).
Return type: character vector of length `n_nodes`.

**Python equivalent:**

```python
import numpy as np

# temp1: list or 1-D numpy array of strings, length = n_nodes * nclass
# nclass: int

def apply_paste_space(temp1, nclass):
    """
    Equivalent to: apply(matrix(temp1, ncol=nclass), 1L, paste, collapse=" ")

    R fills matrices column-major, so reshape with order='F'.
    """
    mat = np.array(temp1).reshape(-1, nclass, order='F')
    return np.array([" ".join(row) for row in mat])
```

**Explanation:**

- `np.array(temp1).reshape(-1, nclass, order='F')`: reshapes the flat column-major character vector into an `(n_nodes, nclass)` array. The `order='F'` (Fortran/column-major) flag is critical — R fills matrices column by column, so without it the per-node strings would mix values from different nodes.
- `" ".join(row)` replicates `paste(..., collapse = " ")` on each row.
- The list comprehension over rows is the direct analogue of `apply(..., MARGIN = 1L, ...)`.
- The result is wrapped in `np.array(...)` to return a NumPy string array, keeping downstream operations consistent.

---

### 4.2 Space-separated join of probabilities (line 87-88)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class` (inner `summary` closure), lines 87-88.

**Original R context:**

```r
# temp2 is a character vector produced by formatg(yprob, format = "%5.3f")
# yprob is a numeric matrix with shape [n_nodes, nclass]

temp2 <- apply(matrix(temp2, ncol = nclass), 1L,
               paste, collapse = " ")
# Result: character vector of length n_nodes
# Each element: nclass probability strings joined by a single space
# e.g. "0.700 0.200 0.100"
```

Input types: character vector (`temp2`), integer scalar (`nclass`).
Return type: character vector of length `n_nodes`.

**Python equivalent:**

```python
import numpy as np

def apply_paste_space(temp2, nclass):
    """
    Equivalent to: apply(matrix(temp2, ncol=nclass), 1L, paste, collapse=" ")
    Identical structure to the counts case; only the input data differs.
    """
    mat = np.array(temp2).reshape(-1, nclass, order='F')
    return np.array([" ".join(row) for row in mat])
```

**Explanation:**

This usage is structurally identical to 4.1 — only the source data (`yprob` instead of `counts`) and number format differ. The same function definition covers both cases. No separate implementation is required.

---

### 4.3 Slash-separated join of counts (line 105-106)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class` (inner `text` closure), lines 105-106.

**Original R context:**

```r
# temp1 is a character vector produced by formatg(counts, digits)
# counts is a numeric matrix with shape [n_nodes, nclass]
# nclass > 1 (guard on line 104)

temp1 <- apply(matrix(temp1, ncol = nclass), 1L,
               paste, collapse = "/")
# Result: character vector of length n_nodes
# Each element: nclass count strings joined by "/"
# e.g. "123/45/6"
```

Input types: character vector (`temp1`), integer scalar (`nclass`).
Return type: character vector of length `n_nodes`.

**Python equivalent:**

```python
import numpy as np

def apply_paste_slash(temp1, nclass):
    """
    Equivalent to: apply(matrix(temp1, ncol=nclass), 1L, paste, collapse="/")
    """
    mat = np.array(temp1).reshape(-1, nclass, order='F')
    return np.array(["/".join(row) for row in mat])
```

**Explanation:**

The only difference from 4.1 is the separator character (`"/"` instead of `" "`). The reshape logic is identical. In practice, a single parameterised helper covers all three usages:

```python
import numpy as np

def r_apply_paste(flat_strings, nclass, sep):
    """
    General replacement for:
        apply(matrix(flat_strings, ncol=nclass), 1L, paste, collapse=sep)

    Parameters
    ----------
    flat_strings : list or 1-D array of str
        Flat, column-major character vector (output of formatg or equivalent).
    nclass : int
        Number of classes; becomes the number of columns after reshape.
    sep : str
        Separator passed to str.join, equivalent to R's `collapse` argument.

    Returns
    -------
    numpy.ndarray of dtype '<U...' (variable-length Unicode strings)
        One joined string per row (tree node).
    """
    mat = np.array(flat_strings).reshape(-1, nclass, order='F')
    return np.array([sep.join(row) for row in mat])
```

Usage examples corresponding to each CSV row:

```python
# Line 85-86 equivalent (summary, counts, space-separated)
temp1_joined = r_apply_paste(temp1, nclass, sep=" ")

# Line 87-88 equivalent (summary, probabilities, space-separated)
temp2_joined = r_apply_paste(temp2, nclass, sep=" ")

# Line 105-106 equivalent (text, counts, slash-separated)
temp1_joined = r_apply_paste(temp1, nclass, sep="/")
```
