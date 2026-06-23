# Conversion Guide: `is.logical` in R (rpart package)

---

## 1. Overview of `is.logical` in R

`is.logical(x)` is a base R predicate function that tests whether its argument `x` is of the logical type — that is, whether `x` is a vector whose elements are `TRUE`, `FALSE`, or `NA` (logical NA). It returns a single scalar `TRUE` or `FALSE`.

Key properties:

- **Input:** Any R object.
- **Output:** A single logical scalar (`TRUE` or `FALSE`). It never returns a vector.
- **Logical type in R:** R's logical type corresponds to Boolean values. Importantly, R distinguishes between a bare logical value (`TRUE`/`FALSE`), an integer (`1L`/`0L`), and a numeric (`1.0`/`0.0`). `is.logical(1L)` returns `FALSE`; `is.logical(TRUE)` returns `TRUE`.
- **NA handling:** `NA` on its own is of type logical in R, so `is.logical(NA)` returns `TRUE`.
- This function is most commonly used for type-guarding arguments before dispatching conditional logic.

---

## 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/labels.rpart.R`
**Function:** `labels.rpart`
**Line:** 21

The relevant block (lines 19-24) is:

```r
if (missing(minlength) && !missing(pretty)) {
    minlength <- if (is.null(pretty)) 1L
    else if (is.logical(pretty)) {
        if (pretty) 4L else 0L
    } else 0L
}
```

**What is happening here:**

The function `labels.rpart` accepts a legacy argument `pretty` for historical compatibility. When `minlength` is not supplied by the caller but `pretty` is, the code infers `minlength` from `pretty` using a three-way type dispatch:

| Value of `pretty` | Inferred `minlength` |
|---|---|
| `NULL` | `1L` |
| A logical (`TRUE` or `FALSE`) | `4L` if `TRUE`, `0L` if `FALSE` |
| Anything else (e.g., numeric `0`) | `0L` |

`is.logical(pretty)` is the guard for the second branch. It confirms that `pretty` holds a genuine Boolean before reading it as `TRUE`/`FALSE`. Because R differentiates numeric `0` from logical `FALSE`, this guard is essential: passing `pretty = 0` (numeric) must fall through to the `else 0L` branch rather than being treated as `FALSE`.

**Data types involved:**

- `pretty` on entry: any R value — `NULL`, `TRUE`, `FALSE`, a numeric like `0`, or potentially a character string in unusual usage.
- `is.logical(pretty)` always returns a single scalar `bool`-equivalent.
- The result is used immediately as a Boolean condition, not stored.

**Pattern:** This is a single, self-contained type-dispatch pattern. There is only one functionally distinct usage in the CSV.

---

## 3. Python Conversion Strategy

**Chosen approach: `isinstance(x, bool)`**

Python's native `isinstance` with the built-in `bool` type is the direct equivalent of R's `is.logical`. No external library (NumPy, pandas, SciPy) is needed or appropriate here, because:

1. The usage is a scalar type guard, not a vectorized computation. R's `is.logical` always returns a single scalar, and `isinstance` mirrors that exactly.
2. NumPy `bool_` arrays would introduce unnecessary complexity — the argument `pretty` in Python will arrive as a plain Python `bool`, `None`, or integer, not as an ndarray.
3. The critical semantic subtlety to preserve is that Python `int` must **not** match the `bool` check, just as R's numeric `0` does not match `is.logical`. In Python, `bool` is a subclass of `int`, so `isinstance(0, bool)` correctly returns `False`, while `isinstance(False, bool)` correctly returns `True`. This behaviour precisely mirrors R's type system for this context.

One important nuance: in Python, `isinstance(True, int)` returns `True` (because `bool` is a subclass of `int`), so the type check order matters when multiple `isinstance` checks are chained. The `bool` check must come before any `int` check.

---

## 4. Step-by-Step Conversion Examples

### Example 1: Type-dispatched inference of `minlength` from the `pretty` argument

**Locations:**
- File: `/groups/jli9/Yufei/python-rpart/rpart/R/labels.rpart.R`
- Function: `labels.rpart`
- Line: 21

**Original R Context:**

`pretty` is a parameter of type `NULL | logical | numeric | any`. `minlength` is an integer parameter with default `1L`. The block below executes only when the caller omits `minlength` but supplies `pretty`.

```r
# pretty: NULL | TRUE | FALSE | numeric (e.g. 0)
# minlength: integer, default 1L

if (missing(minlength) && !missing(pretty)) {
    minlength <- if (is.null(pretty)) 1L
    else if (is.logical(pretty)) {
        if (pretty) 4L else 0L
    } else 0L
}
```

**Python Equivalent:**

```python
_SENTINEL = object()  # used to detect "argument was not supplied"

def labels_rpart(obj, digits=4, minlength=_SENTINEL, pretty=_SENTINEL, collapse=True):
    # Replicate R's missing(minlength) && !missing(pretty) guard
    minlength_missing = minlength is _SENTINEL
    pretty_missing = pretty is _SENTINEL

    if minlength_missing and not pretty_missing:
        if pretty is None:
            minlength = 1
        elif isinstance(pretty, bool):
            minlength = 4 if pretty else 0
        else:
            minlength = 0
    elif minlength is _SENTINEL:
        minlength = 1  # default value when both are absent

    # ... rest of labels_rpart logic follows
    print(f"minlength resolved to: {minlength}")


# Demonstrate the three dispatch branches:
labels_rpart(None, pretty=None)       # minlength -> 1  (NULL branch)
labels_rpart(None, pretty=True)       # minlength -> 4  (logical TRUE branch)
labels_rpart(None, pretty=False)      # minlength -> 0  (logical FALSE branch)
labels_rpart(None, pretty=0)          # minlength -> 0  (numeric/other branch)
labels_rpart(None, minlength=2)       # minlength -> 2  (explicit override, guard skipped)
```

**Expected output:**
```
minlength resolved to: 1
minlength resolved to: 4
minlength resolved to: 0
minlength resolved to: 0
minlength resolved to: 2
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `missing(minlength)` | `minlength is _SENTINEL` | A sentinel default detects whether the caller omitted the argument, since Python has no `missing()` builtin. |
| `is.null(pretty)` | `pretty is None` | R's `NULL` maps to Python's `None`; identity check `is None` is idiomatic. |
| `is.logical(pretty)` | `isinstance(pretty, bool)` | Both check for the Boolean type exclusively. Python's `isinstance(0, bool)` is `False`, so numeric `0` correctly falls through to the `else` branch, preserving the R semantic. |
| `if (pretty) 4L else 0L` | `4 if pretty else 0` | Identical Boolean evaluation; `True` yields `4`, `False` yields `0`. |
| `else 0L` | `else: minlength = 0` | Catch-all for any non-null, non-boolean value of `pretty`. |

The key correctness point is that Python's `bool` is a subclass of `int`, which means `isinstance(True, int)` is `True` in Python. If you ever write a chain of `isinstance` checks that includes both `bool` and `int`, the `bool` check must come first — exactly as the `is.logical` check comes before the numeric fallback in the R code.
