# Conversion Guide: `dimnames` (R to Python)

### 1. Overview of `dimnames` in R

`dimnames` is a base R function that gets or sets the dimension names of a multi-dimensional object, typically a matrix or array. When used as an assignment (`dimnames(x) <- value`), it attaches named labels to each dimension of the object.

The assigned value must be a list of the same length as the number of dimensions. Each element of the list is either a character vector of labels for that dimension, or `NULL` to leave that dimension unlabeled. For a 2D matrix, the list has two elements: row names and column names. Setting a dimension to `NULL` explicitly clears any existing names for that dimension.

- **Input (getter):** Any matrix, array, or data frame.
- **Input (setter):** A list of length equal to the number of dimensions, where each element is a character vector or `NULL`.
- **Output (getter):** A list of character vectors (or `NULL` entries).
- **Output (setter):** The object is modified in-place with its dimension names updated.

---

### 2. Contextual Usage Analysis

All three CSV occurrences use `dimnames` in its assignment form to label the rows and/or columns of a 2D matrix. Two distinct patterns appear:

**Pattern A — Setting row names, clearing column names (line 29):**
`pred` is a numeric matrix produced by subsetting `frame$yval2` with an integer index vector `where`. The call assigns `names(where)` (a character vector of observation identifiers) as row names and `NULL` as column names, explicitly erasing any column labels that existed in the source matrix.

**Pattern B — Setting both row names and column names (lines 37, 182):**

- Line 37: `pred` is again a matrix slice of `frame$yval2`. Row names are set to `names(where)` (observation identifiers) and column names are set to `ylevels` (a character vector of class labels, e.g. `c("setosa", "versicolor", "virginica")`).
- Line 182: `rpfit$cptable` is a numeric matrix returned from C code via `.Call`. Row names are set to a character vector `temp` such as `c("CP", "nsplit", "rel error", "xerror", "xstd")`, and column names are set to the integer sequence `1L:numcp` (coerced to character, representing pruning table column indices).

The recurring pattern is: produce or receive a raw numeric matrix, then attach semantically meaningful row and column labels in a single `dimnames<-` call. The data types are consistently numeric matrices with character-vector labels on one or both axes.

---

### 3. Python Conversion Strategy

The natural Python equivalent is a `pandas.DataFrame`. A `DataFrame` natively carries both row labels (`index`) and column labels (`columns`), exactly mirroring R's row and column dimnames on a 2D matrix. Setting `df.index` and `df.columns` after construction replicates `dimnames(x) <- list(rownames, colnames)` precisely.

`numpy.ndarray` is the lower-level alternative and should only be used when downstream code operates entirely in numpy and does not require labeled access. In that case, labels must be tracked separately, which is error-prone. Because the rpart codebase uses these dimension names for human-readable output (the CP table) and downstream slicing by label (prediction probabilities), `pandas.DataFrame` is the more robust and idiomatic choice.

When only row names need to be set and column names should be cleared (Pattern A), setting `df.columns = range(df.shape[1])` or leaving them as default integer indices achieves the equivalent of `NULL` on the column dimension.

---

### 4. Step-by-Step Conversion Examples

#### Example 1 — Set row names, clear column names

**Locations:** `predict.rpart.R`, function `predict.rpart`, line 29.

**Original R Context:**

- `pred` is a 2D numeric matrix produced by `frame$yval2[where, ]`. Each row corresponds to one observation; columns hold multi-output values (e.g., node counts or probability vectors). Their exact meaning depends on the tree method but the matrix is returned from C code and has no meaningful column labels at this stage.
- `names(where)` is a character vector of observation identifiers (e.g., row names of the input data frame).
- `NULL` as the second list element clears any existing column names.

```r
# pred: numeric matrix, shape (n_obs, n_cols)
# names(where): character vector of length n_obs
# Result: pred has row names = observation IDs, no column names
pred <- frame$yval2[where, ]
dimnames(pred) <- list(names(where), NULL)
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

# pred_array: np.ndarray of shape (n_obs, n_cols), from the equivalent of frame$yval2[where, ]
# row_names: list or array of observation identifier strings, equivalent to names(where)

pred = pd.DataFrame(pred_array)
pred.index = row_names        # set row labels (equivalent to R rownames)
pred.columns = range(pred.shape[1])  # clear column labels (equivalent to NULL in R)
```

**Explanation:**

- `pd.DataFrame(pred_array)` wraps the numpy array in a DataFrame, giving it default integer row and column indices.
- `pred.index = row_names` sets row labels, directly mapping to the first element of the R `list(names(where), NULL)`.
- `pred.columns = range(pred.shape[1])` resets columns to plain integers, reproducing the effect of `NULL` (no meaningful column labels). Alternatively, if downstream code never accesses columns by name, the default integer columns after `pd.DataFrame(pred_array)` are already equivalent and no explicit reset is needed.

