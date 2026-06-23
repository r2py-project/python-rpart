## Conversion Guide: `model.frame` (R to Python)

---

### 1. Overview of `model.frame` in R

`model.frame` is a generic function from R's `stats` package. Its primary purpose is to extract, align, and coerce all variables referenced by a model formula (or `terms` object) from a source data object, and return them as a single `data.frame` that is ready to be consumed by a model fitting or prediction routine.

Key parameters:

- **`formula`**: A model formula (e.g., `y ~ x1 + x2`) or a `terms` object. When a `terms` object is supplied it carries pre-computed metadata (variable roles, factor levels, data classes) that `model.frame` uses for type-checking and level enforcement.
- **`data`**: A `data.frame`, list, or environment from which variables are drawn. If a variable is not found in `data`, R falls back to the formula's enclosing environment.
- **`na.action`**: A function that determines how rows containing `NA` values are handled. Common choices are `na.omit` (drop rows silently), `na.fail` (error on any NA), and `na.pass` (leave NAs in place). The default is taken from `getOption("na.action")`.
- **`xlev`**: A named list mapping column names to their complete, ordered set of factor levels. When provided, `model.frame` enforces that factor columns in `data` carry exactly those levels, allowing new data to align with the level encoding the model was trained on.
- **`subset`**: An optional row index expression for subsetting `data`.

Return value: a `data.frame` whose columns are exactly the variables referenced by `formula`/`terms`, with a `"terms"` attribute attached and, if any rows were removed by `na.action`, a `"na.action"` attribute recording the removed indices.

When called as `model.frame(object)` where `object` is a fitted model (e.g., an `rpart` object), the S3 dispatch system routes the call to a method such as `model.frame.rpart`, which may return the training data stored in the model or reconstruct it on demand.

---

### 2. Contextual Usage Analysis

`model.frame` appears in three distinct locations across the rpart R source, each corresponding to a different invocation pattern.

**Pattern 1 — Reconstruct a model frame for a prediction-path rpart object** (`model.frame.rpart.R`, `model.frame.rpart`, line 10):

```r
m <- model.frame(object$terms, m, na.rpart)
```

Here `object$terms` is the `terms` object saved in the fitted model and `m` is a plain data frame obtained by evaluating the `newdata` argument from the original `predict` call. The third positional argument `na.rpart` is passed as the `na.action`. This call selects and coerces precisely the columns required by the model formula, applying rpart's custom NA handler, and returns the result as a properly attributed `data.frame`. No `xlev` argument is passed here; factor-level alignment is handled earlier in the call chain.

**Pattern 2 — Align new data to model terms at prediction time** (`predict.rpart.R`, `predict.rpart`, line 13):

```r
newdata <- model.frame(Terms, newdata, na.action = na.action,
                       xlev = attr(object, "xlevels"))
```

`Terms` is the result of `delete.response(object$terms)` — a predictor-only `terms` object with the response variable stripped. The `xlev` argument carries the exact factor level sets that were seen during training (`attr(object, "xlevels")`), so that factor columns in `newdata` are re-levelled to match the training encoding before any further processing. `na.action` is forwarded from the caller (defaulting to `na.pass`). This is the canonical R pattern for safe prediction on new data.

**Pattern 3 — Extract the response vector from a stored model frame** (`residuals.rpart.R`, `residuals.rpart`, line 8):

```r
y <- model.extract(model.frame(object), "response")
```

`model.frame(object)` is called with a single argument — the fitted `rpart` object itself. S3 dispatch routes this to `model.frame.rpart`, which first checks `object$model` (the cached training frame stored when `model = TRUE` was passed to `rpart()`). If it is present it is returned immediately; otherwise the original `rpart()` call is reconstructed and re-evaluated. The resulting frame is then passed to `model.extract` to pull out the response column. This pattern appears only in `residuals.rpart` as a fallback when `object$y` is `NULL`.

**Data types across all three patterns:**
- Input `formula`/`Terms`: an R `terms` S3 object (or a fitted model that acts as one under S3 dispatch).
- Input `data`/`newdata`: a plain `data.frame`.
- Input `na.action`: a function or `NULL`.
- Input `xlev`: a named `list` of character vectors (one per factor column), or `NULL`.
- Return value: a `data.frame` with a `"terms"` attribute and an optional `"na.action"` attribute.

---

### 3. Python Conversion Strategy

