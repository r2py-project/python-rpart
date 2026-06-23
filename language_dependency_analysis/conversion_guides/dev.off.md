## Conversion Guide: `dev.off` (R) to Python

---

### 1. Overview of `dev.off` in R

`dev.off` is a base R function from the `grDevices` package. Its purpose is to **close the currently active graphics device**, flushing any pending output to disk or to the screen and releasing the device's resources. It is called purely for its side effect: it does not produce any useful return value (it returns the index of the next active device invisibly).

Key behaviours:

- When a file-based device such as `postscript()`, `pdf()`, or `png()` is the active device, calling `dev.off()` **finalises and closes the output file**, making it readable on disk.
- When the active device is an interactive screen window, `dev.off()` closes that window.
- `dev.off()` takes no mandatory arguments. The optional `which` argument (default: `dev.cur()`) selects which device to close, but is almost always omitted.
- In R, `dev.off()` is commonly registered with `on.exit()` to guarantee the device is closed even if an error is thrown — this is the pattern seen in `post.rpart`.

Signature:

```r
dev.off(which = dev.cur())
```

| R Parameter | Type | Description |
|---|---|---|
| `which` | integer scalar | Index of the device to close. Defaults to the current active device. Almost always omitted. |

Return value: an integer scalar (index of the next active device), returned invisibly and not used in practice.

---

### 2. Contextual Usage Analysis

**Source file:** `rpart/R/post.rpart.R`
**Function:** `post.rpart`
**Line:** 10

The full source of `post.rpart` is:

```r
post.rpart <- function(tree, title.,
                       filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
                       digits = getOption("digits") - 2, pretty = TRUE,
                       use.n = TRUE, horizontal = TRUE, ...)
{
    if (filename != "") {
        postscript(file = filename, horizontal = horizontal, ...)
        par(mar = c(2,2,4,2) + 0.1)
        on.exit(dev.off())         # <-- line 10: the call under analysis
    } else {
        oldpar <- par(mar = c(2,2,4,2) + 0.1)
        on.exit(invisible(par(oldpar)))
    }

    plot(tree, uniform = TRUE, branch = 0.2, compress = TRUE, margin = 0.1)
    text(tree, all = TRUE, use.n = use.n, fancy = TRUE, fancy = TRUE, digits = digits,
         pretty = pretty)

    if (missing(title.)) {
        temp <- attr(tree$terms, "variables")[2L]
        title(paste("Endpoint =", temp), cex = 0.8)
    } else if (nzchar(title.)) title(title., cex = 0.8)
}
```

Key observations:

- `postscript(file = filename, ...)` opens a PostScript file-based graphics device. All subsequent R graphics calls (`plot`, `text`, `title`) render into that file.
- `on.exit(dev.off())` registers `dev.off()` to be executed **automatically when `post.rpart` returns** (normally or due to an error), ensuring the PostScript file is always properly closed and flushed to disk.
- `dev.off()` is called with no arguments, so it always closes the most recently opened device — in this case, the `postscript` device opened two lines earlier.
- The `else` branch (when `filename == ""`) renders to an existing interactive device and restores only `par` settings; no device needs to be closed.
- The call body `dev.off()` takes no inputs and its return value is discarded. The sole purpose is the side effect of closing the file.

---

### 3. Python Conversion Strategy

The Python equivalent is **`matplotlib.pyplot.savefig` followed by `matplotlib.pyplot.close`**, or the use of **`matplotlib.backends.backend_pdf.PdfPages`** (or similar context managers) for file-based output.

The reasoning is:

- R's `postscript()` + `dev.off()` pair corresponds exactly to opening a file-based matplotlib backend, saving the figure, and closing it. In matplotlib, `plt.savefig(filename)` writes the rendered figure to disk, and `plt.close()` releases the figure resources — together these replicate the open/render/close lifecycle that `postscript()`/`dev.off()` provides in R.
- The `on.exit` cleanup pattern is idiomatically replaced in Python by a **`try/finally` block** or a **`with` context manager**, which guarantee cleanup even when exceptions are raised.
- `matplotlib` is the standard Python plotting library and the natural counterpart to R's base `graphics` system. No `numpy` or `scipy` involvement is needed for this call, since `dev.off()` is purely a device-lifecycle operation with no numeric computation.
- For PostScript output specifically, matplotlib supports `plt.savefig("file.ps")` directly (PostScript format is inferred from the `.ps` extension or the `format` argument).

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Closing a File-Based Graphics Device After Rendering

