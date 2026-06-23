# Conversion Guide: `title` (R to Python)

---

## 1. Overview of `title` in R

`title()` is a base R graphics function from the `graphics` package. It adds annotation labels to an existing plot as a side effect — it does not create a new plot or return a meaningful value. Its primary purpose is to set the main title (top of the plot), a subtitle (bottom), and axis labels after a plot has already been drawn.

**Signature:**

```r
title(main = NULL, sub = NULL, xlab = NULL, ylab = NULL,
      line = NA, outer = FALSE, ...)
```

Key parameters relevant to this guide:

| R Parameter | Description |
|---|---|
| `main` | Character string or expression for the main title, displayed at the top of the plot. This is the first positional argument. |
| `sub` | Subtitle displayed at the bottom of the plot. |
| `xlab` / `ylab` | Labels for the x- and y-axes. |
| `cex` | Character expansion factor (relative text size). When passed via `...`, it is forwarded to the underlying `par()` machinery as a graphical parameter that scales title text. |
| `outer` | Logical; if `TRUE`, the title is placed in the outer margin. Defaults to `FALSE`. |
| `line` | Override for the number of margin lines from the plot edge. |

When called with a single unnamed string as the first argument (e.g., `title("some text")`), that string is treated as `main`. The `cex` argument passed in these usages scales the text size of the title.

`title()` is a **pure side-effect function** — it modifies the currently active graphics device and returns `NULL` invisibly.

---

## 2. Contextual Usage Analysis

Both CSV rows come from `post.rpart.R`, function `post.rpart`. The full relevant block (lines 20–23) is:

```r
if (missing(title.)) {
    temp <- attr(tree$terms, "variables")[2L]
    title(paste("Endpoint =", temp), cex = 0.8)
} else if (nzchar(title.)) title(title., cex = 0.8)
```

**Usage pattern:** Both calls share the identical structure — `title(<string>, cex = 0.8)`. The first positional argument is always a plain character string (either constructed via `paste()` or passed directly as the user-supplied `title.` parameter). The `cex = 0.8` argument reduces the title text to 80% of the default size.

**Data types involved:**

- **Line 22 (`title(paste("Endpoint =", temp), cex = 0.8)`):** `temp` is a symbol extracted from the model's terms object — specifically, `attr(tree$terms, "variables")[2L]`, which resolves to the name of the response variable as a character-like symbol. `paste()` coerces it to a plain string. The result is a scalar character string passed as `main`.
- **Line 23 (`title(title., cex = 0.8)`):** `title.` is a function parameter declared in the signature of `post.rpart`. This guard (`nzchar(title.)`) ensures the string is non-empty before calling. Again a scalar character string is passed as `main`.

**Recurring pattern:** In both usages, `title()` is called solely to set the **main (top) title** of a plot that has already been drawn by `plot()` and `text()`. No subtitle, axis labels, or `outer` placement are used. The only non-default argument besides the string is `cex = 0.8`.

---

## 3. Python Conversion Strategy

The Python equivalent is **`matplotlib.pyplot.title()`** (or `ax.set_title()` on an `Axes` object). Matplotlib is the standard Python plotting library and the natural counterpart to R's base graphics system.

Why matplotlib:

- R's `title()` annotates an existing figure on the current graphics device. Matplotlib's `plt.title()` / `ax.set_title()` similarly annotates an existing active plot — the same conceptual model.
- The `cex` scaling factor in R maps directly to the `fontsize` parameter in matplotlib. R's default title text size is governed by `par("cex.main")`, which defaults to `1.2` times the base `cex` (typically `1`). Multiplying by `0.8` yields an effective size of `0.8` relative to base. In matplotlib, the default title font size is typically `12pt`; `cex=0.8` maps to `fontsize=0.8*default_size`. A practical and faithful translation is to pass `fontsize` as a relative scale by using `matplotlib`'s `rcParams` reference size, or to use an absolute point value that approximates `0.8` of the default (e.g., `fontsize=9.6` if the default is `12`). For idiomatic code, passing `fontsize=0.8 * plt.rcParams['axes.titlesize']` is the most accurate translation.
- No vectorized (numpy/scipy) operations are involved — these calls operate on scalar strings and are purely graphical side effects.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Auto-generated title from model terms (Line 22)

**Location:** `post.rpart.R`, function `post.rpart`, line 22.

**Original R Context:**

- Input: `temp` is a symbol/name extracted from the rpart model's terms object, coerced to a string by `paste()`. It is a scalar character string (e.g., `"Kyphosis"`).
- The call sets the main plot title to `"Endpoint = <response_variable_name>"` at 80% character expansion.
- Return value: `NULL` (invisibly); side effect only.

```r
# R
temp <- attr(tree$terms, "variables")[2L]   # e.g., evaluates to symbol 'Kyphosis'
title(paste("Endpoint =", temp), cex = 0.8)
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt

# Assuming `tree` is the fitted rpart-equivalent model object and
# `response_var_name` holds the name of the response variable as a string.
# In a Python rpart port, this might come from the model's feature/target metadata.

response_var_name = tree.terms["variables"][1]  # 0-based index equivalent of R's [2L]
title_text = f"Endpoint = {response_var_name}"

ax = plt.gca()
default_title_size = plt.rcParams.get("axes.titlesize", 12)
ax.set_title(title_text, fontsize=0.8 * default_title_size)
```

**Explanation:**

- `attr(tree$terms, "variables")[2L]` uses 1-based indexing in R; the Python equivalent is index `[1]` (0-based).
- `paste("Endpoint =", temp)` concatenates with a space by default. The Python f-string `f"Endpoint = {response_var_name}"` produces the identical result.
- `cex = 0.8` in R scales the title text to 80% of the base size. In matplotlib, `fontsize` accepts a numeric point size. `0.8 * plt.rcParams.get("axes.titlesize", 12)` computes the scaled size relative to the current theme's default title size, faithfully replicating the scaling behavior.
- `plt.gca()` retrieves the currently active `Axes`, mirroring R's implicit "current graphics device" model. Using `ax.set_title()` is preferred over `plt.title()` for explicitness, but both are valid.

---

### 4.2 User-supplied title string (Line 23)

**Location:** `post.rpart.R`, function `post.rpart`, line 23.

**Original R Context:**

- Input: `title.` is a user-provided character string passed as a parameter to `post.rpart`. The `nzchar(title.)` guard ensures the string is non-empty before this branch executes.
- The call sets the main plot title to the user-supplied string at 80% character expansion.
- Return value: `NULL` (invisibly); side effect only.

```r
# R
# title. is a non-empty character string supplied by the caller
if (nzchar(title.)) title(title., cex = 0.8)
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt

# `title_str` is the user-supplied string parameter, equivalent to R's `title.`
# nzchar() in R returns TRUE for non-empty strings; Python's truthiness check on a
# string is equivalent: an empty string is falsy.

if title_str:  # equivalent to R's nzchar(title.)
    ax = plt.gca()
    default_title_size = plt.rcParams.get("axes.titlesize", 12)
    ax.set_title(title_str, fontsize=0.8 * default_title_size)
```

**Explanation:**

- `nzchar(title.)` in R returns `TRUE` for strings with at least one character. In Python, `if title_str:` is the idiomatic equivalent — an empty string `""` is falsy, a non-empty string is truthy.
- The `title()` call itself translates identically to the previous example: the first positional argument becomes the `label` argument of `ax.set_title()`, and `cex = 0.8` becomes `fontsize=0.8 * default_title_size`.
- No imports beyond `matplotlib.pyplot` are needed. There is no numpy/scipy involvement because the inputs and outputs are plain strings and graphical side effects.
