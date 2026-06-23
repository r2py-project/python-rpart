# Conversion Guide: `plot` in R

## 1. Overview of `plot` in R

`plot` is R's primary generic function for producing graphics. In base R it dispatches on the class of its first argument: when given two numeric vectors `x` and `y` it draws a scatter/line chart; when given an S3 object it may call a registered `plot.<class>` method. Within the rpart package, every call passes two plain numeric vectors (or two-element range vectors) as `x` and `y`, so the dispatch always resolves to the low-level `plot.default`.

Key parameters used across the CSV:

| R parameter | Role |
|---|---|
| `x`, `y` | Numeric vectors of coordinates |
| `type` | `"n"` — set up axes only, draw nothing; `"o"` — points overplotted with lines |
| `axes` | `FALSE` suppresses axis drawing |
| `xlab`, `ylab` | Axis labels (empty string `""` suppresses the label) |
| `xlim`, `ylim` | Explicit axis limits as length-2 numeric vectors |
| `lty` | Line type (integer: 1 = solid, 2 = dashed) |
| `...` | Passed through to the underlying graphics device |

Return value: `NULL` (invisibly). The function is called purely for its side-effect of drawing into the active graphics device.

---

## 2. Contextual Usage Analysis

Across all nine call sites, `plot` is used in three distinct functional roles:

**Role A — invisible canvas setup (`type = "n"`).**
Two functions use `plot` solely to define the coordinate space before other drawing primitives (text, lines) are layered on top. No data marks are drawn by `plot` itself.
- `meanvar.rpart` (line 13): sets up axes for numeric mean vs. deviance scatter.
- `plot.rpart` (line 21): sets up a blank axes-free canvas for the tree diagram drawn by `rpart.branch` / `lines`.

**Role B — `do.call` dispatch.**
`plotcp` (line 20) does not call `plot` directly; it passes `plot` as a function object to `do.call`, which then invokes it with a dynamically assembled argument list. The effective call is identical to `plot(ns, xerror, axes=FALSE, xlab="cp", ylab="X-val Relative Error", type="o", ylim=..., ...)`.

**Role C — data line/point plots (`type = "o"`).**
Five calls draw actual data with overplotted points and lines:
- `post.rpart` (line 16): delegates to `plot.rpart` (see Role A).
- `roc.rpart` (lines 62, 66): ROC curves; `1 - specificity` or `specificity` on x, `sensitivity` on y, with fixed `[0,1]` axis limits.
- `rsq.rpart` (lines 18, 21, 26): three separate plots for R-squared (apparent vs. cross-validated) and cross-validated relative error, all sharing the same `nsplit` x-axis.

All data types involved are plain 1-D numeric vectors derived from matrices or data-frame columns — no special R types. `rsq.rpart` also uses `par(new = TRUE)` before the second `plot` call to overlay two curves in the same device region.

---

## 3. Python Conversion Strategy

The canonical Python equivalent of R's `plot` (in the contexts seen here) is **`matplotlib.pyplot`** (`matplotlib.axes.Axes` methods for object-oriented usage). Matplotlib is chosen because:

- It directly replicates R's plot region / axis label / axis limit model.
- `ax.plot(x, y, ...)` maps cleanly to R's `plot(x, y, type="o", ...)`.
- An invisible canvas (`type="n"`) is reproduced by calling `ax.set_xlim` / `ax.set_ylim` without any data plotting call.
- `do.call(plot, args)` maps naturally to `ax.plot(**kwargs)` or a helper that unpacks the dict.
- Axis suppression (`axes=FALSE`) maps to `ax.set_axis_off()` or `ax.tick_params(...)`.
- Overlaying two plots (`par(new=TRUE)` + second `plot`) maps to plotting two series on the same `Axes` object.

`numpy` is used as a supporting library for array arithmetic (e.g., computing `1 - rel_error`).

---

## 4. Step-by-Step Conversion Examples

### 4.1 Canvas Setup — `meanvar.rpart`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/meanvar.rpart.R`, function `meanvar.rpart`, line 13.

**Original R Context.**

```r
# x: numeric vector — leaf mean response values (frame$yval)
# y: numeric vector — per-leaf deviance/n (frame$dev / frame$n)
# label: character vector of node row-names
plot(x, y, xlab = xlab, ylab = ylab, type = "n", ...)
text(x, y, label)
```

`type = "n"` tells R to scale and draw axes but to place no graphical marks for the data points. Text labels are then placed at every (x, y) position by `text()`.

**Python Equivalent.**