**Locations:** `post.rpart.R`, function `post.rpart`, line 10.

**Original R Context**

- Input types: none (`dev.off()` takes no arguments in this context).
- Return value: integer scalar (index of the next active device), returned invisibly and discarded.
- Side effect: closes and finalises the PostScript file opened by the preceding `postscript(file = filename, ...)` call.

Generalized R code:

```r
# Open a PostScript file-based device
postscript(file = filename, horizontal = horizontal, ...)
par(mar = c(2,2,4,2) + 0.1)

# Register device closure as a guaranteed cleanup action
on.exit(dev.off())

# Render content into the device (side effects)
plot(tree, ...)
text(tree, ...)
title(...)

# dev.off() is called automatically here when post.rpart returns
```

**Python Equivalent**

```python
import matplotlib
matplotlib.use("ps")          # use the PostScript backend explicitly if needed
import matplotlib.pyplot as plt

def post_rpart(tree, title_=None, filename=None, horizontal=True, **kwargs):
    if filename is None:
        filename = f"{tree}.ps"

    if filename != "":
        # Equivalent to R's: postscript(file = filename, horizontal = horizontal, ...)
        fig, ax = plt.subplots()

        # Equivalent to R's: par(mar = c(2,2,4,2) + 0.1)
        fig.subplots_adjust(bottom=0.1, left=0.1, top=0.9, right=0.9)

        try:
            # Render content into the figure (mirrors plot(), text(), title() calls)
            # ... (tree-rendering logic goes here)
            pass
        finally:
            # Equivalent to R's: on.exit(dev.off())
            # savefig flushes the PostScript output to disk; close releases resources.
            orientation = "landscape" if horizontal else "portrait"
            fig.savefig(filename, format="ps", orientation=orientation)
            plt.close(fig)
    else:
        # No file device opened; render into the existing active figure
        fig = plt.gcf()
        ax = plt.gca()

        original_margins = fig.subplotpars  # save state for restoration if needed
        fig.subplots_adjust(bottom=0.1, left=0.1, top=0.9, right=0.9)

        try:
            # ... (tree-rendering logic goes here)
            pass
        finally:
            # Equivalent to R's: on.exit(invisible(par(oldpar)))
            # Restore the previous subplot margins
            fig.subplots_adjust(
                bottom=original_margins.bottom,
                left=original_margins.left,
                top=original_margins.top,
                right=original_margins.right,
            )
```

**Explanation**

1. **`dev.off()` → `plt.close(fig)`** — In R, `dev.off()` closes the active graphics device. In matplotlib, `plt.close(fig)` (or `plt.close('all')`) releases the figure object and all associated resources. For file-based output, the file must first be written with `fig.savefig(...)` before calling `plt.close()`, because matplotlib does not auto-flush on close the way R's PostScript device does on `dev.off()`.

2. **`postscript()` + `dev.off()` → `fig.savefig()` + `plt.close()`** — R's device model separates opening (`postscript()`), rendering (all graphics calls), and closing (`dev.off()`). Matplotlib's model renders into a `Figure` object in memory and writes to disk only when `savefig()` is called. Both calls — `savefig` then `close` — are therefore needed to fully replicate what R's `dev.off()` does at the end of a file-based device session.

3. **`on.exit(dev.off())` → `try/finally`** — R's `on.exit()` registers a cleanup expression that runs unconditionally when the enclosing function exits, whether normally or due to an error. The direct Python idiom for this is a `try/finally` block: the `finally` clause executes regardless of whether an exception is raised, matching R's `on.exit` guarantee exactly. Alternatively, a context manager (`with` statement) encapsulates the same pattern when working with libraries that provide one (e.g., `matplotlib.backends.backend_pdf.PdfPages`).

4. **`horizontal` → `orientation`** — R's `postscript(horizontal = TRUE)` maps to matplotlib's `fig.savefig(..., orientation="landscape")` (and `horizontal = FALSE` maps to `orientation="portrait"`). The PostScript format is selected by passing `format="ps"` or by using a `.ps` file extension.

5. **No-argument call** — `dev.off()` is called with no arguments in this context, meaning it always closes the current active device. The Python equivalent `plt.close(fig)` is similarly explicit: it closes the specific figure created for the file output, avoiding accidental closure of unrelated figures that may be open in an interactive session.

6. **Side-effect-only pattern** — Like `dev.off()`, neither `fig.savefig()` nor `plt.close()` returns any value that is used by the caller. Both are invoked purely for their side effects (writing bytes to disk and freeing memory), matching the R pattern exactly.
