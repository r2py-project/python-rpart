# Conversion Guide: `text` in R (rpart package)

---

## 1. Overview of `text` in R

R's `text()` is a base-graphics function from the `graphics` package. Its core purpose is to add text labels to an active plot at specified (x, y) coordinates. It operates as a side-effecting call — it draws directly onto the current graphics device and returns `NULL` invisibly.

Signature:

```r
text(x, y = NULL, labels = seq_along(x$x), adj = NULL,
     pos = NULL, offset = 0.5, vfont = NULL,
     cex = 1, col = NULL, font = NULL, ...)
```

Key behaviours:
- `x` and `y` are numeric vectors of plot coordinates. If either is shorter, it is recycled.
- `labels` is a character vector (or anything coercible to one) of strings to render.
- Styling parameters (`cex`, `col`, `font`, `adj`, `pos`) are optional and affect appearance and alignment.
- It operates only within an active plot window; a prior `plot()` call establishing axes is always required.

In the rpart package context, two distinct functions named `text` appear:

1. **`graphics::text(x, y, labels, ...)`** — the base R function, used for scatter-plot annotation.
2. **`text.rpart(x, ...)`** (dispatched via `text(tree, ...)` when `tree` is an `"rpart"` object) — an rpart-specific S3 method that annotates a rendered decision-tree dendrogram. Its signature is:

```r
text.rpart(x, splits = TRUE, all = FALSE, use.n = FALSE,
           fancy = FALSE, fwidth = 0.8, fheight = 0.8,
           bg = par("bg"), minlength = 1L, pretty, digits, ...)
```

---

## 2. Contextual Usage Analysis

### Call site 1 — `meanvar.rpart.R`, line 14

```r
text(x, y, label)
```

This is a call to `graphics::text()` (not `text.rpart`). The arguments are:
- `x`: a numeric vector — the `yval` column of leaf-node rows in `tree$frame` (predicted mean response per leaf).
- `y`: a numeric vector — `dev/n` per leaf (average deviance per observation).
- `label`: a character vector — `row.names(frame)`, the node numbers of leaf nodes.

Both `x` and `y` are the same length (one element per leaf). The prior line is `plot(x, y, ..., type = "n")` which creates an empty scatter plot; `text()` then overlays the node-number labels at each leaf's position. This is pure base-graphics text annotation on a scatter plot.

### Call site 2 — `plot.rpart.R`, line 30

```r
if (branch > 0) text(xx[1L], yy[1L], "|")
```

This is also `graphics::text()` applied to two scalar values:
- `xx[1L]` and `yy[1L]`: the single root-node coordinates (the first element of the coordinate vectors computed by `rpartco()`).
- `"|"`: a single literal character string, used as a vertical-bar tick mark to cap the top of the root branch on the dendrogram.

This is a purely decorative placement of a single character at a single coordinate. The condition `if (branch > 0)` gates the call: when `branch == 0` (horizontal lines only), no cap is needed.

### Call site 3 — `post.rpart.R`, line 17

```r
text(tree, all = TRUE, use.n = use.n, fancy = TRUE, digits = digits,
     pretty = pretty)
```

Here `tree` is an `"rpart"` object, so S3 dispatch routes this call to `rpart:::text.rpart()` rather than `graphics::text()`. The arguments are:
- `all = TRUE`: label every node (internal nodes and leaves), not only the terminal leaves.
- `use.n = use.n`: forward the `use.n` parameter, which appends per-node event counts to the labels.
- `fancy = TRUE`: draw ellipses around internal nodes and rectangles around leaves, with edges annotated by split directions.
- `digits = digits`: control significant-digit count in numeric labels.
- `pretty = pretty`: control factor-level label abbreviation.

This call is always paired with `plot(tree, ...)` on the immediately preceding line (line 16), which sets up the dendrogram canvas; `text.rpart()` then populates all nodes with annotations.

**Recurring pattern:** In all three cases, `text(...)` is always called after an explicit `plot(...)` call that creates the canvas. None of the calls return a value used by subsequent logic.

---

## 3. Python Conversion Strategy

Because R's base-graphics system has no one-to-one equivalent in Python, the natural replacement is **Matplotlib** (`matplotlib`), which is the standard Python library for 2-D plotting and provides explicit equivalents for every call site:

| R function | Matplotlib equivalent |
|---|---|
| `graphics::text(x, y, labels)` — vectorised | `ax.text(x[i], y[i], label[i])` in a loop, or a helper that calls it per point |
| `graphics::text(x_scalar, y_scalar, string)` — single annotation | `ax.text(x, y, string)` |
| `text.rpart(tree, ...)` — tree-node annotation | `dtreeviz` or `sklearn.tree.plot_tree()` combined with `ax.annotate()` / `ax.text()` for custom labels |

For call sites 1 and 2, `matplotlib.axes.Axes.text()` is the direct replacement. It accepts scalar `x`, `y`, and a string, and places the text on the current axes — matching R's semantics precisely.

For call site 3, `text.rpart()` is a high-level tree-annotation routine. The closest Python equivalent depends on the upstream tree representation. If the tree is a `sklearn.tree.DecisionTreeRegressor/Classifier`, `sklearn.tree.plot_tree()` handles the full annotation natively. For a custom rpart-ported tree object, each node's label must be computed and placed individually with `ax.text()`.

**Why not use `matplotlib.pyplot.text()`?** While `plt.text()` exists, `ax.text()` is the object-oriented form and is preferred in modern Matplotlib code: it is explicit about which axes receives the annotation and is essential when a figure contains multiple subplots.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Scatter-plot label annotation (vectorised)

**Locations:** `rpart/R/meanvar.rpart.R`, function `meanvar.rpart`, line 14.

**Original R context.**

Inputs:
- `x` — `float[]`, one value per leaf node (predicted mean response).
- `y` — `float[]`, one value per leaf node (average deviance).
- `label` — `str[]`, node numbers as strings (from `row.names(frame)`).

Return value: `None` (side-effecting graphics call).

```r
# Generalised R snippet
plot(x, y, xlab = xlab, ylab = ylab, type = "n")
text(x, y, label)
```

**Python Equivalent.**

```python
import numpy as np
import matplotlib.pyplot as plt

# Inputs (computed from the rpart frame equivalent)
# x: np.ndarray of shape (n_leaves,) — mean predicted values per leaf
# y: np.ndarray of shape (n_leaves,) — mean deviance per leaf
# label: list[str]        — node numbers as strings

fig, ax = plt.subplots()
ax.set_xlabel(xlab)
ax.set_ylabel(ylab)
# type="n" in R creates an empty plot; replicated by plotting nothing first
# then adding text at each (x, y) coordinate
for xi, yi, lbl in zip(x, y, label):
    ax.text(xi, yi, lbl)

plt.show()
```

**Explanation.**

- R's `text(x, y, label)` silently iterates over the three parallel vectors. In Python, explicit iteration with `zip()` replicates this.
- `plot(..., type = "n")` creates axes with correct limits but draws no points. In Matplotlib the axes are always empty until data is added, so simply calling `ax.set_xlabel` / `ax.set_ylabel` and not calling `ax.plot()` achieves the same.
- `ax.text(xi, yi, lbl)` places each string at the corresponding coordinate. Optional styling arguments (`fontsize`, `color`, `ha`, `va`) map to R's `cex`, `col`, `adj`/`pos`.
- No zero-indexing concern arises here because both R and Python iterate over the full vector.

---

### 4.2 Single-character root-node cap (scalar annotation)

**Locations:** `rpart/R/plot.rpart.R`, function `plot.rpart`, line 30.

**Original R context.**

Inputs:
- `xx[1L]` — `float`, x-coordinate of the root node (scalar, first element of the coordinate vector).
- `yy[1L]` — `float`, y-coordinate of the root node (scalar).
- `"|"` — literal `str`, a single vertical bar character.

The call is guarded by `if (branch > 0)`, ensuring it fires only when the tree uses angled (non-horizontal) branch connectors.

Return value: `None` (side-effecting graphics call).

```r
# Generalised R snippet
if (branch > 0) text(xx[1L], yy[1L], "|")
```

**Python Equivalent.**

```python
# xx: np.ndarray — x-coordinates of all nodes (from rpartco equivalent)
# yy: np.ndarray — y-coordinates of all nodes
# branch: float  — branch style parameter

if branch > 0:
    ax.text(xx[0], yy[0], "|", ha="center", va="bottom")
```

**Explanation.**

- R uses 1-based indexing: `xx[1L]` is the first element. Python uses 0-based indexing: `xx[0]`.
- `ax.text()` with a scalar x, y, and a single string is an exact semantic match.
- `ha="center"` and `va="bottom"` replicate R's default centred placement. In R the default `adj = 0.5` centres the text horizontally; setting `va="bottom"` anchors the bar cap visually at the top of the root branch.
- The `if branch > 0` guard translates directly.

