# Conversion Guide: `cat` (R to Python)

---

## 1. Overview of `cat` in R

`cat()` is R's primary function for producing **formatted, concatenated console output**. It converts each of its arguments to character strings and writes them to the standard output (or a specified connection), joined together without any separator by default.

**Function signature:**
```r
cat(..., file = "", sep = " ", fill = FALSE, labels = NULL, append = FALSE)
```

Key behaviours:

- **Multiple arguments** are concatenated in order. The `sep` argument (default `" "`) is inserted *between* each argument. Passing `sep = ""` suppresses all inter-argument whitespace.
- **`\n`** embedded in a string literal produces a real newline in the output.
- Unlike `print()`, `cat()` does **not** add quotes around character values and does **not** append a trailing newline automatically.
- It returns `NULL` invisibly and is used purely for its side-effect (printing).
- When a character vector is passed as a single argument with `sep = "\n"`, each element of the vector is printed on its own line.

---

## 2. Contextual Usage Analysis

Across the five source files (`path.rpart.R`, `print.rpart.R`, `printcp.R`, `snip.rpart.mouse.R`, `summary.rpart.R`), `cat` is used exclusively for **human-readable console output** inside reporting and diagnostic functions (`print.rpart`, `printcp`, `summary.rpart`, `path.rpart`, `snip.rpart.mouse`). No return value of `cat` is ever captured; every call is a pure side-effect.

Four distinct usage patterns appear across the CSV:

| Pattern | Description | Representative call |
|---|---|---|
| **A – Plain string literal** | Print a fixed header or separator string with an embedded `\n`. | `cat("Call:\n")` |
| **B – Mixed scalars with `sep=""`** | Concatenate several scalars/strings with no separator to form one formatted line. | `cat("n=", n[1L], " (", naprint(omit), ")\n\n", sep = "")` |
| **C – Default-sep multi-value** | Print several values separated by a single space (the default `sep`). | `cat("\n", "node number:", n[i], "\n")` |
| **D – Character vector with `sep="\n"`** | Print each element of a character vector on its own line. | `cat(z, sep = "\n")` |

All arguments are scalars (single integers, doubles, or character strings) or character vectors. No matrices or data frames are ever passed directly to `cat`.

---

## 3. Python Conversion Strategy

The direct Python equivalent is `print()` from the standard library, supplemented in a few cases by `str.join()` for vector iteration.

**Why not `numpy` or `pandas`?**  
`cat` in this codebase operates entirely on scalars and character vectors — it performs no numerical computation. There is no vectorised arithmetic to translate. `numpy` and `pandas` are not relevant here.

**Why `print()` plus `str.join()`?**

- Python's `print()` accepts multiple positional arguments, joins them with `sep` (default `" "`), and appends a newline via `end` (default `"\n"`). This maps cleanly onto R's `cat(..., sep=...)`.
- Where R passes a character vector with `sep="\n"`, the Python equivalent is `print("\n".join(vector))`.
- For `sep=""` calls, Python's `print(..., sep="", end="")` (with an explicit `end=""` when the trailing newline is already embedded in the last string) reproduces the exact output.

---

## 4. Step-by-Step Conversion Examples

### Pattern A — Plain string literal

**Locations:**
- `summary.rpart.R` / `summary.rpart`: lines 15, 28, 72, 85, 113
- `print.rpart.R` / `print.rpart`: lines 34, 35, 36
- `printcp.R` / `printcp`: lines 14, 21, 23
- `snip.rpart.mouse.R` / `snip.rpart.mouse`: line 27

**Original R context (generalised):**
```r
# Argument type: single character string containing \n
# Return: NULL (invisible)
cat("Call:\n")
cat("\nVariable importance\n")
cat("      * denotes terminal node\n\n")
cat("Terminal node -- try again\n")
```

**Python equivalent:**
```python
# Single string literals — use print() with end="" because \n is already embedded
print("Call:")                           # equivalent to cat("Call:\n")
print("\nVariable importance")           # equivalent to cat("\nVariable importance\n")
print("      * denotes terminal node\n") # equivalent to cat("      * denotes terminal node\n\n")
print("Terminal node -- try again")      # equivalent to cat("Terminal node -- try again\n")
```

**Explanation:**
R's `cat("some text\n")` writes the text followed by a newline. Python's `print("some text")` does exactly the same (the `print` function appends `\n` by default). When the R string contains a trailing `\n\n` (a blank line), use `print("some text\n")` — Python's default `end="\n"` adds one more newline, giving the double newline. Alternatively, use `print("some text"); print()` for clarity.

---

### Pattern B — Mixed scalars with `sep=""`

**Locations:**
- `print.rpart.R` / `print.rpart`: lines 30, 31
- `printcp.R` / `printcp`: lines 27, 35, 36
- `summary.rpart.R` / `summary.rpart`: lines 21, 22, 71, 73, 80, 83, 84

