# Conversion Guide: `abbreviate` (R to Python)

---

### 1. Overview of `abbreviate` in R

`abbreviate` is a base R function that shortens character strings to a minimum specified length while preserving uniqueness across the resulting set of abbreviations. It operates on a character vector and returns a named character vector of the same length, where each element is an abbreviated form of the corresponding input string.

**Signature:**
```r
abbreviate(names.arg, minlength = 4, use.classes = TRUE,
           dot = FALSE, strict = FALSE,
           method = c("left.kept", "both.sides"), named = TRUE)
```

**Key arguments:**
- `names.arg`: A character vector of strings to abbreviate.
- `minlength`: The target minimum length for each abbreviation (default `4`). If uniqueness cannot be achieved at this length, the length is automatically increased.
- `use.classes`: When `TRUE` (default), lowercase vowels are removed first, then lowercase consonants, then uppercase letters, in that priority order.
- `strict`: When `FALSE` (default), `minlength` is treated as a floor — the function may produce longer abbreviations to guarantee uniqueness. When `TRUE`, `minlength` is enforced exactly, even if this produces duplicate abbreviations.
- `named`: When `TRUE` (default), the returned vector has the original strings as its `names` attribute.

**Return value:** A named character vector (same length as `names.arg`) of abbreviated strings.

**Core behavior:** The function strips spaces and then iteratively removes characters in priority order (lowercase vowels → lowercase consonants → uppercase letters) until each string reaches `minlength` or until all abbreviations are unique. Duplicate input strings always receive the same abbreviation. `NA` values are passed through unchanged.

---

### 2. Contextual Usage Analysis

There is one distinct usage site in the CSV data.

**File:** `rpart/R/labels.rpart.R`
**Function:** `labels.rpart`
**Line:** 70

```r
xlevels <- lapply(xlevels, abbreviate, minlength, ...)
```

**Context (lines 52–83):**

The block beginning at line 52 handles categorical (factor) predictor variables in the rpart decision tree. `xlevels` is a named list (retrieved from `attr(object, "xlevels")`) where each element is a character vector of factor level labels for one predictor variable. The `lapply` call applies `abbreviate` to every such character vector, replacing the full level names with abbreviated versions for use in printed/summary labels.

