# Conversion Guide: `legend` (R to Python)

### 1. Overview of `legend` in R

R's `legend()` function (from the `graphics` package) adds a legend box to an existing plot. It maps visual attributes — line types, colors, point symbols, fill colors — to descriptive text labels, allowing readers to decode what each plotted series represents.

**Signature (simplified):**
```r
legend(x, y = NULL, legend, fill = NULL, col = par("col"),
       lty, lwd, pch, ..., bty = "o", cex = 1, title = NULL)
```

**Key parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `x` | numeric or character | X-coordinate of the top-left corner of the legend box, or a keyword string such as `"topright"`, `"topleft"`, `"bottomleft"`, etc. |
| `y` | numeric or `NULL` | Y-coordinate of the top-left corner. Required when `x` is numeric. |
| `legend` | character vector | Labels to display in the legend, one per entry. |
| `lty` | integer or character vector | Line type(s) for each entry. `1` = solid, `2` = dashed, `3` = dotted, `4` = dotdash, `5` = longdash, `6` = twodash. |
| `col` | character or integer vector | Colors for lines/points; defaults to the current `par("col")` (usually black). |
| `bty` | character | Box type: `"o"` (default, draws a surrounding box) or `"n"` (no box). |
| `cex` | numeric | Character expansion factor scaling text and symbol sizes. |
| `pch` | integer vector | Point character symbols; used when the legend entries represent points rather than lines. |

**Return value:** An invisible named list with elements `rect` (legend bounding box geometry) and `text` (coordinates of each text label). The return value is rarely used directly; the function is called for its side-effect of drawing the legend on the active graphics device.

---

### 2. Contextual Usage Analysis

The single occurrence in the CSV comes from `/groups/jli9/Yufei/python-rpart/rpart/R/rsq.rpart.R`, inside the `rsq.rpart` function (line 23):

```r
legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)
```

Reading the surrounding code (lines 18-23) reveals the full context:

```r
# First series: Apparent R-square (solid line, lty=1)
plot(nsplit, 1 - rel.error, xlab = "Number of Splits", ylab = "R-square",
    ylim = c(0, 1), type = "o")
par(new = TRUE)   # overlay next plot on top of the first
# Second series: X Relative R-square (dashed line, lty=2)
plot(nsplit, 1 - xerror, type = "o", ylim = c(0, 1), lty = 2,
    xlab = " ", ylab = " ")
# Legend placed at data coordinates (0, 1) -- top-left of the y=[0,1] axis range
legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)
```

**Observations:**

- `x = 0, y = 1` are **data coordinates**, not pixel or figure-fraction coordinates. They refer to the position within the current axis range, which is `xlim` derived from `nsplit` (number of tree splits, starting at 0) and `ylim = c(0, 1)`. The point `(0, 1)` is the top-left corner of the plot area.
- `legend` is a length-2 character vector: `c("Apparent", "X Relative")`.
- `lty = 1:2` is a length-2 integer vector expanding to `c(1, 2)`, meaning entry 1 gets a solid line and entry 2 gets a dashed line. No `col` is specified, so both lines default to black.
- No `pch` is provided, so the legend shows lines only (matching the `type = "o"` plots whose line attribute is what is being distinguished).
- The function is called purely for its side-effect; its return value is discarded.

**Pattern summary:** One unique usage pattern is present — a two-entry legend placed at explicit data coordinates with two distinct line types and default (black) color.

---

### 3. Python Conversion Strategy

**Chosen library: `matplotlib`**

`matplotlib` is the natural Python counterpart to R's `graphics` package. It provides:

- `ax.plot(..., linestyle=..., label=...)` to attach labels to line series at draw time.
- `ax.legend()` to render those labels as a legend box with full control over position, line-type proxy artists, font size, and framing.

The two main translation decisions are:

1. **Positioning.** R's `legend(x, y, ...)` places the top-left corner of the legend box at data coordinates `(x, y)`. In matplotlib this is replicated with `ax.legend(loc='upper left', bbox_to_anchor=(x, y), bbox_transform=ax.transData)`. Alternatively, the semantically closest built-in string location `'upper left'` (or `loc=2`) can be used when the intent is "top-left corner of the axes", which is true here since `(0, 1)` coincides with the top-left of the `ylim=[0,1]` range starting at `x=0`.

2. **Line types.** R's `lty` integer codes map to matplotlib `linestyle` strings: `1` -> `'-'` (solid), `2` -> `'--'` (dashed). These are set on the `Line2D` objects that serve as legend proxy artists.

**Why not `plt.legend()` (module-level)?** Both `plt.legend()` and `ax.legend()` work, but `ax.legend()` is preferred when multiple axes or subplots are involved and when `bbox_transform=ax.transData` is needed for coordinate-space positioning. It is also the idiomatic modern matplotlib style.

