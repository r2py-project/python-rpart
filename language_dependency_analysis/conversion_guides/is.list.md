# Conversion Guide: `is.list` (R to Python)

---

### 1. Overview of `is.list` in R

`is.list(x)` is a base R primitive function that tests whether the object `x` is an R list (or a non-empty pairlist). It takes a single argument of any type and returns a single logical scalar (`TRUE` or `FALSE`).

Key behavioral facts:

- Returns `TRUE` for named and unnamed R lists (e.g., `list(a=1, b=2)`), including lists of mixed types.
- Returns `TRUE` for non-empty pairlists.
- Returns `FALSE` for atomic vectors, scalars, character strings, `NULL`, environments, and factors.
- Returns `TRUE` for data frames, because a data frame is internally stored as a named list of column vectors in R.
- It does **not** check that an object is exclusively a plain `list` — it is a broader type predicate. Crucially, it differs from `is.vector()`, which additionally requires the object to have no attributes other than `names`.

In rpart, `is.list` is used as a type-dispatch guard: it distinguishes between a plain string/symbol argument and a structured list object that carries multiple fields (a richer, user-supplied configuration object).

---

### 2. Contextual Usage Analysis

**Usage 1 — `rpart/R/rpart.R`, function `rpart`, line 42**

The `method` parameter of `rpart()` is checked with `is.list(method)` immediately after the block that auto-infers `method` as a character string (lines 35–40). R's `method` argument is documented to accept either:
- A character string (`"anova"`, `"poisson"`, `"class"`, or `"exp"`), or
- A named list containing user-defined split functions (`mlist$init`, `mlist$eval`, `mlist$split`).

The `is.list` guard on line 42 routes execution into the user-defined-method branch. Inside that branch, `method` (the list) is aliased to `mlist`, then `mlist$init(...)` is called to initialize the splitting engine. If `method` is not a list, the `else` branch runs `pmatch()` against the four built-in method strings.

The argument type is therefore: either `character(1)` or a named `list` of functions. The return value of `is.list(method)` is used purely as a branch condition.

**Usage 2 — `rpart/R/rpart.class.R`, function `rpart.class`, line 16**

The `parms` parameter of `rpart.class()` carries classification-specific hyperparameters: prior probabilities, a loss matrix, and the split criterion. The check structure is a three-way conditional:

- Line 11: `if (missing(parms) || is.null(parms))` — use auto-computed defaults.
- Line 16: `else if (is.list(parms))` — validate and unpack the user-supplied named list.
- Line 53: `else stop("Parameter argument must be a list")` — reject any other type.

Inside the list branch, `names(parms)` is verified to be non-null, then `pmatch()` is used to match names to the canonical set `c("prior", "loss", "split")`. The function then validates each component (`$prior`, `$loss`, `$split`) and reassembles a clean, canonical `parms` list. The argument type is therefore a named R list with up to three keys. The `is.list` check here acts as a type assertion before structural validation, preventing the code from attempting `names()` or `$` access on a non-list object.

**Recurring pattern:** In both usages, `is.list` serves as a type-dispatch predicate distinguishing a structured, named-list configuration object from a scalar/string argument. The list object in both cases is heterogeneous and named — closely analogous to a Python `dict`.

---

### 3. Python Conversion Strategy

**Chosen approach: `isinstance(x, dict)` as the primary equivalent, with `isinstance(x, list)` as a secondary option.**

R lists used in both contexts are **named lists** (accessed via `$name` or `[["name"]]`), making Python `dict` the most semantically accurate counterpart. In a well-typed Python translation of rpart:

- The `method` argument would be either a `str` or a `dict` of callables.
- The `parms` argument would be either `None` or a `dict` with keys `"prior"`, `"loss"`, `"split"`.

Using `isinstance(x, dict)` mirrors R's `is.list` in these contexts because:

1. Python `dict` is the natural idiom for a named, heterogeneous container — the defining characteristic of R lists used here.
2. It distinguishes a `dict` from a `str`, just as R's `is.list` distinguishes a list from a character string.
3. Using `isinstance(x, list)` would be misleading because plain Python `list` objects are positional (unnamed), whereas the R lists here are always accessed by name.

If the Python translation needs to accept both `dict` and custom mapping types, `isinstance(x, collections.abc.Mapping)` is the most robust form.

For the general case where unnamed R lists (positional containers) are being translated, `isinstance(x, list)` is correct. The correct choice is determined by whether the R list is named (-> `dict`) or unnamed/positional (-> `list`).

---

### 4. Step-by-Step Conversion Examples

#### Example 1: Dispatching on a user-supplied method object

**Locations:** `rpart/R/rpart.R`, function `rpart`

**Original R Context**

`method` is either a `character(1)` string (one of four built-in names) or a named `list` containing user-defined functions (`$init`, `$eval`, `$split`). `is.list(method)` returns `TRUE` only in the second case.

```r
# method: character(1) | named list of functions
if (is.list(method)) {
    mlist <- method
    method <- "user"
    init <- if (missing(parms)) mlist$init(Y, offset, wt = wt)
            else mlist$init(Y, offset, parms, wt)
    keep <- rpartcallback(mlist, nobs, init)
    method.int <- 4L
    parms <- init$parms
} else {
    method.int <- pmatch(method, c("anova", "poisson", "class", "exp"))
    # ...
}
```

**Python Equivalent**

