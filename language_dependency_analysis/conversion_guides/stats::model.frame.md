## Conversion Guide: `stats::model.frame` (R to Python)

---

### 1. Overview of `stats::model.frame` in R

`stats::model.frame` is a function from R's `stats` package (explicitly namespace-qualified as `stats::model.frame` to avoid ambiguity with any user-defined or package-local `model.frame`). Its core purpose is to extract all variables referenced by a model formula from a given data source and return them as a single, aligned `data.frame` that is ready for model fitting.

Key parameters:

- **`formula`**: A model formula (e.g., `y ~ x1 + x2`) or a `terms` object encoding variable roles and metadata.
- **`data`**: A `data.frame`, list, or environment from which formula variables are resolved. Variables not found in `data` are looked up in the formula's enclosing environment.
- **`weights`**: An optional numeric vector of per-observation weights. When present it is included as a special column in the returned frame with attribute `"weights"`.
- **`subset`**: An optional expression for row selection, evaluated within `data`.
- **`na.action`**: A function that determines how rows containing `NA` values are handled. Common choices are `na.omit` (drop rows with any NA), `na.fail` (raise an error on any NA), and `na.pass` (leave NAs in place). `rpart` supplies its own `na.rpart` here.

Return value: a `data.frame` whose columns are precisely the variables referenced by `formula`, with a `"terms"` attribute attached and, if rows were removed by `na.action`, a `"na.action"` attribute recording the removed row indices.

The pattern in the rpart source uses `stats::model.frame` indirectly: instead of calling it directly, the code places `quote(stats::model.frame)` as the function slot of an already-built `match.call()` expression and then evaluates that modified call via `eval.parent()`. This is a standard R idiom for forwarding selected arguments from an outer function call into `model.frame` without manually restating every argument.

---

### 2. Contextual Usage Analysis

Both CSV rows correspond to the same call-reconstruction idiom and differ only in the surrounding function. In each location the code:

1. Extracts a subset of the original function's call arguments by name using `match` and bracket-subsetting on `match.call()`.
2. Appends any missing default arguments (e.g., `na.action`).
3. Replaces the function slot (`[[1L]]`) with `quote(stats::model.frame)`.
4. Evaluates the modified call in the parent frame with `eval.parent(temp)`.

The returned model frame `m` is then used to extract: the `"terms"` attribute (for formula metadata), the response vector (`model.response`), observation weights (`model.weights`), offsets (`model.offset`), and the predictor matrix (`rpart.matrix`).

**Pattern in `rpart.R`, function `rpart`, line 18:**

```r
indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
temp <- Call[c(1L, indx)]
temp$na.action <- na.action
temp[[1L]] <- quote(stats::model.frame)
m <- eval.parent(temp)
```

Arguments forwarded: `formula`, `data`, `weights`, `subset`. The `na.action` argument is added explicitly before dispatching. This is the primary model-fitting path executed when the caller does not supply a pre-built `data.frame` as the `model` argument.

- Input types: `formula` is an R formula object; `data` is a `data.frame` (or environment); `weights` and `subset` are optional vectors; `na.action` is a function (`na.rpart` by default).
- Return type: a `data.frame` with a `"terms"` attribute and an optional `"na.action"` attribute.

**Pattern in `xpred.rpart.R`, function `xpred.rpart`, line 24:**

```r
m <- fit$call[match(c("", "formula", "data", "weights", "subset",
                      "na.action"), names(fit$call), 0L)]
if (is.null(m$na.action)) m$na.action <- na.rpart
m[[1]] <- quote(stats::model.frame)
m <- eval.parent(m)
```

Arguments forwarded: those that were present in the original `rpart()` call stored in `fit$call`. This path is taken when neither `fit$y` nor `fit$x` is available on the fitted object, so the training data must be reconstructed by re-running `stats::model.frame` against the original call. The empty string `""` in the `match` vector captures the function name slot of the call (position `[[1]]`), which is then immediately overwritten with `quote(stats::model.frame)`.

- Input types: same as above, but arguments come from `fit$call` (a stored `call` object) rather than the live parent frame.
- Return type: identical to the `rpart` pattern — a `data.frame` with a `"terms"` attribute.

**Recurring data types across both patterns:**

| Argument | R type | Notes |
|---|---|---|
| `formula` | `formula` / `terms` S3 object | Encodes LHS (response) and RHS (predictors) |
| `data` | `data.frame` | Primary variable source |
| `weights` | numeric vector or absent | Stored as a special column under `attr(m, "weights")` |
| `subset` | logical / integer vector or absent | Row selection index |
| `na.action` | function | `na.rpart` in both locations |
| Return value | `data.frame` | Has `"terms"` attribute; may have `"na.action"` attribute |

---

### 3. Python Conversion Strategy

