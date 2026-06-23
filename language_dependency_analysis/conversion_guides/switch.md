# Conversion Guide: `switch` in R

## 1. Overview of `switch` in R

`switch` is a control-flow function in R that dispatches on the value of a single expression (typically a character string) and returns the value of the matching named alternative. Its general form is:

```r
switch(EXPR, name1 = value1, name2 = value2, ..., default_value)
```

Key behavioral rules:
- `EXPR` is evaluated first and matched against the names of the remaining arguments.
- When a match is found, the corresponding expression on the right-hand side is evaluated and its value is returned.
- If a named alternative has no right-hand side (i.e., `name = ,`), R falls through to the next alternative with a value — this is R's implicit fall-through mechanism, analogous to a `case` statement without a `break` in C.
- If no match is found and an unnamed final argument exists, that argument serves as the default.
- If no match is found and there is no default, `switch` returns `NULL` invisibly.
- The right-hand side of each alternative can be a scalar, a vector computation, or a braced block `{ ... }` containing multiple statements (side-effecting or not). In the braced-block form, `switch` acts as a statement dispatcher rather than a pure expression dispatcher.

Because R is a vectorized language, the _values_ returned by `switch` branches are often vectors (or matrix-indexed results), not scalars. The string `EXPR` itself, however, is always a length-1 character value.

---

## 2. Contextual Usage Analysis

Four `switch` calls appear across three files. They fall into two functionally distinct patterns:

**Pattern A — String-to-string mapping (pure value return, no side effects).**
Found in `printcp.R` at line 5. The `switch` expression is nested directly inside `cat()`. The EXPR is `x$method`, a single string drawn from `{"anova", "class", "poisson", "exp"}`, and each branch returns a string literal. The result is consumed immediately as the argument to `cat()`.

**Pattern B — String-dispatched side-effect blocks.**
Found in `plotcp.R` at line 26. The EXPR is `upper`, validated earlier by `match.arg()` to one of `{"size", "splits", "none"}`. Each branch is a braced block executing two plotting calls (`axis()` and `mtext()`). The `"none"` case has no branch, so `switch` silently returns `NULL` and nothing is drawn. The return value of `switch` itself is discarded; only the side effects matter.

**Pattern C — String-to-vector-expression mapping (vectorized numeric computation).**
Found in `residuals.rpart.R` at lines 25 and 36. The EXPR is `type`, validated by `match.arg()` to one of `{"usual", "pearson", "deviance"}`. Each branch is a numeric vector expression (matrix indexing, element-wise arithmetic, `log`, `sqrt`, `sign`). The result of `switch` is the computed residual vector, assigned to `resid`. The two calls are inside separate `if/else if` branches (`method == "class"` vs. `method == "poisson"` or `"exp"`), but structurally they are identical: three named alternatives, each returning a numeric vector.

Recurring observations:
- `EXPR` is always a pre-validated string (via `match.arg()` or a known attribute), so there is no need for a runtime default/error branch in Python.
- All numeric operands (`y`, `yhat`, `events`, `expect`, `lambda`, etc.) are NumPy-compatible arrays.
- The braced blocks in Pattern B contain calls to R's graphics system; these will map to Matplotlib equivalents in Python, not to Python data structures.

---

## 3. Python Conversion Strategy

Three Python idioms cover all observed patterns:

| R Pattern | Python Idiom |
|---|---|
| `switch` returning one of several string literals | `dict` lookup: `d[key]` |
| `switch` dispatching braced blocks with side effects | `if/elif` chain |
| `switch` returning one of several NumPy vector expressions | `if/elif` chain assigning to a variable, or a `dict` of callables |

**Why not a plain `dict` for all cases?**

A Python `dict` whose values are expressions would eagerly evaluate all branches at construction time. This is safe only when all branches are cheap, side-effect-free literals. For branches that involve NumPy computations over potentially large arrays (Pattern C) or that call plotting routines (Pattern B), eager evaluation is incorrect. An `if/elif` chain evaluates only the taken branch, exactly mirroring R's lazy semantics.

For Pattern A (string literals only), a `dict` lookup is perfectly idiomatic and the most concise translation.

For Patterns B and C, an `if/elif` chain is the correct and idiomatic Python equivalent.

NumPy is the mandatory library for Pattern C: the operands (`y`, `yhat`, `events`, `expect`, `temp`) are element-wise array quantities, and functions like `np.log`, `np.sqrt`, and `np.sign` replicate R's vectorized `log`, `sqrt`, and `sign` exactly.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — String-to-string dispatch (`printcp.R`)

**Locations:** `printcp.R`, function `printcp`, line 5.

**Original R Context.**

`x$method` is a length-1 character string, one of `"anova"`, `"class"`, `"poisson"`, or `"exp"`. The `switch` call returns the matching string literal, which is passed directly to `cat()`.