```python
import matplotlib.pyplot as plt

def meanvar_rpart(frame, xlab="ave(y)", ylab="ave(deviance)"):
    leaves = frame[frame["var"] == "<leaf>"]
    x = leaves["yval"].to_numpy()
    y = (leaves["dev"] / leaves["n"]).to_numpy()
    label = leaves.index.astype(str).tolist()

    fig, ax = plt.subplots()
    # type="n": set axis range but draw nothing
    ax.set_xlim(x.min(), x.max())
    ax.set_ylim(y.min(), y.max())
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    for xi, yi, lbl in zip(x, y, label):
        ax.text(xi, yi, lbl, ha="center", va="center")
    return {"x": x, "y": y, "label": label}
```

**Explanation.**
R's `type = "n"` has no single matplotlib parameter; the equivalent is to call `ax.set_xlim` / `ax.set_ylim` without issuing any `ax.plot` call. R's `text(x, y, label)` maps to a loop over `ax.text`.

---

### 4.2 Axes-Free Canvas — `plot.rpart`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/plot.rpart.R`, function `plot.rpart`, line 21.

**Original R Context.**

```r
# temp1: length-2 numeric vector — x-axis range (with margin)
# temp2: length-2 numeric vector — y-axis range (with margin)
plot(temp1, temp2, type = "n", axes = FALSE, xlab = "", ylab = "", ...)
# Followed by: lines(c(temp$x), c(temp$y), ...)
```

Both vectors are two-element ranges, not data series. The call exists only to set coordinate limits for the tree branch lines drawn later.

**Python Equivalent.**

```python
import matplotlib.pyplot as plt

def setup_rpart_canvas(temp1, temp2):
    """
    temp1: array-like of length 2, x-axis [min, max]
    temp2: array-like of length 2, y-axis [min, max]
    Returns (fig, ax) for downstream drawing.
    """
    fig, ax = plt.subplots()
    ax.set_xlim(temp1[0], temp1[1])
    ax.set_ylim(temp2[0], temp2[1])
    ax.set_axis_off()          # axes=FALSE, xlab="", ylab=""
    return fig, ax
```

**Explanation.**
`axes = FALSE` in R disables both tick marks and axis lines; `ax.set_axis_off()` is the closest matplotlib equivalent (it removes the entire frame; use `ax.tick_params(bottom=False, left=False, labelbottom=False, labelleft=False)` if only ticks should be removed while keeping the frame visible).

---

### 4.3 `do.call` Dispatch — `plotcp`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/plotcp.R`, function `plotcp`, line 20.

**Original R Context.**

```r
# ns:     integer sequence 1..nrow(p.rpart)
# xerror: numeric vector — cross-validation error per cp entry
# dots:   named list of extra arguments (may contain ylim, etc.)
do.call(plot, c(list(ns, xerror, axes = FALSE, xlab = "cp",
                     ylab = "X-val Relative Error", type = "o"), dots))
box()
axis(2, ...)
segments(ns, xerror - xstd, ns, xerror + xstd)
axis(1L, at = ns, labels = as.character(signif(cp, 2L)), ...)
```

`do.call(plot, args)` is R's way to invoke `plot` with a programmatically assembled argument list. It is equivalent to calling `plot(ns, xerror, axes=FALSE, xlab="cp", ylab="X-val Relative Error", type="o", <dots>)`. The subsequent calls add box borders, custom axis tick labels, and vertical error-bar segments.

**Python Equivalent.**

```python
import numpy as np
import matplotlib.pyplot as plt

def plotcp(x_rpart, minline=True, lty="dotted", col="black"):
    p_rpart = x_rpart["cptable"]          # 2-D numpy array, shape (n, >=5)
    xstd    = p_rpart[:, 4]
    xerror  = p_rpart[:, 3]
    nsplit  = p_rpart[:, 1]
    cp0     = p_rpart[:, 0]
    ns      = np.arange(1, len(nsplit) + 1)   # R's seq_along is 1-based
    cp      = np.sqrt(cp0 * np.concatenate([[np.inf], cp0[:-1]]))

    ylim = (
        (xerror - xstd).min() - 0.1,
        (xerror + xstd).max() + 0.1,
    )

    fig, ax = plt.subplots()
    # do.call(plot, ...) with type="o", axes=FALSE
    ax.plot(ns, xerror, marker="o", linestyle="-", color=col)
    ax.set_xlim(ns[0] - 0.5, ns[-1] + 0.5)
    ax.set_ylim(*ylim)
    ax.set_xlabel("cp")
    ax.set_ylabel("X-val Relative Error")

    # box() — ensure frame is visible (default in matplotlib)
    for spine in ax.spines.values():
        spine.set_visible(True)

    # axis(1L, at=ns, labels=signif(cp, 2))
    ax.set_xticks(ns)
    ax.set_xticklabels([f"{v:.2g}" for v in cp])

    # segments(ns, xerror - xstd, ns, xerror + xstd)
    ax.errorbar(ns, xerror, yerr=xstd, fmt="none", ecolor=col, capsize=3)

    # optional secondary x-axis for tree size (upper="size" default)
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(ns)
    ax2.set_xticklabels([str(int(s) + 1) for s in nsplit])
    ax2.set_xlabel("size of tree")

    # minline: horizontal dashed line at min(xerror + xstd)
    if minline:
        minpos = np.argmin(xerror)
        ax.axhline(y=(xerror + xstd)[minpos], linestyle=lty, color=col)

    return fig, ax
```