**Chosen library: `pandas` (primary), with `patsy` as an optional formula layer.**

Rationale:

- The call-reconstruction idiom (`quote(stats::model.frame)` placed into a stored call) has no direct Python analogue. In Python, arguments are passed explicitly at call time; there is no runtime call-object manipulation. The conversion therefore makes the implicit argument forwarding explicit.
- `pandas.DataFrame` is the structural equivalent of R's `data.frame`. Column selection, NA handling (`dropna`, `isnull`), and weight extraction are all native pandas operations.
- `patsy` can parse R-style formula strings and build a `DesignInfo` object that records predictor/response roles, dummy-coding schemes, and interaction terms — closely mirroring what a `terms` object encodes. Using `patsy.dmatrices` at fit time produces both the response series and the predictor matrix in a single call, replicating what `model.frame` followed by `model.response`/`rpart.matrix` achieves in R.
- When the formula is simple (no interactions, no transformations) and factor encoding is handled externally, pure `pandas` column selection is sufficient and avoids the `patsy` dependency.
- `numpy` is not the primary tool here because `model.frame` operates on heterogeneous tabular data, not uniform numeric arrays.

---

### 4. Step-by-Step Conversion Examples

#### Usage 1: Build model frame from a live formula call (`rpart`, line 18)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, function `rpart`

**Original R Context:**

```r
# Call       : match.call() — the full call to rpart() captured at entry
# na.action  : function, default na.rpart
# Arguments forwarded: formula, data, weights, subset

indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
# temp is a subset of the original call object, keeping only the named args
temp <- Call[c(1L, indx)]
temp$na.action <- na.action          # add the default na.action
temp[[1L]] <- quote(stats::model.frame)  # swap in model.frame as the function
m <- eval.parent(temp)               # evaluate: effectively calls
                                     #   stats::model.frame(formula, data,
                                     #                      weights, subset,
                                     #                      na.action=na.action)

# Return: data.frame m with attr(m, "terms") set
Terms <- attr(m, "terms")
Y     <- model.response(m)   # response column
wt    <- model.weights(m)    # weights column (NULL if not supplied)
```

- Input types: `formula` is a formula object; `data` is a `data.frame`; `weights` and `subset` are optional vectors; `na.action` is a function.
- Output: a `data.frame` `m` whose columns are all variables in `formula`, with special attributes for `terms`, `weights`, and optionally `na.action`.

**Python Equivalent:**