---

#### Example 2 — Set both row names and column names (class probability matrix)

**Locations:** `predict.rpart.R`, function `predict.rpart`, line 37.

**Original R Context:**

- `pred` is a numeric probability matrix of shape `(n_obs, nclass)`, produced by slicing `frame$yval2` to extract per-class probability columns.
- `names(where)` is a character vector of observation identifiers.
- `ylevels` is a character vector of class labels (e.g., `c("class_A", "class_B", "class_C")`).
- After the call, `pred[i, j]` can be accessed as `pred["obs_id", "class_label"]`.

```r
# pred: numeric matrix, shape (n_obs, nclass)
# names(where): character vector of length n_obs
# ylevels: character vector of length nclass
pred <- frame$yval2[where, 1L + nclass + 1L:nclass, drop = FALSE]
dimnames(pred) <- list(names(where), ylevels)
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

# pred_array: np.ndarray of shape (n_obs, nclass)
# row_names: list of observation identifier strings, equivalent to names(where)
# ylevels: list of class label strings, e.g. ["class_A", "class_B", "class_C"]

# Equivalent of the R matrix slice (0-based, nclass cols starting at offset nclass+1):
# frame_yval2[:, nclass + 1 : nclass + 1 + nclass]  (adjust indices for 0-based Python)
pred = pd.DataFrame(
    pred_array,
    index=row_names,
    columns=ylevels
)
```

**Explanation:**

- The R index `1L + nclass + 1L:nclass` selects columns in 1-based R indexing. In Python (0-based), this translates to `pred_array[:, nclass + 1 : 2 * nclass + 1]` — adjust the concrete slice according to the actual array layout when implementing the full function.
- `index=row_names` at construction time is equivalent to the first element of the R `list(names(where), ylevels)`.
- `columns=ylevels` is equivalent to the second element.
- After conversion, `pred.loc["obs_id", "class_A"]` in pandas mirrors `pred["obs_id", "class_A"]` in R, preserving label-based access semantics.

---

#### Example 3 — Set row names and integer-sequence column names (CP table)

**Locations:** `rpart.R`, function `rpart`, line 182.

**Original R Context:**

- `rpfit$cptable` is a numeric matrix returned from C code via `.Call(C_rpart, ...)`. It has either 3 or 5 rows (depending on whether cross-validation was performed) and `numcp` columns (one per complexity parameter value evaluated).
- `temp` is a character vector — either `c("CP", "nsplit", "rel error")` or `c("CP", "nsplit", "rel error", "xerror", "xstd")` — used as row names.
- `1L:numcp` is an integer sequence coerced to character in R's dimnames, producing column labels `"1"`, `"2"`, ..., `"numcp"`.

```r
# rpfit$cptable: numeric matrix, shape (3 or 5, numcp)
# temp: character vector of length 3 or 5
# numcp: integer scalar
numcp <- ncol(rpfit$cptable)
temp <- if (nrow(rpfit$cptable) == 3L) c("CP", "nsplit", "rel error")
        else c("CP", "nsplit", "rel error", "xerror", "xstd")
dimnames(rpfit$cptable) <- list(temp, 1L:numcp)
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

# cptable_array: np.ndarray of shape (3 or 5, numcp), from the C call result
# numcp: int, number of CP columns

n_rows = cptable_array.shape[0]
numcp = cptable_array.shape[1]

if n_rows == 3:
    row_names = ["CP", "nsplit", "rel error"]
else:
    row_names = ["CP", "nsplit", "rel error", "xerror", "xstd"]

col_names = list(range(1, numcp + 1))  # [1, 2, ..., numcp], matching R's 1L:numcp

cptable = pd.DataFrame(
    cptable_array,
    index=row_names,
    columns=col_names
)
```

**Explanation:**

- R's `1L:numcp` creates the integer sequence `1, 2, ..., numcp`. In R's `dimnames`, these integers are stored as character strings internally, but `range(1, numcp + 1)` in Python produces equivalent integer column labels. Use `[str(i) for i in range(1, numcp + 1)]` if strict string-type column labels are required for downstream compatibility.
- R's matrix is oriented with metrics (CP, nsplit, etc.) as rows and CP candidates as columns, which is transposed relative to the typical "observations as rows" convention. The Python DataFrame preserves this orientation exactly — do not transpose unless downstream code explicitly expects it.
- `cptable.loc["CP"]` in pandas then returns the row of CP values across all candidates, mirroring `rpfit$cptable["CP", ]` in R.