**Original R context (generalised):**
```r
# Arguments: mixture of string literals, integer scalars, formatted strings
# sep="" suppresses all inter-argument whitespace
# Return: NULL (invisible)

# Example 1 – omit path (line 30 in print.rpart.R)
# n[1L]: integer scalar, naprint(omit): character scalar
cat("n=", n[1L], " (", naprint(omit), ")\n\n", sep = "")

# Example 2 – no-omit path (line 31 in print.rpart.R)
cat("n=", n[1L], "\n\n")

# Example 3 – root node error (line 27 in printcp.R)
cat("Root node error: ", format(frame$dev[1L], digits = digits), "/",
    frame$n[1L], " = ",
    format(frame$dev[1L]/frame$n[1L], digits = digits),
    "\n\n", sep = "")

# Example 4 – node header (line 71 in summary.rpart.R)
cat("\nNode number ", id[i], ": ", nn, " observations", sep = "")

# Example 5 – complexity param (line 73 in summary.rpart.R)
cat(",    complexity param=",
    format(signif(ff$complexity[i], digits)), "\n", sep = "")

# Example 6 – left/right son (line 80 in summary.rpart.R)
cat("  left son=", sons[1L], " (", sons.n[1L], " obs)",
    " right son=", sons[2L], " (", sons.n[2L], " obs)", sep = "")

# Example 7 – observations remain (line 83 in summary.rpart.R)
cat(", ", j, " observations remain\n", sep = "")
```

**Python equivalent:**
```python
import sys

# Example 1
print(f"n={n[0]} ({naprint(omit)})\n", end="")

# Example 2
print(f"n={n[0]}\n")

# Example 3
print(
    f"Root node error: {format_r(frame_dev_1, digits=digits)}"
    f"/{frame_n_1} = "
    f"{format_r(frame_dev_1 / frame_n_1, digits=digits)}\n",
    end=""
)

# Example 4  (no trailing newline — next cat continues the same line)
print(f"\nNode number {id_i}: {nn} observations", end="")

# Example 5
print(f",    complexity param={format_r(signif(complexity_i, digits))}", end="\n")

# Example 6
print(
    f"  left son={sons[0]} ({sons_n[0]} obs)"
    f" right son={sons[1]} ({sons_n[1]} obs)",
    end=""
)

# Example 7
print(f", {j} observations remain")   # \n supplied by print's end default
```

**Explanation:**

- R's `sep=""` means every argument is concatenated with no gap. The cleanest Python translation is an f-string that assembles all parts into one string, then passes it to `print()`.
- When the R call's last string ends with `\n`, use `print(..., end="")` so Python's own default newline is not doubled.
- When the R call does NOT end with `\n` (e.g., line 71 `sep=""` and no trailing newline), use `print(..., end="")` to suppress the automatic newline and keep the cursor on the same line for the next `cat` call.
- R's 1-based indexing (e.g., `n[1L]`, `sons[1L]`) maps to Python's 0-based `n[0]`, `sons[0]`.
- R's `format(signif(..., digits))` maps to a custom helper or Python's `f"{value:.{digits}g}"`.

---

### Pattern C — Default-sep multi-value output

**Locations:**
- `path.rpart.R` / `path.rpart`: lines 18, 27
- `snip.rpart.mouse.R` / `snip.rpart.mouse`: lines 33, 34, 35, 37, 38, 39
- `printcp.R` / `printcp`: line 5

**Original R context (generalised):**
```r
# Arguments: mix of string literals and scalar values
# Default sep=" " inserts a space between each argument
# Return: NULL (invisible)

# Example 1 – path.rpart.R line 18
# n[i]: character (row name), printed with surrounding newlines
cat("\n", "node number:", n[i], "\n")

# Example 2 – snip.rpart.mouse.R line 33
# node[choose]: integer, ff$n[choose]: integer
cat("node number:", node[choose], " n=", ff$n[choose], "\n")

# Example 3 – snip.rpart.mouse.R line 34
# ff$yval[choose]: numeric scalar
cat("    response=", format(ff$yval[choose]))

# Example 4 – snip.rpart.mouse.R lines 37, 38
# ff$yval2[choose, ] or ff$yval2[choose]: numeric vector or scalar
cat(" (", format(ff$yval2[choose, ]), ")\n")   # matrix row
cat(" (", format(ff$yval2[choose]), ")\n")     # scalar

# Example 5 – snip.rpart.mouse.R line 39
cat("    Error (dev) = ", format(ff$dev[choose]), "\n")

# Example 6 – printcp.R line 5 (switch result is a single string)
cat(switch(x$method,
           anova   = "\nRegression tree:\n",
           class   = "\nClassification tree:\n",
           poisson = "\nRates regression tree:\n",
           exp     = "\nSurvival regression tree:\n"))
```