```python
import pandas as pd
import numpy as np
import patsy
from typing import Optional

def build_model_frame(
    formula: str,
    data: pd.DataFrame,
    weights: Optional[pd.Series] = None,
    subset: Optional[pd.Index] = None,
    na_action: str = "omit",
) -> dict:
    """
    Python equivalent of the R pattern:

        temp[[1L]] <- quote(stats::model.frame)
        m <- eval.parent(temp)

    which effectively calls:
        m <- stats::model.frame(formula, data, weights, subset,
                                na.action = na.action)

    Parameters
    ----------
    formula   : R-style formula string, e.g. "y ~ x1 + x2"
    data      : pd.DataFrame — the training data
    weights   : optional pd.Series of per-observation weights
    subset    : optional index/boolean mask to select rows before processing
    na_action : "omit" -> drop NA rows (na.rpart / na.omit behaviour)
                "fail" -> raise on any NA (na.fail behaviour)
                "pass" -> leave NAs in place (na.pass behaviour)

    Returns
    -------
    dict with keys:
        "frame"   : pd.DataFrame — the model frame (all formula variables)
        "terms"   : patsy.DesignInfo — metadata equivalent to R's terms object
        "y"       : pd.Series — the response vector  (model.response equivalent)
        "X"       : pd.DataFrame — predictor columns (rpart.matrix equivalent)
        "wt"      : pd.Series or None — observation weights (model.weights equiv)
        "na_action_idx" : list — row labels removed by na_action (may be empty)
    """
    # 1. Apply subset (mirrors the 'subset' argument to stats::model.frame)
    if subset is not None:
        data = data.loc[subset].copy()

    # 2. Parse formula and extract response + predictors using patsy
    #    patsy.dmatrices is the closest Python equivalent:
    #    it applies the formula to 'data' and returns (response_matrix,
    #    predictor_matrix), both as patsy.DesignMatrix objects that carry
    #    a .design_info attribute (the Python analogue of R's terms object).
    y_mat, X_mat = patsy.dmatrices(formula, data=data, return_type="dataframe")

    # Combine into a single frame mirroring R's model.frame output
    response_col = y_mat.columns[0]
    frame = pd.concat([y_mat, X_mat.drop(columns=["Intercept"], errors="ignore")],
                      axis=1)

    # Attach weights as a special column (mirrors attr(m, "weights") in R)
    if weights is not None:
        weights = weights.loc[frame.index]
        frame["(weights)"] = weights.values

    # 3. Apply NA action (mirrors the na.action argument)
    na_action_idx = []
    if na_action == "omit":
        na_mask = frame.isnull().any(axis=1)
        na_action_idx = frame.index[na_mask].tolist()
        frame = frame.dropna()
        y_mat = y_mat.loc[frame.index]
        X_mat = X_mat.loc[frame.index]
        if weights is not None:
            weights = weights.loc[frame.index]
    elif na_action == "fail":
        if frame.isnull().any(axis=None):
            raise ValueError(
                "Missing values found in the data; na_action='fail'."
            )
    # "pass" / "omit" with na.rpart semantics: leave NAs for downstream handling

    y = frame[response_col]
    X = frame.drop(
        columns=[response_col] + (["(weights)"] if weights is not None else [])
    )
    wt = frame["(weights)"] if weights is not None else None

    return {
        "frame": frame,
        "terms": X_mat.design_info,   # patsy.DesignInfo — mirrors terms object
        "y": y,
        "X": X,
        "wt": wt,
        "na_action_idx": na_action_idx,
    }


# --- Typical call site (mirrors rpart() startup logic) ---
result = build_model_frame(
    formula="Species ~ Sepal.Length + Sepal.Width",
    data=train_df,
    weights=weight_series,   # None if not supplied
    subset=None,
    na_action="omit",        # na.rpart default
)
Terms   = result["terms"]         # store for later use in predict
Y       = result["y"]
wt      = result["wt"] if result["wt"] is not None else pd.Series(
              np.ones(len(result["X"])), index=result["X"].index
          )
X       = result["X"]
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `quote(stats::model.frame)` placed into a call object | No equivalent needed — Python arguments are passed explicitly |
| `eval.parent(temp)` with forwarded args | Direct function call `build_model_frame(formula, data, weights, subset, na_action)` |
| `attr(m, "terms")` | `patsy.DesignInfo` stored in `result["terms"]` |
| `model.response(m)` | `result["y"]` — the LHS column extracted by `patsy.dmatrices` |
| `model.weights(m)` | `result["wt"]` — the `(weights)` column, or `None` |
| `na.rpart` (NA omit with index recording) | `dropna()` with the removed indices recorded in `result["na_action_idx"]` |
| `model.offset(m)` | Not handled above; add an `offset` column to `data` before calling `patsy.dmatrices` and extract it from `frame["offset"]` |

The most important nuance is that R's call-object manipulation (`temp[[1L]] <- quote(stats::model.frame)`) is a metaprogramming shortcut for passing the parent function's arguments through to `model.frame` without restating them. In Python there is no such mechanism; the equivalent is explicit argument forwarding, as shown above.

---

#### Usage 2: Reconstruct the training model frame from a stored call (`xpred.rpart`, line 24)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`, function `xpred.rpart`

**Original R Context:**

```r
# fit       : fitted rpart object; fit$call is the original rpart() call
# fit$y and fit$x are NULL (not cached), so the frame must be rebuilt
# fit$model is also NULL; full reconstruction is required

m <- fit$call[match(c("", "formula", "data", "weights", "subset",
                      "na.action"), names(fit$call), 0L)]
# m is now a subset call-object containing only the matched argument slots.
# The "" entry captures the function name slot (position [[1]]).

if (is.null(m$na.action)) m$na.action <- na.rpart
# Ensure na.action is always set, defaulting to na.rpart

m[[1]] <- quote(stats::model.frame)
# Replace the function slot: turns the stored rpart() call into a
# stats::model.frame() call with the same arguments.

m <- eval.parent(m)
# Evaluate in the parent frame so that 'data' and 'formula' are resolved
# in the caller's environment (where the original rpart() was called).

# m is now the same data.frame that rpart() built at training time.
if (is.null(X)) X <- rpart.matrix(m)
if (is.null(wt)) wt <- model.extract(m, "weights")
```

