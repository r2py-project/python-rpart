# Conversion Guide: `FUN` (Callable Parameter Defaulting to `text`) in R

---

## 1. Overview of `FUN` in R

In R, function arguments can themselves be functions — this is a first-class feature of the language. In the rpart source, `FUN` is a formal parameter of `text.rpart()` declared as:

```r
function(x, splits = TRUE, label, FUN = text, all = FALSE, ...)
```

The default value `text` refers to R's base graphics function `graphics::text()`, which draws character strings at specified (x, y) coordinates on an active plot device. Its signature is:

```r
text(x, y = NULL, labels = seq_along(x), adj = NULL, pos = NULL,
     offset = 0.5, vfont = NULL, cex = 1, col = NULL, font = NULL, ...)
```

Key parameters:
- `x`, `y`: Numeric vectors of plot coordinates where text is to be placed.
- `labels`: A character vector of strings to draw at the given coordinates.
- `adj`: A scalar or length-2 vector in [0, 1] controlling horizontal (and optionally vertical) text justification. `0` = left-aligned, `0.5` = centred, `1` = right-aligned relative to the anchor point.
- `...`: Additional graphical parameters forwarded to `par()` (e.g., `srt`, `col`, `cex`).

Return value: `invisible(NULL)` — the function is called purely for its side effect of drawing on the active graphics device.

Because `FUN` is a parameter, a caller can substitute any function that accepts `(x, y, labels, ...)` in place of the default `text`. All five call sites in the CSV follow this same three-positional-argument pattern: coordinates x, coordinates y, and a character vector of labels, followed by `...` forwarding.

---

## 2. Contextual Usage Analysis

All five usages occur inside `text.rpart()` in `/groups/jli9/Yufei/python-rpart/rpart/R/text.rpart.R`. They split into two logical groups based on the `fancy` flag:

**Group A — fancy = TRUE, split labels on branches (lines 42–44)**

`FUN` is called twice to annotate the midpoints of the left and right branches of the tree with their split-label strings. The x/y coordinates are derived from `rpart.branch()` output (midpoints of branch line segments), vertically offset by `+/- 0.52 * cxy[2L]` (roughly half a character height) to clear the branch line. The labels argument is `rows[left.child[!is.na(left.child)]]` or its right-child equivalent — a character vector produced by `labels(x, ...)`.

**Group B — fancy = FALSE, split labels at node (line 47)**

A single `FUN` call places the same split-label strings (`rows[left.child]`) at the node coordinates `xy$x`, `xy$y`, offset upward by `0.5 * cxy[2L]`.

**Group C — node value annotations (lines 100–101)**

Two further calls place the node-value summary strings (`stat`, produced by `x$functions$text(...)`) at leaf node positions. In the `fancy` branch (line 100), labels go above the node (`+ 0.5 * cxy[2L]`). In the plain branch (line 101), labels go below (`- 0.5 * cxy[2L]`) and `adj = 0.5` is passed explicitly to centre the text horizontally.

**Data types summary:**
- `x` coordinate: numeric vector (one element per node or per leaf).
- `y` coordinate: numeric vector, same length as `x`, arithmetically adjusted.
- `labels`: character vector (split labels or node-value summaries), same length as `x`.
- `adj`: scalar numeric (only supplied explicitly in line 101 as `0.5`).
- `...`: additional keyword graphical parameters passed through from the caller.

---

## 3. Python Conversion Strategy

The default `FUN` is a **plotting side-effect function** with no meaningful return value. Its Python equivalent lives in **Matplotlib** (`matplotlib.axes.Axes.text` or the pyplot wrapper `matplotlib.pyplot.text`). Matplotlib is the standard Python library for 2-D plotting and provides direct analogues to every R base-graphics text primitive.

