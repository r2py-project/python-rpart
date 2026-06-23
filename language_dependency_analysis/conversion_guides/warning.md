# Conversion Guide: `warning` (R to Python)

---

## 1. Overview of `warning` in R

`warning()` in R generates a warning message and (by default) continues execution. It does **not** halt the program like `stop()`. Warnings are collected and displayed at the end of a top-level expression or immediately if `options(warn = 1)` is set; they become errors if `options(warn = 2)` is set.

**Signature:**

```r
warning(..., call. = TRUE, immediate. = FALSE, noBreaks. = FALSE, domain = NULL)
```

Key parameters:
- `...` — one or more character strings (or objects coercible to character) that are concatenated to form the warning message.
- `call.` — logical; if `TRUE` (the default), the call that generated the warning is included in the message.
- `domain` — translation domain for `gettext`/`gettextf` messages. When `domain = NA`, translation is suppressed and the string is used verbatim.

The function returns `NULL` invisibly and is called purely for its side effect of emitting a diagnostic.

---

## 2. Contextual Usage Analysis

Across the ten call sites in the CSV, `warning` is used in two broad patterns:

**Pattern A — Literal string messages (no interpolation)**

The message is a fixed string literal passed directly to `warning`. This appears in `rpart.control.R` (four calls) and in `rsq.rpart.R` and `text.rpart.R` (one call each). The warnings guard against invalid parameter values or deprecated arguments and run after an `if` condition detects the problem.

**Pattern B — Interpolated or translated string messages**

The message is built at runtime using either:
- `gettext("... %s ...", value)` — retrieves a translated string and substitutes a runtime value (used in `snip.rpart.R` line 20).
- `gettextf("... %s ...", paste(...))` — a `sprintf`-style variant that also handles translation (used in `zzz.R` lines 25 and 29).
- A plain literal with `domain = NA` to suppress translation (used in `labels.rpart.R` line 66).

In every case the inputs are scalars or short character strings and the warning message is a single string. No vectorized data types are involved. The return value of `warning()` itself is never captured by any caller.

---

## 3. Python Conversion Strategy

The direct Python equivalent of `warning()` is `warnings.warn()` from the Python standard library module `warnings`. No third-party library (NumPy, SciPy, pandas) is needed because `warning` is a purely diagnostic, non-computational function — it carries no numerical or array logic.

Key mapping decisions:

| R concept | Python equivalent |
|---|---|
| `warning("msg")` | `warnings.warn("msg")` |
| `warning("msg", call. = TRUE)` | `warnings.warn("msg", stacklevel=2)` (includes caller frame) |
| `domain = NA` (suppress translation) | No action needed; Python's `warnings.warn` is not translated by default |
| `gettext("Nodes %s ...", value)` | f-string or `str.format()` |
| `gettextf("nodes %s ...", paste(x, collapse=","))` | f-string with `", ".join(...)` |
| `warning` inside a guard `if` block | `warnings.warn` inside an equivalent `if` block |

The default warning category `UserWarning` is the closest semantic match to R's general-purpose `warning`. More specialised categories (`RuntimeWarning`, `DeprecationWarning`, `ValueError`) may be used where the context warrants it, as noted in the examples below.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Literal string warning — parameter validation guards

**Locations:**
- `rpart/R/rpart.control.R`, function `rpart.control`, lines 8, 12, 19, 23

**Original R Context:**

The function `rpart.control` validates its integer/scalar control parameters and issues a warning before clamping or resetting the value to an in-range default.

```r
# Parameter type: scalar integer/numeric
# Return value of warning(): NULL (ignored)

if (maxcompete < 0L) {
    warning("The value of 'maxcompete' supplied is < 0; the value 0 was used instead")
    maxcompete <- 0L
}
if (any(xval < 0L)) {
    warning("The value of 'xval' supplied is < 0; the value 0 was used instead")
    xval <- 0L
}
if ((usesurrogate < 0L) || (usesurrogate > 2L)) {
    warning("The value of 'usesurrogate' supplied was out of range, the default value of 2 is used instead.")
    usesurrogate <- 2L
}
if ((surrogatestyle < 0L) || (surrogatestyle > 1L)) {
    warning("The value of 'surrogatestyle' supplied was out of range, the default value of 0 is used instead.")
    surrogatestyle <- 0L
}
```