R's `model.frame` performs three interleaved operations: column selection driven by a formula/terms metadata object, NA handling, and factor-level enforcement. No single Python function replicates all three simultaneously. The conversion therefore decomposes the call into its constituent responsibilities.

**Chosen libraries: `pandas` (primary) and `patsy` (formula layer).**

Rationale:

- `pandas` `DataFrame` is the direct structural equivalent of R's `data.frame`. Column selection, NA handling (`dropna`, `fillna`, masking), and categorical dtype enforcement are all native pandas operations.
- `patsy` is the closest Python analogue to R's formula and `terms` system. It parses R-style formula strings, builds a `DesignInfo` object (analogous to a `terms` object), and can apply the same encoding to new data frames via `patsy.dmatrix(design_info, newdata)`. This is the faithful equivalent of `model.frame(terms, newdata, xlev=...)`.
- For the simpler patterns (Pattern 1, Pattern 3) where no formula encoding is needed — only column subsetting and NA handling — pure `pandas` is sufficient and preferable over pulling in `patsy`.
- `numpy` is not required here because `model.frame` operates on heterogeneous tabular data (mixed numeric and categorical), not on homogeneous numeric arrays.

---

### 4. Step-by-Step Conversion Examples

#### Usage 1: Reconstruct a model frame for a predict-path object (Pattern 1)

**Locations:** `rpart/R/model.frame.rpart.R`, function `model.frame.rpart`

**Original R Context:**

```r
# object$terms : terms object from the fitted rpart model
# m            : a data.frame obtained from evaluating newdata
# na.rpart     : rpart's custom na.action function (wraps na.omit with
#                attribute tracking)

# Signature (positional):
# model.frame(formula, data, na.action)
m <- model.frame(object$terms, m, na.rpart)

# Return type: data.frame with "terms" attribute and optional "na.action" attribute
```

- Input types: `object$terms` is a `terms` object; `m` is a `data.frame`; `na.rpart` is a function.
- Output type: a `data.frame` containing only the columns named in `object$terms`, with rows filtered according to `na.rpart`.

**Python Equivalent:**

```python
import pandas as pd
import numpy as np
from typing import Optional

def model_frame_reconstruct(
    feature_names: list[str],
    data: pd.DataFrame,
    na_action: str = "omit",
) -> pd.DataFrame:
    """
    Python equivalent of:
        m <- model.frame(object$terms, m, na.rpart)

    Parameters
    ----------
    feature_names : list of column names required by the model
                    (derived from the stored terms / DesignInfo at training time)
    data          : pd.DataFrame — raw new data supplied by the caller
    na_action     : "omit"  -> drop rows with any NA  (na.omit / na.rpart behaviour)
                    "fail"  -> raise on any NA         (na.fail behaviour)
                    "pass"  -> leave NAs in place      (na.pass behaviour)
    """
    # 1. Select only the columns referenced by the model formula
    missing = set(feature_names) - set(data.columns)
    if missing:
        raise ValueError(f"Required columns missing from data: {missing}")
    frame = data[feature_names].copy()

    # 2. Apply NA action (mirrors R's na.action argument)
    if na_action == "omit":
        na_idx = frame.index[frame.isnull().any(axis=1)]
        frame = frame.dropna()
        # Attach the removed indices as metadata (mirrors R's "na.action" attribute)
        frame.attrs["na.action"] = na_idx.tolist()
    elif na_action == "fail":
        if frame.isnull().any(axis=None):
            raise ValueError("Missing values (NAs) found in data; na.action='fail'.")
    # "pass" — do nothing

    return frame


# Example usage
# feature_names is stored on the Python model at training time,
# analogous to the column names encoded in object$terms.
feature_names = model.feature_names   # e.g. ["Sepal.Length", "Sepal.Width"]
aligned_frame = model_frame_reconstruct(feature_names, newdata, na_action="omit")
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `object$terms` (column metadata) | `model.feature_names` — a list of required column names stored on the Python model at fit time |
| Column selection by `model.frame` | `data[feature_names].copy()` |
| `na.rpart` (custom NA omit) | `dropna()` with recording of removed indices in `frame.attrs["na.action"]` |
| `"terms"` attribute on the result | Not required in Python; the caller already knows the schema |

The key nuance is that R's `model.frame` automatically looks up which columns are needed by inspecting the `terms` object. In Python this metadata must be stored explicitly (as `feature_names` or a `patsy.DesignInfo`) when the model is fitted.

---

#### Usage 2: Align new data to a predictor-only terms object with factor-level enforcement (Pattern 2)

**Locations:** `rpart/R/predict.rpart.R`, function `predict.rpart`

**Original R Context:**

```r
# Terms        : result of delete.response(object$terms)
#                predictor-only terms object, response column removed
# newdata      : plain data.frame supplied by the user at prediction time
# na.action    : forwarded from the caller; default is na.pass
# xlev         : named list of character vectors, one entry per factor column,
#                containing the levels the model was trained on
#                e.g. list(Species = c("setosa", "versicolor", "virginica"))

