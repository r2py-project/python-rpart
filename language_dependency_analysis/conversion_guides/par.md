# Conversion Guide: `par` (R) to Python (Matplotlib)

## 1. Overview of `par` in R

`par()` is R's unified interface for querying and setting graphical parameters that control the appearance and layout of base R graphics. It is part of R's `graphics` package and applies globally to the active graphics device.

`par()` operates in three distinct modes depending on how it is called:

- **Setter mode** — `par(name = value, ...)`: Sets one or more graphical parameters on the current device and returns a named list of the *previous* values of those parameters. This return value is the canonical mechanism for save-and-restore patterns.
- **Restore mode** — `par(saved_list)`: When passed a named list (typically the return value of a prior `par()` setter call), it restores all parameters in that list to their saved values.
- **Query mode** — `par("name")`: Returns the current value of the named parameter as a scalar or vector, without modifying anything.

The parameters encountered in this CSV are:

| Parameter | Type | Meaning |
|---|---|---|
| `mar` | numeric vector of length 4 | Margin sizes in lines: `c(bottom, left, top, right)` |
| `pty` | character string | Plot type: `"s"` for square, `"m"` for maximal |
| `new` | logical | If `TRUE`, the next high-level plot overlays the current one without erasing |
| `"bg"` | character string | Background color of the plot region (query) |
| `"cxy"` | numeric vector of length 2 | Size of one character in user coordinate units: `c(width, height)` (query) |

---

## 2. Contextual Usage Analysis

Across the four source files, `par` appears in five functionally distinct roles:

**Role 1 — Margin setting with save/restore (`post.rpart.R`, lines 9 and 12–13).**
The function `post.rpart` sets `mar = c(2,2,4,2) + 0.1` to produce a plot with a larger top margin for the title. When writing to a PostScript file (line 9), no previous value is saved because the device is owned by the function and will be closed on exit. When rendering interactively (line 12), the previous `mar` is saved in `oldpar` and restored via `on.exit(par(oldpar))` to leave the caller's graphics state unchanged.

**Role 2 — Square plot aspect ratio with save/restore (`roc.rpart.R`, lines 59–60).**
`par(pty = "s")` forces the plot region to be square (equal x and y axis scales), which is standard for ROC curves. The previous `pty` is saved and restored with `on.exit`.

**Role 3 — Overlay plot on existing axes (`rsq.rpart.R`, line 20).**
`par(new = TRUE)` instructs R to draw the next high-level plot call (`plot(...)`) on top of the existing axes without clearing the device or redrawing axis labels.

**Role 4 — Query background color (`text.rpart.R`, line 8).**
`par("bg")` is called in the function signature default argument `bg = par("bg")`, making the default background color for polygon fills match the device's current background. This is a pure read, returning a character string such as `"white"`.

**Role 5 — Query character dimensions in user coordinates (`text.rpart.R`, line 19).**
`par("cxy")` returns a two-element numeric vector `c(char_width, char_height)` measured in the current plot's user coordinate system. These values are used to offset text annotations relative to tree nodes by a fraction of one character height.

---

## 3. Python Conversion Strategy

Python's equivalent of R's base graphics system is **Matplotlib**. The chosen strategy is:

- All graphical state manipulation is done through the active `matplotlib.axes.Axes` object or `matplotlib.figure.Figure`, rather than through a global device state. This is the idiomatic Matplotlib approach.
- The save/restore pattern (`oldpar <- par(...); on.exit(par(oldpar))`) is replaced by saving the relevant Matplotlib property before modification and restoring it afterward, typically using a `try/finally` block.
- `par(new = TRUE)` has a direct analogue: `plt.gca()` returns the current axes without clearing it, so the next `ax.plot(...)` call naturally overlays. When axes sharing is needed explicitly, `ax.twinx()` or drawing on the same `Axes` object is appropriate.
- `par("bg")` and `par("cxy")` are pure queries. Their Matplotlib equivalents are `ax.get_facecolor()` and a computation derived from the renderer's `points_to_pixels` combined with `ax.transData`, respectively.
- **numpy** is not the primary library here because `par` is a graphics-state function, not a numerical computation. Matplotlib is the correct primary equivalent.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Setting Margins (Setter-Only, No Restore)