**Explanation.**
`do.call(plot, c(list(...), dots))` is unpacked into a direct `ax.plot` call with the equivalent keyword arguments. R's 1-based `seq_along` becomes `np.arange(1, n+1)`. `box()` is a no-op in matplotlib (frame is drawn by default). Error bars replace `segments`. `axis(1L, at=..., labels=...)` maps to `ax.set_xticks` + `ax.set_xticklabels`. `axis(3L, ...)` + `mtext(...)` map to a twin x-axis via `ax.twiny()`.

---

### 4.4 Delegation Through a Class Method — `post.rpart`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/post.rpart.R`, function `post.rpart`, line 16.

**Original R Context.**

```r
# tree: an "rpart" object
plot(tree, uniform = TRUE, branch = 0.2, compress = TRUE, margin = 0.1)
text(tree, all = TRUE, use.n = use.n, fancy = TRUE, ...)
```

Because `tree` is an `rpart` object, R's generic dispatch calls `plot.rpart(tree, ...)`, which is the canvas-setup function described in Section 4.2. This call is not a scatter plot; it delegates entirely to the rpart tree-layout logic.

**Python Equivalent.**

```python
# In Python this call should be replaced with an invocation of the
# already-converted plot_rpart() function (the Python equivalent of plot.rpart).

def post_rpart(tree, title=None, digits=None, pretty=True, use_n=True,
               horizontal=True, filename=""):
    fig, ax = plot_rpart(tree, uniform=True, branch=0.2,
                          compress=True, margin=0.1)
    text_rpart(ax, tree, all_nodes=True, use_n=use_n,
               fancy=True, digits=digits, pretty=pretty)

    if title is None:
        response_var = tree.terms_variables[1]
        ax.set_title(f"Endpoint = {response_var}", fontsize="small")
    elif title:
        ax.set_title(title, fontsize="small")

    if filename:
        fig.savefig(filename)
    return fig, ax
```

**Explanation.**
R's S3 dispatch (`plot(tree, ...)` calling `plot.rpart`) becomes an explicit call to the Python `plot_rpart` function. PostScript output (`postscript(...)`) is replaced by `fig.savefig(filename)`, which automatically selects the format from the file extension.

---

### 4.5 ROC Curve Plots — `roc.rpart`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/roc.rpart.R`, function `roc.rpart`, lines 62 and 66.

**Original R Context.**

```r
# sensitivity: numeric column vector of length cutoff.n
# specificity: numeric column vector of length cutoff.n
# Branch 1 (x.orient == 1L):
plot(1 - specificity, sensitivity, type = "o",
     xlim = c(0, 1), ylim = c(0, 1),
     ylab = "Sensitivity", xlab = "1-Specificity")

# Branch 2 (x.orient == 2L):
plot(specificity, sensitivity, type = "o",
     xlim = c(0, 1), ylim = c(0, 1),
     ylab = "Sensitivity", xlab = "Specificity")
```

Both are standard ROC curves. The only difference is whether the x-axis shows `1 - specificity` (traditional orientation) or `specificity` (inverted). `type = "o"` draws both the lines and the data points overplotted on each other.

**Python Equivalent.**

```python
import numpy as np
import matplotlib.pyplot as plt

def roc_rpart(object_rpart, plot_ok=True, x_orient=1):
    # ... (computation of sensitivity, specificity omitted for brevity) ...

    if plot_ok:
        fig, ax = plt.subplots(figsize=(5, 5))   # par(pty="s") -> square
        if x_orient == 1:
            x_vals = 1 - specificity.ravel()
            xlabel = "1-Specificity"
        else:
            x_vals = specificity.ravel()
            xlabel = "Specificity"

        # type="o": lines + overplotted points
        ax.plot(x_vals, sensitivity.ravel(),
                marker="o", linestyle="-")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Sensitivity")
        ax.set_aspect("equal")
        plt.show()
```

