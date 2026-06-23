# Conversion Guide: `sub` (R to Python)

### 1. Overview of `sub` in R

`sub(pattern, replacement, x, ...)` performs **single-substitution regex matching** on a character vector. It searches each element of `x` for the first occurrence of `pattern` and replaces it with `replacement`. If the pattern is not found in an element, that element is returned unchanged.

Key characteristics:

- **Only the first match** in each string is replaced (unlike `gsub`, which replaces all matches).
- `pattern` is a POSIX extended regular expression by default (or Perl-compatible when `perl = TRUE`).
- **Backreferences** in `replacement` use `\\1`, `\\2`, etc. to refer to captured groups in the pattern.
- Input `x` is a **character vector**; the function is vectorized and returns a character vector of the same length.
- Default arguments: `ignore.case = FALSE`, `perl = FALSE`, `fixed = FALSE`, `useBytes = FALSE`.

---

### 2. Contextual Usage Analysis

**Source file:** `rpart/R/rpart.matrix.R`, function `rpart.matrix`, line 29.

**Surrounding logic (lines 27-30):**

```r
X <- model.matrix(attr(frame, "terms"), frame)[, -1L, drop = FALSE]
## model.matrix labels columns with backticks, and rpart.matrix did not.
colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
class(X) <- c("rpart.matrix", class(X))
```

**What is happening:**

1. `model.matrix()` builds a numeric design matrix from the model frame. R's `model.matrix` wraps column names that contain spaces or special characters in backtick delimiters, e.g. `` `my var` `` or `` `factor(x)A` ``.
2. `colnames(X)` returns a **character vector** of all column names of the matrix `X`.
3. `sub("^`(.*)`", "\\1", colnames(X))` applies the regex to every element of that character vector:
   - Pattern `` ^`(.*)`$ `` anchors to the full string: it matches only names that start with a backtick and end with a backtick, capturing everything in between in group 1.
   - Replacement `\\1` replaces the entire matched string with the captured group, effectively stripping the surrounding backticks.
   - Names that do **not** match (i.e., names that were never backtick-quoted) are left unchanged.
4. The result is assigned back to `colnames(X)`.

**Data types:**
- Input: a character vector (one string per column name).
- Output: a character vector of the same length, with backtick wrappers removed where present.

**Pattern:** This is a classic "strip delimiters" operation — a single-pass regex substitution applied uniformly across a vector of strings. There is exactly one distinct functional pattern in the CSV.

---

### 3. Python Conversion Strategy

The **`re` module** from the Python standard library is the correct and idiomatic equivalent. The reasoning:

- `sub` operates on a **character vector** (array of strings), not a numeric array, so `numpy` and `pandas` numeric functions are not applicable here.
- The operation is a simple regex replacement over a list of strings. Python's `re.sub()` is the direct counterpart to R's `sub()`.
- Because Python's `re.sub()` operates on a **single string** (not a vector), the vectorization over `colnames(X)` (a list of strings in Python) is handled with a list comprehension, which is idiomatic and efficient.
- If the column names are stored in a `pandas.DataFrame`, `pandas.Series.str.replace()` with `regex=True` is an alternative, but since the target here is a NumPy matrix whose column names are kept as a plain Python list, the `re` module with a list comprehension is the cleanest fit.

---

### 4. Step-by-Step Conversion Examples

#### Example 1 — Strip backtick delimiters from model matrix column names

**Locations:**
- File: `rpart/R/rpart.matrix.R`
- Function: `rpart.matrix`

**Original R Context:**

- `colnames(X)` returns a `character` vector, e.g. `` c("`age`", "sex", "`body weight`") ``.
- `sub("^`(.*)`", "\\1", colnames(X))` returns `c("age", "sex", "body weight")`.
- The regex anchors (`^` and the trailing backtick before end-of-string) ensure only fully backtick-wrapped names are modified; partially wrapped or un-wrapped names pass through untouched.

Generalized R snippet:

```r
# colnames(X) is a character vector such as:
# c("`age`", "sex", "`body weight`")
colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
# Result: c("age", "sex", "body weight")
```

**Python Equivalent:**

```python
import re
import numpy as np

# Suppose X is a 2-D numpy array and col_names is a list of column name strings,
# mirroring what colnames(X) would return in R.
col_names = ["`age`", "sex", "`body weight`"]

# re.sub() replaces only the FIRST match in each string, exactly like R's sub().
# The pattern anchors to start (^) and requires a closing backtick at the end ($).
# Group 1 (.*) captures everything between the backticks.
pattern = r"^`(.*)`$"

col_names_clean = [re.sub(pattern, r"\1", name) for name in col_names]
# Result: ["age", "sex", "body weight"]

# If X is a numpy matrix you can store the cleaned names as an attribute or
# use a structured approach (e.g., pandas DataFrame):
# X_df = pd.DataFrame(X, columns=col_names_clean)
print(col_names_clean)
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `sub(pattern, replacement, x)` | `re.sub(pattern, replacement, string)` | R's `sub` is vectorized; Python's `re.sub` acts on one string at a time, so a list comprehension provides the equivalent vectorization. |
| Pattern `"^`(.*)`"` | `r"^`(.*)`$"` | The R pattern relies on the fact that `$` is implicit when the replacement must cover the whole string; adding explicit `$` in Python makes the anchor unambiguous and is equivalent behavior. |
| Replacement `"\\1"` | `r"\1"` | R requires double-escaped backslash in a regular string literal (`"\\1"`); Python raw strings (`r"\1"`) avoid the double-escape. Both refer to captured group 1. |
| `colnames(X) <- result` | `col_names = [...]` then assign to DataFrame or keep as list | NumPy arrays do not have named columns natively; in a Python translation the column names are typically stored as a plain list or as `DataFrame.columns`. |
| Only first match replaced | `re.sub` replaces only first match by default (but because anchors `^` and `$` force the pattern to span the whole string, only one match is ever possible per element) | For this specific anchored pattern, `re.sub` and `re.subn(..., count=1)` behave identically. If the anchor were removed, use `count=1` to mimic `sub` vs. `gsub`. |