```python
# method: str | dict with callable values keyed by "init", "eval", "split"
if isinstance(method, dict):
    mlist = method
    method = "user"
    if parms is None:
        init = mlist["init"](Y, offset, wt=wt)
    else:
        init = mlist["init"](Y, offset, parms, wt)
    keep = rpartcallback(mlist, nobs, init)
    method_int = 4
    parms = init["parms"]
else:
    valid_methods = ["anova", "poisson", "class", "exp"]
    if method not in valid_methods:
        raise ValueError("Invalid method")
    method_int = valid_methods.index(method) + 1  # 1-based to match R
    # ...
```

**Explanation**

- `is.list(method)` -> `isinstance(method, dict)`. The R list is named and accessed via `$key`, so `dict` is the correct Python analogue.
- R's `mlist$init(...)` becomes `mlist["init"](...)`. The `$` accessor for a named list maps directly to dict key access.
- `missing(parms)` in R (checking whether the caller omitted the argument) maps to a Python convention of using `parms=None` as the default sentinel and checking `if parms is None`.
- R's `pmatch()` for the `else` branch is replaced by a plain `in` check and `list.index()`, since Python strings do not need partial matching in this context.

---

#### Example 2: Validating a structured hyperparameter object

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class`

**Original R Context**

`parms` is either absent/`NULL` (use computed defaults) or a named list with up to three keys: `"prior"` (numeric vector), `"loss"` (numeric matrix), `"split"` (integer or string). `is.list(parms)` gates the validation block and guards `names(parms)` access.

```r
# parms: NULL | named list with keys "prior", "loss", "split"
if (missing(parms) || is.null(parms)) {
    parms <- list(prior = counts / sum(counts),
                  loss  = matrix(rep(1, numclass^2) - diag(numclass), numclass),
                  split = 1)
} else if (is.list(parms)) {
    if (is.null(names(parms))) stop("The parms list must have names")
    temp <- pmatch(names(parms), c("prior", "loss", "split"), 0L)
    if (any(temp == 0L)) stop("'parms' component not matched")
    names(parms) <- c("prior", "loss", "split")[temp]
    # ... validate $prior, $loss, $split individually ...
    parms <- list(prior = temp, loss = matrix(temp2, numclass), split = temp3)
} else {
    stop("Parameter argument must be a list")
}
```

**Python Equivalent**

```python
import numpy as np

# parms: None | dict with keys from {"prior", "loss", "split"}
VALID_PARMS_KEYS = {"prior", "loss", "split"}

if parms is None:
    parms = {
        "prior": counts / counts.sum(),
        "loss":  np.ones((numclass, numclass)) - np.eye(numclass),
        "split": 1,
    }
elif isinstance(parms, dict):
    if not parms:
        raise ValueError("The parms dict must have keys")
    unknown = set(parms.keys()) - VALID_PARMS_KEYS
    if unknown:
        raise ValueError(f"'parms' component not matched: {unknown}")

    prior = parms.get("prior")
    if prior is None:
        prior = counts / counts.sum()
    else:
        prior = np.asarray(prior, dtype=float)
        if not np.isclose(prior.sum(), 1.0):
            raise ValueError("Priors must sum to 1")
        if np.any(prior < 0):
            raise ValueError("Priors must be >= 0")
        if len(prior) != numclass:
            raise ValueError("Wrong length for priors")

    loss = parms.get("loss")
    if loss is None:
        loss = np.ones((numclass, numclass)) - np.eye(numclass)
    else:
        loss = np.asarray(loss, dtype=float).reshape(numclass, numclass)
        if np.any(np.diag(loss) != 0):
            raise ValueError("Loss matrix must have zero on diagonals")
        if np.any(loss < 0):
            raise ValueError("Loss matrix cannot have negative elements")
        if np.any(loss.sum(axis=1) == 0):
            raise ValueError("Loss matrix has a row of zeros")

    split_val = parms.get("split", 1)
    valid_splits = ["gini", "information"]
    if isinstance(split_val, str):
        matches = [s for s in valid_splits if s.startswith(split_val)]
        if not matches:
            raise ValueError("Invalid splitting rule")
        split_val = valid_splits.index(matches[0]) + 1  # 1-based index

    parms = {"prior": prior, "loss": loss, "split": split_val}
else:
    raise TypeError("Parameter argument must be a dict")
```

**Explanation**

- `is.list(parms)` -> `isinstance(parms, dict)`. The `parms` R list is always named and accessed by key (`$prior`, `$loss`, `$split`), so `dict` is the correct Python type.
- The three-way R conditional (`missing/NULL` -> `is.list` -> `else stop`) maps cleanly to Python's `if parms is None` -> `elif isinstance(parms, dict)` -> `else raise TypeError(...)`.
- `is.null(names(parms))` (checking for an unnamed list) becomes `if not parms` (empty dict) — an empty `dict` has no keys, just as an unnamed R list has no `names`.
- R's `pmatch(names(parms), c("prior","loss","split"), 0L)` (partial-match key names) is replaced by explicit set-difference validation using `set(parms.keys()) - VALID_PARMS_KEYS`, which is more Pythonic and equally strict.
- R's `matrix(rep(1, numclass^2) - diag(numclass), numclass)` becomes `np.ones((numclass, numclass)) - np.eye(numclass)` using NumPy, preserving the vectorized construction of the default loss matrix.
- R's `pmatch(parms$split, c("gini", "information"))` for the split criterion is replicated with a prefix-match list comprehension, matching R's partial-matching semantics.