**Python Equivalent:**

```python
import warnings

def rpart_control(
    minsplit=20,
    minbucket=None,
    cp=0.01,
    maxcompete=4,
    maxsurrogate=5,
    usesurrogate=2,
    xval=10,
    surrogatestyle=0,
    maxdepth=30,
):
    if minbucket is None:
        minbucket = round(minsplit / 3)

    if maxcompete < 0:
        warnings.warn(
            "The value of 'maxcompete' supplied is < 0; the value 0 was used instead",
            UserWarning,
            stacklevel=2,
        )
        maxcompete = 0

    if any(x < 0 for x in ([xval] if isinstance(xval, int) else xval)):
        warnings.warn(
            "The value of 'xval' supplied is < 0; the value 0 was used instead",
            UserWarning,
            stacklevel=2,
        )
        xval = 0

    if maxdepth > 30:
        raise ValueError("Maximum depth is 30")
    if maxdepth < 1:
        raise ValueError("Maximum depth must be at least 1")

    if not (0 <= usesurrogate <= 2):
        warnings.warn(
            "The value of 'usesurrogate' supplied was out of range, "
            "the default value of 2 is used instead.",
            UserWarning,
            stacklevel=2,
        )
        usesurrogate = 2

    if not (0 <= surrogatestyle <= 1):
        warnings.warn(
            "The value of 'surrogatestyle' supplied was out of range, "
            "the default value of 0 is used instead.",
            UserWarning,
            stacklevel=2,
        )
        surrogatestyle = 0

    return dict(
        minsplit=minsplit,
        minbucket=minbucket,
        cp=cp,
        maxcompete=maxcompete,
        maxsurrogate=maxsurrogate,
        usesurrogate=usesurrogate,
        surrogatestyle=surrogatestyle,
        maxdepth=maxdepth,
        xval=xval,
    )
```

**Explanation:**
- Each `warning(...)` maps to `warnings.warn(..., UserWarning, stacklevel=2)`. `stacklevel=2` ensures the warning points to the caller of `rpart_control` rather than to the line inside the function, mirroring R's default `call. = TRUE` behaviour.
- R's `any(xval < 0L)` (which vectorises over a length-n `xval`) becomes a generator expression that handles both scalar integers and lists.
- R's `stop(...)` becomes `raise ValueError(...)`.

---

### 4.2 Literal string warning — deprecated argument

**Locations:**
- `rpart/R/text.rpart.R`, function `text.rpart`, line 15

**Original R Context:**

```r
# 'label' is a named argument present in the function signature for
# backward compatibility; its value is never used after the check.
# Parameter type: any (presence detected by missing())
# Return value of warning(): NULL (ignored)

if (!missing(label)) warning("argument 'label' is no longer used")
```

**Python Equivalent:**

```python
import warnings

def text_rpart(x, splits=True, label=None, FUN=None, all=False, ...):
    if label is not None:
        warnings.warn(
            "argument 'label' is no longer used",
            DeprecationWarning,
            stacklevel=2,
        )
    ...
```

**Explanation:**
- R uses `missing(label)` to detect whether the caller explicitly supplied the argument. In Python the idiomatic equivalent is a sentinel default of `None`, with an `is not None` check.
- `DeprecationWarning` is preferred over `UserWarning` here because the message describes a deprecated API, which matches Python's standard warning taxonomy.

---

### 4.3 Literal string warning — inapplicable method

**Locations:**
- `rpart/R/rsq.rpart.R`, function `rsq.rpart`, line 17

**Original R Context:**

```r
# 'method' is a scalar string extracted from the rpart object.
# The warning fires when the caller uses a non-anova method.
# Return value of warning(): NULL (ignored)

if (!method == "anova")
    warning("may not be applicable for this method")
```

**Python Equivalent:**

```python
import warnings

def rsq_rpart(x):
    ...
    method = x.method
    if method != "anova":
        warnings.warn(
            "may not be applicable for this method",
            UserWarning,
            stacklevel=2,
        )
    ...
```

