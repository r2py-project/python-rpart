# Conversion Guide: `eval.parent` in R (rpart Package)

---

## 1. Overview of `eval.parent` in R

`eval.parent` is an R base function that evaluates an expression in the **parent frame** (the calling environment) of the current function. Its signature is:

```r
eval.parent(expr, n = 1)
```

- `expr`: An R language object (typically a `call` object) to be evaluated.
- `n`: The number of frames to go up in the call stack. The default `1` means the immediate parent of the current function's environment.

`eval.parent(expr)` is exactly equivalent to `eval(expr, parent.frame(1))`. Its primary purpose is to evaluate a manipulated call object — such as a modified copy of the original `match.call()` result — inside the environment where the outer function was itself called. This ensures that variable names referenced in user-supplied arguments (e.g., a `data` argument by name) are resolved in the caller's scope rather than inside the function body, preventing "object not found" errors for symbols that exist only in the caller's environment.

The return value is whatever the evaluated expression returns. In both usages in the rpart package, that value is a **model frame** (a `data.frame` subclass with a `"terms"` attribute), produced by evaluating a reconstructed call to `stats::model.frame`.

---

## 2. Contextual Usage Analysis

Both usages follow the same canonical R idiom: capture the original call with `match.call()`, extract only the arguments relevant to `stats::model.frame`, replace the function name in the call object, then evaluate the modified call in the caller's environment.

### Usage in `rpart.R` — `rpart()`, line 19

Located at `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`.

The `rpart()` function receives a formula interface (`formula`, `data`, `weights`, `subset`, `na.action`). It:

1. Captures the original call with `match.call()` into `Call`.
2. Extracts the indices of `formula`, `data`, `weights`, and `subset` from `Call`.
3. Builds `temp` as a sub-call containing only those arguments plus a default `na.action`.
4. Replaces `temp[[1L]]` (the function name) with `quote(stats::model.frame)`.
5. Calls `eval.parent(temp)` so that `stats::model.frame(formula, data, weights, subset, na.action)` is evaluated in the caller's environment, where `data` and other variables are in scope.

The result `m` is a model frame (a `data.frame` with a `"terms"` attribute).

### Usage in `xpred.rpart.R` — `xpred.rpart()`, line 25

Located at `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`.

`xpred.rpart()` takes an already-fitted `rpart` object (`fit`). When `fit$y` or `fit$x` are `NULL` (i.e., the fitted object did not store the original data), and the model frame was not cached in `fit$model`, the function reconstructs the model frame from the original call stored in `fit$call`:

1. It extracts from `fit$call` the subset of named arguments matching `""`, `"formula"`, `"data"`, `"weights"`, `"subset"`, `"na.action"` (index `0L` for unmatched entries is excluded by the match semantics).
2. Appends a default `na.action = na.rpart` if not present.
3. Replaces `m[[1]]` with `quote(stats::model.frame)`.
4. Calls `eval.parent(m)` to evaluate the reconstructed call in the caller's environment.

The result `m` is again a model frame, subsequently used to recover the predictor matrix `X`, case weights `wt`, and response `Y`.

### Recurring Pattern

Both usages are instances of the same pattern:

- A **language/call object** is manipulated to redirect a formula-based call to `stats::model.frame`.
- `eval.parent` ensures that user-supplied variable names (e.g., a bare `data = mydf`) resolve against the caller's environment, not the library function's internal scope.
- The return type is always a `data.frame`-based model frame.

---

## 3. Python Conversion Strategy

`eval.parent` has **no direct Python equivalent** because it is a metaprogramming construct specific to R's non-standard evaluation (NSE) and call-stack frame system. However, its *functional purpose* — deferring the construction of a dataset from a formula and named data sources until runtime, resolving names in the caller's scope — can be replicated in Python using `pandas` and explicit argument passing.

The appropriate Python conversion strategy is:

- **Replace the formula-based model-frame construction with explicit `pandas` DataFrame manipulation.** In Python, there is no formula language or `stats::model.frame`; callers pass DataFrames or arrays directly. The `eval.parent` idiom that reconstructs and re-evaluates a call is replaced by standard Python function arguments that are passed by the caller explicitly.
- The `na.action` logic (row dropping for `NA`s) maps to `pandas.DataFrame.dropna()`.
- Subsetting (`subset` argument) maps to boolean indexing on a `pandas.DataFrame`.
- Weights map to an explicit `weights` array/Series parameter.
- The `"terms"` attribute, which carries the formula's metadata, is replaced by explicit tracking of the response column name and predictor column names.

No runtime code-object manipulation (analogous to `eval.parent`) is needed or appropriate in Python. The NSE mechanism becomes irrelevant when callers pass DataFrames directly.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Usage in `rpart()` — `rpart/R/rpart.R`, line 19

