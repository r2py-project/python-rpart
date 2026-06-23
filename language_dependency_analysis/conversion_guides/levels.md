### 1. Overview of `levels` in R

`levels()` is a base R function that extracts the **levels attribute** of a factor object. In R, a factor is a categorical variable stored internally as integers, but with an associated character vector of human-readable label strings called "levels." These levels are always returned as a **character vector**, sorted in the order they were assigned when the factor was created (typically alphabetical order by default when using `as.factor()`).

**Signature:**
```r
levels(x)
```

**Input:** `x` — any R object that has a `levels` attribute, most commonly a `factor`.

**Output:** A character vector of the unique category labels, in the order they are stored on the factor. Returns `NULL` if the object has no levels attribute.

**Key nuances:**
- The return type is always `character` (string), never numeric, even if the original values were numbers.
- The order of levels is fixed at factor creation time and does not necessarily match the order of first appearance in the data.
- `levels()` also has a replacement form (`levels(x) <- value`) for renaming levels, but that usage is unrelated to the read-only extraction used in this codebase.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/rpart.class.R`
**Function:** `rpart.class`
**Line:** 56

The relevant block is:

```r
rpart.class <- function(y, offset, parms, wt) {
    ...
    fy <- as.factor(y)       # coerce raw response vector to a factor
    y  <- as.integer(fy)     # extract the integer codes (1-based class indices)
    ...
    list(y = y, parms = parms, numresp = numclass + 2L, counts = counts,
         ylevels = levels(fy),   # line 56: extract the string labels of each class
         ...)
}
```

The argument `y` is the raw response vector passed into rpart's classification method — it may arrive as a character vector, numeric vector, or already a factor. It is immediately coerced to a factor with `as.factor(y)`, and the resulting factor `fy` is the direct input to `levels()` on line 56.

`levels(fy)` therefore returns a **character vector** of the unique class labels in their canonical factor order (alphabetical by default). This vector is stored as `ylevels` in the returned list, and is subsequently used throughout rpart's internal machinery to map integer class codes back to human-readable category names when printing or summarizing the tree.

**Pattern summary:**
- Input to `levels()`: a factor (`fy`) derived from coercing an arbitrary response vector.
- Output: a character vector of unique class label strings.
- Purpose: preserve the original class label strings after the data has been encoded as integers for numerical computation.

---

### 3. Python Conversion Strategy

The natural Python equivalent is **pandas `Categorical`**, because it is the closest structural analog to R's factor — it stores both integer codes and a fixed, ordered array of category labels.

The specific call `levels(fy)` maps directly to the `.categories` attribute of a `pandas.Categorical` (or `pandas.Series` with `dtype="category"`):

```python
pd.Categorical(y).categories
```

This returns a `pandas.Index` of the unique category labels, sorted in the same default alphabetical order that R uses when calling `as.factor()`. Where a plain Python list or NumPy array is needed downstream, `.tolist()` or `np.array(...)` can be applied.

**Why pandas over numpy:**
- `numpy` has no native categorical/factor type with an attached labels array.
- `pandas.Categorical` directly models R's factor: integer codes (`Categorical.codes`, 0-based in pandas vs. 1-based in R) plus a sorted, fixed label array (`Categorical.categories`).
- The default sort order of `pd.Categorical(y).categories` matches R's `as.factor(y)` default alphabetical sort, making the translation faithful without extra sorting logic.

---

### 4. Step-by-Step Conversion Examples

#### Example 1 — Extracting class labels after factor coercion

**Locations:**
- File: `rpart/R/rpart.class.R`
- Function: `rpart.class`
- Line: 56 (`ylevels = levels(fy)`)

**Original R Context:**

- `y`: an arbitrary response vector (character, numeric, or factor) representing classification targets.
- `fy`: a factor produced by `as.factor(y)` — stores integer codes internally with a `levels` character vector attached.
- Return value of `levels(fy)`: a **character vector** of unique class label strings in sorted (alphabetical) order.

Generalized R snippet:

```r
# y is the raw response vector, e.g. c("setosa", "versicolor", "setosa", "virginica")
fy <- as.factor(y)          # coerce to factor; levels sorted alphabetically by default
y  <- as.integer(fy)        # integer codes, 1-based: 1 = "setosa", 2 = "versicolor", ...

ylevels <- levels(fy)       # character vector: c("setosa", "versicolor", "virginica")
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# y is the raw response array, e.g. a list or numpy array of class labels
y = np.array(["setosa", "versicolor", "setosa", "virginica"])

# Step 1: coerce to pandas Categorical (mirrors R's as.factor)
fy = pd.Categorical(y)          # categories sorted alphabetically by default

# Step 2: extract integer codes (0-based in pandas; add 1 to match R's 1-based codes)
y_int = fy.codes + 1            # array([1, 2, 1, 3])

# Step 3: extract the string labels (mirrors R's levels(fy))
ylevels = fy.categories.tolist()  # ['setosa', 'versicolor', 'virginica']
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `as.factor(y)` | `pd.Categorical(y)` | Both sort unique labels alphabetically by default and store integer codes internally. |
| `as.integer(fy)` | `fy.codes + 1` | R codes are 1-based; pandas `.codes` are 0-based, so `+1` aligns them. |
| `levels(fy)` | `fy.categories.tolist()` | `.categories` is a `pandas.Index`; `.tolist()` converts it to a plain Python list of strings matching R's character vector. |
| Return type: `character vector` | Return type: `list[str]` (or `pd.Index`) | Both are ordered string sequences with deterministic alphabetical ordering when using the default coercion path. |

If the downstream code needs a NumPy array instead of a list, use `fy.categories.to_numpy()` in place of `.tolist()`. If `y` may already be a pandas Series with `dtype="category"`, access `y.cat.categories` directly rather than constructing a new `Categorical`.