```r
cat(switch(x$method,
           anova   = "\nRegression tree:\n",
           class   = "\nClassification tree:\n",
           poisson = "\nRates regression tree:\n",
           exp     = "\nSurvival regression tree:\n")
    )
```

**Python Equivalent.**

```python
_METHOD_HEADER = {
    "anova":   "\nRegression tree:\n",
    "class":   "\nClassification tree:\n",
    "poisson": "\nRates regression tree:\n",
    "exp":     "\nSurvival regression tree:\n",
}

print(_METHOD_HEADER[x.method], end="")
```

**Explanation.**

- All four branch values are plain string literals with no side effects, so a `dict` is both correct and idiomatic. The dictionary can be defined at module level as a constant.
- R's `cat()` does not append a newline by default; Python's `print()` does. Setting `end=""` neutralizes that difference, letting the `\n` characters inside the strings control spacing exactly as in R.
- Dictionary key lookup raises `KeyError` if `x.method` is not present. Because the original R code has no default branch either (returning `NULL` silently for unknown methods), a `KeyError` is actually a stricter — and preferable — behavior. If silent fallback is desired, use `_METHOD_HEADER.get(x.method, "")`.

---

### 4.2 Pattern B — Side-effect block dispatch (`plotcp.R`)

**Locations:** `plotcp.R`, function `plotcp`, line 26.

**Original R Context.**

`upper` is a length-1 string, pre-validated by `match.arg()` to one of `"size"`, `"splits"`, or `"none"`. Each branch calls two graphics functions (`axis()` and `mtext()`). When `upper == "none"` no branch is matched and nothing is drawn. The return value of `switch` is discarded.

```r
switch(upper,
       size = {
           axis(3L, at = ns, labels = as.character(nsplit + 1), ...)
           mtext("size of tree", side = 3, line = 3)
       },
       splits = {
           axis(3L, at = ns, labels = as.character(nsplit), ...)
           mtext("number of splits", side = 3, line = 3)
       })
# "none" has no branch — switch returns NULL silently, no drawing occurs
```

**Python Equivalent.**

In the Python translation the R graphics calls map to Matplotlib operations. `axis(3L, ...)` adds a secondary x-axis (top). `mtext(..., side = 3, ...)` adds a label to that top axis. The surrounding context supplies `ax` (the primary `Axes`), `ns` (a 1-D integer array of tree-size indices), and `nsplit` (a 1-D integer array of split counts).

```python
import numpy as np
import matplotlib.pyplot as plt

# upper: str, one of {"size", "splits", "none"}
# ax: matplotlib.axes.Axes  (primary axes object)
# ns: np.ndarray of int     (x-positions, 1-indexed sequence)
# nsplit: np.ndarray of int (number of splits at each cp step)

if upper == "size":
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(ns)
    ax2.set_xticklabels([str(v) for v in (nsplit + 1)])
    ax2.set_xlabel("size of tree")
elif upper == "splits":
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(ns)
    ax2.set_xticklabels([str(v) for v in nsplit])
    ax2.set_xlabel("number of splits")
# upper == "none": no secondary axis is drawn — intentional no-op
```

**Explanation.**

- A `dict` cannot be used here because each branch executes multiple statements with side effects. An `if/elif` chain evaluates only the matched branch, matching R's lazy semantics.
- The absence of an `else` clause mirrors R's silent `NULL` return for the `"none"` case.
- `nsplit + 1` in the `"size"` branch uses NumPy broadcasting. In R, `nsplit` is a numeric vector and `+1` is vectorized; `np.ndarray + 1` behaves identically.
- R's `axis(3L, ...)` draws on the third side (top). The Matplotlib equivalent is a twin x-axis (`ax.twiny()`), whose x-limits must be synchronized with the primary axis to keep tick positions aligned.
- Additional keyword arguments passed via `...` in R (forwarded to `axis()`) would be handled in Python by passing `**kwargs` through to the relevant Matplotlib calls.

---

### 4.3 Pattern C — Vectorized numeric dispatch, classification residuals (`residuals.rpart.R`, `method == "class"`)

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 25.

**Original R Context.**

This branch executes when `object$method == "class"`. `type` is pre-validated to one of `"usual"`, `"pearson"`, or `"deviance"`. All operands are vectors:

- `y`: integer vector of observed class labels (1-indexed).
- `yhat`: numeric vector (for `"usual"`) or numeric matrix column slice (for `"pearson"` / `"deviance"`), representing predicted class probabilities or the predicted probability for the observed class.
- `loss`: a numeric loss matrix indexed as `loss[observed_class, predicted_class]`.