newdata <- model.frame(Terms, newdata,
                       na.action = na.action,
                       xlev = attr(object, "xlevels"))

# Return type: data.frame — newdata columns aligned, typed, and re-levelled
#              to match the training-time encoding
```

- Input types: `Terms` is a `terms` object; `newdata` is a `data.frame`; `na.action` is a function; `xlev` is a named `list`.
- Output type: a `data.frame` whose factor columns carry exactly the levels in `xlev`.

**Python Equivalent (patsy workflow — recommended):**

```python
import pandas as pd
import patsy

def model_frame_predict(
    design_info: patsy.DesignInfo,
    newdata: pd.DataFrame,
    na_action: str = "pass",
) -> pd.DataFrame:
    """
    Python equivalent of:
        Terms   <- delete.response(object$terms)
        newdata <- model.frame(Terms, newdata,
                               na.action = na.action,
                               xlev = attr(object, "xlevels"))

    Parameters
    ----------
    design_info : patsy.DesignInfo saved from training (RHS only, i.e.
                  already the predictor-only equivalent of delete.response)
    newdata     : pd.DataFrame — user-supplied data at prediction time
    na_action   : "pass" -> keep NAs (na.pass default in predict.rpart)
                  "omit" -> drop NA rows
                  "fail" -> raise on any NA
    """
    # patsy.dmatrix with a saved DesignInfo applies the identical encoding
    # (dummy coding, factor levels, interactions) used at training time.
    # This atomically implements delete.response + model.frame + xlev enforcement.
    X_new = patsy.dmatrix(
        design_info,
        newdata,
        NA_action=na_action,
        return_type="dataframe",
    )
    return X_new
```

**Python Equivalent (pure pandas workflow — when patsy is not used):**

```python
import pandas as pd

def model_frame_predict_pandas(
    feature_names: list[str],
    cat_levels: dict[str, list],   # mirrors xlev = attr(object, "xlevels")
    newdata: pd.DataFrame,
    na_action: str = "pass",
) -> pd.DataFrame:
    """
    Pure pandas equivalent of model.frame with xlev enforcement.

    Parameters
    ----------
    feature_names : list of predictor column names (response already excluded,
                    mirrors delete.response semantics)
    cat_levels    : dict mapping each factor column name to its ordered list
                    of training-time levels (mirrors xlev argument)
    newdata       : pd.DataFrame
    na_action     : "pass" | "omit" | "fail"
    """
    missing = set(feature_names) - set(newdata.columns)
    if missing:
        raise ValueError(f"newdata is missing columns required by the model: {missing}")

    frame = newdata[feature_names].copy()

    # Enforce factor levels (= xlev argument)
    # pd.CategoricalDtype with a fixed categories list is the direct analogue
    # of R's xlev: it ensures that factor columns in newdata carry exactly
    # the levels the model was trained on, including unseen levels as NaN.
    for col, levels in cat_levels.items():
        if col in frame.columns:
            frame[col] = pd.Categorical(frame[col], categories=levels)

    # Apply NA action
    if na_action == "omit":
        frame = frame.dropna()
    elif na_action == "fail":
        if frame.isnull().any(axis=None):
            raise ValueError("Missing values found in newdata; na_action='fail'.")
    # "pass" — leave NAs in place

    return frame


# --- How to save design_info / cat_levels at training time ---
# patsy workflow:
import patsy
formula = "y ~ x1 + x2 + species"   # RHS only for prediction: "~ x1 + x2 + species"
y_train, X_train = patsy.dmatrices(formula, data=train_df, return_type="dataframe")
model.design_info = X_train.design_info   # save predictor-only DesignInfo

