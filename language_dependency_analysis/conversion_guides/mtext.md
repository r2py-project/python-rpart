# Conversion Guide: `mtext` (R to Python)

---

## 1. Overview of `mtext` in R

`mtext()` is a base R graphics function from the `graphics` package that writes text into one of the four margins of the current plot region (or the outer device margins). It is called exclusively for its side effect of rendering text on the current graphical device; it returns `NULL` invisibly.

**Function signature:**

```r
mtext(text, side = 3, line = 0, outer = FALSE, at = NA,
      adj = NA, padj = NA, cex = NA, col = NA, font = NA, ...)
```

**Key parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | character or expression vector | required | The string(s) to render; non-character objects are coerced via `as.graphicsAnnot()` |
| `side` | integer (1–4) | `3` | Margin side: 1 = bottom, 2 = left, 3 = top, 4 = right |
| `line` | numeric | `0` | Margin line on which to place the text, counting outward from 0 (the plot border) |
| `outer` | logical | `FALSE` | If `TRUE`, write in the outer device margin rather than the figure margin |
| `at` | numeric | `NA` | Horizontal (or vertical) position in user coordinates; `NA` uses `adj` for centering |
| `adj` | numeric | `NA` | Alignment along the reading direction: 0 = left/bottom, 1 = right/top; default follows `par("las")` |
| `padj` | numeric | `NA` | Alignment perpendicular to reading direction; default follows `par("las")` |
| `cex` | numeric | `NA` | Character expansion factor; `NA` inherits `par("cex")` |
| `col` | color | `NA` | Text color; `NA` inherits `par("col")` |
| `font` | integer | `NA` | Font face; `NA` inherits `par("font")` |
| `...` | — | — | Additional graphical parameters forwarded to `par()` (e.g., `family`, `las`, `xpd`) |

The `line` parameter controls how far from the plot boundary the text sits. Line 0 is immediately adjacent to the plot frame; higher values push the text further into the margin. This is how `mtext` is distinguished from `title()` — it offers fine-grained control over the exact margin line, making it suitable for secondary axis labels that must clear the tick-mark area.

---

## 2. Contextual Usage Analysis

Both `mtext` calls appear inside a single function, `plotcp`, defined in `/groups/jli9/Yufei/python-rpart/rpart/R/plotcp.R`. `plotcp` draws a diagnostic cross-validation error plot for an `rpart` model. Both calls are used to label a top secondary axis (side 3) that is drawn immediately before each `mtext` call by a corresponding `axis(3L, ...)` statement.

The two occurrences are inside mutually exclusive branches of a `switch` on the `upper` argument (line 26):

| Line | `text` argument | `side` | `line` | Purpose |
|------|-----------------|--------|--------|---------|
| 29 | `"size of tree"` | `3` | `3` | Label the top axis when `upper = "size"` |
| 33 | `"number of splits"` | `3` | `3` | Label the top axis when `upper = "splits"` |

Recurring pattern observations:

- **Same side and line in every call.** `side = 3` and `line = 3` are identical across both occurrences. `line = 3` is chosen to clear the tick marks and tick labels that `axis(3L, ...)` renders in lines 0–2.
- **Scalar string input.** `text` is always a single string literal, not a character vector.
- **No positioning arguments.** Neither `at`, `adj`, nor `padj` is supplied, so R centers the label automatically at the midpoint of the top axis.
- **No style overrides.** No `cex`, `col`, or `font` arguments are passed, so all styling inherits from the active `par()` settings.
- **Structural role.** These calls act as the axis title for the secondary top x-axis. They are the equivalent of what `xlab` / `ylab` provide for the primary axes.

---

## 3. Python Conversion Strategy

The direct Python equivalent is **`matplotlib`**. In matplotlib, a secondary top x-axis is created with `ax.twiny()`, which returns a new `Axes` object (`ax_top`) that shares the same y-scale but carries its own independent top x-axis. On that twin axis, the label that `mtext(text, side=3, line=3)` renders is most naturally expressed as `ax_top.set_xlabel(text, labelpad=...)`.