**Locations:** `post.rpart.R`, function `post.rpart`, line 9 (inside the PostScript branch).

**Original R Context.**

```r
# Called when writing to a PostScript file; the device will be closed on exit
# so there is no need to save and restore the previous margin.
postscript(file = filename, horizontal = horizontal)
par(mar = c(2,2,4,2) + 0.1)   # mar: numeric vector length 4 (bottom, left, top, right)
on.exit(dev.off())
```

`mar` values are specified in units of text line heights. `c(2,2,4,2) + 0.1` produces `c(2.1, 2.1, 4.1, 2.1)`.

**Python Equivalent.**

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()

# R's mar = c(bottom, left, top, right) in lines.
# Matplotlib's subplots_adjust uses figure-fraction units; for tight control
# per-axes, use ax.set_position() or Figure.subplots_adjust().
# A common translation is to set padding via tight_layout with pad, or
# directly via rcParams for line-to-inch conversion.

# Simplest direct approach: use Figure.subplots_adjust or rcParams
# mar c(2.1, 2.1, 4.1, 2.1) — larger top margin for a title
LINE_HEIGHT_INCHES = 0.2  # approximate; 1 line ~ 0.2 inches at default font size
fig.subplots_adjust(
    bottom=2.1 * LINE_HEIGHT_INCHES / fig.get_figheight(),
    left=2.1 * LINE_HEIGHT_INCHES / fig.get_figwidth(),
    top=1 - 4.1 * LINE_HEIGHT_INCHES / fig.get_figheight(),
    right=1 - 2.1 * LINE_HEIGHT_INCHES / fig.get_figwidth(),
)

# ... draw the tree plot ...
fig.savefig("output.pdf")
plt.close(fig)
```

**Explanation.** R's `mar` is measured in margin lines (each ~1 text line tall). Matplotlib has no direct line-unit margin parameter; the closest equivalent is `Figure.subplots_adjust`, which takes fractions of the figure dimensions. When targeting a file output (PDF/PostScript), `plt.close(fig)` replaces `dev.off()` — no restore is needed because the figure is discarded afterward.

---

### 4.2 Setting Margins With Save/Restore

**Locations:** `post.rpart.R`, function `post.rpart`, lines 12–13 (interactive branch).

**Original R Context.**

```r
# Interactive device branch: save current mar, change it, restore on exit.
# oldpar is a named list; par(oldpar) restores all saved parameters.
oldpar <- par(mar = c(2,2,4,2) + 0.1)   # returns list(mar = <previous_value>)
on.exit(invisible(par(oldpar)))          # restore previous mar when function exits
```

**Python Equivalent.**

```python
import matplotlib.pyplot as plt

fig = plt.gcf()

# Save the current subplot geometry before modification
original_subplotpars = {
    "bottom": fig.subplotpars.bottom,
    "left":   fig.subplotpars.left,
    "top":    fig.subplotpars.top,
    "right":  fig.subplotpars.right,
}

LINE_HEIGHT_INCHES = 0.2
try:
    fig.subplots_adjust(
        bottom=2.1 * LINE_HEIGHT_INCHES / fig.get_figheight(),
        left=2.1 * LINE_HEIGHT_INCHES / fig.get_figwidth(),
        top=1 - 4.1 * LINE_HEIGHT_INCHES / fig.get_figheight(),
        right=1 - 2.1 * LINE_HEIGHT_INCHES / fig.get_figwidth(),
    )
    # ... draw the tree plot ...
finally:
    # Restore previous layout (equivalent to par(oldpar))
    fig.subplots_adjust(**original_subplotpars)
