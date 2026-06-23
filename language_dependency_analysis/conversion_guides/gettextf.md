### 1. Overview of `gettextf` in R

`gettextf` is R's internationalization-aware string formatting function. It combines the behavior of `sprintf` (C-style format string substitution) with the `gettext` translation lookup mechanism. Its signature is:

```r
gettextf(fmt, ..., domain = NULL)
```

- `fmt` is a C-style format string (e.g., `"Argument %s not matched"`), where `%s`, `%d`, `%f`, etc. are placeholders.
- `...` are the values to be substituted into the format string positionally.
- `domain` controls which message catalog is used for translation. When `domain = NA` (as in every call in this codebase), internationalization lookup is explicitly suppressed, and the function behaves purely as a vectorized `sprintf`.

The return value is a character vector of formatted strings. When one of the substitution arguments is itself a character vector of length greater than 1 (e.g., multiple unmatched names), `gettextf` returns a vector of formatted strings, one per element. This is the key behavioral distinction from Python's `str.format()`, which operates on scalars only.

In all six usages in this codebase, the result is passed immediately into `stop()` or `warning()`, making `gettextf` a diagnostic formatting tool whose output is consumed by the error/warning system.

---

### 2. Contextual Usage Analysis

All six calls share a consistent structural pattern:

1. A partial-match or exact-match lookup is performed against a set of valid names (using `pmatch` or `match`), producing an integer index vector.
2. Elements where the index equals `0L` (no match found) are extracted: `names(extraArgs)[indx == 0L]` or `names(parms)[temp == 0L]`.
3. These unmatched names — a character vector of arbitrary length — are substituted into a `%s` format string via `gettextf`.
4. The resulting formatted string is passed to `stop()` or `warning()`.

The substituted argument is always a **character vector** (names of a list or a pasted string of node numbers), never a scalar integer or numeric. When the vector has more than one element, R's `gettextf` (behaving as vectorized `sprintf`) returns a vector of strings, each element containing one unmatched name. `stop()` and `warning()` then concatenate this vector automatically.

Two functional sub-patterns exist:

**Sub-pattern A — direct character vector substitution:** The unmatched names vector is passed directly to `%s`. This applies to five of the six calls (across `rpart.R`, `rpart.class.R`, `rpart.exp.R`, and `rpart.poisson.R`). Since `stop()` collapses the resulting vector with newlines, each unmatched name appears on its own line in the error message.

**Sub-pattern B — pre-collapsed string substitution:** The argument is first collapsed into a single comma-separated string with `paste(..., collapse = ",")` before being passed to `%s`. This applies to both calls in `zzz.R` (`node.match`). The result is always a scalar string.

---

### 3. Python Conversion Strategy

The correct Python equivalent is **`%` string formatting** or `str % (value,)`, which mirrors C-style `sprintf` semantics. For the scalar case (sub-pattern B), a simple f-string or `"fmt" % value` is idiomatic. For the vectorized case (sub-pattern A), a list comprehension over the unmatched names replicates R's per-element formatting behavior.

`numpy` is not applicable here because the inputs and outputs are strings, not numeric arrays. `str.format()` is avoided because it uses `{}` syntax, not `%s`, making the mapping from R less transparent.

The `domain = NA` in every R call means translation is suppressed, so no `gettext`/`ngettext` translation infrastructure is needed in Python. The full equivalent is:

- For a **single unmatched name or a pre-collapsed string**: `"format string %s" % value`
- For a **character vector of unmatched names**: `["format string %s" % v for v in bad_names]`

When the result feeds into `raise ValueError(...)` or `warnings.warn(...)`, the list must be joined to replicate how R's `stop()` collapses a vector: `"\n".join([...])`.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Unmatched Extra Arguments in `rpart`

**Locations:** `rpart/R/rpart.R`, function `rpart`, line 99.

**Original R Context.**

- `extraArgs` is a named list built from `...`.
- `indx` is an integer vector from `match(names(extraArgs), controlargs, nomatch = 0L)`.
- `names(extraArgs)[indx == 0L]` is a character vector of one or more unmatched argument names.
- The formatted character vector is passed to `stop()`, which raises an error.

```r
indx <- match(names(extraArgs), controlargs, nomatch = 0L)
if (any(indx == 0L))
    stop(gettextf("Argument %s not matched",
                  names(extraArgs)[indx == 0L]),
         domain = NA)
```

**Python Equivalent.**

```python
import warnings

# extra_args: dict of keyword arguments passed by the caller
# control_args: list of valid parameter names
unmatched = [k for k in extra_args if k not in control_args]
if unmatched:
    messages = ["Argument %s not matched" % name for name in unmatched]
    raise ValueError("\n".join(messages))
```

**Explanation.** `match(..., nomatch = 0L)` maps directly to a membership test (`k not in control_args`). The list comprehension replicates R's vectorized `gettextf`. `"\n".join(...)` replicates how R's `stop()` collapses a character vector. `ValueError` is the idiomatic Python equivalent of R's `stop()`.

---

#### 4.2 Unmatched `parms` Components (Classification)

**Locations:** `rpart/R/rpart.class.R`, function `rpart.class`, line 20.

**Original R Context.**

- `parms` is a named list supplied by the user.
- `temp` is an integer vector from `pmatch(names(parms), c("prior", "loss", "split"), 0L)`.
- `names(parms)[temp == 0L]` is a character vector of unrecognized component names.

```r
temp <- pmatch(names(parms), c("prior", "loss", "split"), 0L)
if (any(temp == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[temp == 0L]), domain = NA)
```

**Python Equivalent.**

