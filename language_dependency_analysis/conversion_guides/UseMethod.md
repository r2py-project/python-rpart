# Conversion Guide: `UseMethod` in R

---

## 1. Overview of `UseMethod` in R

`UseMethod` is the core mechanism for **S3 generic dispatch** in R. When a function body calls `UseMethod("genericName")`, R inspects the class of the first argument and looks for a registered method of the form `genericName.ClassName`. If found, R calls that method; otherwise it falls back to `genericName.default` (if defined) or raises an error.

**Signature:**
```r
UseMethod(generic, object)
```

| Parameter | Description |
|-----------|-------------|
| `generic` | A character string: the name of the generic function to dispatch on. |
| `object`  | Optional. The object whose class drives dispatch. Defaults to the first argument of the calling function. |

**Key properties:**
- `UseMethod` never returns to the calling function. After dispatch, the matched method executes in the same call frame.
- All arguments from the generic are automatically forwarded to the dispatched method.
- The `...` in a generic's signature passes through to the method transparently.
- S3 dispatch is purely name-based and requires no formal class declaration.

In rpart, `UseMethod` is used to define public-facing generic entry points (e.g., `prune`, `post`, `meanvar`) that dispatch to `rpart`-specific implementations (`prune.rpart`, `post.rpart`, `meanvar.rpart`), as registered via `S3method(...)` in the package `NAMESPACE`.

---

## 2. Contextual Usage Analysis

All three occurrences in the CSV follow an identical one-liner pattern: a thin generic wrapper function that immediately calls `UseMethod`. The dispatch target in every case is the `rpart` S3 class, registered in the package `NAMESPACE` file (`/groups/jli9/Yufei/python-rpart/rpart/NAMESPACE`).

| Generic   | File                  | Dispatched Method  | Method File          |
|-----------|-----------------------|--------------------|----------------------|
| `meanvar` | `meanvar.rpart.R`     | `meanvar.rpart`    | `meanvar.rpart.R`    |
| `post`    | `post.R`              | `post.rpart`       | `post.rpart.R`       |
| `prune`   | `prune.R`             | `prune.rpart`      | `prune.rpart.R`      |

Recurring patterns:

- **Generic signature:** Always `function(tree, ...) UseMethod("genericName")`. The first argument is named `tree` and holds an `rpart` object. The `...` passes additional arguments through to the method.
- **No logic in the generic:** The generic itself performs zero computation; 100% of the work lives in the `.rpart` method.
- **Single registered class:** Each generic has exactly one registered method (`*.rpart`), so dispatch is deterministic for all valid inputs.
- **Input type:** The first argument (`tree`) is always an `rpart` object — a named list with slots such as `$frame`, `$cptable`, `$method`, and `$terms`.

---

## 3. Python Conversion Strategy

R's S3 dispatch has a direct structural equivalent in Python: **class-based method dispatch using object-oriented programming (OOP)**. The idiomatic translation is:

1. Define a Python class `RPart` (or reuse one already translated from the `rpart` object structure).
2. Implement each `genericName.rpart` method as a regular instance method (`def genericName(self, ...)`) on that class.
3. The public generic `genericName <- function(tree, ...) UseMethod("genericName")` collapses into a direct method call on the Python object: `tree.genericName(...)`.

No external library (numpy, scipy, etc.) is needed to replicate `UseMethod` itself — it is a pure dispatch mechanism. The libraries needed are determined by the bodies of the dispatched methods, not the generic entry points.

**Why class-based OOP over `functools.singledispatch`:**
- `functools.singledispatch` can replicate S3 dispatch for standalone functions but adds boilerplate with no benefit here, because there is only one registered type per generic (`rpart`).
- Python class methods are simpler, more readable, and naturally group all `*.rpart` methods on the single `RPart` class.
- `singledispatch` is the correct choice only when the same generic must handle several unrelated Python types — a scenario not present in this rpart subset.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `meanvar` Generic

**Locations:** `meanvar.rpart.R` — function `meanvar`; dispatches to `meanvar.rpart` in the same file.

**Original R Context:**