**Why not `seaborn` or `pandas.plot`?** The surrounding R code uses base-graphics primitives (`plot`, `par`, `segments`), all of which translate most directly to `matplotlib` primitives. Seaborn and pandas plotting wrap matplotlib but do not offer simpler legend-placement APIs for this pattern.

---

### 4. Step-by-Step Conversion Examples

#### Example 1: Two-entry line-type legend at data coordinates

**Locations:**
- File: `rsq.rpart.R`
- Function: `rsq.rpart`
- Line: 23

**Original R Context:**

Input types:
- `nsplit`: integer vector (number of splits at each node, e.g. `c(0, 1, 2, 3)`)
- `rel.error`: numeric vector of relative errors (same length as `nsplit`)
- `xerror`: numeric vector of cross-validation errors (same length as `nsplit`)

Return value of `legend()`: invisible list (discarded).

```r
# Generalized R snippet
plot(nsplit, 1 - rel.error,
     xlab = "Number of Splits", ylab = "R-square",
     ylim = c(0, 1), type = "o")
par(new = TRUE)
plot(nsplit, 1 - xerror,
     type = "o", ylim = c(0, 1), lty = 2,
     xlab = " ", ylab = " ")
legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

# --- Example data (mirrors the R variables) ---
nsplit    = np.array([0, 1, 2, 3])
rel_error = np.array([1.0, 0.60, 0.42, 0.35])
xerror    = np.array([1.0, 0.65, 0.50, 0.48])

fig, ax = plt.subplots()

# First series: Apparent R-square (solid line, lty=1 -> linestyle='-')
ax.plot(nsplit, 1 - rel_error,
        linestyle='-', marker='o',
        color='black',
        label='Apparent')

# Second series: X Relative R-square (dashed line, lty=2 -> linestyle='--')
ax.plot(nsplit, 1 - xerror,
        linestyle='--', marker='o',
        color='black',
        label='X Relative')

ax.set_xlabel("Number of Splits")
ax.set_ylabel("R-square")
ax.set_ylim(0, 1)

# ---------------------------------------------------------------
# legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)
#
# R places the top-left corner of the legend box at data
# coordinates (x=0, y=1).  In matplotlib this is expressed with
# bbox_to_anchor in data-coordinate space.
# ---------------------------------------------------------------
ax.legend(
    loc='upper left',
    bbox_to_anchor=(0, 1),
    bbox_transform=ax.transData,
)

plt.tight_layout()
plt.show()
```

**Explanation:**

| R concept | Python / matplotlib equivalent | Notes |
|-----------|-------------------------------|-------|
| `plot(..., type = "o")` | `ax.plot(..., marker='o')` | `type="o"` means "both lines and points" |
| `lty = 1` (solid) | `linestyle='-'` | Default matplotlib linestyle |
| `lty = 2` (dashed) | `linestyle='--'` | R's integer code 2 maps to matplotlib `'--'` |
| `legend(0, 1, labels, lty=1:2)` | `ax.legend(loc='upper left', bbox_to_anchor=(0,1), bbox_transform=ax.transData)` | R positions the legend top-left corner at data coords `(0,1)`; matplotlib replicates this with `bbox_to_anchor` using `ax.transData` to interpret the tuple as data coordinates |
| `par(new = TRUE)` | Second `ax.plot()` call on the same `Axes` | matplotlib plots overlay on the same axes by default — no special call needed |
| Labels via `legend` vector | Labels via `label=` kwarg in each `ax.plot()` call | matplotlib collects `label` from plotted artists automatically when `ax.legend()` is called |
| Return value (invisible list) | Return value of `ax.legend()` is a `Legend` object | Typically discarded; assigned only if further programmatic manipulation is needed |

**Alternative: using `loc` string instead of data coordinates**

When the intent is simply "top-left corner of the axes" (which is the case here since `(0, 1)` is the top-left of the data range), the simpler form is equally correct and more portable:

```python
ax.legend(loc='upper left')
```

Use `bbox_to_anchor` with `ax.transData` only when the legend must be anchored to a specific data-space position that does not coincide with an axes corner.

**Alternative: explicit proxy artists**

If the series are not drawn with `label=` (e.g., when replicating code that uses `par(new=TRUE)` with two separate `plot()` calls that cannot easily be refactored), legend entries can be constructed manually:

```python
solid_line  = mlines.Line2D([], [], color='black', linestyle='-',  label='Apparent')
dashed_line = mlines.Line2D([], [], color='black', linestyle='--', label='X Relative')

ax.legend(handles=[solid_line, dashed_line], loc='upper left')
```

This mirrors R's behavior of specifying the legend content independently from the plot calls themselves.