**Locations:** `rpart.R`, function `rpart`

**Original R Context**

Input types:
- `formula`: an R `formula` object (e.g., `y ~ x1 + x2`)
- `data`: a `data.frame` (optional; may be `NULL`)
- `weights`: a numeric vector (optional)
- `subset`: a logical or integer vector (optional)
- `na.action`: a function (default `na.rpart`, which removes rows with `NA`s)

Return type of `eval.parent(temp)`: a `data.frame` (model frame) with a `"terms"` attribute encoding the formula structure.

```r
Call <- match.call()
indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
if (indx[1] == 0L) stop("a 'formula' argument is required")
temp <- Call[c(1L, indx)]           # subset the call to keep only needed args
temp$na.action <- na.action         # add na.action
temp[[1L]] <- quote(stats::model.frame)  # redirect to model.frame
m <- eval.parent(temp)              # evaluate in caller's environment
# m is a data.frame with attr(m, "terms") set
```

**Python Equivalent**

```python
import pandas as pd
import numpy as np
from typing import Optional, List

def _build_model_frame(
    data: pd.DataFrame,
    response_col: str,
    feature_cols: Optional[List[str]] = None,
    weights: Optional[np.ndarray] = None,
    subset: Optional[np.ndarray] = None,
    na_action: str = "na_omit",
) -> dict:
    """
    Replaces the eval.parent(stats::model.frame(...)) idiom in rpart().

    Parameters
    ----------
    data        : The input DataFrame (caller passes it explicitly).
    response_col: Name of the response/target column.
    feature_cols: Names of predictor columns. If None, all non-response columns.
    weights     : Optional 1-D array of per-row case weights.
    subset      : Optional boolean or integer array for row selection.
    na_action   : "na_omit" (default) drops rows with any NA;
                  "na_pass" keeps them.

    Returns
    -------
    dict with keys:
        "frame"      : pd.DataFrame of selected rows/cols (model frame)
        "y"          : pd.Series -- the response column
        "X"          : pd.DataFrame -- the predictor columns
        "weights"    : np.ndarray or None
        "terms"      : dict with response and feature column names
    """
    # --- subset rows ---
    if subset is not None:
        data = data.iloc[subset] if np.issubdtype(
            np.array(subset).dtype, np.integer
        ) else data[subset]

    # --- resolve columns ---
    if feature_cols is None:
        feature_cols = [c for c in data.columns if c != response_col]

    cols_needed = [response_col] + feature_cols
    if weights is not None:
        frame = data[cols_needed].copy()
        frame["(weights)"] = weights
    else:
        frame = data[cols_needed].copy()

    # --- na_action ---
    if na_action == "na_omit":
        frame = frame.dropna(subset=cols_needed)

    y = frame[response_col]
    X = frame[feature_cols]
    w = frame["(weights)"].to_numpy() if "(weights)" in frame.columns else None

    terms = {"response": response_col, "features": feature_cols}
    return {"frame": frame, "y": y, "X": X, "weights": w, "terms": terms}


# Example call (mirrors rpart(Species ~ ., data=iris, na.action=na.omit)):
import sklearn.datasets
iris = pd.DataFrame(
    sklearn.datasets.load_iris().data,
    columns=["Sepal.Length", "Sepal.Width", "Petal.Length", "Petal.Width"]
)
iris["Species"] = sklearn.datasets.load_iris().target

model_frame = _build_model_frame(
    data=iris,
    response_col="Species",
)
y = model_frame["y"]
X = model_frame["X"]
```

**Explanation**

| R concept | Python translation |
|---|---|
| `match.call()` / call manipulation | Not needed; Python functions receive values, not unevaluated expressions |
| `eval.parent(temp)` | Eliminated; caller passes the `data` DataFrame directly |
| `stats::model.frame(formula, data, ...)` | `_build_model_frame(data, response_col, feature_cols, ...)` |
| `na.action = na.rpart` (drop NA rows) | `pd.DataFrame.dropna(subset=cols_needed)` |
| `subset` argument | Boolean or integer indexing via `df.iloc[subset]` or `df[subset]` |
| `attr(m, "terms")` | A plain `dict` carrying `response` and `features` column names |

