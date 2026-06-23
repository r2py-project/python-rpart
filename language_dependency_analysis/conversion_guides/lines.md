## Conversion Guide: `lines` (R) to Python

---

### 1. Overview of `lines` in R

`lines` is a base R graphics function from the `graphics` package. It adds a connected line path to an **existing** plot as a side effect — it does not create a new plot and returns `NULL` invisibly. The function takes two paired numeric vectors of x- and y-coordinates and draws line segments connecting consecutive points in order.

Key signature:

```r
lines(x, y = NULL, type = "l", col = par("col"), lty = par("lty"), lwd = par("lwd"), ...)
```

| R Parameter | Type | Description |
|---|---|---|
| `x` | numeric vector | x-coordinates of the points to connect |
| `y` | numeric vector | y-coordinates of the points to connect (same length as `x`) |
| `col` | integer or color string | line color (e.g., `1` = black, `0` = background/white) |
| `lty` | integer or character | line type (e.g., `1` = solid, `2` = dashed) |
| `lwd` | numeric scalar | line width in display units |

A critical feature used throughout this codebase is that `NA` values embedded in the coordinate vectors cause `lines` to **lift the pen** — that is, the NA breaks the line path without starting a new `lines` call. This is the standard R technique for drawing multiple disconnected line segments in a single call.

---

### 2. Contextual Usage Analysis

Both usages appear in rpart's interactive tree-plotting infrastructure. The coordinates are produced by `rpart.branch` (defined in `rpart/R/rpart.branch.R`), which returns a named list with elements `x` and `y`. These are **matrices** with 5 rows per branch, constructed via `rbind`:

```r
xx <- rbind(x[is.left], x[is.left] + temp,
            x[sibling] - temp, x[sibling], NA)
yy <- rbind(y[is.left], y[parent], y[parent], y[sibling], NA)
list(x = xx, y = yy)
```

Each column of the matrix represents one branch: 4 coordinate points forming a horseshoe/V shape, followed by a row of `NA` to lift the pen before the next branch. When the matrix is flattened column-by-column with `c(...)`, the result is a single numeric vector containing all branch coordinates interleaved with `NA` separators — exactly the format `lines` expects for drawing multiple disconnected segments in one call.

**Usage 1 — `plot.rpart.R`, `plot.rpart`, line 31:**
All branches of the tree are drawn at once. `c(temp$x)` and `c(temp$y)` flatten the entire matrix (all columns) into a single coordinate vector. The call uses graphical parameters `branch.col`, `branch.lty`, and `branch.lwd` passed in from the user-facing `plot.rpart` function, controlling the visual appearance of every branch uniformly.

**Usage 2 — `snip.rpart.mouse.R`, `snip.rpart.mouse`, line 53:**
Only a **subset of branches** is drawn (those selected by the logical/integer index vector `temp`). `draw$x[, temp]` and `draw$y[, temp]` select specific columns of the branch matrix before flattening. The color `col = 0L` is R's background color (effectively white on a white canvas), which **erases** the selected branches by painting over them — the standard R technique for interactive removal of sub-tree branches from a displayed plot.

Recurring patterns:
- `c(matrix)` is used in both calls to convert a matrix to a flat column-major vector.
- `NA` sentinels embedded in the vectors drive the pen-lift behavior.
- `lines` is called purely for its side effect; its return value (`NULL`) is always discarded.

---

### 3. Python Conversion Strategy

The direct Python equivalent is **`matplotlib.pyplot.plot`** (or `Axes.plot` on an explicit `Axes` object).

Reasons for this choice:

- `plt.plot(x, y)` draws a connected line path on the current axes, exactly mirroring `lines`. Unlike `abline` or `axhline`, `lines` is the general-purpose polyline primitive, and `plt.plot` is its matplotlib counterpart.
- matplotlib natively handles `NaN` values in coordinate arrays as pen-lift separators, replicating R's `NA`-based segment-break technique exactly. NumPy's `np.nan` is used to represent these break points.
- **NumPy** is required for the upstream matrix manipulation: converting an R matrix (stored as a 2-D NumPy array) to a flat column-major vector via `.flatten(order='F')`, and for column-subset selection via standard NumPy indexing.
- The `col = 0L` erase pattern (Usage 2) maps to setting the matplotlib line `color` to the axes background color, typically `'white'` or the figure's `facecolor`.

