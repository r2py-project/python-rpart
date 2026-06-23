# Conversion Guide: `polygon` (R to Python)

---

## 1. Overview of `polygon` in R

`polygon` is part of R's base `graphics` package. It draws one or more filled polygons on the current graphics device, using vectors of x and y coordinates as the polygon vertices. R automatically closes each polygon by connecting the last vertex back to the first.

Key parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `x` | numeric vector | x-coordinates of the vertices |
| `y` | numeric vector | y-coordinates of the vertices |
| `col` | color value or `NA` | Fill color of the polygon interior. `NA` (the default) leaves the polygon unfilled. |
| `border` | color value, `NA`, or logical | Color of the polygon outline. `NULL` (default) uses the current foreground color. `NA` omits the border. A logical `TRUE` is accepted for backward compatibility and resolves to the current foreground color. |
| `density` | numeric or `NULL` | Lines-per-inch for cross-hatching. `NULL` (default) means no hatching; fill is controlled by `col` alone. |
| `lty` | line type | Line type for border and hatching. |
| `fillOddEven` | logical | Fill rule for self-intersecting polygons (`FALSE` = non-zero winding rule, `TRUE` = even-odd rule). |

`polygon` returns `NULL` invisibly. Its effect is a side effect: drawing on the active graphics device.

---

## 2. Contextual Usage Analysis

Both usages of `polygon` in this CSV originate from the `fancy`-mode branch of `text.rpart` in `/groups/jli9/Yufei/python-rpart/rpart/R/text.rpart.R`. The call signature is identical in both locations:

```r
polygon(newx, newy, border = TRUE, col = bg)
```

**In `oval` (line 66):**
- `newx` and `newy` are numeric vectors of length 61 (one point per step of `theta <- seq(0, 2*pi, pi/30)`), forming a smooth ellipse centered at `(middlex, middley)` with semi-axes `a` and `b`.
- The result is a filled ellipse approximated by a 61-vertex polygon.

**In `rectangle` (line 74):**
- `newx` is a length-4 numeric vector: `middlex + c(a, a, -a, -a)`.
- `newy` is a length-4 numeric vector: `middley + c(b, -b, -b, b)`.
- The result is a filled rectangle (4-vertex polygon) centered at `(middlex, middley)`.

**Shared argument pattern:**
- `border = TRUE` — backward-compatible logical that resolves to the current foreground color, so the polygon is always outlined.
- `col = bg` — `bg` is a color string (e.g., `"white"` or whatever `par("bg")` returns after the alpha guard at line 60). The interior is always filled with the background color.

**Data types:**
- `newx`, `newy`: plain R numeric vectors (double precision).
- `border`: logical scalar (`TRUE`).
- `col`: a character string representing a named or hex color.

---

## 3. Python Conversion Strategy

The direct Python equivalent for R's `polygon` drawing primitive is **`matplotlib`**, specifically:

- `matplotlib.patches.Polygon` — the patch class that accepts an array of (x, y) vertex pairs and supports `facecolor` and `edgecolor` styling.
- `matplotlib.pyplot.fill` — a convenience wrapper that accepts separate x and y arrays and fills the closed polygon, with keyword arguments for face and edge color.

`matplotlib.pyplot.fill` is the most direct drop-in for `polygon(x, y, col=..., border=...)` because it accepts the same separate x/y arrays that R uses. For richer patch control (linewidth, linestyle, zorder) `matplotlib.patches.Polygon` is preferred.

