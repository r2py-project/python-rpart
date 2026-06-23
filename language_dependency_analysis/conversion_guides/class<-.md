# Conversion Guide: `class<-` in R

---

## 1. Overview of `class<-` in R

`class<-` is R's replacement function for assigning S3 class labels to an object. It operates via R's assignment-style syntax:

```r
class(x) <- value
```

- **`x`**: Any R object (vector, list, data frame, etc.).
- **`value`**: A character vector of one or more class names to attach to `x`, or `NULL` to strip all class information.

Internally, `class<-` sets the `"class"` attribute of the object. When a generic function (e.g., `print`, `summary`) is later called on that object, R's S3 dispatch mechanism walks the class vector from left to right, looking for a method named `generic.classname`, and falls back to `generic.default` if none is found.

Assigning a vector of class names (e.g., `c("na.rpart", "omit")`) establishes an inheritance chain: the object is considered an instance of `"na.rpart"` first, and of `"omit"` second. This means method dispatch will try `generic.na.rpart` before `generic.omit` before `generic.default`.

Setting `value = NULL` removes the class attribute entirely, reverting the object to its implicit class (e.g., `"integer"`, `"list"`).

---

## 2. Contextual Usage Analysis

### Source location

- **File:** `rpart/R/na.rpart.R`
- **Function:** `na.rpart`
- **Line:** 21

### Relevant source block (lines 17-23)

```r
temp <- seq(keep)[!keep]
names(temp) <- row.names(x)[!keep]
## the methods for this group are all the same as for na.omit
class(temp) <- c("na.rpart", "omit")
structure(x[keep , , drop = FALSE], na.action = temp)
```

### Data types involved

| Variable | Type before assignment | Value after `class<-` |
|----------|------------------------|------------------------|
| `temp`   | `integer` vector (indices of dropped rows) | `c("na.rpart", "omit")` |
| `names(temp)` | character vector of the dropped row names | unchanged |

`temp` is a named integer vector produced by `seq(keep)[!keep]`, where `keep` is a logical vector marking which rows of the input data frame `x` should be retained. After `class(temp) <- c("na.rpart", "omit")`, `temp` is used as the `na.action` attribute of the returned data frame, signalling to downstream code which rows were removed and why.

The class vector `c("na.rpart", "omit")` mirrors the convention used by base R's `na.omit()`, which tags its result with `class "omit"`. Appending `"na.rpart"` first allows rpart-specific methods (e.g., `print.na.rpart`) to override the default `"omit"` behaviour while still inheriting it as a fallback.

### Recurring pattern

There is exactly one occurrence of `class<-` in the CSV subset. The pattern is:
1. Build a plain atomic/list object.
2. Attach metadata to it via `names()`, `attr()`, or similar.
3. Stamp the object with one or more S3 class labels using `class(obj) <- c("primary.class", "fallback.class")`.
4. Use the stamped object as an attribute of a larger structure.

---

## 3. Python Conversion Strategy

Python does not have S3-style dispatch, but the closest idiomatic equivalent depends on what the stamped object is used for:

| R mechanism | Python equivalent |
|-------------|-------------------|
| S3 class label for dispatch | A proper Python `class` (type) |
| Named integer vector with class attribute | A subclass of `numpy.ndarray` or a lightweight custom class holding a `numpy` array plus metadata |
| `na.action` attribute on a data frame | An attribute stored on a `pandas.DataFrame` via `df.attrs` or a companion variable |

For this specific usage — where `temp` is a named integer index vector that is later attached as `na.action` metadata — the recommended Python strategy is to define a lightweight class that wraps a `numpy.ndarray` (for the integer indices) and stores the row names as a parallel array. This preserves both the data and the type identity needed for isinstance checks and method dispatch.

**Chosen libraries:** `numpy` for the underlying integer array, plain Python `class` definitions for the S3-equivalent type hierarchy.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Assigning a multi-class S3 label to a named integer vector

