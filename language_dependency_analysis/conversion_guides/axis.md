# Conversion Guide: `axis` (R to Python)

---

## 1. Overview of `axis` in R

`axis()` is a base R graphics function from the `graphics` package that adds a labeled axis to an existing plot. It is called exclusively for its side effect of drawing on the current graphical device; it returns the tick-mark positions invisibly.

**Function signature:**

```r
axis(side, at = NULL, labels = TRUE, tick = TRUE, line = NA,
     pos = NA, outer = FALSE, font = NA, lty = "solid",
     lwd = 1, lwd.ticks = lwd, col = NULL, col.ticks = NULL,
     hadj = NA, padj = NA, gap.axis = NA, ...)
```

**Key parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `side` | integer (1–4) | required | Side of the plot: 1 = bottom, 2 = left, 3 = top, 4 = right |
| `at` | numeric vector | `NULL` | Positions (in data coordinates) where tick marks are drawn; auto-computed when `NULL` |
| `labels` | logical / character vector | `TRUE` | Custom text labels at each tick; `TRUE` uses the `at` values; `FALSE` draws ticks only |
| `tick` | logical | `TRUE` | Whether to draw tick marks and the axis line |
| `...` | — | — | Additional graphical parameters forwarded to the underlying rendering (e.g., `cex.axis`, `col.axis`, `las`) |

Non-finite values in `at` are silently omitted. Overlapping labels are suppressed automatically.

---

## 2. Contextual Usage Analysis

All four `axis` calls appear in a single function, `plotcp`, defined in `/groups/jli9/Yufei/python-rpart/rpart/R/plotcp.R`. The function draws a diagnostic cross-validation error plot for an `rpart` model and adds three custom axes.

The surrounding context (lines 1–38) reveals the following:

- **`ns`** (`seq_along(nsplit)`) — integer vector of sequential indices (1, 2, 3, …), used as the x-axis positions for every tick mark passed to `at`.
- **`cp`** — numeric vector of complexity parameter geometric means derived from `p.rpart[, 1L]`.
- **`nsplit`** — integer vector of split counts from `p.rpart[, 2L]`.
- **`...` (dots)** — graphical parameters forwarded from the `plotcp` caller (e.g., `cex`, `col.axis`); passed through to every `axis` call.

There are three distinct usage patterns:

| Line | Side | `at` | `labels` | Purpose |
|------|------|------|----------|---------|
| 23 | `2` (left) | auto | auto | Default y-axis with no custom ticks or labels |
| 25 | `1` (bottom) | `ns` | `signif(cp, 2L)` as strings | Bottom x-axis labeled with rounded CP values |
| 28 | `3` (top) | `ns` | `nsplit + 1` as strings | Top x-axis labeled with tree size (splits + 1) |
| 32 | `3` (top) | `ns` | `nsplit` as strings | Top x-axis labeled with number of splits |

Lines 28 and 32 are mutually exclusive branches of a `switch` on the `upper` argument, so they represent the same axis position with two different label sets.

---

## 3. Python Conversion Strategy

The direct Python equivalent of R's `axis()` is **`matplotlib`**. Matplotlib's `Axes` object exposes fine-grained axis configuration through methods on `ax.xaxis`, `ax.yaxis`, and the twin-axis mechanism `ax.twiny()` / `ax.twinx()`. There is no single one-to-one function, but the mapping is straightforward:

| R call | Primary matplotlib equivalent |
|--------|-------------------------------|
| `axis(side, ...)` | `ax.yaxis` / `ax.xaxis` setters or `ax.tick_params()` |
| `axis(side, at=..., labels=..., ...)` | `ax.set_xticks()` + `ax.set_xticklabels()` (or y variants) |
| Top axis (`side=3`) | `ax_top = ax.twiny()` then configure `ax_top` |

`numpy` is used where label values must be computed (e.g., `np.round`, `np.sqrt`) to match R's vectorized arithmetic that feeds into `labels`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Default Left-Side (y) Axis — Line 23

**Locations:** `plotcp.R`, function `plotcp`, line 23.

**Original R context:**

```r
# side = 2 means the left (y) axis
# No 'at' or 'labels' supplied; R renders automatic ticks
# '...' forwards caller-supplied graphical params (e.g. col.axis, cex.axis)
axis(2, ...)
```

- Input types: `side` is a scalar integer literal `2`; `...` contains optional named graphical parameters.
- Return value: numeric vector of tick positions (returned invisibly; not used by `plotcp`).

**Python equivalent:**

```python
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

fig, ax = plt.subplots()

# R's axis(2, ...) — left y-axis with automatic ticks and labels.
# matplotlib draws this axis by default; explicit configuration is only
# needed when forwarding caller-supplied style parameters.
ax.yaxis.set_major_locator(ticker.AutoLocator())
ax.yaxis.set_major_formatter(ticker.ScalarFormatter())

# Optional: forward caller style kwargs (equivalent to R's '...')
# e.g. ax.tick_params(axis='y', labelsize=10, colors='blue')
```