```r
# object$method == "class"
# type: one of "usual", "pearson", "deviance"
# y:    integer vector of class labels (1-indexed in R)
# yhat: numeric vector of predicted values / probabilities
# loss: numeric matrix (loss[y, yhat])

resid <- switch(type,
                usual    = loss[cbind(y, yhat)],
                pearson  = (1 - yhat) / yhat,
                deviance = -2 * log(yhat))
```

**Python Equivalent.**

```python
import numpy as np

# type_: str, one of {"usual", "pearson", "deviance"}
# y:     np.ndarray of int, 0-indexed class labels (converted from R's 1-indexed)
# yhat:  np.ndarray of int (for "usual") or float (for "pearson"/"deviance")
# loss:  np.ndarray of shape (n_classes, n_classes), the loss matrix

if type_ == "usual":
    resid = loss[y, yhat]          # advanced integer-array indexing
elif type_ == "pearson":
    resid = (1.0 - yhat) / yhat
elif type_ == "deviance":
    resid = -2.0 * np.log(yhat)
```

**Explanation.**

- R uses 1-based integer indexing; NumPy uses 0-based. R's `loss[cbind(y, yhat)]` selects one element per row using paired integer indices. In Python, `loss[y, yhat]` with 0-indexed integer arrays achieves the same result. When translating, subtract 1 from both `y` and `yhat` if they were read directly from R's 1-indexed representation.
- `log` in R is the natural logarithm; `np.log` is its direct equivalent.
- All three branches return vectors of the same length as `y`, and NumPy's element-wise arithmetic operators (`/`, `*`) replicate R's vectorized behavior without any explicit loops.
- `np.log(yhat)` will produce `-inf` for `yhat == 0` (and a `RuntimeWarning`). R's `log(0)` similarly produces `-Inf` with a warning. If the caller guarantees `yhat > 0` (which predicted probabilities typically do), no additional guard is needed.

---

### 4.4 Pattern C — Vectorized numeric dispatch, Poisson/survival residuals (`residuals.rpart.R`, `method == "poisson"` or `"exp"`)

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 36.

**Original R Context.**

This branch executes when `object$method == "poisson"` or `object$method == "exp"`. All operands are numeric vectors derived from the model frame:

- `events`: numeric vector of observed event counts.
- `expect`: numeric vector of expected event counts (`lambda * time`).
- `temp`: numeric vector, equal to `expect` but with a small failsafe value (`0.0001`) substituted wherever `expect == 0`, preventing `log(0)`.

```r
# object$method == "poisson" or "exp"
# events: numeric vector of observed events
# expect: numeric vector of expected events (lambda * time)
# temp:   numeric vector = ifelse(expect == 0, 0.0001, expect)

resid <- switch(type,
                usual    = events - expect,
                pearson  = (events - expect) / sqrt(temp),
                deviance = sign(events - expect) *
                               sqrt(2 * (events * log(events / temp) -
                                         (events - expect))))
```

**Python Equivalent.**

```python
import numpy as np

# type_:   str, one of {"usual", "pearson", "deviance"}
# events:  np.ndarray of float, observed event counts
# expect:  np.ndarray of float, expected event counts (lambda_ * time)
# temp:    np.ndarray of float, failsafe version of expect (0 replaced by 0.0001)

if type_ == "usual":
    resid = events - expect
elif type_ == "pearson":
    resid = (events - expect) / np.sqrt(temp)
elif type_ == "deviance":
    resid = (np.sign(events - expect) *
             np.sqrt(2.0 * (events * np.log(events / temp) -
                            (events - expect))))
```

The `temp` failsafe is constructed as:

```python
temp = np.where(expect == 0, 0.0001, expect)
```

**Explanation.**

- `ifelse(expect == 0, 0.0001, expect)` in R is a vectorized conditional; `np.where(condition, x, y)` is the direct NumPy equivalent.
- R's `sign()`, `sqrt()`, and `log()` are all vectorized over their inputs; `np.sign()`, `np.sqrt()`, and `np.log()` behave identically on NumPy arrays.
- The `deviance` formula involves `events * log(events / temp)`. When `events == 0`, this produces `0 * log(0)` which is mathematically defined as 0 by the Poisson deviance convention but yields `nan` in floating-point arithmetic. R handles this case the same way (producing `NaN`). If strict correctness is required, add a guard: `np.where(events == 0, 0.0, events * np.log(events / temp))`.
- Operator precedence in the `deviance` branch: the `*` between `np.sign(...)` and `np.sqrt(...)` is element-wise array multiplication, matching R's `*` between vectors.
- No `else` branch is needed in Python (just as there is no default in R) because `type_` is pre-validated by `match.arg()` before `switch` is reached. In Python this validation would be an explicit check such as `assert type_ in {"usual", "pearson", "deviance"}` before entering the `if/elif` chain.
