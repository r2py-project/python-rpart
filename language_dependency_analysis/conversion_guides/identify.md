# Conversion Guide: `identify` in R

---

## 1. Overview of `identify` in R

`identify()` is an interactive graphics function from R's built-in `graphics` package. It reads the position of mouse clicks on an active plot and identifies which plotted point(s) lie closest to each click, returning their integer indices into the coordinate vectors.

**Signature:**
```r
identify(x, y = NULL, labels = seq_along(x), n = length(x),
         plot = TRUE, atpen = FALSE, offset = 0.5, tolerance = 0.25, ...)
```

Key parameters relevant to the rpart usages:

| R Parameter | Description |
|---|---|
| `x` | A two-component list with `$x` and `$y` numeric coordinate vectors (or the x-coordinates directly). When a list is passed, `y` is omitted. |
| `n` | Maximum number of points to identify before automatically returning. With `n = 1L`, the call returns after the first mouse click. |
| `plot` | When `FALSE`, no label is drawn next to the identified point. |

**Return value:** An integer vector of 1-based indices into the coordinate vectors indicating which points were selected. Returns an empty integer vector `integer(0)` when the user signals termination (right-click or pressing Escape, depending on the platform), which has `length()` equal to zero.

---

## 2. Contextual Usage Analysis

Both usages are structurally identical and follow the same interactive while-loop pattern:

```r
while (length(i <- identify(xy, n = 1L, plot = FALSE)) > 0L) {
    # process i — the 1-based integer index of the selected node
}
```

- `xy` is the return value of `rpartco(tree)`, a named list with components `$x` (numeric vector of x-coordinates) and `$y` (numeric vector of y-coordinates), one entry per node in the tree plot.
- `n = 1L` restricts each call to a single mouse click, so `identify` blocks until the user clicks once and then returns immediately with a length-1 integer vector.
- `plot = FALSE` suppresses label rendering; the calling code handles all annotation itself.
- The `while` condition `length(...) > 0L` drives the interactive loop: as long as the user clicks a valid node, the loop body executes. When the user signals "done" (right-click / Escape), `identify` returns `integer(0)`, `length()` becomes zero, and the loop exits.
- The returned index `i` (or `choose` in `snip.rpart.mouse`) is used directly to subscript into frame rows, coordinate vectors, and split-label vectors — all 1-based in R.

**Locations:**

| File | Function | Line |
|---|---|---|
| `rpart/R/path.rpart.R` | `path.rpart` | 15 |
| `rpart/R/snip.rpart.mouse.R` | `snip.rpart.mouse` | 25 |

Both occurrences are functionally identical: they differ only in what the loop body does with the returned index.

---

## 3. Python Conversion Strategy

`identify()` is a blocking, interactive GUI call with no direct equivalent in standard scientific Python libraries such as `numpy`, `scipy`, or `pandas`. These libraries operate on data, not on GUI events.

The correct Python replacement is **`matplotlib`'s event-driven picking system** using `Figure.canvas` callbacks. Specifically:

- `matplotlib.pyplot` renders the plot.
- The `pick_event` mechanism (`artist.set_picker(True)` + `canvas.mpl_connect('pick_event', callback)`) fires a callback each time the user clicks near a plotted artist, providing the index of the nearest point.
- Alternatively, `matplotlib.pyplot.ginput(n=1)` can be used to capture a raw coordinate click, after which the nearest point index is found by computing Euclidean distances — closely mirroring how R's `identify` internally matches the click to the nearest point within a tolerance radius.

The `ginput`-based approach is chosen here because it most directly mirrors R's `identify(xy, n=1L, plot=FALSE)` semantics: it blocks for a single click, returns coordinates, and leaves labelling entirely to the caller. The index is then recovered by finding the nearest node.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Interactive Node-Selection Loop (`path.rpart` and `snip.rpart.mouse`)

**Locations:**
- `rpart/R/path.rpart.R`, function `path.rpart`, line 15
- `rpart/R/snip.rpart.mouse.R`, function `snip.rpart.mouse`, line 25