```r
# Generic entry point (line 18, meanvar.rpart.R)
meanvar <- function(tree, ...) UseMethod("meanvar")

# Dispatched method (lines 1-16, meanvar.rpart.R)
# tree: rpart object (list). xlab, ylab: character scalars. ...: passed to plot().
# Returns: invisible named list with elements x (numeric vector), y (numeric vector),
#          label (character vector).
meanvar.rpart <- function(tree, xlab = "ave(y)", ylab = "ave(deviance)", ...) {
    if (!inherits(tree, "rpart"))
        stop("Not a legitimate \"rpart\" object")
    if (!tree$method == "anova")
        stop("Plot not useful for classification or poisson trees")
    frame  <- tree$frame
    frame  <- frame[frame$var == "<leaf>", ]
    x      <- frame$yval
    y      <- frame$dev / frame$n
    label  <- row.names(frame)
    plot(x, y, xlab = xlab, ylab = ylab, type = "n", ...)
    text(x, y, label)
    invisible(list(x = x, y = y, label = label))
}
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt
import numpy as np


class RPart:
    def meanvar(self, xlab="ave(y)", ylab="ave(deviance)", **kwargs):
        """
        Plot mean vs. variance for the leaf nodes of an anova rpart tree.

        Parameters
        ----------
        xlab : str
            X-axis label.
        ylab : str
            Y-axis label.
        **kwargs :
            Additional keyword arguments forwarded to matplotlib.

        Returns
        -------
        dict with keys 'x' (np.ndarray), 'y' (np.ndarray), 'label' (list[str]).
        """
        if self.method != "anova":
            raise ValueError(
                "Plot not useful for classification or poisson trees"
            )

        frame = self.frame
        leaves = frame[frame["var"] == "<leaf>"]

        x = leaves["yval"].to_numpy()
        y = (leaves["dev"] / leaves["n"]).to_numpy()
        label = list(leaves.index.astype(str))

        fig, ax = plt.subplots(**kwargs)
        ax.set_xlabel(xlab)
        ax.set_ylabel(ylab)
        for xi, yi, lbl in zip(x, y, label):
            ax.text(xi, yi, lbl)
        ax.set_visible(True)

        return {"x": x, "y": y, "label": label}
```

**Explanation:**
- The R generic `meanvar <- function(tree, ...) UseMethod("meanvar")` disappears entirely. In Python, calling `tree.meanvar(...)` on an `RPart` instance achieves exactly the same dispatch without any extra code.
- `tree$frame[tree$frame$var == "<leaf>", ]` becomes a pandas DataFrame boolean-index filter: `frame[frame["var"] == "<leaf>"]`.
- `frame$dev / frame$n` is element-wise division; pandas Series already vectorizes this, so no explicit numpy call is needed. `.to_numpy()` is used at the end to produce numpy arrays matching R's numeric vector output.
- `invisible(list(...))` in R suppresses auto-printing but still returns the value; Python methods always return explicitly, so `return {...}` is the direct equivalent.

---

### 4.2 `post` Generic

**Locations:** `post.R` — function `post` (line 1); dispatches to `post.rpart` in `post.rpart.R`.

**Original R Context:**

```r
# Generic entry point (line 1, post.R)
post <- function(tree, ...) UseMethod("post")

# Dispatched method (lines 2-24, post.rpart.R)
# tree: rpart object. title.: character scalar (optional). filename: character scalar.
# digits: integer scalar. pretty, use.n, horizontal: logical scalars.
# ...: forwarded to postscript().
# Side effect: writes a PostScript file (or renders to current device). Returns NULL invisibly.
post.rpart <- function(tree, title.,
                       filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
                       digits = getOption("digits") - 2, pretty = TRUE,
                       use.n = TRUE, horizontal = TRUE, ...) {
    if (filename != "") {
        postscript(file = filename, horizontal = horizontal, ...)
        par(mar = c(2, 2, 4, 2) + 0.1)
        on.exit(dev.off())
    } else {
        oldpar <- par(mar = c(2, 2, 4, 2) + 0.1)
        on.exit(invisible(par(oldpar)))
    }
    plot(tree, uniform = TRUE, branch = 0.2, compress = TRUE, margin = 0.1)
    text(tree, all = TRUE, use.n = use.n, fancy = TRUE,
         digits = digits, pretty = pretty)
    if (missing(title.)) {
        temp <- attr(tree$terms, "variables")[2L]
        title(paste("Endpoint =", temp), cex = 0.8)
    } else if (nzchar(title.)) title(title., cex = 0.8)
}
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt
import matplotlib.backends.backend_pdf as pdf_backend


class RPart:
    def post(
        self,
        title=None,
        filename=None,
        digits=None,
        pretty=True,
        use_n=True,
        horizontal=True,
        **kwargs,
    ):
        """
        Render the rpart tree to a PostScript/PDF file or to the current figure.

        Parameters
        ----------
        title : str or None
            Title string. None triggers auto-title from the response variable name.
        filename : str or None
            Output file path. None renders to the current matplotlib figure.
        digits : int or None
            Number of significant digits for node labels.
        pretty : bool
            Whether to use pretty class labels.
        use_n : bool
            Whether to display node counts in labels.
        horizontal : bool
            Page orientation when writing to a file.
        **kwargs :
            Additional keyword arguments.
        """
        fig, ax = plt.subplots()
        fig.subplots_adjust(left=0.1, right=0.95, top=0.85, bottom=0.1)

        # Delegate to the tree's own plot/text methods (translated separately)
        self.plot(ax=ax, uniform=True, branch=0.2, compress=True, margin=0.1)
        self.text(
            ax=ax,
            all_nodes=True,
            use_n=use_n,
            fancy=True,
            digits=digits,
            pretty=pretty,
        )

        # Determine title
        if title is None:
            response_var = self.terms_variables[1]   # index 1 = second element
            ax.set_title(f"Endpoint = {response_var}", fontsize="small")
        elif title:
            ax.set_title(title, fontsize="small")

        # Write to file or leave figure open
        if filename:
            fig.savefig(filename, format="ps", orientation="landscape" if horizontal else "portrait")
            plt.close(fig)
```