R `lty` integer-to-matplotlib `linestyle` mapping:

| R `lty` value | Matplotlib `linestyle` |
|---|---|
| `1` (solid) | `'-'` |
| `2` (dashed) | `'--'` |
| `3` (dotted) | `':'` |
| `4` (dotdash) | `'-.'` |

R `col` integer-to-matplotlib `color` mapping (R default palette):

| R `col` integer | Matplotlib color |
|---|---|
| `0` | `'white'` (background — used for erasure) |
| `1` | `'black'` |
| `2` | `'red'` |
| `3` | `'#00CD00'` (green3) |
| `4` | `'blue'` |

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Drawing All Tree Branches at Once

**Locations:** `plot.rpart.R`, function `plot.rpart`, line 31.

**Original R Context**

- `temp` is the return value of `rpart.branch(xx, yy, node, branch)`, a named list with elements `x` and `y`, each a numeric **matrix** of shape `(5, n_branches)`. The 5th row of every column is `NA` to separate branches when flattened.
- `c(temp$x)` and `c(temp$y)` flatten the matrices to plain numeric vectors in column-major order, producing vectors of length `5 * n_branches`.
- `branch.col`, `branch.lty`, `branch.lwd` are scalar graphical parameters passed in by the user.
- Return value: `NULL` invisibly (side effect only).

Generalized R code:

```r
# temp$x, temp$y: numeric matrices of shape (5, n_branches) from rpart.branch()
# Row 5 of each column is NA — causes lines() to lift the pen between branches
lines(c(temp$x), c(temp$y), col = branch.col, lty = branch.lty, lwd = branch.lwd)
```

**Python Equivalent**

```python
import numpy as np
import matplotlib.pyplot as plt

# temp_x, temp_y: 2-D numpy arrays of shape (5, n_branches) from the Python
# equivalent of rpart.branch(). Row index 4 (0-based) of each column is np.nan.

# Flatten column-major (Fortran order) to match R's c() on a matrix
x_coords = temp_x.flatten(order='F')   # shape: (5 * n_branches,)
y_coords = temp_y.flatten(order='F')   # shape: (5 * n_branches,)

# Map R graphical parameters to matplotlib equivalents
lty_map = {1: '-', 2: '--', 3: ':', 4: '-.'}
col_map = {0: 'white', 1: 'black', 2: 'red', 3: '#00CD00', 4: 'blue'}

branch_col = 1    # default: black
branch_lty = 1    # default: solid
branch_lwd = 1.0  # default line width

linestyle = lty_map.get(branch_lty, '-')
color     = col_map.get(branch_col, branch_col) if isinstance(branch_col, int) else branch_col

# matplotlib treats NaN exactly like R treats NA: it lifts the pen without
# breaking the call into multiple plot() invocations.
plt.plot(x_coords, y_coords, color=color, linestyle=linestyle, linewidth=branch_lwd)
```

**Explanation**

1. **Matrix flattening** — R's `c(matrix)` iterates column by column (column-major), producing a flat vector. NumPy's `.flatten(order='F')` applies the same Fortran/column-major order. Using the default `order='C'` (row-major) would produce incorrect coordinate pairings.

2. **NA → NaN pen-lift** — R's `lines` automatically stops drawing and lifts the pen whenever it encounters `NA` in the coordinate vectors, then resumes at the next non-`NA` value. matplotlib's `plt.plot` behaves identically with `np.nan`. The 5th row of each branch column in the matrix (set to `NA`/`np.nan` by `rpart.branch`) therefore creates clean visual gaps between branch segments without needing separate `plt.plot` calls per branch.