```

**Explanation.** The `on.exit(par(oldpar))` idiom is a deferred restore: it runs when the R function exits regardless of whether it exits normally or via an error. In Python the equivalent is `try/finally`. The current subplot parameters are saved into a plain dict before modification and unpacked back into `subplots_adjust` in the `finally` block.

---

### 4.3 Forcing a Square Plot Aspect Ratio With Save/Restore

**Locations:** `roc.rpart.R`, function `roc.rpart`, lines 59–60.

**Original R Context.**

```r
# par(pty = "s") forces the plot region to be square.
# The return value is a list: list(pty = <previous_value>)
o.par <- par(pty = "s")   # pty: character scalar, "s" = square, "m" = maximal
on.exit(par(o.par))       # restore previous pty on exit
plot(1 - specificity, sensitivity, type = "o", xlim = c(0,1), ylim = c(0,1), ...)
```

**Python Equivalent.**

```python
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots()

# Save current aspect ratio
original_aspect = ax.get_aspect()

try:
    # "equal" makes one unit in x equal one unit in y, producing a square plot
    # when xlim and ylim span the same range. This is the equivalent of pty="s".
    ax.set_aspect("equal")

    # ROC curve: axes both span [0,1], so "equal" aspect + equal data ranges
    # results in a square plot region.
    ax.plot(1 - specificity, sensitivity, marker="o", linestyle="-")
    ax.set_xlabel("1 - Specificity")
    ax.set_ylabel("Sensitivity")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
finally:
    # Restore previous aspect ratio
    ax.set_aspect(original_aspect)
```

**Explanation.** R's `pty = "s"` constrains the physical plot region to be square regardless of the figure size. Matplotlib's `ax.set_aspect("equal")` achieves the same visual result when `xlim` and `ylim` span the same range (both `[0,1]` in a ROC curve). The prior aspect ratio is read with `ax.get_aspect()` and restored in a `finally` block, mirroring the `on.exit(par(o.par))` pattern.

---

### 4.4 Overlaying a Second Plot on Existing Axes

**Locations:** `rsq.rpart.R`, function `rsq.rpart`, line 20.

**Original R Context.**

```r
# First plot draws apparent R-squared
plot(nsplit, 1 - rel.error, xlab = "Number of Splits", ylab = "R-square",
     ylim = c(0, 1), type = "o")

# par(new = TRUE) suppresses clearing the device before the next high-level plot
par(new = TRUE)

# Second plot overlays cross-validated R-squared on the same axes
plot(nsplit, 1 - xerror, type = "o", ylim = c(0, 1), lty = 2,
     xlab = " ", ylab = " ")

legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)
```

**Python Equivalent.**

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()

# First series — Apparent R-squared (solid line, equivalent to lty=1)
ax.plot(nsplit, 1 - rel_error, marker="o", linestyle="-", label="Apparent")

# par(new = TRUE) is not needed in Matplotlib: calling ax.plot() again on the
# same Axes object automatically overlays without clearing the plot.
# Second series — Cross-validated R-squared (dashed line, equivalent to lty=2)
ax.plot(nsplit, 1 - xerror, marker="o", linestyle="--", label="X Relative")

ax.set_xlabel("Number of Splits")
ax.set_ylabel("R-square")
ax.set_ylim(0, 1)
ax.legend(loc="upper left")

plt.show()
```

**Explanation.** `par(new = TRUE)` is an R-specific workaround: R's `plot()` clears the device by default, so `par(new = TRUE)` suppresses that clearing to allow the second `plot()` call to draw over the first. In Matplotlib, calling `ax.plot()` multiple times on the same `Axes` instance always overlays — there is no clearing between calls, and no special flag is required. `par(new = TRUE)` therefore has no Python equivalent and should simply be omitted.

---

### 4.5 Querying the Background Color

**Locations:** `text.rpart.R`, function `text.rpart`, line 8 (function default argument).

**Original R Context.**

```r
# par("bg") queries the current background color as a character string (e.g. "white").
# It is used here as a default argument so the polygon fill matches the device background.
text.rpart <- function(x, ..., bg = par("bg"), ...) {
    # bg is a character scalar: a color name or hex code
    ...
    polygon(newx, newy, border = TRUE, col = bg)
}
```

**Python Equivalent.**

