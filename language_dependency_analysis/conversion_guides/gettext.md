# Conversion Guide: `gettext` (R to Python)

---

### 1. Overview of `gettext` in R

`gettext` is a base R function that attempts to translate character strings through R's Native Language Support (NLS) internationalization framework, which is built on the GNU Gettext standard. When a translation for the current locale is available in a message catalog, the function returns the translated string; when no translation exists or when translation is suppressed, the original string is returned unchanged.

**Signature:**
```r
gettext(..., domain = NULL, trim = TRUE)
```

**Key arguments:**
- `...`: One or more character vectors whose elements are the strings to translate. Each element is translated independently; the function does NOT perform any `sprintf`-style substitution itself.
- `domain`: The translation domain (message catalog) to consult. `NULL` (default) lets R infer the domain from the calling package's namespace. `NA` explicitly suppresses translation and causes the original string to be returned as-is.
- `trim`: When `TRUE` (default), leading and trailing whitespace is stripped before looking up the translation, so indentation does not prevent a match.

**Return value:** A character vector with one element per input string. If no translation is found for an element, that element is returned unchanged.

**Important distinction — `gettext` does not format strings.** The `%s` placeholder in the rpart call body (`"Nodes %s are not in this tree"`) is not processed by `gettext`; `gettext` only looks up the translation of the literal template string. String interpolation is handled separately by `sprintf` or `paste` at the call site if required. In the rpart usage examined here, the second positional argument (`toss[toss.idx == 0L]`) is passed as an additional character vector to translate alongside the template — it is not a format argument. Both elements are translated independently and concatenated by `warning()`.

---

### 2. Contextual Usage Analysis

There is one usage site in the CSV data.

**File:** `rpart/R/snip.rpart.R`
**Function:** `snip.rpart`
**Line:** 20

```r
warning(gettext("Nodes %s are not in this tree", toss[toss.idx == 0L]),
        domain = NA)
```

**Surrounding context (lines 16–24):**

```r
toss <- unique(toss)
toss.idx <- match(toss, id, 0L)   # the rows of the named nodes
if (any(toss.idx == 0L)) {
    ## FIXME: plural?
    warning(gettext("Nodes %s are not in this tree", toss[toss.idx == 0L]),
            domain = NA)
    toss <- toss[toss.idx > 0L]
    toss.idx <- toss.idx[toss.idx > 0L]
}
```

**What the call does:**

- `toss` is an integer vector of node IDs supplied by the caller of `snip.rpart`.
- `toss.idx` is the result of `match(toss, id, 0L)`: for each element of `toss`, its row index in the tree frame, or `0L` if that node is absent from the tree.
- `toss[toss.idx == 0L]` is an integer vector of the node IDs that were not found — these are the "bad" nodes.
- `gettext("Nodes %s are not in this tree", toss[toss.idx == 0L])` passes **two arguments** to `gettext`: the template string and a second character/integer vector. `gettext` translates each element independently and returns a character vector of translated strings.
- `warning(...)` concatenates all elements of that character vector and emits the result as a single warning message. The `domain = NA` argument belongs to `warning`, not `gettext`, and suppresses any additional translation that `warning` would otherwise attempt.
- The `## FIXME: plural?` comment reveals that the developer was aware of the awkward pattern: the `%s` in the template is never filled by `gettext`; instead the bad node IDs are passed as additional arguments and end up appended to the warning message by `warning`'s own string concatenation.

**Data types involved:**
- First argument to `gettext`: a single character string (the message template, length 1).
- Second argument to `gettext`: an integer vector of node IDs whose length varies from 1 to the total number of nodes in `toss`.
- Return value of `gettext`: a character vector — first element is the (possibly translated) template string, remaining elements are the stringified node IDs.
- `warning()` collapses this character vector into a single warning message.

**Recurring pattern:** This is the only occurrence of `gettext` in the rpart R source. The pattern is: `gettext` wraps a message template purely for NLS lookup, with additional diagnostic data passed as extra positional arguments that `warning` concatenates into the final message.

---

### 3. Python Conversion Strategy

The correct Python equivalent is **no function at all in most deployment contexts**, paired with a simple `warnings.warn()` call.

The sole purpose of `gettext` here is NLS string lookup. In a Python rpart port, NLS is not expected to be active (no `.po`/`.mo` message catalogs will be shipped). The translated string therefore always equals the original English string.

However, Python has a built-in `gettext` module in its standard library (`import gettext`) that mirrors the GNU Gettext interface exactly. If NLS support is ever required, the `gettext.gettext()` function (commonly aliased as `_()`) is the direct drop-in. For the common case where no translation catalogs are installed, `gettext.gettext(s)` simply returns `s` unchanged — identical behavior to R's `gettext` with `domain = NA`.

**Library choice:** Python's `gettext` standard library module. No `numpy`, `scipy`, or `pandas` dependency is needed because `gettext` operates only on scalar strings; there is no vectorization concern.

For the `warning()` wrapping pattern, Python's `warnings.warn()` is the direct equivalent of R's `warning()`.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 `gettext` inside `warning()` with supplementary node ID data

**Locations:** `snip.rpart.R` — `snip.rpart`

**Original R Context:**

