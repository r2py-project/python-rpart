# Conversion Guide: `pmatch` (R to Python)

---

## 1. Overview of `pmatch` in R

`pmatch(x, table, nomatch = NA_integer_, duplicates.ok = FALSE)`

`pmatch` performs **partial string matching**. For each element of `x`, it searches `table` for a unique partial match and returns the **integer index** of the matched element in `table`. "Partial" means that `x[i]` is accepted if it is an unambiguous prefix of exactly one element in `table`.

Key behavioural rules:

- If `x[i]` exactly or partially matches exactly one element of `table`, the 1-based integer position of that element is returned.
- If `x[i]` matches zero elements, or matches more than one element ambiguously, the value of `nomatch` is returned (default `NA_integer_`).
- Passing `nomatch = 0L` causes unmatched elements to return `0` (an integer zero) rather than `NA`. This is the idiom used when the caller wants to detect failed matches with `any(result == 0L)` instead of `any(is.na(result))`.
- The return value is always an **integer vector** of the same length as `x`.
- When `x` is a character scalar and `table` is a character vector, the return is a single integer — which R code often uses directly as an index into `table` to canonicalise the matched string.

Typical inputs: character scalar or character vector `x`; character vector `table`; optional integer `nomatch`.
Typical outputs: integer scalar or integer vector.

---

## 2. Contextual Usage Analysis

Across the eight call sites in the CSV, `pmatch` is used in two distinct patterns:

**Pattern A — single-value method dispatch** (3 call sites): A single string argument (e.g., `method`) is matched against a fixed set of allowed string literals. The returned integer is used directly as an index to validate and canonicalise the input, and the calling code raises an error when `NA` is returned.

**Pattern B — named-list key validation** (5 call sites): `names(parms)` (a character vector of user-supplied parameter names) is matched against a canonical names vector. `nomatch = 0L` is passed so that unmatched entries produce `0` instead of `NA`, enabling `any(indx == 0L)` as the failure check. The result vector is then used to reorder/canonicalise `names(parms)` by indexing into the canonical names vector.

All arguments are plain R character strings or character vectors. No numeric or factor types are involved. The return values are integer scalars (Pattern A) or integer vectors (Pattern B).

---

## 3. Python Conversion Strategy

The standard library `difflib.get_close_matches` is not suitable because it uses similarity scoring rather than prefix matching. The best Python equivalent is a **custom prefix-matching function** that replicates R's exact semantics: unambiguous prefix lookup returning a 1-based integer index (to preserve parity with R's indexing) or a sentinel value on failure.

For Pattern A (single scalar lookup), a lightweight helper that returns the 1-based index or `None`/raises on failure is sufficient.

For Pattern B (vector lookup with `nomatch = 0`), the same helper is applied element-wise, returning a list of integers where `0` signals no match — directly mirroring the `nomatch = 0L` behaviour.

`numpy` is not needed here because the inputs and outputs are small Python lists of strings and integers, not numerical arrays. The conversion is purely string-processing logic.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Single-Value Method Dispatch

**Locations:**
- `rpart/R/rpart.R`, function `rpart`, line 58
- `rpart/R/xpred.rpart.R`, function `xpred.rpart`, line 10
- `rpart/R/rpart.class.R`, function `rpart.class`, line 48
- `rpart/R/rpart.exp.R`, function `rpart.exp`, line 121
- `rpart/R/rpart.poisson.R`, function `rpart.poisson`, line 26

**Original R Context:**

Input: a single character string (e.g., `method` or `parms$split` or `parms$method`).
Output: a single integer (1-based position in `table`), or `NA` on failure.

```r
# rpart.R line 58-60
method.int <- pmatch(method, c("anova", "poisson", "class", "exp"))
if (is.na(method.int)) stop("Invalid method")
method <- c("anova", "poisson", "class", "exp")[method.int]

# xpred.rpart.R line 10-11
method.int <- pmatch(method, c("anova", "poisson", "class", "user", "exp"))
if (method.int == 5L) method.int <- 2L

# rpart.class.R line 48-49
temp3 <- pmatch(parms$split, c("gini", "information"))
if (is.null(temp3)) stop("Invalid splitting rule")

# rpart.exp.R line 121-122  (identical pattern in rpart.poisson.R line 26-27)
method <- pmatch(parms$method, c("deviance", "sqrt"))
if (is.na(method)) stop("Invalid error method for Poisson")
```

**Python Equivalent:**

```python
def pmatch(x, table, nomatch=None):
    """
    Partial string matching replicating R's pmatch().

    Returns the 1-based integer index of the unique element in `table`
    that `x` is a prefix of.  Returns `nomatch` if there is no match
    or if the match is ambiguous.
    """
    matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
    if len(matches) == 1:
        return matches[0]
    # Exact match wins over ambiguity (mirrors R behaviour)
    exact = [i + 1 for i, s in enumerate(table) if s == x]
    if len(exact) == 1:
        return exact[0]
    return nomatch


# --- rpart equivalent (rpart.R line 58-60) ---
METHODS = ["anova", "poisson", "class", "exp"]

method_int = pmatch(method, METHODS)
if method_int is None:
    raise ValueError("Invalid method")
method = METHODS[method_int - 1]   # convert to 0-based for Python list access

# --- xpred.rpart equivalent (xpred.rpart.R line 10-11) ---
XPRED_METHODS = ["anova", "poisson", "class", "user", "exp"]

method_int = pmatch(method, XPRED_METHODS)
if method_int == 5:
    method_int = 2   # remap "exp" to the same internal code as "poisson"

# --- rpart.class split parameter (rpart.class.R line 48-49) ---
SPLIT_OPTIONS = ["gini", "information"]

temp3 = pmatch(parms["split"], SPLIT_OPTIONS)
if temp3 is None:
    raise ValueError("Invalid splitting rule")

# --- rpart.exp / rpart.poisson method parameter (lines 121 / 26) ---
METHOD_OPTIONS = ["deviance", "sqrt"]

method = pmatch(parms["method"], METHOD_OPTIONS)
if method is None:
    raise ValueError("Invalid error method for Poisson")
```