---

### 4.3 Full decision-tree node annotation via `text.rpart` dispatch

**Locations:** `rpart/R/post.rpart.R`, function `post.rpart`, line 17.

**Original R context.**

Inputs:
- `tree` — an `"rpart"` object (the fitted decision tree).
- `all = TRUE` — label all nodes, not only leaves.
- `use.n = use.n` — `bool`, append per-node sample counts to labels.
- `fancy = TRUE` — draw ellipses/rectangles around nodes and annotate branch edges.
- `digits = digits` — `int`, significant-digit count for numeric labels.
- `pretty = pretty` — `bool` or `int`, controls factor abbreviation.

Return value: `None` (side-effecting; annotates the active dendrogram canvas).

```r
# Generalised R snippet
plot(tree, uniform = TRUE, branch = 0.2, compress = TRUE, margin = 0.1)
text(tree, all = TRUE, use.n = use.n, fancy = TRUE,
     digits = digits, pretty = pretty)
```

**Python Equivalent.**

Option A — using `sklearn.tree.plot_tree()` (when the tree is a scikit-learn model):

```python
from sklearn.tree import plot_tree
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 8))
plot_tree(
    decision_tree=sklearn_tree,   # sklearn DecisionTreeClassifier or Regressor
    filled=True,                  # analogous to fancy=TRUE (coloured nodes)
    impurity=True,                # show split criterion value at each node
    proportion=False,             # show raw counts (use.n=TRUE equivalent)
    rounded=True,                 # rounded boxes (approximates fancy rectangles)
    precision=digits,             # significant digits (digits= equivalent)
    ax=ax,
)
plt.show()
```

Option B — manual per-node annotation on a custom dendrogram (when the tree is a ported rpart object):

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Assumes a Python rpart tree object with attributes mirroring R's tree$frame:
#   node_coords: dict mapping node_id -> (x, y)
#   frame: dict with keys 'var', 'yval', 'n', 'dev', 'label'

fig, ax = plt.subplots(figsize=(12, 8))

# Draw the dendrogram branches first (equivalent of plot.rpart)
draw_rpart_branches(ax, tree, branch=0.2)   # custom function equivalent to plot.rpart

# Annotate all nodes (all=TRUE equivalent: iterate over every node, not just leaves)
for node_id, (x, y) in tree.node_coords.items():
    row = tree.frame[node_id]
    is_leaf = row["var"] == "<leaf>"

    # Build label text
    label_parts = [f"{row['yval']:.{digits}g}"]
    if use_n:
        label_parts.append(f"n={row['n']}")
    label_text = "\n".join(label_parts)

    if fancy:
        # Interior nodes: ellipse; leaves: rectangle (text.rpart fancy=TRUE behaviour)
        if is_leaf:
            bbox_props = dict(boxstyle="square,pad=0.3", fc="white", ec="black")
        else:
            bbox_props = dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="black")
        ax.text(x, y, label_text, ha="center", va="center",
                fontsize=8, bbox=bbox_props)
    else:
        ax.text(x, y, label_text, ha="center", va="center", fontsize=8)

ax.axis("off")
plt.show()
```

**Explanation.**

- In R, passing an `"rpart"` object as the first argument to `text()` silently dispatches to `text.rpart()` via S3 generic dispatch. Python has no equivalent mechanism; the call must be explicit.
- `all = TRUE` maps to iterating over every `node_id` in `tree.frame`, including both internal and terminal nodes.
- `fancy = TRUE` drives the ellipse/rectangle bounding-box logic. Matplotlib's `ax.text(..., bbox=dict(boxstyle=...))` replicates this: `"round"` box style for interior nodes (ellipse-like) and `"square"` for leaves.
- `use.n = use.n` translates to conditionally appending the sample-count string to the label.
- `digits` maps directly to Python's f-string format specifier `:.{digits}g`.
- `pretty` in R controls how factor levels are abbreviated in split labels. A direct Python equivalent requires implementing the same truncation logic on factor-level names; for purely numeric trees this parameter has no effect.
- The output canvas in R is a postscript device (`postscript()` in `post.rpart`). The Python equivalent would be `fig.savefig("output.pdf")` or `fig.savefig("output.eps")` to produce a vector-format file analogous to a PostScript output.