- `toss`: integer vector of node IDs requested for pruning (e.g., `c(3L, 7L, 15L)`).
- `toss.idx`: integer vector, same length as `toss`, holding row indices (`0L` = not found).
- `toss[toss.idx == 0L]`: integer sub-vector of unrecognized node IDs (length ≥ 1 when this branch is entered).
- Return of `gettext(...)`: a character vector; first element is the translated template, remaining elements are the coerced node IDs.
- `warning()` collapses that vector into one warning string.

```r
# R generalized snippet
bad_nodes <- toss[toss.idx == 0L]   # integer vector, e.g. c(7L, 15L)
warning(gettext("Nodes %s are not in this tree", bad_nodes),
        domain = NA)
# Emitted warning (no NLS catalog): "Nodes %s are not in this tree7 15"
# (warning() pastes all elements with no separator)
```

Note: `%s` in the template is **never substituted** by `gettext`. The resulting message from R is literally `"Nodes %s are not in this tree7 15"` (elements concatenated without a separator). The `## FIXME: plural?` comment in the source acknowledges this is imperfect; a cleaner formulation would use `sprintf` or `paste`.

**Python Equivalent:**

```python
import warnings
import gettext as gettext_module

# Option A: No NLS — direct string construction (recommended for rpart port)
def warn_invalid_nodes(bad_nodes):
    """
    Python equivalent of:
        warning(gettext("Nodes %s are not in this tree", bad_nodes), domain = NA)

    Parameters
    ----------
    bad_nodes : list[int] or numpy.ndarray
        The node IDs that were not found in the tree.
    """
    # Replicate R's gettext() + warning() concatenation behavior exactly:
    # R pastes all elements of the character vector with no separator.
    node_str = " ".join(str(n) for n in bad_nodes)
    message = f"Nodes %s are not in this tree{node_str}"
    warnings.warn(message)


# Option B: With NLS support via Python's gettext module
def warn_invalid_nodes_nls(bad_nodes, translation=None):
    """
    NLS-aware variant. Pass a gettext.GNUTranslations object as `translation`
    to enable locale-specific message lookup; pass None to use identity translation.

    Parameters
    ----------
    bad_nodes : list[int] or numpy.ndarray
        The node IDs that were not found in the tree.
    translation : gettext.GNUTranslations or None
        If provided, used to translate the template string. If None, the
        original English template is used (equivalent to R's domain=NA).
    """
    template = "Nodes %s are not in this tree"
    if translation is not None:
        template = translation.gettext(template)   # NLS lookup

    node_str = " ".join(str(n) for n in bad_nodes)
    # Concatenate exactly as R's warning() does: template + stringified IDs
    message = f"{template}{node_str}"
    warnings.warn(message)


# --- Example usage (mirrors the rpart snip.rpart scenario) ---
import numpy as np

toss = np.array([3, 7, 15], dtype=int)
tree_node_ids = np.array([1, 2, 3, 4, 5, 6], dtype=int)

# Equivalent of R's match(toss, id, 0L): 0 where not found, index+1 where found
toss_idx = np.array([
    np.searchsorted(tree_node_ids, n) + 1
    if n in tree_node_ids else 0
    for n in toss
], dtype=int)

bad_nodes = toss[toss_idx == 0]   # [7, 15]

if len(bad_nodes) > 0:
    warn_invalid_nodes(bad_nodes)
    toss = toss[toss_idx > 0]
    toss_idx = toss_idx[toss_idx > 0]

# warnings.warn emits: "Nodes %s are not in this tree7 15"
```

**Explanation:**

| R concept | Python translation |
|---|---|
| `gettext("template", extra_vec)` | No direct equivalent needed; construct the message string manually |
| `gettext` NLS lookup | `gettext_module.GNUTranslations.gettext("template")` from Python's `gettext` stdlib |
| `domain = NA` (suppress translation) | Pass `translation=None`; the `if translation is not None` guard is skipped |
| `warning(char_vec, domain = NA)` | `warnings.warn(message)` where `message` is the manually concatenated string |
| R's `warning()` collapsing char vector elements without separator | `"".join(...)` — elements are concatenated directly with no separator (note the `f"{template}{node_str}"` pattern above) |
| Integer vector `toss[toss.idx == 0L]` | `numpy.ndarray` boolean indexing: `toss[toss_idx == 0]` |
| `as.integer` coercion in `warning` output | `str(n)` applied to each numpy integer element |

**Key nuances:**

1. `gettext` in R does **not** perform `sprintf`-style substitution. The `%s` in `"Nodes %s are not in this tree"` is a literal part of the template string used as an NLS lookup key, not a format directive. The Python port should not call `str % value` or `str.format()` on this template unless the rpart behavior is intentionally improved upon.

2. R's `warning()` concatenates all elements of a character vector passed to it with **no separator**. The Python equivalent must replicate this by joining the template and the stringified node IDs without inserting any space or comma between them (see `f"{template}{node_str}"` in the snippet above, where `node_str` itself uses space-separated IDs produced by `" ".join(...)`).

3. If the Python rpart port aims for cleaner warning messages than the original R code (which the `## FIXME: plural?` comment suggests is desirable), a better formulation is:
   ```python
   node_list = ", ".join(str(n) for n in bad_nodes)
   warnings.warn(f"Nodes {node_list} are not in this tree")
   ```
   This produces `"Nodes 7, 15 are not in this tree"` — more readable than R's literal output, while conveying identical information.
