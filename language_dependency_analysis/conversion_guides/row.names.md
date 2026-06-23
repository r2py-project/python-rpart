# Conversion Guide: `row.names` in R to Python

---

## 1. Overview of `row.names` in R

`row.names` is a base R function that retrieves (or sets) the row names of a data frame or matrix. When called as a getter — the only usage pattern in this codebase — it returns a **character vector** of the row labels attached to the object:

```r
row.names(x)  # returns character vector of row labels
```

Key characteristics:
- The return type is always **character**, even when the underlying labels look numeric (e.g., `"1"`, `"2"`, `"4"`, `"8"`).
- It is semantically equivalent to `rownames()` for data frames; both functions read from the same internal attribute.
- For an rpart `frame` data frame in particular, the row names are the **node numbers** of the decision tree, stored as character strings of integers (e.g., `"1"`, `"2"`, `"3"`, `"4"`, ...). These node numbers encode the tree topology: node `k` has left child `2k` and right child `2k+1`.

---

## 2. Contextual Usage Analysis

All 14 call sites apply `row.names` to one of two kinds of objects:

**Pattern A — rpart `frame` data frame (13 call sites):**
The rpart `frame` object is a data frame whose row names are the integer node numbers of the tree, set explicitly during tree construction in `rpart.R` via `data.frame(row.names = rpfit$inode[, 1L], ...)`. Every downstream function extracts these node IDs using `row.names(frame)` or `row.names(x$frame)` or `row.names(ff)` and immediately converts the result to numeric/integer for arithmetic tree-navigation logic (parent lookup via integer division `%/% 2`, parity checks via `%%`, etc.).

**Pattern B — model frame `m` (1 call site, `rpart.R` line 269):**
Here `row.names(m)` is called on a model frame (a data frame of the input data rows), and the result — the original row identifiers of the training observations — is used as the names of the `where` vector that maps each observation to its terminal node.

The recurring patterns are:
1. `as.numeric(row.names(frame))` — extract node IDs as numbers for arithmetic.
2. `as.integer(row.names(frame))` — extract node IDs as integers for C-level calls or matching.
3. Raw `row.names(frame)` stored as a character vector for labelling (plot text, path keys, names of omitted-row vectors).

---

## 3. Python Conversion Strategy

In the Python translation of rpart, the `frame` object maps to a **`pandas.DataFrame`**. Pandas DataFrames expose their row labels through the `.index` attribute, which is the direct structural equivalent of R row names.

- `row.names(df)` → `df.index` (returns a `pandas.Index` object, iterable as strings/integers depending on how the index was constructed).
- When the R code immediately converts to numeric (`as.numeric(row.names(frame))`), the Python equivalent is `df.index.astype(int)` or `df.index.to_numpy(dtype=int)` (yielding a `numpy.ndarray` of integers), which supports the same vectorized arithmetic (`// 2`, `% 2`, etc.) that R performs.
- When the R code uses the character labels directly (for naming, labelling, or dict keys), `df.index.astype(str)` or simply `df.index` (if already a string index) is appropriate.
- For the model frame case (`row.names(m)` on training data), the equivalent is `m.index` — the original row labels carried by the input DataFrame.

`pandas` is the correct primary library because the rpart `frame` is a data frame structure. `numpy` is used as a secondary tool for the vectorized integer arithmetic after the index is extracted.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Extract Node Numbers as Numeric Array for Tree Navigation

**Locations:**
- `labels.rpart.R` — `labels.rpart` (line 100)
- `path.rpart.R` — `path.rpart` (line 9)
- `plot.rpart.R` — `plot.rpart` (line 27)
- `print.rpart.R` — `print.rpart` (line 9)
- `rpartco.R` — `rpartco` (line 12)
- `snip.rpart.mouse.R` — `snip.rpart.mouse` (line 21)
- `summary.rpart.R` — `summary.rpart` (line 34)
- `text.rpart.R` — `text.rpart` (line 23)

**Original R Context:**

Input: `frame` or `ff` is a `data.frame` whose row names are integer node number strings (e.g., `"1"`, `"2"`, `"3"`, `"4"`, ...).
Return value of `as.numeric(row.names(frame))`: a numeric vector of node IDs.

```r
# R
frame <- tree$frame          # data.frame; row.names are node number strings
node  <- as.numeric(row.names(frame))
# node is now e.g. c(1, 2, 3, 4, ...) as doubles
# used for: parent <- match(node %/% 2L, node)
#           odd   <- as.logical(node %% 2L)
#           depth <- tree.depth(node)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# frame is a pd.DataFrame; its index holds integer node IDs
# (index dtype may be int64 or object/string depending on construction)

node = frame.index.to_numpy(dtype=int)
# node is now e.g. np.array([1, 2, 3, 4, ...], dtype=int64)

# Tree navigation arithmetic — identical logic to R
parent  = np.searchsorted(node, node // 2)   # equivalent to match(node %/% 2L, node)
is_odd  = (node % 2).astype(bool)            # equivalent to as.logical(node %% 2L)
```

**Explanation:**
- `frame.index.to_numpy(dtype=int)` converts the DataFrame index to a NumPy integer array, exactly mirroring `as.numeric(row.names(frame))`.
- All subsequent vectorized arithmetic (`// 2`, `% 2`) works identically on NumPy arrays.
- R's `match(a, b)` finds each element of `a` in `b` and returns its 1-based position; Python uses `np.searchsorted` (0-based) or `pd.Index.get_indexer` as the equivalent.