**Original R Context:**

- `xy` — a named list returned by `rpartco(tree)`, with `xy$x` and `xy$y` as parallel numeric vectors of length equal to the number of tree nodes.
- `n = 1L` — integer scalar; limit one click per call.
- `plot = FALSE` — logical scalar; suppresses label drawing.
- Return type: integer vector of length 1 (valid click) or length 0 (user terminates).

```r
# xy is a list: list(x = numeric_vector, y = numeric_vector)
while (length(i <- identify(xy, n = 1L, plot = FALSE)) > 0L) {
    # i is a 1-based integer index into xy$x / xy$y
    # ... process the selected node at index i ...
}
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt


def identify_once(xy: dict) -> int | None:
    """
    Block for a single mouse click on the current matplotlib figure and return
    the 0-based index of the nearest point in xy, or None if the user closes
    the figure or clicks outside tolerance.

    Parameters
    ----------
    xy : dict with keys 'x' and 'y', each a 1-D array-like of node coordinates.

    Returns
    -------
    int or None
        0-based index of the nearest node, or None to signal termination.
    """
    coords = plt.ginput(n=1, timeout=-1)  # block until one click or window close
    if not coords:
        return None

    click_x, click_y = coords[0]
    xs = np.asarray(xy["x"])
    ys = np.asarray(xy["y"])

    # Compute Euclidean distance from click to every node in data coordinates.
    distances = np.hypot(xs - click_x, ys - click_y)
    nearest = int(np.argmin(distances))
    return nearest


# ----- Usage pattern replacing the R while-loop -----
# xy = rpartco(tree)  ->  {"x": [...], "y": [...]}

plt.ion()  # enable interactive mode so the plot stays open

while True:
    idx = identify_once(xy)      # 0-based index, or None
    if idx is None:
        break
    # Equivalent of R's 1-based index i: use idx directly (Python is 0-based).
    # Example: access the selected frame row
    selected_node = frame.iloc[idx]
    # ... process selected_node ...
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `identify(xy, n = 1L, plot = FALSE)` | `plt.ginput(n=1, timeout=-1)` + nearest-point search |
| Returns `integer(0)` to signal end | Returns `[]` (empty list) when figure is closed; mapped to `None` |
| `length(result) > 0L` loop guard | `if idx is None: break` |
| 1-based index `i` | 0-based index `idx` (subtract nothing; adjust downstream subscripts) |
| `xy$x`, `xy$y` list components | `xy["x"]`, `xy["y"]` dict values |
| Nearest-point tolerance is built into `identify` | Replicated with `np.hypot` + `np.argmin` over Euclidean distances in data coordinates |

Key nuances:

1. **1-based vs 0-based indexing.** R's `identify` returns a 1-based position into the coordinate vectors. Python uses 0-based indexing. All downstream subscripts (e.g., `frame.iloc[idx]`, `splits[idx]`) must use the 0-based `idx` directly — no offset adjustment is needed as long as the Python data structures are also 0-indexed (which `pandas` DataFrames and NumPy arrays are).

2. **Blocking behaviour.** `plt.ginput(n=1, timeout=-1)` blocks indefinitely until the user clicks, matching R's blocking `identify`. Setting `timeout=0` would also block; `-1` is the explicit infinite-wait form used in matplotlib.

3. **Tolerance.** R's `identify` uses a configurable tolerance in inches (`tolerance = 0.25` by default). The `ginput`-based approach performs nearest-point selection in data coordinates, which is simpler but does not replicate the inch-based cutoff exactly. If strict tolerance is required, the distance in display (pixel) coordinates can be computed by transforming with `ax.transData`.

4. **No label drawing.** Since `plot = FALSE` is used in both R call sites, `ginput` with no annotation is the correct match. If labelling were needed, `ax.annotate()` could be called inside the loop body after identifying the point.

5. **Required imports.**
   ```python
   import numpy as np
   import matplotlib.pyplot as plt
   ```
   No additional packages beyond `numpy` and `matplotlib` are required.