# pandas workflow:
model.feature_names = list(X_train.columns)
model.cat_levels = {
    col: list(train_df[col].cat.categories)
    for col in train_df.select_dtypes("category").columns
    if col in model.feature_names
}
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `Terms` (predictor-only `terms` from `delete.response`) | `patsy.DesignInfo` for RHS only (saved as `model.design_info`); or `feature_names` list without the response column |
| `model.frame(Terms, newdata, ...)` | `patsy.dmatrix(design_info, newdata)` (patsy) or `newdata[feature_names].copy()` (pandas) |
| `xlev = attr(object, "xlevels")` | `patsy.DesignInfo` (stores level info internally); or `pd.Categorical(col, categories=levels)` via `cat_levels` dict (pandas) |
| `na.action = na.pass` | `NA_action="pass"` in `patsy.dmatrix`; or no `dropna()` call in pandas path |
| Factor level out-of-range → converted silently to `NA` in R | `pd.Categorical` with a fixed `categories` list converts unseen values to `NaN` automatically |

The critical nuance is `xlev`: in R, `model.frame` uses `xlev` to re-level factor columns in `newdata` to exactly match the training-time encoding (in the correct order), so that integer codes map to the same categories as during training. In Python the direct equivalent is `pd.Categorical(series, categories=ordered_level_list)`, which assigns the identical ordered encoding. Any value in `newdata` that is absent from `cat_levels` becomes `NaN` — matching R's behaviour where an unseen factor level results in an `NA`.

---

#### Usage 3: Extract the stored or reconstructed training model frame (Pattern 3)

**Locations:** `rpart/R/residuals.rpart.R`, function `residuals.rpart`

**Original R Context:**

```r
# object : a fitted rpart object
# Called with a single argument — S3 dispatch routes to model.frame.rpart,
# which checks object$model first (training frame cached when model=TRUE
# was set) and reconstructs via eval(object$call) if not cached.

y <- model.extract(model.frame(object), "response")

# Return type of model.frame(object): data.frame with "terms" attribute
# containing both predictor and response columns from the training data.
# model.extract then pulls out the response column as a vector.
```

- Input type: a fitted `rpart` S3 object.
- Output type of `model.frame(object)`: a `data.frame` containing all training variables (predictors + response).
- Output type of the full expression: a vector (or factor) of response values.

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

def get_response_from_model(model, train_df: pd.DataFrame = None) -> pd.Series:
    """
    Python equivalent of:
        y <- model.extract(model.frame(object), "response")

    Retrieves the response vector from a fitted Python rpart-equivalent model.
    Mirrors R's two-path logic:
      1. If the training frame (including the response column) was cached on
         the model at fit time (analogous to rpart's model=TRUE), return it
         directly.
      2. Otherwise fall back to the caller-supplied training data frame.

    Parameters
    ----------
    model    : fitted Python model object; expected attributes:
                 model.y          — cached response array/Series (may be None)
                 model.response_col — name of the response column (str)
    train_df : pd.DataFrame — the original training data, used only when
               model.y is None (mirrors eval(object$call) reconstruction)
    """
    # Path 1: response cached on model (mirrors object$y / object$model)
    if hasattr(model, "y") and model.y is not None:
        y = model.y
        if not isinstance(y, pd.Series):
            y = pd.Series(y, name=model.response_col)
        return y

    # Path 2: reconstruct from training data (mirrors eval(object$call))
    if train_df is None:
        raise ValueError(
            "Response vector is not cached on the model and no training "
            "data frame was supplied. Set model.y at fit time, or pass "
            "train_df explicitly."
        )
    if model.response_col not in train_df.columns:
        raise KeyError(
            f"Response column '{model.response_col}' not found in train_df."
        )
    return train_df[model.response_col].copy()


# --- How to cache the response at fit time ---
model.y = y_train.values          # np.ndarray or pd.Series
model.response_col = "y"          # name of the response column
```

**Explanation:**

| R concept | Python equivalent |
|---|---|
| `model.frame(object)` via S3 dispatch to `model.frame.rpart` | `model.y` (cached) or `train_df[model.response_col]` (reconstructed) |
| `object$model` (cached training frame when `model=TRUE`) | `model.y` attribute set at fit time |
| `eval(object$call)` (full re-fit fallback) | Passing the original `train_df` to the function (a stored reference) |
| `model.extract(..., "response")` | Direct column access: `train_df[model.response_col]` |

The key difference in Python is that there is no equivalent to R's `call` object (a stored, re-evaluable expression). In Python, re-evaluation of the training process would require re-running the fit, which is expensive and unusual. The recommended practice is to store `model.y = y_train` at fit time so that the response is always available without recomputation. This is the direct analogue of R's `rpart(..., model = TRUE)` option.