The critical insight is that `eval.parent` exists solely because R must evaluate the user-written symbol `data` (a bare name in the caller's workspace) after the call has been restructured. Python function calls resolve all arguments to concrete objects at the call site, so the entire metaprogramming layer disappears.

---

### 4.2 Usage in `xpred.rpart()` — `rpart/R/xpred.rpart.R`, line 25

**Locations:** `xpred.rpart.R`, function `xpred.rpart`

**Original R Context**

Input types:
- `fit$call`: a `call` object — the original call that created the rpart model.
- The call is modified the same way as in `rpart()`: arguments are extracted, `na.action` is defaulted, function name is replaced with `quote(stats::model.frame)`.
- `eval.parent(m)` resolves symbol names from `fit$call` (e.g., a `data = df_name` reference) against the environment of the caller of `xpred.rpart()`.

Return type: a `data.frame` model frame; subsequently used to recover `X` (predictor matrix) and `Y` (response vector).

```r
m <- fit$call[match(c("", "formula", "data", "weights", "subset",
                      "na.action"), names(fit$call), 0L)]
if (is.null(m$na.action)) m$na.action <- na.rpart
m[[1]] <- quote(stats::model.frame)
m <- eval.parent(m)   # recover model frame from the original call's arguments
if (is.null(X)) X <- rpart.matrix(m)
if (is.null(wt)) wt <- model.extract(m, "weights")
```

**Python Equivalent**

In a Python port, the fitted model object stores the original data (or references to it) explicitly rather than as a re-evaluable call object. The `eval.parent` recovery step is replaced by storing `data`, `feature_cols`, and `response_col` on the fitted object at training time, then reading them back when needed.

```python
import pandas as pd
import numpy as np
from typing import Optional, List

# ---------- At fit time: store data on the fitted object ----------

class RpartFit:
    """Simplified fitted rpart model. Stores what xpred_rpart needs."""
    def __init__(self):
        self.method: str = ""
        self.terms: dict = {}      # {"response": str, "features": List[str]}
        # Cached arrays (set if x=True / y=True in the original fit call):
        self.X: Optional[pd.DataFrame] = None
        self.y: Optional[pd.Series]    = None
        self.wt: Optional[np.ndarray]  = None
        # Fallback: the original data frame (replaces fit$model / fit$call[data])
        self.data: Optional[pd.DataFrame] = None
        # ... other fit attributes (tree structure, etc.)


def _recover_model_frame(
    fit: RpartFit,
    na_action: str = "na_omit",
) -> dict:
    """
    Replaces the eval.parent(m) idiom in xpred.rpart().

    When fit.X or fit.y are None, recover the model frame from the stored
    data. This mirrors the R pattern of reconstructing stats::model.frame
    from fit$call in the caller's environment.

    Returns the same dict shape as _build_model_frame() above.
    """
    if fit.X is not None and fit.y is not None:
        # Fast path: cached on the fit object (x=True, y=True at fit time)
        w = fit.wt if fit.wt is not None else np.ones(len(fit.y))
        return {
            "frame": None,
            "y": fit.y,
            "X": fit.X,
            "weights": w,
            "terms": fit.terms,
        }

    # Slow path: re-derive from stored data (mirrors eval.parent reconstruction)
    if fit.data is None:
        raise ValueError(
            "fit.data is None and fit.X/fit.y are not cached. "
            "Refit with x=True, y=True or pass data explicitly."
        )

    response_col  = fit.terms["response"]
    feature_cols  = fit.terms["features"]
    data = fit.data.copy()

    if na_action == "na_omit":
        data = data.dropna(subset=[response_col] + feature_cols)

    y  = data[response_col]
    X  = data[feature_cols]
    wt = fit.wt if fit.wt is not None else np.ones(len(y))

    return {
        "frame": data[[response_col] + feature_cols],
        "y": y,
        "X": X,
        "weights": wt,
        "terms": fit.terms,
    }


# ---------- Inside xpred_rpart(): ----------

def xpred_rpart(fit: RpartFit, xval: int = 10, cp: float = None,
                return_all: bool = False):
    X   = fit.X
    y   = fit.y
    wt  = fit.wt

    if X is None or y is None:
        mf = _recover_model_frame(fit)   # <-- replaces eval.parent(m)
        if X  is None: X  = mf["X"]
        if wt is None: wt = mf["weights"]
        if y  is None: y  = mf["y"]

    # ... rest of cross-validation logic
```

**Explanation**

| R concept | Python translation |
|---|---|
| `fit$call` — stored original call object | `fit.data`, `fit.terms` — stored original data and column names |
| Reconstructing call arguments from `fit$call` | Reading `.terms["response"]` and `.terms["features"]` from the fit object |
| `eval.parent(m)` — re-evaluating `stats::model.frame` in caller's env | `_recover_model_frame(fit)` — re-filtering the stored DataFrame |
| `model.extract(m, "weights")` | `fit.wt` or `np.ones(len(y))` |
| `rpart.matrix(m)` | `data[feature_cols]` (the predictor sub-DataFrame) |

The fundamental difference is that in Python there is no mechanism for a call object to remember the names of variables from the caller's scope and re-resolve them later. The Python port avoids this by **storing the actual data** (the resolved DataFrame) on the fit object at training time. This is the standard Python/scikit-learn convention (`fit.X_train_`, etc.) and is both simpler and more explicit than R's call-reconstruction approach.