**Locations:** `na.rpart.R` — function `na.rpart`, line 21.

**Original R context**

```r
# temp: integer vector of dropped-row indices (1-based)
# names(temp): character vector of dropped row names
temp <- seq(keep)[!keep]
names(temp) <- row.names(x)[!keep]
class(temp) <- c("na.rpart", "omit")
```

- Input type of `temp` before assignment: `integer` (1-based positional indices).
- `class<-` attaches the attribute `c("na.rpart", "omit")` in place; `temp` is not copied.
- Return type: the same `integer` vector, now with a `class` attribute — R's S3 dispatch will resolve methods in order `na.rpart` → `omit` → `default`.

**Python equivalent**

```python
import numpy as np


class Omit(np.ndarray):
    """
    Base class mirroring R's "omit" S3 class.
    Wraps a 1-D integer array of dropped-row indices (0-based in Python)
    and stores the corresponding row names.
    """

    def __new__(cls, indices: np.ndarray, row_names: list[str]):
        obj = np.asarray(indices, dtype=np.intp).view(cls)
        obj.row_names = list(row_names)
        return obj

    def __array_finalize__(self, obj):
        if obj is not None:
            self.row_names = getattr(obj, "row_names", [])


class NaRpart(Omit):
    """
    Mirrors R's "na.rpart" S3 class (inherits from Omit).
    Python method resolution order: NaRpart → Omit → np.ndarray.
    """
    pass


# --- translation of the na.rpart logic ---

def na_rpart(x_df):
    """
    x_df: pandas.DataFrame (equivalent to R's data frame x).
    Returns the filtered DataFrame with an `na_action` attribute, or x_df unchanged.
    """
    import pandas as pd

    keep = ~x_df.isnull().any(axis=1)          # boolean mask of retained rows

    if keep.all():
        return x_df

    # Indices of dropped rows (0-based, matching Python convention)
    dropped_positions = np.where(~keep.to_numpy())[0]
    dropped_names = x_df.index[~keep].tolist()

    # R: class(temp) <- c("na.rpart", "omit")
    temp = NaRpart(dropped_positions, dropped_names)

    result = x_df.loc[keep].copy()
    result.attrs["na_action"] = temp            # equivalent to structure(..., na.action = temp)
    return result
```

**Explanation**

| R construct | Python translation | Notes |
|---|---|---|
| `seq(keep)[!keep]` | `np.where(~keep)[0]` | R indices are 1-based; Python uses 0-based. Subtract 1 if an exact numeric match with R output is required. |
| `names(temp) <- row.names(x)[!keep]` | `NaRpart(..., row_names=...)` constructor argument | Stored as `.row_names` attribute on the ndarray subclass. |
| `class(temp) <- c("na.rpart", "omit")` | `class NaRpart(Omit)` with `class Omit(np.ndarray)` | Python's MRO (`NaRpart → Omit → ndarray`) exactly mirrors R's dispatch order (`na.rpart → omit → default`). |
| S3 dispatch `generic.na.rpart` | `isinstance(obj, NaRpart)` or overriding a method in `NaRpart` | Define the more specific behaviour in `NaRpart`, fall back to `Omit`. |
| `structure(..., na.action = temp)` | `result.attrs["na_action"] = temp` | `pandas.DataFrame.attrs` is the idiomatic slot for arbitrary metadata; it survives most non-aggregating DataFrame operations. |

Key nuances:
- R's `class<-` mutates the object in place (no copy). The Python equivalent achieves the same effect by constructing the typed object directly instead of building a plain array first.
- Subclassing `np.ndarray` requires the `__new__` / `__array_finalize__` protocol to ensure the custom attribute (`row_names`) survives numpy operations that internally create new views of the array.
- If downstream code only needs `isinstance` checks (and never calls numpy operations on the index array), a simpler plain-Python dataclass can replace the `np.ndarray` subclass entirely, which is often more readable.
