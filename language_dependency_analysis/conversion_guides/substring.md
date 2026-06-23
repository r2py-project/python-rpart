# Conversion Guide: `substring` (R to Python)

---

## 1. Overview of `substring` in R

`substring` (aliased as `substr`) is a base-R function that extracts or replaces substrings within a character vector.

**Signature:**
```r
substring(text, first, last = 1000000L)
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `text` | character vector | The input string(s) from which substrings are extracted. |
| `first` | integer (scalar or vector) | 1-based index of the first character to extract. |
| `last` | integer (scalar or vector) | 1-based index of the last character to extract (inclusive). Defaults to `1000000L`, effectively meaning "to the end of the string". |

**Return value:** A character vector of length equal to the longest of the arguments. Arguments are recycled cyclically to match that length.

**Key behaviors:**
- Indexing is **1-based** and **inclusive** on both ends (both `first` and `last` are included in the result).
- When `first` or `last` are vectors, recycling applies: all three arguments are expanded to the length of the longest, enabling multiple substrings to be extracted from a single string in one call.
- If `first` exceeds the string length, an empty string `""` is returned.
- `NA` in any argument propagates to `NA` in the corresponding output element.
- Encoding (Latin-1, UTF-8, bytes) is preserved; for byte-encoded strings, positions are byte offsets rather than character offsets.

---

## 2. Contextual Usage Analysis

Two distinct usages appear in the rpart source files, both extracting a single substring from a single string (scalar-in, scalar-out). Neither exploits the vectorized recycling feature of `substring`.

**Usage 1 — `model.frame.rpart.R`, line 6:**
A fixed-length prefix check: the first 7 characters of a deparsed call name are extracted to test whether the original call was a `predict(...)` call.

**Usage 2 — `print.rpart.R`, line 14:**
A vectorized extraction over an integer sequence: a single long blank string (`indent`) is sliced at multiple lengths simultaneously. `seq(depth)` produces the integer vector `1, 2, ..., max(depth)`, so `substring(indent, 1L, spaces * seq(depth))` returns a character vector where element `i` is a prefix of `indent` of length `spaces * i`. This produces one indentation string per unique depth level, exploiting R's recycling of the scalar `first = 1L` against the vector `last`.

---

## 3. Python Conversion Strategy

The chosen Python library is the **built-in `str` type** with standard slice notation (`s[start:stop]`) for the scalar case, and a **list comprehension** or `numpy` vectorized approach for the multi-value case.

**Rationale:**
- Usage 1 is purely a scalar string operation; a Python slice `s[0:7]` is the most direct and idiomatic equivalent.
- Usage 2 produces a list of strings of varying lengths. A list comprehension over a `range` is the clearest Python equivalent and avoids unnecessary dependencies. `numpy` string operations (`np.char.ljust`, etc.) are less readable for this pattern and offer no performance benefit at the small sizes involved in a tree-depth vector.

**Critical indexing difference:** R's `substring(text, first, last)` is 1-based and inclusive on both ends. Python slices are 0-based with an exclusive upper bound. The mapping is:

```
R:      substring(s, first, last)
Python: s[first - 1 : last]
```

---

## 4. Step-by-Step Conversion Examples

### 4.1 Fixed-Length Prefix Extraction

**Locations:**
- File: `rpart/R/model.frame.rpart.R`
- Function: `model.frame.rpart`
- Line: 6

**Original R context:**

```r
# oc is a language object (a call); oc[[1L]] is the function-name symbol.
# deparse() converts that symbol to a plain character string (scalar).
# substring extracts characters 1 through 7 (inclusive, 1-based).
if (substring(deparse(oc[[1L]]), 1L, 7L) == "predict") {
    ...
}
```

- Input: a single character string (scalar), e.g. `"predict.foo"`
- `first = 1L`, `last = 7L` — both scalars
- Output: a single character string (scalar), e.g. `"predict"`

**Python equivalent:**

```python
import ast

# In the Python translation, oc is the stored call representation.
# deparse(oc[[1L]]) becomes something like str(oc_func_name).
func_name_str: str = ...  # scalar string, the deparsed function name

# R: substring(deparse(oc[[1L]]), 1L, 7L) == "predict"
# Python: s[first-1 : last]  =>  s[0:7]
if func_name_str[0:7] == "predict":
    ...
```

**Explanation:**
- R's `first = 1L` maps to Python slice start `1 - 1 = 0`.
- R's `last = 7L` (inclusive) maps to Python slice stop `7` (exclusive upper bound, so characters at indices 0–6, i.e. 7 characters total).
- No library import is needed; plain Python string slicing is sufficient for this scalar case.

---

### 4.2 Vectorized Prefix Generation (Multiple Lengths from One String)

**Locations:**
- File: `rpart/R/print.rpart.R`
- Function: `print.rpart`
- Line: 14

**Original R context:**

```r
spaces <- 2L                                         # integer scalar
indent <- paste(rep(" ", spaces * 32L), collapse = "")  # single string of 64 spaces
depth  <- tree.depth(node)                           # integer vector, e.g. c(0,1,1,2,3,...)

# seq(depth) produces 1:max(depth), an integer sequence.
# spaces * seq(depth) produces e.g. c(2, 4, 6, ..., 2*max_depth).
# substring recycles first=1L against each element of last,
# returning a character vector: indent[1:2], indent[1:4], indent[1:6], ...
indent <- substring(indent, 1L, spaces * seq(depth))
# Result: character vector of length max(depth),
#         where element i is a prefix of indent of length spaces*i.
```

- `text` (`indent`): scalar string — recycled against each `last` value
- `first`: scalar `1L` — recycled
- `last`: integer vector `spaces * seq(depth)` (length = `max(depth)`)
- Output: character vector of the same length as `last`

**Python equivalent:**

```python
spaces: int = 2
max_depth: int = int(depth.max())   # depth is a numpy int array or Python list

indent_full: str = " " * (spaces * 32)   # 64-space string

# R: substring(indent, 1L, spaces * seq(depth))
# seq(depth) in R = 1:max(depth), so Python equivalent is range(1, max_depth + 1)
# For each i in 1..max_depth, extract indent[0 : spaces*i]
indent_vec: list[str] = [indent_full[0 : spaces * i] for i in range(1, max_depth + 1)]

# indent_vec[i] is then indexed by depth[node_index] - 1
# (because R uses 1-based depth values as indices into the result vector)
```

If a NumPy-based approach is preferred for consistency with the surrounding numeric code:

```python
import numpy as np

lengths = spaces * np.arange(1, max_depth + 1)          # array of stop positions
indent_vec = np.array([indent_full[:stop] for stop in lengths])  # object array of strings
```

**Explanation:**
- R's `seq(depth)` generates integers from `1` to `max(depth)` inclusive. Python's `range(1, max_depth + 1)` is the exact equivalent.
- The scalar `first = 1L` (R, 1-based) maps to Python slice start `0` (fixed for all iterations).
- The vector `last = spaces * seq(depth)` (R, 1-based inclusive) maps directly to the Python slice stop (0-based exclusive), because `last` already equals the desired number of characters to keep.
- The result is consumed on line 15 of `print.rpart` as `indent[depth]` (R 1-based indexing into the vector), which in Python becomes `indent_vec[depth_value - 1]` (0-based list/array indexing).
