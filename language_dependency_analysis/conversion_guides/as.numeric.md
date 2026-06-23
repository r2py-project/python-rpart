# Conversion Guide: `as.numeric` (R to Python)

### 1. Overview of `as.numeric` in R

`as.numeric` is a base R coercion function that converts its argument to a numeric (double-precision floating-point) vector. It is one of R's fundamental type-coercion functions, with the following characteristics:

- **Input:** Any R object — character vectors, factors, logical vectors, integer vectors, lists, or other atomic types.
- **Output:** A `double`-typed numeric vector of the same length as the input. Elements that cannot be coerced produce `NA` with a warning.
- **Key behaviors:**
  - When applied to a **character vector**, it attempts to parse each string as a number.
  - When applied to a **factor**, it returns the underlying integer codes of the factor levels (1-based), not the level labels as strings.
  - When applied to a **logical vector** (`TRUE`/`FALSE`), it returns `1.0`/`0.0`.
  - When applied to a vector that is already numeric, it is a no-op type guarantee.
  - When applied to a **list or named vector** using `as.vector()` first (a pattern seen in rpart callbacks), it strips all attributes and then coerces the result to a flat numeric vector.

---

### 2. Contextual Usage Analysis

Across the twelve call sites in the rpart package, `as.numeric` is used in four functionally distinct patterns:

**Pattern A — `as.numeric(row.names(...))`**
Found in `labels.rpart.R`, `plot.rpart.R`, `print.rpart.R`, `rpartco.R`, `text.rpart.R`, and `path.rpart.R`. In all cases, `row.names()` (or the equivalent `row.names(frame)`, `row.names(ff)`, `row.names(x$frame)`) returns a **character vector** of node numbers (e.g., `"1"`, `"2"`, `"3"`, ...) stored as strings in the rpart frame's row names. `as.numeric` parses these strings into a numeric vector of node identifiers, which is then used for integer arithmetic (e.g., `node %/% 2L` to find a parent node, `node %% 2L` to determine odd/even). The return type is a `double` vector used as integers for tree traversal logic.

**Pattern B — `as.numeric(factor(x))`**
Found in `rpart.matrix.R` (line 20). The input `x` is a **character column** of a data frame. `factor(x)` first converts the character vector into a factor (assigning integer codes 1, 2, 3, ... to each distinct level in sorted order), and then `as.numeric()` extracts those integer codes as a numeric vector. This is a standard R idiom for encoding categorical string columns as numbers before passing them to numerical routines.

**Pattern C — `as.numeric(x)` on a non-numeric, non-character column**
Found in `rpart.matrix.R` (line 21). Here `x` is a column that is neither character nor already numeric (e.g., a logical vector or an ordered factor). `as.numeric` coerces it directly to numeric.

**Pattern D — `as.numeric(as.vector(c(...)))`**
Found in `rpartcallback.R` (lines 39, 58, 68, 89). The inner `c(temp$deviance, temp$label)` or `c(temp$goodness, temp$direction)` concatenates two named numeric-like vectors from user-defined callback functions into a single vector. `as.vector()` strips all names and attributes, and `as.numeric()` ensures the result is a plain, flat `double` vector. This flat vector is the interface format expected by the C-level callback mechanism. The result is always a 1-D numeric vector of known length.

---

### 3. Python Conversion Strategy

**Chosen library: `numpy`**

All four patterns deal with arrays or vectors — never isolated scalars — making `numpy` the natural equivalent:

- R's numeric vector corresponds directly to a 1-D `numpy.ndarray` with `dtype=float64`.
- `numpy` provides vectorized coercion functions (`asarray`, `astype`, etc.) that match R's element-wise semantics.
- `pandas` provides `DataFrame.index` (the equivalent of R's `row.names`), but after extraction the result is typically converted to a `numpy` array for arithmetic.
- `scipy` is not needed for any of these type-coercion patterns.

The dominant context for all uses is numerical computation on rpart's `frame`, which in Python will be represented as a `pandas.DataFrame`. Row names become the `pandas` index; `row.names(frame)` maps to `frame.index`.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Pattern A — Converting Row Names (String Node IDs) to Numeric

**Locations:**
- `labels.rpart.R`, function `labels.rpart`, line 100
- `path.rpart.R`, function `path.rpart`, line 10
- `plot.rpart.R`, function `plot.rpart`, line 27
- `print.rpart.R`, function `print.rpart`, line 9
- `rpartco.R`, function `rpartco`, line 12
- `text.rpart.R`, function `text.rpart`, line 23

**Original R Context:**

The rpart `frame` object is a data frame whose row names are character strings of node numbers. `row.names()` returns a `character` vector; `as.numeric` parses each string into a `double`. The result is used in integer tree-arithmetic.

```r
# R: frame is an rpart $frame data.frame
# row.names(frame) -> character vector: c("1", "2", "3", "4", ...)
node <- as.numeric(row.names(frame))
# node -> numeric vector: c(1, 2, 3, 4, ...)

# Subsequent arithmetic on the integer node IDs:
parent <- match(node %/% 2L, node)
odd    <- as.logical(node %% 2L)
depth  <- tree.depth(node)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# frame is a pandas.DataFrame whose index holds string node IDs
# frame.index -> Index(['1', '2', '3', '4', ...], dtype='object')

node = frame.index.to_numpy().astype(float)
# node -> np.ndarray([1., 2., 3., 4., ...], dtype=float64)

# Same downstream arithmetic translates directly:
parent_nodes = (node // 2).astype(int)
odd = (node % 2).astype(bool)
```

**Explanation:**
- `frame.index` is the pandas equivalent of R's `row.names(frame)`. It holds the node IDs as strings (because pandas preserves the original R row-name strings when importing).
- `.to_numpy()` materializes the index as a `numpy` array of `dtype=object` (strings).
- `.astype(float)` performs the same coercion as `as.numeric`, parsing the string `"1"` to `1.0`. Using `float` (i.e., `float64`) matches R's `double` output.
- R's `%/%` (integer division) and `%%` (modulo) map directly to Python's `//` and `%` operators on `numpy` arrays.
- Note: no zero-based indexing issue here since node IDs are tree node numbers (starting at 1 for the root), not positional indices.

---

#### 4.2 Pattern B — Encoding a Character Column via Factor Codes

**Locations:**
- `rpart.matrix.R`, function `rpart.matrix`, line 20

**Original R Context:**

The input `x` is a character column of a model frame (a `character` vector). `factor(x)` assigns integer codes 1-based in sorted level order; `as.numeric` extracts those codes as a `double` vector. This converts a categorical string column into a numeric encoding before passing it to `model.matrix`.

```r
# x is a character vector, e.g. c("cat", "dog", "cat", "bird")
# factor(x)             -> factor with levels: bird=1, cat=2, dog=3
# as.numeric(factor(x)) -> numeric vector: c(2, 3, 2, 1)
if (is.character(x)) as.numeric(factor(x))
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# x is a pandas.Series of dtype object (strings)
# e.g. x = pd.Series(["cat", "dog", "cat", "bird"])

def as_numeric_factor(x: pd.Series) -> np.ndarray:
    # pd.Categorical assigns codes based on sorted unique levels,
    # matching R's factor() default behaviour (alphabetical sort).
    cat = pd.Categorical(x, categories=sorted(x.dropna().unique()))
    # .codes is 0-based; add 1 to match R's 1-based factor codes
    return (cat.codes + 1).astype(float)

result = as_numeric_factor(x)
# result -> np.ndarray([2., 3., 2., 1.], dtype=float64)
```

**Explanation:**
- R's `factor(x)` sorts unique values alphabetically and assigns 1-based integer codes. `pd.Categorical` with an explicit `categories=sorted(...)` argument reproduces the same sorted level assignment.
- `.codes` in pandas is **0-based** (unlike R's 1-based codes), so `+1` is required to match R's output exactly.
- `.astype(float)` matches R's `as.numeric` output type (`double`).
- `NA`/`NaN` handling: R assigns `NA` for missing values; pandas assigns `-1` in `.codes` for missing entries. If the downstream code must handle `NaN`, replace the `+1` line with: `np.where(cat.codes == -1, np.nan, cat.codes + 1)`.

---

#### 4.3 Pattern C — Coercing a Non-Numeric, Non-Character Column to Numeric

**Locations:**
- `rpart.matrix.R`, function `rpart.matrix`, line 21

**Original R Context:**

The `else if (!is.numeric(x))` branch handles columns that are neither character nor already numeric — most commonly logical vectors or ordered factors. `as.numeric` converts them to doubles.

```r
# x might be a logical vector: c(TRUE, FALSE, TRUE)
# or an ordered factor
else if (!is.numeric(x)) as.numeric(x)
# logical -> c(1, 0, 1)  (TRUE=1, FALSE=0)
# ordered factor -> integer codes as doubles
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

def coerce_to_numeric(x: pd.Series) -> np.ndarray:
    if x.dtype == bool or pd.api.types.is_bool_dtype(x):
        # Logical / boolean: True->1.0, False->0.0
        return x.to_numpy().astype(float)
    elif hasattr(x, 'cat') or isinstance(x.dtype, pd.CategoricalDtype):
        # Ordered or unordered factor: return 1-based integer codes
        return (x.cat.codes + 1).astype(float)
    else:
        # Generic fallback: attempt numeric coercion
        return pd.to_numeric(x, errors='coerce').to_numpy().astype(float)
```

**Explanation:**
- For boolean columns, numpy's `.astype(float)` reproduces R's `TRUE -> 1.0`, `FALSE -> 0.0` coercion.
- For pandas `Categorical` columns (ordered or not), the same 1-based correction from Pattern B applies.
- `pd.to_numeric(..., errors='coerce')` matches R's behavior of producing `NA` (here `NaN`) for values that cannot be parsed, with no exception raised.

---

#### 4.4 Pattern D — Flattening and Coercing Concatenated Named Vectors from Callbacks

**Locations:**
- `rpartcallback.R`, function `rpartcallback`, lines 39, 58, 68, 89

**Original R Context:**

User-defined rpart callback functions (`user.eval`, `user.split`) return named lists with elements like `$deviance`, `$label`, `$goodness`, `$direction`. These elements may carry names or other attributes. `c(...)` concatenates them into a single named vector; `as.vector()` strips all attributes (including names); `as.numeric()` ensures the result is a plain `double` vector. This flat vector is passed to the C callback interface, which expects a raw array of doubles at a known memory offset.

```r
# temp$deviance is a length-1 numeric: e.g. 42.7
# temp$label    is a named numeric vector of length numresp
# c(temp$deviance, temp$label) -> named numeric vector, length 1 + numresp
# as.vector(...)               -> strips names/attributes -> unnamed numeric vector
# as.numeric(...)              -> ensures double type -> plain double vector
as.numeric(as.vector(c(temp$deviance, temp$label)))

# Similarly for the split callback:
as.numeric(as.vector(c(temp$goodness, temp$direction)))
```

**Python Equivalent:**

```python
import numpy as np

# temp is a dict (or object with attributes) returned by the user callback:
# temp["deviance"] is a float or 0-d/1-d numpy array
# temp["label"]    is a 1-D numpy array of length numresp

def flatten_to_numeric(*arrays) -> np.ndarray:
    """
    Concatenate and flatten an arbitrary number of scalar/array values
    into a single 1-D float64 numpy array, stripping all structure.
    Equivalent to R's: as.numeric(as.vector(c(...)))
    """
    return np.concatenate([np.atleast_1d(np.asarray(a, dtype=float).ravel())
                           for a in arrays])

# Eval callback (lines 39 and 68):
result = flatten_to_numeric(temp["deviance"], temp["label"])
# -> np.ndarray of shape (1 + numresp,), dtype=float64

# Split callback (lines 58 and 89):
result = flatten_to_numeric(temp["goodness"], temp["direction"])
# -> np.ndarray of shape (nback-1 + nback-1,) or similar, dtype=float64
```

**Explanation:**
- R's `c(a, b)` concatenates vectors; `np.concatenate` does the same for arrays. `np.atleast_1d` handles scalars (0-d arrays or plain Python floats) so they concatenate correctly.
- R's `as.vector()` strips all attributes (names, dim, class). In numpy, `.ravel()` removes shape structure, and `np.asarray(...).ravel()` has no equivalent of named attributes to worry about since numpy arrays carry no names. If the Python callback returns a pandas `Series` with an index, calling `.to_numpy()` first drops the index, mirroring `as.vector()`.
- `dtype=float` ensures the output matches R's `double` type (`float64`), which is the format expected by the C interface.
- The idiom `np.asarray(a, dtype=float).ravel()` is robust: it handles plain Python `float`/`int`, 0-d numpy arrays, 1-D arrays, and `pandas.Series` uniformly.