NumPy is required to construct the vertex arrays (matching R's vectorized arithmetic on `cos`/`sin` and `c()`).

**Why not `shapely` or `PIL`?**
Both are non-plotting libraries. The R usage here is purely a rendering call on an active plotting device; matplotlib is the correct layer for that.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `oval` — Ellipse Approximated as a Polygon

**Location:** `text.rpart.R`, function `oval`, line 66.

**Original R Context:**

```r
# Input types:
#   middlex, middley : numeric scalar — center coordinates in plot space
#   a, b             : numeric scalar — horizontal and vertical semi-axes
#   bg               : character scalar — fill color string, e.g. "white"
#
# newx, newy are numeric vectors of length 61 (double precision)

oval <- function(middlex, middley, a, b) {
    theta <- seq(0, 2 * pi, pi/30)          # 61-element numeric vector
    newx  <- middlex + a * cos(theta)        # numeric vector, length 61
    newy  <- middley + b * sin(theta)        # numeric vector, length 61
    polygon(newx, newy, border = TRUE, col = bg)
    # Draws a filled ellipse:
    #   interior color  = bg  (the background color string)
    #   border color    = current foreground (border=TRUE resolves to fg)
}
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def oval(ax, middlex, middley, a, b, bg="white", fg="black"):
    """
    Draw a filled ellipse approximated by a 61-vertex polygon on Axes `ax`.

    Parameters
    ----------
    ax      : matplotlib.axes.Axes  — target axes (replaces R's active device)
    middlex : float                  — x-coordinate of the ellipse center
    middley : float                  — y-coordinate of the ellipse center
    a       : float                  — horizontal semi-axis length
    b       : float                  — vertical semi-axis length
    bg      : str                    — fill color (default "white"), mirrors R's `bg`
    fg      : str                    — border color (default "black"), mirrors R's fg
    """
    theta = np.linspace(0, 2 * np.pi, 61)   # matches seq(0, 2*pi, pi/30) -> 61 pts
    newx  = middlex + a * np.cos(theta)      # shape (61,) float64 array
    newy  = middley + b * np.sin(theta)      # shape (61,) float64 array

    vertices = np.column_stack([newx, newy]) # shape (61, 2)
    patch = mpatches.Polygon(
        vertices,
        closed=True,          # auto-close: connects last vertex to first (R default)
        facecolor=bg,         # col = bg
        edgecolor=fg,         # border = TRUE -> current foreground color
        linewidth=1.0,
    )
    ax.add_patch(patch)
```

**Explanation:**

| R | Python |
|---|--------|
| `seq(0, 2*pi, pi/30)` | `np.linspace(0, 2*np.pi, 61)` — `seq` with a `by` step of `pi/30` over `[0, 2*pi]` produces 61 points; `linspace` with `num=61` replicates this exactly. |
| `middlex + a * cos(theta)` | `middlex + a * np.cos(theta)` — element-wise, identical semantics. |
| `polygon(newx, newy, ...)` | `mpatches.Polygon(np.column_stack([newx, newy]), ...)` — matplotlib expects an `(N, 2)` array of vertices; `np.column_stack` zips the two length-N arrays. |
| `col = bg` | `facecolor=bg` |
| `border = TRUE` | `edgecolor=fg` — R's `border=TRUE` resolves to the current foreground color; in Python this must be passed explicitly. |
| Draws on the active device | `ax.add_patch(patch)` — matplotlib requires explicitly adding the patch to the target `Axes`. |

---

### 4.2 `rectangle` — Filled Rectangle as a 4-Vertex Polygon

**Location:** `text.rpart.R`, function `rectangle`, line 74.

**Original R Context:**

```r
# Input types:
#   middlex, middley : numeric scalar — center coordinates in plot space
#   a, b             : numeric scalar — half-widths in x and y directions
#   bg               : character scalar — fill color string
#
# newx, newy are numeric vectors of length 4 (double precision)

rectangle <- function(middlex, middley, a, b) {
    newx <- middlex + c(a,  a, -a, -a)    # numeric vector, length 4
    newy <- middley + c(b, -b, -b,  b)    # numeric vector, length 4
    polygon(newx, newy, border = TRUE, col = bg)
    # Draws a filled rectangle:
    #   vertices (clockwise from top-right):
    #     (middlex+a, middley+b)
    #     (middlex+a, middley-b)
    #     (middlex-a, middley-b)
    #     (middlex-a, middley+b)
    #   interior color = bg
    #   border color   = current foreground
}
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def rectangle(ax, middlex, middley, a, b, bg="white", fg="black"):
    """
    Draw a filled rectangle centered at (middlex, middley) with half-widths
    a (horizontal) and b (vertical) on Axes `ax`.

    Parameters
    ----------
    ax      : matplotlib.axes.Axes  — target axes
    middlex : float                  — x-coordinate of the rectangle center
    middley : float                  — y-coordinate of the rectangle center
    a       : float                  — horizontal half-width
    b       : float                  — vertical half-height
    bg      : str                    — fill color (default "white"), mirrors R's `bg`
    fg      : str                    — border color (default "black"), mirrors R's fg
    """
    newx = middlex + np.array([ a,  a, -a, -a])   # shape (4,) float64
    newy = middley + np.array([ b, -b, -b,  b])   # shape (4,) float64

    vertices = np.column_stack([newx, newy])        # shape (4, 2)
    patch = mpatches.Polygon(
        vertices,
        closed=True,          # auto-close (R polygon always closes)
        facecolor=bg,         # col = bg
        edgecolor=fg,         # border = TRUE -> foreground color
        linewidth=1.0,
    )
    ax.add_patch(patch)

# --- Alternative: using matplotlib.pyplot.fill (closer to R's call style) ---
def rectangle_fill(ax, middlex, middley, a, b, bg="white", fg="black"):
    newx = middlex + np.array([ a,  a, -a, -a])
    newy = middley + np.array([ b, -b, -b,  b])
    # plt.fill / ax.fill accepts separate x and y arrays, mirroring R's polygon(x, y, ...)
    ax.fill(newx, newy, facecolor=bg, edgecolor=fg, linewidth=1.0)
```

**Explanation:**

| R | Python |
|---|--------|
| `c(a, a, -a, -a)` | `np.array([a, a, -a, -a])` — R's `c()` concatenation becomes a NumPy array literal. |
| `middlex + c(...)` | `middlex + np.array([...])` — scalar-broadcast arithmetic, identical semantics. |
| `polygon(newx, newy, border=TRUE, col=bg)` | `ax.fill(newx, newy, facecolor=bg, edgecolor=fg)` or `mpatches.Polygon(vertices, facecolor=bg, edgecolor=fg)` |
| 4 vertices define the full rectangle | Same — `closed=True` / `ax.fill` both auto-close, so no need to repeat the first vertex. |
| `border = TRUE` | `edgecolor=fg` — see note in §4.1; R's `TRUE` is a legacy alias for the foreground pen color. |

**Note on `matplotlib.pyplot.fill` vs `matplotlib.patches.Polygon`:**
`ax.fill(x, y, ...)` is more concise and directly mirrors R's `polygon(x, y, ...)` call signature. `mpatches.Polygon` is preferred when the patch needs to be stored, transformed, or managed as a reusable object. For this rpart rendering context either works; `ax.fill` is recommended for translation fidelity.