- Input types: `fit$call` is a stored `call` object; arguments within it are an R formula, a `data.frame` name (a symbol resolved in the caller's environment), and optional weight/subset vectors.
- Output: a `data.frame` `m` identical to the one produced during training.

**Python Equivalent:**

```python
import pandas as pd
import numpy as np
import patsy
from typing import Optional

def reconstruct_model_frame(
    fit,
    train_df: pd.DataFrame,
    na_action: str = "omit",
) -> dict:
    """
    Python equivalent of the R pattern in xpred.rpart:

        m <- fit$call[match(c("","formula","data","weights","subset",
                             "na.action"), names(fit$call), 0L)]
        if (is.null(m$na.action)) m$na.action <- na.rpart
        m[[1]] <- quote(stats::model.frame)
        m <- eval.parent(m)

    R reconstructs the training model frame by replaying the stored rpart()
    call with stats::model.frame substituted as the function. In Python there
    is no call-object mechanism; instead, the fitting metadata saved on the
    Python model object is used to recreate the same frame from the supplied
    training data.

    Parameters
    ----------
    fit        : fitted Python rpart-equivalent model; expected attributes:
                   fit.formula_str  — formula string used at training time
                   fit.feature_names — list of predictor column names
                   fit.response_col  — name of the response column
                   fit.cat_levels    — dict[str, list] of factor column levels
                   fit.subset_idx    — row index used for subset at training
                                       time, or None
                   fit.weights_col   — name of the weights column in train_df,
                                       or None
    train_df   : pd.DataFrame — the original training data frame (must be
                 accessible at the call site, mirroring the environment lookup
                 that eval.parent() performs in R)
    na_action  : "omit" | "fail" | "pass"

    Returns
    -------
    dict with keys:
        "frame"         : pd.DataFrame — reconstructed model frame
        "X"             : pd.DataFrame — predictor matrix
        "y"             : pd.Series    — response vector
        "wt"            : pd.Series or None
        "na_action_idx" : list — row labels removed by na_action
    """
    # 1. Apply subset (mirrors the subset argument stored in fit$call)
    data = train_df
    if getattr(fit, "subset_idx", None) is not None:
        data = data.loc[fit.subset_idx].copy()

    # 2. Reconstruct the model frame using the stored formula.
    #    patsy.dmatrices replicates what stats::model.frame + rpart.matrix do.
    y_mat, X_mat = patsy.dmatrices(
        fit.formula_str, data=data, return_type="dataframe"
    )
    response_col = y_mat.columns[0]
    frame = pd.concat(
        [y_mat, X_mat.drop(columns=["Intercept"], errors="ignore")], axis=1
    )

    # 3. Attach weights column if present (mirrors model.extract(m, "weights"))
    weights = None
    if getattr(fit, "weights_col", None) is not None:
        weights = data[fit.weights_col].loc[frame.index]
        frame["(weights)"] = weights.values

    # 4. Enforce factor levels saved at training time
    #    (mirrors xlev handling inside stats::model.frame)
    for col, levels in getattr(fit, "cat_levels", {}).items():
        if col in frame.columns:
            frame[col] = pd.Categorical(frame[col], categories=levels)

    # 5. Apply NA action (mirrors na.rpart default)
    na_action_idx = []
    if na_action == "omit":
        na_mask = frame.isnull().any(axis=1)
        na_action_idx = frame.index[na_mask].tolist()
        frame = frame.dropna()
    elif na_action == "fail":
        if frame.isnull().any(axis=None):
            raise ValueError(
                "Missing values found when reconstructing model frame; "
                "na_action='fail'."
            )

    y = frame[response_col]
    X = frame.drop(
        columns=[response_col] + (["(weights)"] if weights is not None else [])
    )
    wt = frame["(weights)"] if weights is not None else None

    return {
        "frame": frame,
        "X": X,
        "y": y,
        "wt": wt,
        "na_action_idx": na_action_idx,
    }


# --- Typical call site (mirrors xpred.rpart fallback logic) ---
if fit.X is None or fit.y is None:
    result = reconstruct_model_frame(fit, train_df, na_action="omit")
    X   = result["X"]
    wt  = result["wt"]
    Y   = result["y"]
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `fit$call` (stored `call` object from original `rpart()`) | `fit.formula_str`, `fit.weights_col`, `fit.subset_idx` — metadata attributes stored on the Python model at fit time |
| `match(c("","formula","data",...), names(fit$call), 0L)` | No equivalent needed — Python uses named attributes directly |
| `m[[1]] <- quote(stats::model.frame)` then `eval.parent(m)` | Direct call to `reconstruct_model_frame(fit, train_df)` |
| `eval.parent(m)` — resolving `data` symbol in the caller's environment | `train_df` passed explicitly as a parameter; the caller is responsible for supplying the correct data frame |
| `model.extract(m, "weights")` | `data[fit.weights_col]` — direct column access |
| `rpart.matrix(m)` | `result["X"]` — the predictor-only `pd.DataFrame` from `patsy.dmatrices` |
| Factor level enforcement via `xlev` inside `model.frame` | `pd.Categorical(col, categories=fit.cat_levels[col])` |

The central design difference is that R stores the original `rpart()` call verbatim in `fit$call`, allowing full replay in any environment. Python has no equivalent of a stored, re-evaluable call. The correct mitigation is to save all necessary reconstruction metadata (`formula_str`, `weights_col`, `subset_idx`, `cat_levels`) on the model object at fit time, so that `reconstruct_model_frame` can rebuild the frame without re-running the full fitting procedure.