**Explanation:**
- The R condition `!method == "anova"` is equivalent to Python's `method != "anova"` (R's `!` has lower precedence than `==`, so `!method == "anova"` is parsed as `!(method == "anova")`).
- A simple `UserWarning` is appropriate; the message text is retained verbatim.

---

### 4.4 Warning with `domain = NA` and a literal string (factor level truncation)

**Locations:**
- `rpart/R/labels.rpart.R`, function `labels.rpart`, line 66

**Original R Context:**

```r
# ncat is an integer vector; the condition checks whether any factor
# has more than 52 levels.
# domain = NA: use the message string as-is without gettext translation.
# Return value of warning(): NULL (ignored)

if (any(ncat > 52L))
    warning("more than 52 levels in a predicting factor, truncated for printout",
            domain = NA)
```

**Python Equivalent:**

```python
import warnings

# ncat is a list or numpy array of integers
if any(n > 52 for n in ncat):
    warnings.warn(
        "more than 52 levels in a predicting factor, truncated for printout",
        UserWarning,
        stacklevel=2,
    )
```

**Explanation:**
- `domain = NA` in R suppresses internationalisation; in Python `warnings.warn` never performs i18n, so no special handling is needed.
- R's `any(ncat > 52L)` vectorises the comparison over the integer vector `ncat`. The Python translation uses a generator expression; if `ncat` is a NumPy array the idiomatic form is `np.any(ncat > 52)`.

---

### 4.5 Warning with `gettext` — runtime node interpolation

**Locations:**
- `rpart/R/snip.rpart.R`, function `snip.rpart`, line 20

**Original R Context:**

```r
# toss: integer vector of node numbers supplied by the caller
# toss.idx: integer vector of match results (0 means no match)
# gettext() looks up a translated format string; domain = NA bypasses that.
# The runtime value inserted is toss[toss.idx == 0L] — an integer vector
#   formatted as a comma-separated string by the implicit print coercion.
# Return value of warning(): NULL (ignored)

if (any(toss.idx == 0L)) {
    warning(gettext("Nodes %s are not in this tree", toss[toss.idx == 0L]),
            domain = NA)
    toss <- toss[toss.idx > 0L]
    toss.idx <- toss.idx[toss.idx > 0L]
}
```

Note: In R `gettext("Nodes %s ...", value)` is *not* the same as `sprintf`; it is a translation lookup followed by concatenation. The `%s` is not a format placeholder here — R will paste the two arguments. The actual node numbers appear as their default integer-to-string representation. In the translated Python equivalent we reproduce the visible string that R would produce.

**Python Equivalent:**

```python
import warnings

# toss: list or numpy array of integer node ids
# toss_idx: list of 0/non-zero match results (0 = not found)

invalid_mask = [i == 0 for i in toss_idx]
if any(invalid_mask):
    bad_nodes = [t for t, m in zip(toss, invalid_mask) if m]
    warnings.warn(
        f"Nodes {bad_nodes} are not in this tree",
        UserWarning,
        stacklevel=2,
    )
    toss = [t for t, m in zip(toss, toss_idx) if m > 0]
    toss_idx = [i for i in toss_idx if i > 0]
```

**Explanation:**
- R's `gettext("Nodes %s are not in this tree", toss[toss.idx == 0L])` concatenates the format string with the vector's printed representation; the Python f-string `f"Nodes {bad_nodes} are not in this tree"` produces an equivalent readable output.
- If NumPy arrays are used: `bad_nodes = toss[toss_idx == 0]` and `np.any(toss_idx == 0)`.

---

### 4.6 Warning with `gettextf` — interpolated node list (not found)

**Locations:**
- `rpart/R/zzz.R`, function `node.match`, line 25

**Original R Context:**