**Explanation:** In matplotlib, the y-axis is present and auto-ticked by default, so this call is a no-op in many translation contexts. When the caller supplies extra styling (R's `...`), those are forwarded via `ax.tick_params(axis='y', ...)`. No `at` or `labels` argument means no custom tick positions are set.

---

### 4.2 Bottom (x) Axis with CP Value Labels — Line 25

**Locations:** `plotcp.R`, function `plotcp`, line 25.

**Original R context:**

```r
# ns      : integer vector 1..N (sequential indices)
# cp      : numeric vector of geometric-mean CP values
# side=1  : bottom x-axis
# at=ns   : tick positions at each integer index
# labels  : character vector of CP values rounded to 2 significant figures
axis(1L, at = ns, labels = as.character(signif(cp, 2L)), ...)
```

- `ns`: `integer[]`, length N, values `1, 2, …, N`.
- `cp`: `numeric[]`, length N.
- `labels`: `character[]`, length N — two-significant-figure representations of each CP value.
- Return value: numeric tick positions (returned invisibly).

**Python equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

# Assume these are already computed (matching the R context):
#   ns     = np.arange(1, N + 1)          # integer positions
#   cp     = ...                           # numeric array of CP values

# R: signif(cp, 2L) rounds to 2 significant figures — no direct numpy
# equivalent, so use a helper:
def signif(x, digits=2):
    """Round array x to `digits` significant figures (mirrors R's signif)."""
    x = np.asarray(x, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        magnitude = np.floor(np.log10(np.abs(x)))
        magnitude = np.where(np.isfinite(magnitude), magnitude, 0)
    factor = 10 ** (digits - 1 - magnitude)
    return np.round(x * factor) / factor

cp_labels = [str(v) for v in signif(cp, 2)]

fig, ax = plt.subplots()

# R's axis(1L, at=ns, labels=as.character(signif(cp, 2L)), ...)
ax.set_xticks(ns)
ax.set_xticklabels(cp_labels)
ax.set_xlabel("cp")

# Optional style forwarding (equivalent to R's '...')
# ax.tick_params(axis='x', labelsize=10)
```

**Explanation:** `ax.set_xticks(ns)` maps directly to R's `at = ns`. `ax.set_xticklabels(cp_labels)` maps to R's `labels = as.character(signif(cp, 2L))`. Because R's `signif()` has no exact numpy counterpart, a small vectorized helper is provided. Note that matplotlib uses 0-based figure coordinates internally, but since `ns` starts at 1 and matches the data coordinates established by the preceding `plot()` call, no index offset is needed.

---

### 4.3 Top (x) Axis with Tree Size Labels — Line 28

**Locations:** `plotcp.R`, function `plotcp`, line 28 (active when `upper = "size"`).

**Original R context:**

```r
# side=3  : top x-axis
# at=ns   : tick positions at integer indices
# labels  : number of terminal nodes = nsplit + 1
axis(3L, at = ns, labels = as.character(nsplit + 1), ...)
mtext("size of tree", side = 3, line = 3)
```

- `nsplit`: `integer[]`, length N — number of splits at each CP row.
- `labels`: `character[]` values of `nsplit + 1` (tree size = terminal nodes).
- Return value: numeric tick positions (returned invisibly).

**Python equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

# Assume ns and nsplit are already numpy arrays (computed earlier in plotcp).

fig, ax = plt.subplots()
# ... (main plot and bottom axis already configured) ...

# R's axis(3L, at=ns, labels=as.character(nsplit + 1), ...)
# A top x-axis in matplotlib requires a twin axis that shares the same
# x-scale but carries its own tick configuration.
ax_top = ax.twiny()
ax_top.set_xlim(ax.get_xlim())          # share x-range with main axis
ax_top.set_xticks(ns)
ax_top.set_xticklabels([str(v) for v in (nsplit + 1)])

# R's mtext("size of tree", side=3, line=3)
ax_top.set_xlabel("size of tree", labelpad=12)
```

**Explanation:** R's `side = 3` targets the top of the plot. In matplotlib this is achieved with `ax.twiny()`, which creates a second `Axes` object sharing the same y-scale. `set_xlim` is called immediately after `twiny()` to synchronize the data range with the primary axis, ensuring tick positions in `ns` fall at the correct locations. `nsplit + 1` is a numpy scalar broadcast addition, exactly matching R's vectorized `nsplit + 1`.

---

### 4.4 Top (x) Axis with Number-of-Splits Labels — Line 32

**Locations:** `plotcp.R`, function `plotcp`, line 32 (active when `upper = "splits"`).

**Original R context:**

```r
# side=3  : top x-axis
# at=ns   : tick positions at integer indices
# labels  : number of splits (nsplit, without the +1 offset)
axis(3L, at = ns, labels = as.character(nsplit), ...)
mtext("number of splits", side = 3, line = 3)
```

- `nsplit`: `integer[]`, length N — number of splits (used directly, no offset).
- `labels`: `character[]` representation of `nsplit`.
- Return value: numeric tick positions (returned invisibly).

**Python equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

# Assume ns and nsplit are already numpy arrays.

fig, ax = plt.subplots()
# ... (main plot and bottom axis already configured) ...

# R's axis(3L, at=ns, labels=as.character(nsplit), ...)
ax_top = ax.twiny()
ax_top.set_xlim(ax.get_xlim())
ax_top.set_xticks(ns)
ax_top.set_xticklabels([str(v) for v in nsplit])

# R's mtext("number of splits", side=3, line=3)
ax_top.set_xlabel("number of splits", labelpad=12)
```

**Explanation:** This is structurally identical to section 4.3. The only difference is that the labels are `nsplit` rather than `nsplit + 1`, reflecting raw split counts instead of terminal node counts. The `twiny()` + `set_xlim` + `set_xticks` + `set_xticklabels` pattern is the same.