**Explanation:**

- R's `pmatch` returns a 1-based integer. The Python helper preserves 1-based indexing so that downstream remapping logic (e.g., `method.int == 5L`) can be ported without offset adjustments.
- R returns `NA` on failure; the Python helper returns `None` (or a caller-supplied sentinel), and the caller raises an exception, matching the `stop(...)` calls in R.
- The exact-match tiebreaker (checking `s == x` after prefix matches) replicates R's rule that an exact match always wins over ambiguous prefix matches.
- The xpred.rpart remap (`if method.int == 5L: method.int <- 2L`) translates directly since 1-based indexing is preserved.

---

### 4.2 Pattern B — Named-List Key Validation with `nomatch = 0L`

**Locations:**
- `rpart/R/rpart.class.R`, function `rpart.class`, line 18
- `rpart/R/rpart.exp.R`, function `rpart.exp`, line 114
- `rpart/R/rpart.poisson.R`, function `rpart.poisson`, line 19

**Original R Context:**

Input: a character vector `names(parms)` (user-supplied parameter names); a canonical names vector; `nomatch = 0L`.
Output: an integer vector of the same length as `names(parms)`, where each element is the 1-based position of the matched canonical name, or `0` for any name that failed to match.

```r
# rpart.class.R lines 18-22
temp <- pmatch(names(parms), c("prior", "loss", "split"), 0L)
if (any(temp == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[temp == 0L]), domain = NA)
names(parms) <- c("prior", "loss", "split")[temp]

# rpart.poisson.R lines 19-23  (identical pattern in rpart.exp.R lines 114-118)
parmsNames <- c("method", "shrink")
indx <- pmatch(names(parms), parmsNames, 0L)
if (any(indx == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[indx == 0L]), domain = NA)
else names(parms) <- parmsNames[indx]
```

**Python Equivalent:**

```python
def pmatch_vec(x_vec, table, nomatch=0):
    """
    Vectorised partial string matching replicating R's pmatch() with a vector x.

    Returns a list of 1-based integer indices (length == len(x_vec)).
    Elements that do not match uniquely are set to `nomatch` (default 0).
    """
    result = []
    for x in x_vec:
        matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
        if len(matches) == 1:
            result.append(matches[0])
        else:
            exact = [i + 1 for i, s in enumerate(table) if s == x]
            result.append(exact[0] if len(exact) == 1 else nomatch)
    return result


# --- rpart.class equivalent (rpart.class.R lines 18-22) ---
PARMS_NAMES_CLASS = ["prior", "loss", "split"]

temp = pmatch_vec(list(parms.keys()), PARMS_NAMES_CLASS, nomatch=0)
unmatched = [k for k, idx in zip(parms.keys(), temp) if idx == 0]
if unmatched:
    raise ValueError(f"'parms' component not matched: {', '.join(unmatched)}")
# Canonicalise the keys using the matched indices (convert to 0-based)
parms = {PARMS_NAMES_CLASS[idx - 1]: v for (k, v), idx in zip(parms.items(), temp)}

# --- rpart.poisson / rpart.exp equivalent (lines 19-23 / 114-118) ---
PARMS_NAMES_SURV = ["method", "shrink"]

indx = pmatch_vec(list(parms.keys()), PARMS_NAMES_SURV, nomatch=0)
unmatched = [k for k, idx in zip(parms.keys(), indx) if idx == 0]
if unmatched:
    raise ValueError(f"'parms' component not matched: {', '.join(unmatched)}")
parms = {PARMS_NAMES_SURV[idx - 1]: v for (k, v), idx in zip(parms.items(), indx)}
```

**Explanation:**

- `pmatch_vec` applies the same prefix-matching logic element-wise to a list of strings, returning a plain Python list of integers — the direct analogue of R's vectorised `pmatch` over a character vector.
- R's `nomatch = 0L` becomes `nomatch=0` in Python. The sentinel is `0` (not `None`) to allow the `any(indx == 0)` style check to work cleanly with a list comprehension.
- `names(parms)[temp == 0L]` (logical subsetting in R) maps to a list comprehension that pairs keys with their match indices.
- `c("prior", "loss", "split")[temp]` (R integer vector indexing) maps to `PARMS_NAMES_CLASS[idx - 1]` with an explicit `-1` to convert from 1-based to 0-based indexing.
- Because Python `dict` preserves insertion order (Python 3.7+), iterating `parms.items()` in parallel with `indx` is safe and correct.