3. **`lwd` → `linewidth`** — R's `lwd` is a relative line width multiplier (1 = default, 2 = twice as wide). matplotlib's `linewidth` is in display points. For a faithful mapping, treat R `lwd=1` as a `linewidth` of approximately 1.5 (matplotlib's default), scaling proportionally for other values. For a simple port, passing the raw integer value is usually acceptable.

4. **`col` → `color`** — R integer color codes use R's default palette. The lookup dictionary covers the common range; if the caller passes a named R color string or hex code directly, matplotlib accepts those without further mapping.

5. **Side-effect pattern** — Both `lines` and `plt.plot` operate as side effects on the current active plot. If the surrounding Python code uses the object-oriented matplotlib API (`fig, ax = plt.subplots()`), replace `plt.plot(...)` with `ax.plot(...)`.

---

#### 4.2 Erasing a Subset of Branches by Overpainting

**Locations:** `snip.rpart.mouse.R`, function `snip.rpart.mouse`, line 53.

**Original R Context**

- `draw` is the return value of `rpart.branch(xy$x, xy$y, node, branch)` — same structure as Usage 4.1: a list with `x` and `y` matrices of shape `(5, n_branches)`.
- `temp` is an **integer or logical vector** produced by `match(id, node[ff$var != "<leaf>"], 0L)`, selecting the column indices of the branches belonging to the sub-tree rooted at the node being snipped.
- `draw$x[, temp]` and `draw$y[, temp]` perform R matrix column-subsetting, returning a sub-matrix of shape `(5, length(temp))`.
- `c(...)` flattens these sub-matrices to coordinate vectors.
- `col = 0L` is R's background color (white on a white canvas), used to **paint over** (erase) the selected branches from the displayed plot. This is the standard R base-graphics technique for interactive visual removal.
- Return value: `NULL` invisibly.

Generalized R code:

```r
# draw$x, draw$y: numeric matrices (5 x n_branches) from rpart.branch()
# temp: integer/logical index vector selecting the columns to erase
lines(c(draw$x[, temp]), c(draw$y[, temp]), col = 0L)
```

**Python Equivalent**

```python
import numpy as np
import matplotlib.pyplot as plt

# draw_x, draw_y: 2-D numpy arrays of shape (5, n_branches)
# temp: 1-D array of 0-based integer column indices (or boolean mask)
#       selecting the branches to erase

# Column-subset the branch matrices (equivalent to R's draw$x[, temp])
sub_x = draw_x[:, temp]   # shape: (5, len(temp))
sub_y = draw_y[:, temp]   # shape: (5, len(temp))

# Flatten column-major to get the coordinate vectors, including NaN pen-lifts
x_coords = sub_x.flatten(order='F')
y_coords = sub_y.flatten(order='F')

# col = 0L in R is the background color.
# In matplotlib, retrieve the axes background color for an exact match.
ax = plt.gca()
bg_color = ax.get_facecolor()   # typically 'white' or (1.0, 1.0, 1.0, 1.0)

# Overpaint the selected branches with the background color to erase them
ax.plot(x_coords, y_coords, color=bg_color, linestyle='-', linewidth=1.0)
plt.draw()   # flush the update to the interactive canvas
```

**Explanation**

1. **Column subsetting** — R's `matrix[, temp]` selects columns by position (1-based). In NumPy, `array[:, temp]` selects columns by 0-based index. If `temp` was produced by `match(...) > 0` in R (a logical vector), converting it to a boolean NumPy mask works directly. If `temp` contains 1-based integer positions from R, subtract 1 before indexing: `temp_0based = temp - 1`.

2. **Erasing via overpainting** — R does not have a native erase primitive for base graphics. The conventional trick is to redraw the same geometry in the background color (`col = 0`). matplotlib supports the same approach: retrieve `ax.get_facecolor()` and use it as the `color` argument to `ax.plot(...)`. After the call, `plt.draw()` (or `fig.canvas.draw()`) forces the canvas to refresh so the erasure is visible in an interactive session.

3. **`col = 0L`** — R's color index `0` is special: it refers to the current background color of the graphics device (set by `par("bg")`), which defaults to white. It does not mean "transparent." The matplotlib equivalent is therefore the axes face color, not `'none'` (which would be transparent in matplotlib).

4. **Interactive context** — `snip.rpart.mouse` is an interactive function driven by mouse clicks (`identify`). In Python, a comparable interactive loop would use matplotlib's event system (`fig.canvas.mpl_connect('button_press_event', handler)`). The `lines` call here is the visual feedback mechanism for the erase action, triggered on the second click on a node. The `plt.draw()` call after `ax.plot(...)` is therefore important to ensure the canvas updates immediately, mirroring R's implicit redraw after `lines`.