Because all call sites pass **vectors** (NumPy arrays or Python lists) of coordinates and a matching list of label strings, the conversion must loop over elements or use a helper that iterates, since `matplotlib.pyplot.text()` annotates a single point at a time (unlike R's `text()` which is natively vectorised over `x`, `y`, and `labels`). A thin wrapper is the clearest idiom.

`numpy` is used only for the arithmetic on coordinate arrays (the `+/- 0.5 * cxy` offset), keeping the conversion straightforward.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Group A — Fancy mode: split labels on branch midpoints

**Locations:** `text.rpart.R`, function `text.rpart`, lines 42–44.

**Original R Context:**

```r
# leftptx, leftpty: numeric vectors, one element per internal node,
#                   giving the midpoint of each left branch segment.
# rightptx, rightpty: same for right branch segments.
# rows: character vector of split-label strings for every node.
# left.child, right.child: integer index vectors into rows.
# cxy[2L]: scalar — character height in user coordinates (from par("cxy")).

FUN(leftptx, leftpty + 0.52 * cxy[2L],
    rows[left.child[!is.na(left.child)]], ...)

FUN(rightptx, rightpty - 0.52 * cxy[2L],
    rows[right.child[!is.na(right.child)]], ...)
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

def fun_text(x, y, labels, ax=None, **kwargs):
    """Vectorised analogue of R's text(): draw each label at its (x, y) point."""
    if ax is None:
        ax = plt.gca()
    for xi, yi, lab in zip(x, y, labels):
        ax.text(xi, yi, lab, **kwargs)

# cxy: tuple/array of length 2, (char_width, char_height) in data coordinates.
# leftptx, leftpty: 1-D numpy arrays of branch midpoint coordinates.
# rows: list/array of split-label strings for every node.
# left_child: integer index array (NaN entries already removed via boolean mask).
# right_child: same for right children.

left_mask = ~np.isnan(left_child.astype(float))
right_mask = ~np.isnan(right_child.astype(float))

left_idx  = left_child[left_mask].astype(int)
right_idx = right_child[right_mask].astype(int)

fun_text(leftptx,  leftpty  + 0.52 * cxy[1], [rows[i] for i in left_idx],  **kwargs)
fun_text(rightptx, rightpty - 0.52 * cxy[1], [rows[i] for i in right_idx], **kwargs)
```

**Explanation:**

- R's `text()` is natively vectorised; `fun_text` replicates this by iterating with `zip`.
- R uses 1-based indexing; Python uses 0-based. `left_child` and `right_child` must be adjusted accordingly when they are constructed (subtract 1 from the R `match()` results).
- `cxy[2L]` in R is the **second** element (1-based); in Python this is `cxy[1]` (0-based).
- `!is.na(left.child)` becomes `~np.isnan(left_child.astype(float))` because Python integer arrays cannot hold `NaN`; the cast to float allows the NA-equivalent check.
- `...` keyword arguments from the R caller map to `**kwargs` in Python.

---

### 4.2 Group B — Plain mode: split labels at node positions

**Locations:** `text.rpart.R`, function `text.rpart`, line 47.

**Original R Context:**

```r
# xy$x, xy$y: numeric vectors of node (x, y) coordinates for all nodes.
# rows[left.child]: character vector of split labels; NA entries are included
#                   here (R's text() silently skips NA labels).
# cxy[2L]: scalar character height.

FUN(xy$x, xy$y + 0.5 * cxy[2L], rows[left.child], ...)
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

def fun_text(x, y, labels, ax=None, **kwargs):
    if ax is None:
        ax = plt.gca()
    for xi, yi, lab in zip(x, y, labels):
        if lab is not None and not (isinstance(lab, float) and np.isnan(lab)):
            ax.text(xi, yi, str(lab), **kwargs)

# xy_x, xy_y: 1-D numpy arrays of all node coordinates.
# rows: list of split-label strings (may contain None for leaf nodes).
# left_child: integer index array (may contain NaN/None for leaf nodes).

labels_for_nodes = [
    rows[i] if (i is not None and not np.isnan(float(i))) else None
    for i in left_child
]

fun_text(xy_x, xy_y + 0.5 * cxy[1], labels_for_nodes, **kwargs)
```

**Explanation:**

- In R, indexing a vector with an `NA` index returns `NA`, and `text()` skips `NA` label entries. The Python equivalent explicitly guards against `None`/`NaN` labels inside `fun_text`.
- The vertical offset `0.5 * cxy[1]` shifts label anchors upward by half a character height, keeping parity with the R offset.

---

### 4.3 Group C — Node value annotations (fancy and plain)

**Locations:** `text.rpart.R`, function `text.rpart`, lines 100–101.

**Original R Context:**

```r
# xy$x[leaves], xy$y[leaves]: coordinate sub-vectors for leaf nodes only.
# stat: character vector of node-value summary strings, one per leaf.
# cxy[2L]: scalar character height.
# adj = 0.5 (line 101 only): explicit centring argument.

# fancy branch — labels above the node oval:
if (fancy) FUN(xy$x[leaves], xy$y[leaves] + 0.5 * cxy[2L], stat, ...)

# plain branch — labels below the node, centred:
else        FUN(xy$x[leaves], xy$y[leaves] - 0.5 * cxy[2L], stat, adj = 0.5, ...)
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

def fun_text(x, y, labels, ax=None, **kwargs):
    if ax is None:
        ax = plt.gca()
    for xi, yi, lab in zip(x, y, labels):
        ax.text(xi, yi, lab, **kwargs)

# xy_x, xy_y: full node coordinate arrays.
# leaves: boolean array, True for leaf nodes.
# stat: list of summary strings, one per leaf.
# cxy: (char_width, char_height) in data coordinates.

if fancy:
    fun_text(xy_x[leaves], xy_y[leaves] + 0.5 * cxy[1], stat, **kwargs)
else:
    fun_text(xy_x[leaves], xy_y[leaves] - 0.5 * cxy[1], stat,
             ha="center", **kwargs)
```

**Explanation:**

- R's `adj` parameter for `text()` controls horizontal justification: `adj = 0.5` centres the string on the anchor point. The Matplotlib equivalent is the `ha` (horizontal alignment) keyword argument with value `"center"`. If the caller also relies on vertical justification, use `va` (`"bottom"`, `"center"`, or `"top"`).
- In the `fancy` branch (line 100), no explicit `adj` is passed in R, so the default left-alignment applies (`adj = 0` in R, `ha="left"` in Matplotlib). In practice the caller's `...` may override this; preserve that behaviour by not hard-coding `ha` in the fancy branch.
- `xy_x[leaves]` and `xy_y[leaves]` assume `leaves` is a boolean NumPy array used for fancy indexing, exactly matching R's `xy$x[leaves]` vector subsetting.
- The `stat` list is already aligned to the leaf subset (produced by `x$functions$text(...)` called with `[leaves]`-subsetted inputs), so no re-indexing is needed.

---

## Summary Table

| CSV Lines | R Call Pattern | Python Equivalent | Key Mapping Notes |
|---|---|---|---|
| 42, 44 | `FUN(midx, midy +/- 0.52*cxy[2], labels[idx[!is.na(idx)]], ...)` | `fun_text(midx, midy +/- 0.52*cxy[1], [...], **kwargs)` | NA-guard on index; 0-based cxy |
| 47 | `FUN(xy$x, xy$y + 0.5*cxy[2], rows[left.child], ...)` | `fun_text(xy_x, xy_y + 0.5*cxy[1], labels_for_nodes, **kwargs)` | Skip None labels inside wrapper |
| 100 | `FUN(xy$x[leaves], xy$y[leaves] + 0.5*cxy[2], stat, ...)` | `fun_text(xy_x[leaves], xy_y[leaves] + 0.5*cxy[1], stat, **kwargs)` | Boolean index subsetting |
| 101 | `FUN(xy$x[leaves], xy$y[leaves] - 0.5*cxy[2], stat, adj=0.5, ...)` | `fun_text(xy_x[leaves], xy_y[leaves] - 0.5*cxy[1], stat, ha="center", **kwargs)` | `adj=0.5` -> `ha="center"` |