```python
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

def text_rpart(x, bg=None, **kwargs):
    ax = plt.gca()

    # Resolve default: match the axes face color if bg not provided
    if bg is None:
        # ax.get_facecolor() returns an RGBA tuple; convert to hex for consistency
        rgba = ax.get_facecolor()
        bg = mcolors.to_hex(rgba)

    # bg is now a hex color string (e.g. "#ffffff"), equivalent to R's "white"
    # Use it as the facecolor when drawing polygons (ellipses, rectangles on nodes)
    from matplotlib.patches import Polygon
    patch = Polygon(xy_coords, closed=True, edgecolor="black", facecolor=bg)
    ax.add_patch(patch)
```

**Explanation.** R's `par("bg")` returns the device background color as a named color string. Matplotlib separates figure background (`fig.get_facecolor()`) from axes background (`ax.get_facecolor()`). For drawn polygons that should blend into the plot area (as in the fancy node boxes in `text.rpart`), `ax.get_facecolor()` is the correct equivalent. The RGBA tuple is converted to a hex string with `mcolors.to_hex()` to match the string type that R returns.

---

### 4.6 Querying Character Dimensions in User Coordinates

**Locations:** `text.rpart.R`, function `text.rpart`, line 19.

**Original R Context.**

```r
# par("cxy") returns a numeric vector of length 2:
#   c(char_width_in_user_coords, char_height_in_user_coords)
# These are used to offset text labels relative to node positions.
cxy <- par("cxy")   # e.g. c(0.04, 0.05) depending on current xlim/ylim

# Usage — offset label above a node by half a character height:
text(xy$x, xy$y + 0.5 * cxy[2], labels, ...)

# Reverse when text is rotated 90 degrees:
if (!is.null(srt) && srt == 90) cxy <- rev(cxy)
```

**Python Equivalent.**

```python
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms

def get_cxy(ax, fig):
    """
    Compute character width and height in Axes data (user) coordinates.
    Equivalent to R's par("cxy").

    Returns a tuple (char_width, char_height) in the same units as ax.get_xlim()
    and ax.get_ylim().
    """
    # Get the renderer (needed for font metric calculations)
    fig.canvas.draw()  # ensure layout is up to date
    renderer = fig.canvas.get_renderer()

    # Font size in points
    fontsize_pt = plt.rcParams["font.size"]  # default 10 pt

    # 1 point = 1/72 inch; convert points to display pixels
    dpi = fig.get_dpi()
    char_height_px = fontsize_pt * dpi / 72.0
    # Approximate character width as ~60% of height (standard for proportional fonts)
    char_width_px = char_height_px * 0.6

    # Convert from display pixels to data (user) coordinates
    # using the inverse of the Axes data transform
    inv_transform = ax.transData.inverted()
    # Reference point at the origin in display space
    origin_disp = ax.transData.transform((0, 0))
    # Shift by character dimensions in display space and invert
    x_shift_disp = origin_disp + [char_width_px, 0]
    y_shift_disp = origin_disp + [0, char_height_px]

    char_width_data  = inv_transform.transform(x_shift_disp)[0] - inv_transform.transform(origin_disp)[0]
    char_height_data = inv_transform.transform(y_shift_disp)[1] - inv_transform.transform(origin_disp)[1]

    return char_width_data, char_height_data


# Usage — offset a label above a node by half a character height:
# (mirroring: text(xy$x, xy$y + 0.5 * cxy[2], ...))
cxy = get_cxy(ax, fig)
ax.text(node_x, node_y + 0.5 * cxy[1], label, ha="center", va="bottom")

# When text is rotated 90 degrees, swap width and height (mirroring rev(cxy)):
srt = kwargs.get("srt", 0)
if srt == 90:
    cxy = (cxy[1], cxy[0])
```

**Explanation.** R's `par("cxy")` is computed automatically by the graphics device from the current font size, device resolution, and data coordinate ranges. There is no single Matplotlib property that exposes this directly. The equivalent must be derived by converting a font-sized pixel offset through the inverse of the Axes data transform (`ax.transData.inverted()`). `fig.canvas.draw()` must be called first to ensure the layout has been committed and the transform is accurate. The resulting `(char_width_data, char_height_data)` tuple is used identically to R's `cxy`: to offset annotation positions by a fraction of a character dimension in the same coordinate space as the plotted data.