```r
# nodes: integer vector of node numbers supplied by the caller
# nodelist: integer vector of valid node numbers in the tree
# node.index: integer vector of match results (0 = not found)
# bad: integer vector of nodes that were not found
# paste(bad, collapse = ","): collapses the integer vector to "1,3,7"
# gettextf: sprintf-style with translation; domain = NA bypasses translation.
# Return value of warning(): NULL (ignored)

node.index <- match(nodes, nodelist, 0L)
bad <- nodes[node.index == 0L]
if (length(bad) > 0 && print.it)
    warning(gettextf("supplied nodes %s are not in this tree",
                     paste(bad, collapse = ",")), domain = NA)
```

**Python Equivalent:**

```python
import warnings

def node_match(nodes, nodelist, leaves=None, print_it=True):
    node_index = [next((i + 1 for i, n in enumerate(nodelist) if n == node), 0)
                  for node in nodes]
    bad = [nodes[i] for i, idx in enumerate(node_index) if idx == 0]

    if len(bad) > 0 and print_it:
        bad_str = ",".join(str(b) for b in bad)
        warnings.warn(
            f"supplied nodes {bad_str} are not in this tree",
            UserWarning,
            stacklevel=2,
        )
    ...
```

**Explanation:**
- R's `gettextf("supplied nodes %s are not in this tree", paste(bad, collapse=","))` is equivalent to Python's `f"supplied nodes {bad_str} are not in this tree"` where `bad_str = ",".join(str(b) for b in bad)`.
- `domain = NA` suppresses translation in R; the Python code naturally has no translation layer.

---

### 4.7 Warning with `gettextf` — interpolated node list (leaves)

**Locations:**
- `rpart/R/zzz.R`, function `node.match`, line 29

**Original R Context:**

```r
# good: integer vector of nodes that were found in nodelist
# leaves: logical vector indicating which good nodes are leaves
# paste(good[leaves], collapse = ","): collapses leaf node ids to "2,4"
# Return value of warning(): NULL (ignored)

good <- nodes[node.index > 0L]
if (!missing(leaves) && any(leaves <- leaves[node.index])) {
    warning(gettextf("supplied nodes %s are leaves",
            paste(good[leaves], collapse = ",")), domain = NA)
    node.index[node.index > 0L][!leaves]
} else node.index[node.index > 0L]
```

**Python Equivalent:**

```python
import warnings

# good: list of node ids that matched the nodelist
# is_leaf: list of booleans (True = node is a leaf)

good = [nodes[i] for i, idx in enumerate(node_index) if idx > 0]

if leaves_provided and any(is_leaf):
    leaf_nodes = [g for g, lf in zip(good, is_leaf) if lf]
    leaf_str = ",".join(str(n) for n in leaf_nodes)
    warnings.warn(
        f"supplied nodes {leaf_str} are leaves",
        UserWarning,
        stacklevel=2,
    )
    return [idx for idx, lf in zip(
        [i for i in node_index if i > 0], is_leaf) if not lf]
else:
    return [i for i in node_index if i > 0]
```

**Explanation:**
- R's `any(leaves <- leaves[node.index])` is an assignment-inside-condition idiom. In Python the filtering step is performed explicitly before the `if` test.
- `gettextf("supplied nodes %s are leaves", paste(good[leaves], collapse=","))` translates directly to an f-string with `",".join(...)`.
- `domain = NA` has no Python equivalent action needed.

---

## Summary Table

| R call site | Pattern | Python translation |
|---|---|---|
| `labels.rpart.R:66` | Literal + `domain=NA` | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `rpart.control.R:8` | Literal, guard clamp | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `rpart.control.R:12` | Literal, guard clamp | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `rpart.control.R:19` | Literal, guard reset | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `rpart.control.R:23` | Literal, guard reset | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `rsq.rpart.R:17` | Literal, method check | `warnings.warn("...", UserWarning, stacklevel=2)` |
| `snip.rpart.R:20` | `gettext` + `domain=NA` | f-string in `warnings.warn` |
| `text.rpart.R:15` | Literal, deprecated arg | `warnings.warn("...", DeprecationWarning, stacklevel=2)` |
| `zzz.R:25` | `gettextf` + `paste` | f-string with `",".join(...)` in `warnings.warn` |
| `zzz.R:29` | `gettextf` + `paste` | f-string with `",".join(...)` in `warnings.warn` |