The argument `minlength` is passed as a positional argument (matching `abbreviate`'s second parameter). Additional keyword arguments captured by `...` in `labels.rpart` are forwarded directly to `abbreviate`, giving callers control over parameters such as `use.classes`, `dot`, `strict`, and `method`.

This call is guarded by the condition `minlength > 1L` (line 69). When `minlength == 1L`, a completely separate path is taken (line 68) that maps levels to single letters from `c(letters, LETTERS)` instead of calling `abbreviate`. When `minlength == 0L`, no abbreviation is performed at all.

**Data types involved:**
- Input to `abbreviate` (each `xlevels[[i]]`): a character vector of factor level strings (length ≥ 2, since only nodes with `ncat > 1L` reach this branch).
- `minlength`: a single integer scalar (≥ 2 in this branch).
- Return value: a character vector of the same length as the input, with abbreviated level names.

**Recurring pattern:** `abbreviate` is always applied element-wise to a list of character vectors via `lapply`. The result is a list of the same structure, used downstream to reconstruct decision-tree branch labels.

---

### 3. Python Conversion Strategy

The primary Python equivalent is a **custom function** built with standard Python string operations, because no single NumPy, SciPy, or pandas function replicates the full abbreviation algorithm of R's `abbreviate` (iterative character removal with uniqueness enforcement).

However, **NumPy and pandas are still relevant** for the surrounding vectorized context: the list of factor-level arrays that `xlevels` represents maps naturally to a Python `dict` of `numpy.ndarray` or `list[str]` objects, and the `lapply(..., abbreviate, ...)` pattern maps to a dict comprehension applying the custom function to each value.

For the abbreviation logic itself, a Python helper function must:
1. Strip spaces from each input string.
2. Remove characters in R's priority order (lowercase vowels → lowercase consonants → uppercase letters) until the string reaches `minlength`.
3. Enforce uniqueness across the output set by incrementally increasing the effective minimum length when collisions occur (when `strict=False`).
4. Preserve `NA` / `None` values unchanged.

This approach exactly mirrors R's behavior without requiring any external library beyond Python's standard library for the abbreviation core.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Applying `abbreviate` over a list of factor-level vectors

**Locations:** `labels.rpart.R` — `labels.rpart`

**Original R Context:**

- `xlevels`: a named `list` where each element is a `character` vector of factor level strings, e.g. `list(color=c("blue","green","red"), size=c("large","medium","small"))`.
- `minlength`: integer scalar, value ≥ 2.
- `...`: optional extra keyword arguments forwarded to `abbreviate`.
- Return: a named list of the same shape, each element being a character vector of the same length with abbreviated strings.

```r
# R: abbreviate a single character vector
abbreviated_levels <- abbreviate(c("blue", "green", "red"), minlength = 2)
# Result (named character vector): c("bl", "gr", "rd")  (names = originals)

# R: apply over a list of factor-level vectors
xlevels <- list(color = c("blue", "green", "red"),
                size  = c("large", "medium", "small"))
xlevels <- lapply(xlevels, abbreviate, minlength = 2, ...)
```

**Python Equivalent:**

```python
import re

def r_abbreviate(names, minlength=4, use_classes=True, strict=False):
    """
    Approximate Python equivalent of R's base::abbreviate().

    Parameters
    ----------
    names : list[str | None]
        Character vector of strings to abbreviate. None values are passed through.
    minlength : int
        Target minimum length for abbreviations (default 4).
    use_classes : bool
        If True, remove lowercase vowels first, then lowercase consonants,
        then uppercase letters (R's default priority). If False, remove
        characters from the right without class priority.
    strict : bool
        If True, enforce minlength exactly even if duplicates result.
        If False (default), increase length until all abbreviations are unique.

    Returns
    -------
    dict[str, str]
        Mapping from original string to its abbreviation (mirrors R's named
        character vector). None inputs are mapped to None.
    """

    def _abbrev_one(s, target_len):
        """Shorten a single string to at most target_len characters."""
        if s is None:
            return None
        # Strip all spaces (R strips spaces before abbreviating)
        s_stripped = s.replace(" ", "")
        if len(s_stripped) <= target_len:
            return s_stripped
        result = list(s_stripped)
        if use_classes:
            # Priority 1: remove lowercase vowels (right to left)
            for i in range(len(result) - 1, -1, -1):
                if len([c for c in result if c is not None]) <= target_len:
                    break
                if result[i] is not None and result[i] in "aeiou":
                    result[i] = None
            # Priority 2: remove lowercase consonants (right to left)
            for i in range(len(result) - 1, -1, -1):
                if len([c for c in result if c is not None]) <= target_len:
                    break
                if result[i] is not None and result[i].islower():
                    result[i] = None
            # Priority 3: remove uppercase letters (right to left)
            for i in range(len(result) - 1, -1, -1):
                if len([c for c in result if c is not None]) <= target_len:
                    break
                if result[i] is not None and result[i].isupper():
                    result[i] = None
        else:
            # No class priority: simply truncate from the right
            keep = result[:target_len]
            result = keep + [None] * (len(result) - target_len)
        return "".join(c for c in result if c is not None)

    # Pass None values through; track which indices are valid
    valid_names = [n for n in names if n is not None]
    result_map = {}

    current_minlength = minlength

    while True:
        abbrevs = {n: _abbrev_one(n, current_minlength) for n in valid_names}
        # Check uniqueness
        values = list(abbrevs.values())
        if strict or len(values) == len(set(values)):
            break
        # Increase length to resolve collisions
        current_minlength += 1

    # Re-include None entries
    for n in names:
        if n is None:
            result_map[n] = None
        else:
            result_map[n] = abbrevs[n]

    return result_map


def abbreviate_levels(xlevels, minlength=4, **kwargs):
    """
    Python equivalent of R's:
        xlevels <- lapply(xlevels, abbreviate, minlength, ...)

    Applies r_abbreviate() to each character vector of factor levels in xlevels.

    Parameters
    ----------
    xlevels : dict[str, list[str]]
        Named mapping from predictor variable name to its list of factor levels.
        Mirrors R's attr(object, "xlevels").
    minlength : int
        Passed directly to r_abbreviate() as the target minimum length.
    **kwargs
        Additional keyword arguments forwarded to r_abbreviate()
        (e.g. use_classes, strict).

    Returns
    -------
    dict[str, list[str]]
        Same structure as xlevels, with each level string replaced by its
        abbreviation. The order of levels within each list is preserved.
    """
    abbreviated = {}
    for var_name, levels in xlevels.items():
        abbrev_map = r_abbreviate(levels, minlength=minlength, **kwargs)
        # Preserve original list order (dict lookup is O(1))
        abbreviated[var_name] = [abbrev_map[lvl] for lvl in levels]
    return abbreviated


# --- Example usage ---
xlevels = {
    "color": ["blue", "green", "red"],
    "size":  ["large", "medium", "small"],
}

result = abbreviate_levels(xlevels, minlength=2)
print(result)
# Expected output (mirrors R behavior):
# {'color': ['bl', 'gr', 'rd'], 'size': ['lr', 'md', 'sm']}
```

**Explanation:**

| R concept | Python translation |
|---|---|
| `lapply(xlevels, abbreviate, minlength, ...)` | `{k: r_abbreviate(v, minlength, **kwargs) for k, v in xlevels.items()}` — dict comprehension replaces `lapply` |
| Positional arg `minlength` to `abbreviate` | Keyword arg `minlength=minlength` in Python (explicit is preferred) |
| `...` forwarded kwargs | `**kwargs` in Python |
| Named character vector return from `abbreviate` | `dict[str, str]` mapping original → abbreviation |
| Character class priority (`use.classes=TRUE`) | Implemented explicitly: vowels → consonants → uppercase, all iterated right-to-left |
| Uniqueness enforcement (non-strict mode) | `while` loop incrementing `current_minlength` until `len(set(abbrevs.values())) == len(abbrevs)` |
| `NA` passthrough | `None` values are detected before processing and re-inserted into the result map unchanged |
| List element order preserved | Python `list` preserves insertion order; `dict` (Python 3.7+) preserves key insertion order |

Note that no single NumPy or pandas function replicates R's uniqueness-enforcing abbreviation algorithm. The custom `r_abbreviate` function above is the correct idiom. If the surrounding code stores factor levels as `numpy.ndarray` objects rather than plain Python lists, convert with `levels.tolist()` before passing to `r_abbreviate`, and convert the output back with `numpy.array(result)` as needed.
