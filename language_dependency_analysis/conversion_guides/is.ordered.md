# Conversion Guide: `is.ordered` (R to Python)

### 1. Overview of `is.ordered` in R

`is.ordered(x)` is a base R predicate function that tests whether its argument is an **ordered factor**. It returns a single logical scalar: `TRUE` if `x` has the class `c("ordered", "factor")`, and `FALSE` for any other object (including plain unordered factors, character vectors, numeric vectors, or matrices).

An ordered factor is a categorical variable whose levels carry an inherent ranking (e.g., `"low" < "medium" < "high"`). Because the levels have a defined order, ordered factors support all comparison operators (`<`, `<=`, `>`, `>=`), whereas plain factors only support equality (`==`, `!=`).

**Signature:**
```r
is.ordered(x)
```
- **Input:** Any R object.
- **Output:** A single logical value (`TRUE` or `FALSE`).

---

### 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`
**Function:** `tfun` (defined inline inside `rpart`), used at line 152.

The relevant block (lines 146-161) reads:

```r
##
## Have C code consider ordered categories as continuous
##  A right-hand side variable that is a matrix forms a special case
## for the code.
##
tfun <- function(x)
    if (is.matrix(x)) rep(is.ordered(x), ncol(x)) else is.ordered(x)
labs <- sub("^`(.*)`$", "\\1", attr(Terms, "term.labels"))
isord <- unlist(lapply(m[labs], tfun))

...
rpfit <- .Call(C_rpart,
               ncat = as.integer(cats * !isord),
               ...)
```

**How `is.ordered` is used here:**

- `m` is the model frame: a data frame where each column corresponds to a predictor variable from the formula.
- `labs` is the character vector of predictor variable names extracted from the formula terms.
- `m[labs]` selects those columns; each element passed to `tfun` is one predictor column — either a plain vector (e.g., an ordered factor, an unordered factor, or a numeric vector) or a matrix (when a matrix predictor was included in the formula).
- Inside `tfun`, `is.ordered(x)` returns a single `TRUE` or `FALSE` for that column. If the column is a matrix, the result is replicated `ncol(x)` times so that the length of `isord` equals the total number of predictor columns in `X`.
- `isord` is a logical vector (one entry per predictor column). It is used immediately to compute `ncat = as.integer(cats * !isord)`. The variable `cats` holds the number of category levels for each predictor (0 for numeric predictors, >0 for factors). Multiplying by `!isord` zeroes out `ncat` for any predictor that is an ordered factor, instructing the C backend to treat ordered factors as continuous (i.e., use numeric splitting, not categorical splitting).

**Data types involved:**
- Input to `tfun` (`x`): a single data frame column — typically an ordered factor, an unordered factor, or a numeric vector; may also be a matrix.
- Return value of `is.ordered(x)`: a single logical scalar (`TRUE` / `FALSE`).
- `isord`: a logical vector of length equal to the number of predictor columns in the model matrix.

**Recurring pattern:** `is.ordered` is called once per predictor variable, always used as a boolean flag to gate downstream numeric vs. categorical treatment. There is exactly one distinct functional usage in the CSV.

---

### 3. Python Conversion Strategy

**Chosen library: `pandas`**

In Python, the direct equivalent of an R ordered factor is a `pandas.Categorical` (or a Series with `CategoricalDtype`) with `ordered=True`. The check `is.ordered(x)` therefore maps to inspecting whether a pandas Series has a categorical dtype that is ordered.

`numpy` is not appropriate here because numpy arrays have no native concept of ordered categories. `scipy` similarly provides no categorical dtype. `pandas` is the canonical Python library for representing and inspecting categorical data, making it the most robust and idiomatic equivalent.

For the specific use case inside `rpart` — determining whether each predictor column should be treated as continuous — the Python translation checks the `.dtype` of each column in the pandas DataFrame that serves as the model frame.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 `is.ordered(x)` on a single predictor column inside `tfun`

**Locations:**
- File: `rpart/R/rpart.R`
- Function: `tfun` (inline lambda-style helper inside `rpart`)

**Original R Context:**

`x` is a single column from a model-frame data frame. It may be:
- An ordered factor (class `c("ordered", "factor")`) — returns `TRUE`
- An unordered factor or any other type — returns `FALSE`
- A matrix (when the predictor was entered as a matrix) — `is.ordered(x)` still returns one scalar, which is then replicated across all columns via `rep(..., ncol(x))`