---

### 4.2 Extract Node IDs as Integer Array for C-Level / Matching Calls

**Locations:**
- `pred.rpart.R` — `pred.rpart` (line 21)
- `prune.rpart.R` — `prune.rpart` (line 4)
- `snip.rpart.R` — `snip.rpart` (line 14)

**Original R Context:**

Input: `frame` or `ff` is the rpart `frame` data frame. The result is passed to `as.integer()` for use in integer matching or as a C-level integer argument.

```r
# R — prune.rpart
ff <- tree$frame
id <- as.integer(row.names(ff))
# id is an integer vector of node numbers
toss <- id[ff$complexity <= cp & ff$var != "<leaf>"]

# R — pred.rpart
as.integer(row.names(frame))   # passed directly to .Call(C_pred_rpart, ...)

# R — snip.rpart
id <- as.integer(row.names(ff))
toss.idx <- match(toss, id, 0L)
```

**Python Equivalent:**

```python
import numpy as np

# frame / ff is a pd.DataFrame with an integer index
id_array = frame.index.to_numpy(dtype=np.int32)   # or dtype=int for 64-bit

# prune equivalent: boolean mask on the array
mask = (ff["complexity"].to_numpy() <= cp) & (ff["var"].to_numpy() != "<leaf>")
toss = id_array[mask]

# snip equivalent: find positions of toss elements in id_array
# np.isin gives a boolean mask; np.searchsorted gives positions
toss_positions = np.where(np.isin(id_array, toss))[0]  # 0-based row indices
```

**Explanation:**
- `dtype=np.int32` matches R's `integer` (32-bit). Use `dtype=int` (int64) if the wrapping Python code expects 64-bit integers.
- R's `match(toss, id, 0L)` returns 1-based indices with 0 for no-match; the Python equivalent using `np.searchsorted` or `np.isin` operates 0-based and returns `-1` or `False` for no-match — adjust index arithmetic accordingly.

---

### 4.3 Retain Raw Character Labels for Text Annotation or Dict Keys

**Locations:**
- `meanvar.rpart.R` — `meanvar.rpart` (line 12)
- `path.rpart.R` — `path.rpart` (line 9)

**Original R Context:**

Input: `frame` is the rpart `frame` data frame (or a subset of it). The raw character labels are used as plot text annotations or as list keys.

```r
# R — meanvar.rpart
frame  <- tree$frame
frame  <- frame[frame$var == "<leaf>", ]   # subset to leaf nodes only
label  <- row.names(frame)                 # character vector, e.g. c("2", "3", "4")
text(x, y, label)                          # used as text annotations in a plot

# R — path.rpart
n      <- row.names(frame)                 # character vector of all node IDs
path[[n[i]]] <- path.i                     # used as list (dict) keys
cat("node number:", n[i], "\n")            # printed directly as strings
```

**Python Equivalent:**

```python
# meanvar equivalent
frame_leaves = frame[frame["var"] == "<leaf>"]
label = frame_leaves.index.astype(str).tolist()
# label is e.g. ["2", "3", "4"] — use with matplotlib ax.annotate() or ax.text()

# path.rpart equivalent
n     = frame.index.astype(str).tolist()   # list of node ID strings
path  = {}
path[n[i]] = path_i                        # string key in a Python dict
print(f"node number: {n[i]}")
```

**Explanation:**
- `frame.index.astype(str).tolist()` produces a plain Python list of strings, which is the closest equivalent to R's character vector.
- When subsetting with a boolean mask, pandas preserves the original index on the result, so `frame_leaves.index` still holds the original node-number labels — the same behavior as R's `row.names` on a subsetted data frame.
- Python dictionaries accept string keys directly, matching R's named list pattern `path[[n[i]]]`.

---

### 4.4 Retrieve Row Names of the Training Model Frame to Name an Output Vector

**Locations:**
- `rpart.R` — `rpart` (line 269)

**Original R Context:**

Input: `m` is the model frame (a `data.frame` of the training data after `model.frame()` processing). Its row names are the original row identifiers of the training observations. The result is used as the `names` attribute of the `where` integer vector.

```r
# R — rpart
where         <- rpfit$which        # integer vector: which leaf each obs lands in
names(where)  <- row.names(m)       # attach training-observation row IDs as names
```

**Python Equivalent:**

```python
import pandas as pd

# m is a pd.DataFrame built from the training data;
# its index holds the original observation row labels (integers or strings)

where_series = pd.Series(
    rpfit_which,              # array of leaf node assignments (int)
    index=m.index,            # original observation row labels as the index
    dtype=int
)
# where_series.index gives the observation IDs; where_series.values gives leaf assignments
```

**Explanation:**
- In R, `names(where) <- row.names(m)` creates a named integer vector. The idiomatic Python equivalent is a `pandas.Series` where the index carries the row labels and the values carry the leaf-node assignments.
- `m.index` directly provides the training observation identifiers, exactly as `row.names(m)` does in R.
- If the downstream code only needs a plain dict mapping observation ID to leaf node, `dict(zip(m.index, rpfit_which))` is a simpler alternative.