The `line` parameter in R specifies a margin line offset in units of `par("mex")` times the character height. In matplotlib, the equivalent concept is `labelpad`, which shifts the label away from the tick labels by a number of points. `line = 3` in R typically corresponds to a `labelpad` of approximately 10–14 points, depending on the tick label font size. A value of `labelpad=12` is a reliable default when the tick labels are rendered at matplotlib's default font size.

`matplotlib` is the correct library here because:

- All surrounding code in the Python conversion of `plotcp` already targets matplotlib (via `ax.plot`, `ax.twiny`, `ax.set_xticks`, `ax.set_xticklabels`, etc.).
- There is no vectorization or numerical computation involved; both `text` arguments are plain Python strings.
- `numpy` and `scipy` are irrelevant for this function — `mtext` is a pure rendering call.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Top Axis Label — "size of tree" (Line 29)

**Locations:** `plotcp.R`, function `plotcp`, line 29 (active when `upper = "size"`).

**Original R context:**

```r
# Called immediately after axis(3L, at=ns, labels=as.character(nsplit + 1), ...)
# text  : scalar character string
# side  : 3 — the top margin
# line  : 3 — placed 3 margin lines outward from the plot border, clearing tick labels
mtext("size of tree", side = 3, line = 3)
```

- `text`: `character` scalar `"size of tree"`.
- `side`: integer scalar `3` — top margin.
- `line`: integer scalar `3` — third margin line from the plot border.
- Return value: `NULL` (invisibly); the function is called solely for its rendering side effect.

**Python equivalent:**

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
# ... (main plot, bottom axis, and twiny top axis already configured) ...

# ax_top was created earlier by ax.twiny() for the top-axis tick marks.
# R's mtext("size of tree", side=3, line=3)
ax_top.set_xlabel("size of tree", labelpad=12)
```

**Explanation:** `ax_top.set_xlabel()` places a label on the top x-axis of the twin axes object, which corresponds to R's `side = 3`. The `labelpad=12` argument offsets the label outward from the tick labels, approximating R's `line = 3`. Because R's `line` units are character-height multiples and matplotlib's `labelpad` is in points, a direct numerical mapping is not possible; `labelpad=12` is a visually equivalent approximation at typical font sizes. No centering argument is needed because matplotlib centers the axis label by default, matching R's behavior when `at` and `adj` are left at their `NA` defaults.

---

### 4.2 Top Axis Label — "number of splits" (Line 33)

**Locations:** `plotcp.R`, function `plotcp`, line 33 (active when `upper = "splits"`).

**Original R context:**

```r
# Called immediately after axis(3L, at=ns, labels=as.character(nsplit), ...)
# text  : scalar character string
# side  : 3 — the top margin
# line  : 3 — placed 3 margin lines outward from the plot border, clearing tick labels
mtext("number of splits", side = 3, line = 3)
```

- `text`: `character` scalar `"number of splits"`.
- `side`: integer scalar `3` — top margin.
- `line`: integer scalar `3` — third margin line from the plot border.
- Return value: `NULL` (invisibly); the function is called solely for its rendering side effect.

**Python equivalent:**

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
# ... (main plot, bottom axis, and twiny top axis already configured) ...

# ax_top was created earlier by ax.twiny() for the top-axis tick marks.
# R's mtext("number of splits", side=3, line=3)
ax_top.set_xlabel("number of splits", labelpad=12)
```

**Explanation:** This call is structurally identical to section 4.1. The only difference is the label text — `"number of splits"` instead of `"size of tree"` — reflecting the alternate branch of the `switch` statement. The matplotlib translation pattern is the same: `ax_top.set_xlabel(text, labelpad=12)`. Both calls share the same `side = 3` and `line = 3` arguments, so no change to the `labelpad` value or the twin-axis setup is required between the two branches.