```python
valid_parms = ("prior", "loss", "split")
unmatched = [k for k in parms if k not in valid_parms]
if unmatched:
    messages = ["'parms' component not matched: %s" % name for name in unmatched]
    raise ValueError("\n".join(messages))
```

**Explanation.** `pmatch` in R performs partial matching; when translating to Python, a simple membership test against the tuple of valid names is the closest equivalent (full-match semantics). If partial matching must be preserved, a helper using `str.startswith` or `difflib.get_close_matches` can replace the membership check. The format string and collapse strategy are identical to 4.1.

---

#### 4.3 Unmatched `parms` Components (Exponential Survival)

**Locations:** `rpart/R/rpart.exp.R`, function `rpart.exp`, line 116.

**Original R Context.**

- `parms` is coerced to a named list with `as.list(parms)`.
- `parmsNames` is `c("method", "shrink")`.
- `indx` is from `pmatch(names(parms), parmsNames, 0L)`.
- Unmatched names are `names(parms)[indx == 0L]`.

```r
parmsNames <- c("method", "shrink")
indx <- pmatch(names(parms), parmsNames, 0L)
if (any(indx == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[indx == 0L]), domain = NA)
```

**Python Equivalent.**

```python
valid_parms = ("method", "shrink")
unmatched = [k for k in parms if k not in valid_parms]
if unmatched:
    messages = ["'parms' component not matched: %s" % name for name in unmatched]
    raise ValueError("\n".join(messages))
```

**Explanation.** Structurally identical to 4.2, with a different set of valid parameter names. The format string `"'parms' component not matched: %s"` is the same. No additional translation nuances apply.

---

#### 4.4 Unmatched `parms` Components (Poisson)

**Locations:** `rpart/R/rpart.poisson.R`, function `rpart.poisson`, line 21.

**Original R Context.**

- Identical structure to 4.3. `parmsNames` is `c("method", "shrink")`, `indx` comes from `pmatch`, unmatched names are `names(parms)[indx == 0L]`.

```r
parmsNames <- c("method", "shrink")
indx <- pmatch(names(parms), parmsNames, 0L)
if (any(indx == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[indx == 0L]), domain = NA)
```

**Python Equivalent.**

```python
valid_parms = ("method", "shrink")
unmatched = [k for k in parms if k not in valid_parms]
if unmatched:
    messages = ["'parms' component not matched: %s" % name for name in unmatched]
    raise ValueError("\n".join(messages))
```

**Explanation.** This is a copy of the same validation pattern used in `rpart.exp`. Both functions validate the same two `parms` keys and produce the same error format.

---

#### 4.5 Nodes Not Found in Tree (Warning, Pre-collapsed String)

**Locations:** `rpart/R/zzz.R`, function `node.match`, line 25.

**Original R Context.**

- `nodes` is an integer vector of requested node indices.
- `nodelist` is an integer vector of all node indices present in the tree.
- `node.index` is from `match(nodes, nodelist, 0L)`.
- `bad` is `nodes[node.index == 0L]` — an integer vector of node numbers not found.
- `paste(bad, collapse = ",")` collapses `bad` to a single comma-separated string (scalar).
- The result is passed to `warning()`.

```r
node.index <- match(nodes, nodelist, 0L)
bad <- nodes[node.index == 0L]
if (length(bad) > 0 && print.it)
    warning(gettextf("supplied nodes %s are not in this tree",
                     paste(bad, collapse = ",")), domain = NA)
```

**Python Equivalent.**

```python
import warnings

node_index = {n: i for i, n in enumerate(nodelist)}
bad = [n for n in nodes if n not in node_index]
if bad and print_it:
    warnings.warn("supplied nodes %s are not in this tree" % ",".join(str(n) for n in bad))
```

**Explanation.** `paste(bad, collapse = ",")` becomes `",".join(str(n) for n in bad)` because Python's `join` requires strings and `bad` contains integers. The `%s` substitution is then a scalar operation on the already-collapsed string, so no list comprehension is needed. `warnings.warn` is the Python equivalent of R's `warning()`.

---

#### 4.6 Nodes That Are Leaves (Warning, Pre-collapsed String)

**Locations:** `rpart/R/zzz.R`, function `node.match`, line 29.

**Original R Context.**

- `good` is `nodes[node.index > 0L]` — nodes that were found.
- `leaves` is a logical vector indicating which found nodes are leaf nodes.
- `good[leaves]` selects the leaf nodes among the matched ones.
- `paste(good[leaves], collapse = ",")` collapses to a single string.
- Result passed to `warning()`.

```r
good <- nodes[node.index > 0L]
if (!missing(leaves) && any(leaves <- leaves[node.index])) {
    warning(gettextf("supplied nodes %s are leaves",
            paste(good[leaves], collapse = ",")), domain = NA)
```

**Python Equivalent.**

```python
import warnings

good = [n for n in nodes if n in node_index]
# leaves_mask: a boolean list/array of the same length as good
leaf_nodes = [n for n, is_leaf in zip(good, leaves_mask) if is_leaf]
if leaf_nodes:
    warnings.warn("supplied nodes %s are leaves" % ",".join(str(n) for n in leaf_nodes))
```

**Explanation.** The R expression `good[leaves]` is boolean subsetting of a vector; in Python this becomes a list comprehension over `zip(good, leaves_mask)`. As in 4.5, `paste(..., collapse = ",")` maps to `",".join(str(n) for n in ...)`, and the `gettextf` call reduces to a single scalar `%` substitution since the collapsed argument is already a scalar string. `warnings.warn` replaces `warning()`.