**Explanation:**
- Again, the generic `post <- function(tree, ...) UseMethod("post")` collapses to `tree.post(...)` in Python.
- R's `postscript()` + `dev.off()` graphics device pattern is replaced by `matplotlib`'s `fig.savefig(..., format="ps")`. The `on.exit(dev.off())` teardown idiom is handled by `plt.close(fig)` after saving.
- `missing(title.)` (R's way of detecting an unset argument) is mapped to a Python default of `None` with a conditional check `if title is None`.
- R's `getOption("digits") - 2` default for `digits` becomes `None` in the signature and is resolved at call time by whatever rendering logic handles node labels.
- `attr(tree$terms, "variables")[2L]` (1-based second element) maps to `self.terms_variables[1]` (0-based index 1).
- `nzchar(title.)` (non-zero-length string check) maps to Python's truthy string check `elif title:`.

---

### 4.3 `prune` Generic

**Locations:** `prune.R` — function `prune` (line 2); dispatches to `prune.rpart` in `prune.rpart.R`.

**Original R Context:**

```r
# Generic entry point (line 2, prune.R)
prune <- function(tree, ...) UseMethod("prune")

# Dispatched method (lines 1-16, prune.rpart.R)
# tree: rpart object. cp: numeric scalar (complexity parameter threshold).
# ...: forwarded (unused in method body).
# Returns: pruned rpart object (same structure as input, with modified $frame,
#          $cptable, and $variable.importance).
prune.rpart <- function(tree, cp, ...) {
    ff   <- tree$frame
    id   <- as.integer(row.names(ff))
    toss <- id[ff$complexity <= cp & ff$var != "<leaf>"]
    if (length(toss) == 0L) return(tree)
    newx <- snip.rpart(tree, toss)
    temp <- pmax(tree$cptable[, 1L], cp)
    keep <- match(unique(temp), temp)
    newx$cptable <- tree$cptable[keep, , drop = FALSE]
    newx$cptable[length(keep), 1L] <- cp
    newx$variable.importance <- importance(newx)
    newx
}
```

**Python Equivalent:**

```python
import numpy as np
import copy


class RPart:
    def prune(self, cp: float) -> "RPart":
        """
        Prune an rpart tree to the given complexity parameter threshold.

        Parameters
        ----------
        cp : float
            Complexity parameter. Internal nodes with complexity <= cp are
            removed (snipped to leaves).

        Returns
        -------
        RPart
            A new RPart object representing the pruned tree.
        """
        ff = self.frame   # pandas DataFrame with columns: var, complexity, ...
        id_vals = ff.index.astype(int).to_numpy()

        # Nodes to remove: non-leaf nodes with complexity <= cp
        mask = (ff["complexity"].to_numpy() <= cp) & (ff["var"].to_numpy() != "<leaf>")
        toss = id_vals[mask]

        if len(toss) == 0:
            return self   # nothing to prune; return original tree

        newx = self.snip(toss)   # translated snip.rpart; returns new RPart

        # Trim the CP table
        cp_col = self.cptable[:, 0]               # first column of the CP matrix
        temp = np.maximum(cp_col, cp)             # pmax equivalent
        unique_temp, first_indices = np.unique(temp, return_index=True)
        # match(unique(temp), temp) in R gives the *first* position of each unique value
        keep = np.sort(first_indices)

        newx.cptable = self.cptable[keep, :]
        newx.cptable[len(keep) - 1, 0] = cp      # overwrite last row's cp value

        newx.variable_importance = newx.importance()
        return newx
```

**Explanation:**
- The generic `prune <- function(tree, ...) UseMethod("prune")` maps directly to `tree.prune(cp)` in Python.
- `as.integer(row.names(ff))` — R's 1-based character row names converted to integers — maps to `ff.index.astype(int).to_numpy()` because pandas DataFrames use a labeled Index.
- `ff$complexity <= cp & ff$var != "<leaf>"` is vectorized boolean logic; numpy and pandas both support this natively with `&`.
- `pmax(tree$cptable[, 1L], cp)` — R's element-wise maximum between a vector and a scalar — maps to `np.maximum(cp_col, cp)`. `numpy.maximum` is the correct vectorized equivalent of R's `pmax` (not `numpy.max`, which reduces).
- `match(unique(temp), temp)` in R returns the first occurrence index of each unique element. The Python equivalent is `numpy.unique(..., return_index=True)` which populates `first_indices` with exactly those positions. Sorting them preserves the original ordering (matching R's behaviour since `unique` in R preserves order of first appearance).
- `tree$cptable[keep, , drop=FALSE]` (row-subset of a matrix, retaining matrix type) maps to `self.cptable[keep, :]` (2-D numpy array row slice, which always remains 2-D).
- `newx$cptable[length(keep), 1L] <- cp` uses 1-based indexing on the last kept row; Python uses 0-based `len(keep) - 1`.
- `importance(newx)` is an internal rpart helper; it translates to `newx.importance()` as a method on the same class.
- The method returns a new `RPart` instance rather than modifying in place, matching R's copy-on-modify semantics.