**Explanation.**
`type = "o"` maps to `marker="o", linestyle="-"` in matplotlib. `xlim = c(0, 1)` maps to `ax.set_xlim(0, 1)`. R's `par(pty = "s")` enforces a square plot region; `ax.set_aspect("equal")` is the matplotlib equivalent. The two R branches (lines 62 and 66) collapse into a single Python function with an `if x_orient == 1` guard. The matrix column vectors `sensitivity` and `specificity` are flattened with `.ravel()` before plotting.

---

### 4.6 Multi-Panel R-squared Plots — `rsq.rpart`

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/rsq.rpart.R`, function `rsq.rpart`, lines 18, 21, and 26.

**Original R Context.**

```r
# nsplit:    numeric vector — number of splits per cp row
# rel.error: numeric vector — apparent relative error
# xerror:    numeric vector — cross-validated relative error
# xstd:      numeric vector — std dev of cross-validated error

# Panel 1: R-squared (apparent)
plot(nsplit, 1 - rel.error,
     xlab = "Number of Splits", ylab = "R-square",
     ylim = c(0, 1), type = "o")

# Panel 2: R-squared (cross-validated), overlaid on Panel 1
par(new = TRUE)
plot(nsplit, 1 - xerror,
     type = "o", ylim = c(0, 1), lty = 2, xlab = " ", ylab = " ")
legend(0, 1, c("Apparent", "X Relative"), lty = 1:2)

# Panel 3: Cross-validated relative error with error bars
plot(nsplit, xerror,
     xlab = "Number of Splits", ylab = "X Relative Error",
     ylim = ylim, type = "o")
segments(nsplit, xerror - xstd, nsplit, xerror + xstd)
```

Lines 18 and 21 together form one compound panel (two overlaid series on the same axes). Line 26 is a separate second panel. R uses `par(new = TRUE)` before the second `plot` call to prevent the second call from clearing the device — the second `plot` then draws over the first.

**Python Equivalent.**

```python
import numpy as np
import matplotlib.pyplot as plt

def rsq_rpart(x_rpart):
    p_rpart = x_rpart["cptable"]   # numpy array, shape (n, >=5)
    xstd      = p_rpart[:, 4]
    xerror    = p_rpart[:, 3]
    rel_error = p_rpart[:, 2]
    nsplit    = p_rpart[:, 1]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))

    # --- Panel 1: R-squared (lines 18 + 21 combined via par(new=TRUE)) ---
    # Apparent R-squared (line 18, lty=1 = solid)
    ax1.plot(nsplit, 1 - rel_error,
             marker="o", linestyle="-", label="Apparent")
    # Cross-validated R-squared (line 21, lty=2 = dashed)
    ax1.plot(nsplit, 1 - xerror,
             marker="o", linestyle="--", label="X Relative")
    ax1.set_xlim(nsplit.min(), nsplit.max())
    ax1.set_ylim(0, 1)
    ax1.set_xlabel("Number of Splits")
    ax1.set_ylabel("R-square")
    ax1.legend(loc="upper left")

    # --- Panel 2: Cross-validated relative error with error bars (line 26) ---
    ylim_lo = (xerror - xstd).min() - 0.1
    ylim_hi = (xerror + xstd).max() + 0.1
    ax2.plot(nsplit, xerror, marker="o", linestyle="-")
    # segments() -> vertical error bars
    ax2.errorbar(nsplit, xerror, yerr=xstd,
                 fmt="none", ecolor="black", capsize=3)
    ax2.set_ylim(ylim_lo, ylim_hi)
    ax2.set_xlabel("Number of Splits")
    ax2.set_ylabel("X Relative Error")

    plt.tight_layout()
    return fig
```

**Explanation.**
R's `par(new = TRUE)` prevents the second `plot` from wiping the device; in Python the equivalent is simply calling `ax1.plot(...)` a second time on the same `Axes` — no device reset occurs between calls. R's `lty = 2` (dashed) maps to `linestyle="--"`. `segments(nsplit, xerror - xstd, nsplit, xerror + xstd)` draws vertical error bars and maps to `ax.errorbar(..., yerr=xstd, fmt="none")`. The three R `plot` calls that logically form two panels are reorganized into two `Axes` objects on a single `Figure`.