```r
# Generalised R snippet
tfun <- function(x)
    if (is.matrix(x)) rep(is.ordered(x), ncol(x)) else is.ordered(x)

labs  <- attr(Terms, "term.labels")          # character vector of predictor names
isord <- unlist(lapply(m[labs], tfun))       # logical vector, one entry per X column

# isord is then used as:
ncat <- as.integer(cats * !isord)
# Ordered factors get ncat == 0 (treated as continuous by the C backend)
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

def is_ordered(x):
    """
    Equivalent of R's is.ordered(x).

    Returns True if x is a pandas Series (or array-like) backed by an
    ordered CategoricalDtype, False otherwise.
    """
    if isinstance(x, pd.Series):
        return isinstance(x.dtype, pd.CategoricalDtype) and x.dtype.ordered
    if isinstance(x, pd.Categorical):
        return x.ordered
    return False


def tfun(x):
    """
    Equivalent of the R inline tfun helper.

    If x is a 2-D numpy array or DataFrame (matrix predictor), replicate
    the ordered check across all columns; otherwise return a single bool.
    """
    if isinstance(x, (np.ndarray, pd.DataFrame)) and np.ndim(x) == 2:
        n_cols = x.shape[1]
        # For a matrix predictor, check the whole object (R does the same)
        return [is_ordered(x)] * n_cols
    return is_ordered(x)


# --- Usage example mirroring the rpart context ---

# Suppose `m` is the pandas DataFrame acting as the model frame
# and `labs` is the list of predictor column names.

# Example model frame
size = pd.Categorical(["small", "medium", "large"] * 4,
                      categories=["small", "medium", "large"],
                      ordered=True)
color = pd.Categorical(["red", "blue", "green"] * 4,
                       categories=["red", "blue", "green"],
                       ordered=False)
weight = np.random.randn(12)

m = pd.DataFrame({"size": size, "color": color, "weight": weight})
labs = ["size", "color", "weight"]

# Build isord: one boolean per predictor column
isord_list = []
for lab in labs:
    result = tfun(m[lab])
    if isinstance(result, list):
        isord_list.extend(result)
    else:
        isord_list.append(result)

isord = np.array(isord_list, dtype=bool)
# isord -> [True, False, False]

# Mirror the downstream R logic:  ncat = as.integer(cats * !isord)
# cats would be the array of category counts (0 for numeric predictors)
cats = np.array([3, 3, 0])          # example: size has 3 levels, color has 3, weight is numeric
ncat = (cats * (~isord)).astype(int)
# ncat -> [0, 3, 0]
# Ordered factor "size" gets ncat=0 (treated as continuous)
# Unordered factor "color" keeps ncat=3 (treated as categorical)
# Numeric "weight" stays 0
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `is.ordered(x)` | `isinstance(x.dtype, pd.CategoricalDtype) and x.dtype.ordered` | The `ordered` attribute on `CategoricalDtype` is the direct counterpart to R's ordered-factor class attribute. |
| Ordered factor column in data frame | `pd.Series` with `CategoricalDtype(ordered=True)` | Created via `pd.Categorical(..., ordered=True)` or `pd.CategoricalDtype(categories=[...], ordered=True)`. |
| Plain factor column | `pd.Series` with `CategoricalDtype(ordered=False)` | `is_ordered` returns `False`, preserving categorical treatment in `ncat`. |
| Numeric/character column | `pd.Series` with numeric or object dtype | `is_ordered` returns `False`; `cats` is already 0 for these, so `ncat` remains 0. |
| Matrix branch: `rep(is.ordered(x), ncol(x))` | `[is_ordered(x)] * x.shape[1]` | Replicates the single boolean across every column of a matrix predictor. |
| `unlist(lapply(m[labs], tfun))` | List comprehension + `np.array(..., dtype=bool)` | `unlist` flattens the list; `np.array` with `dtype=bool` achieves the same flat boolean array. |
| `!isord` | `~isord` | Logical negation on a numpy boolean array uses `~` rather than `not`. |
| `cats * !isord` | `cats * (~isord)` then `.astype(int)` | R coerces logicals to integers automatically; Python requires an explicit `.astype(int)` or multiplication handles it if `cats` is already an integer array. |