**Python equivalent:**
```python
# Example 1 – spaces between items (default sep=" ")
# R output: "\n node number: <n_i> \n"  (spaces inserted by sep)
print(f"\n node number: {n_i} \n", end="")
# or, preserving R's exact spacing behaviour:
print("\n", "node number:", n_i, "\n", sep=" ", end="")

# Example 2
print("node number:", node_choose, " n=", ff_n_choose, "\n", sep=" ", end="")

# Example 3 – no trailing newline in original R call
print("    response=", format_r(ff_yval_choose), sep=" ", end="")

# Example 4a – matrix row (format returns a character vector; join with space)
formatted = " ".join(format_r(v) for v in ff_yval2_row)
print(f" ( {formatted} )\n", end="")

# Example 4b – scalar
print(f" ( {format_r(ff_yval2_scalar)} )\n", end="")

# Example 5
print(f"    Error (dev) =  {format_r(ff_dev_choose)} \n", end="")

# Example 6
method_labels = {
    "anova":   "\nRegression tree:\n",
    "class":   "\nClassification tree:\n",
    "poisson": "\nRates regression tree:\n",
    "exp":     "\nSurvival regression tree:\n",
}
print(method_labels[x_method], end="")
```

**Explanation:**

- R's default `sep=" "` inserts a single space between every positional argument, including string literals. The easiest Python approach is to build the complete string with an f-string, using `end=""` when the final character is already `\n`, or omitting `end=""` when a newline is desired from `print`'s default.
- R's `switch()` with named cases is a dictionary lookup in Python.
- Where R's `format()` on a numeric vector returns a character vector (e.g., for a matrix row), the Python equivalent is a list comprehension with a formatting helper, then `" ".join(...)`.
- Note the space added by R's default `sep=" "` around `format(ff$yval2[choose, ])` in Example 4a: R produces `" ( val1 val2 )\n"`. Replicate this by adding spaces around the joined string.

---

### Pattern D — Character vector with `sep="\n"`

**Locations:**
- `path.rpart.R` / `path.rpart`: lines 19, 29
- `print.rpart.R` / `print.rpart`: line 38
- `summary.rpart.R` / `summary.rpart`: lines 76, 91, 104

**Original R context (generalised):**
```r
# Argument: character vector (each element is one formatted line)
# sep="\n" places a newline between each element; no trailing \n is added
# Return: NULL (invisible)

# Example 1 – path.rpart.R lines 19, 29
# path.i: character vector of split label strings
cat(paste("  ", path.i), sep = "\n")

# Example 2 – print.rpart.R line 38
# z: character vector of formatted node rows
cat(z, sep = "\n")

# Example 3 – summary.rpart.R line 76
# tprint[ii]: single character string (one summary block)
cat(tprint[ii], "\n")

# Example 4 – summary.rpart.R lines 91, 104
# paste(...): character vector, one element per split/surrogate
cat(paste("      ", format(sname[j], justify = "left"), " ", temp,
          " improve=", format(signif(x$splits[j, 3L], digits)),
          ", (", nn - x$splits[j, 1L], " missing)", sep = ""),
    sep = "\n")
```

**Python equivalent:**
```python
# Example 1
# path_i: list of str
lines = ["  " + s for s in path_i]
print("\n".join(lines))

# Example 2
# z: list of str (formatted node rows)
print("\n".join(z))

# Example 3
# tprint_ii: str
print(tprint_ii)   # print adds \n automatically

# Example 4 – primary splits (one formatted string per split)
import numpy as np

lines = [
    f"      {format_ljust(sname_j)} {temp_j}"
    f" improve={format_r(signif(splits_j3, digits))}"
    f", ({nn - splits_j1} missing)"
    for sname_j, temp_j, splits_j3, splits_j1 in zip(snames, temps, splits_col3, splits_col1)
]
print("\n".join(lines))

# Example 5 – surrogate splits (same structure with agree/adj)
lines = [
    f"      {format_ljust(sname_j)} {temp_j}"
    f" agree={round(agree_j, 3)}"
    f", adj={round(adj_j, 3)}"
    f", ({split_j} split)"
    for sname_j, temp_j, agree_j, adj_j, split_j in zip(snames, temps, agrees, adjs, splits_col1)
]
print("\n".join(lines))
```

**Explanation:**

- R's `cat(vector, sep="\n")` prints all elements of `vector` joined by newlines. The closest Python idiom is `print("\n".join(vector))`, which also appends a trailing newline (matching R's behaviour when the last element does not itself end with `\n`).
- R's `paste("  ", path.i)` concatenates `"  "` to each element of `path.i` (vectorised over `path.i`). In Python this is a list comprehension: `["  " + s for s in path_i]`.
- R's `format(sname[j], justify = "left")` left-justifies a string to the width of the longest element in the vector. In Python, `format_ljust(s)` can be implemented as `s.ljust(max(len(x) for x in snames))`.
- R's `paste(..., sep = "")` inside the outer `cat(..., sep = "\n")` builds each element of the printed vector with no internal separator. In Python, an f-string concatenating all parts reproduces this exactly.
- Array slicing: R's `x$splits[j, 3L]` (column 3, rows `j`) maps to Python's `splits[j_indices, 2]` (0-based column index 2).
