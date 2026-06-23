## Conversion Guide: `delete.response` (R to Python)

---

### 1. Overview of `delete.response` in R

`delete.response` is a base R function from the `stats` package. It takes a single argument:

- **`termobj`**: A `terms` object, which is the structured metadata object R attaches to a fitted model. A `terms` object encodes a formula (e.g., `y ~ x1 + x2`), the roles of each variable (response vs. predictor), factor interaction tables, and attributes such as `dataClasses` and `xlev`.

It returns a new `terms` object that is identical to the input except that the **response variable (left-hand side)** has been stripped away. The result represents only the predictor side of the formula (e.g., `~ x1 + x2`). This is used when you want to describe the feature space of a model — for example, to validate or construct a new data frame of predictors — without including the target variable.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/predict.rpart.R`
**Function:** `predict.rpart`

The relevant code block (lines 9–17) reads:

```r
where <- if (missing(newdata)) object$where
else {
    if (is.null(attr(newdata, "terms"))) {
        Terms <- delete.response(object$terms)
        newdata <- model.frame(Terms, newdata, na.action = na.action,
                               xlev = attr(object, "xlevels"))
        if (!is.null(cl <- attr(Terms, "dataClasses")))
            .checkMFClasses(cl, newdata, TRUE)
    }
    pred.rpart(object, rpart.matrix(newdata))
}
```

**What is happening:**

1. `object$terms` is the `terms` object saved in the fitted `rpart` model. It captures the full training formula, including the response variable (e.g., `Species ~ Sepal.Length + Sepal.Width`).
2. `delete.response(object$terms)` strips the response variable, producing a `terms` object that describes only the predictor columns (e.g., `~ Sepal.Length + Sepal.Width`).
3. The resulting `Terms` is then passed to `model.frame`, which uses it to select, type-check, and align the columns of `newdata` to match exactly what the model expects — but without requiring a response column to be present in `newdata` (since at prediction time, the target is unknown).
4. The `dataClasses` attribute on `Terms` is additionally used by `.checkMFClasses` to validate that every predictor column in `newdata` has the correct storage type (numeric, factor, etc.).

**Data types involved:**
- Input: a `terms` object (`object$terms`), which is an R S3 object with a class attribute of `"terms"` and `"formula"`.
- Output: another `terms` object with the response variable removed.
- The result is immediately consumed by `model.frame` and attribute introspection (`attr(Terms, "dataClasses")`).

**Recurring pattern:** This is the canonical R pattern for safe prediction on new data: strip the response from the training formula, then use the stripped terms to coerce and validate the new data frame into the correct shape for the model's feature matrix.

---

### 3. Python Conversion Strategy

R's `terms` object has no single direct Python counterpart, because Python ML libraries (scikit-learn, XGBoost, etc.) do not encode formula metadata in a unified object the way R does. The equivalent concept must be reconstructed from whatever metadata the Python model object stores.

The closest Python analogue to this entire pattern (stripping the response and using the result to align new data) comes from the **scikit-learn** `Pipeline` / `ColumnTransformer` pattern, but more directly from the **patsy** library, which is the closest Python equivalent to R's formula interface and `terms` objects.

**Chosen approach: `patsy`** for the formula/terms layer, with **`pandas`** for data-frame manipulation.

Rationale:
- `patsy` parses R-style formulas (`"y ~ x1 + x2"`), builds a `DesignInfo` object that is the closest analogue to an R `terms` object, and can apply that design to new data (the equivalent of `model.frame`).
- In `patsy`, the split between response and predictors is handled by `dmatrices` (which produces both) vs. `dmatrix` (which produces only the right-hand side / predictors). Using `dmatrix` with a stored `DesignInfo` is the direct semantic equivalent of `delete.response` followed by `model.frame`.
- In a pure scikit-learn workflow (no patsy), the equivalent is simply selecting the stored feature column names from the new data frame, which is the minimal faithful translation when no formula object exists.

---

### 4. Step-by-Step Conversion Examples

#### Usage 1: Strip response from a fitted model's terms, then build a predictor frame from new data

**Locations:** `predict.rpart.R`, function `predict.rpart`

**Original R Context:**

```r
# object$terms  : a terms object from the fitted rpart model,
#                 e.g. encodes "Species ~ Sepal.Length + Sepal.Width"
# newdata       : a plain data.frame supplied by the user at prediction time
#                 (does NOT contain the response column)

# Step 1: remove the response from the training terms
Terms <- delete.response(object$terms)
# Terms now encodes "~ Sepal.Length + Sepal.Width"

# Step 2: use the predictor-only terms to align and type-check newdata
newdata <- model.frame(Terms, newdata,
                       na.action = na.action,
                       xlev = attr(object, "xlevels"))

# Step 3: validate column types against what the model saw at training time
if (!is.null(cl <- attr(Terms, "dataClasses")))
    .checkMFClasses(cl, newdata, TRUE)
```

- Input types: `object$terms` is a `terms`/`formula` S3 object; `newdata` is a `data.frame`.
- Output type: a revalidated `data.frame` containing only the predictor columns, correctly typed.

**Python Equivalent (patsy-based):**

```python
import pandas as pd
import patsy

# -----------------------------------------------------------------------
# Assume the fitted Python model stores the following at training time:
#   model.design_info  : a patsy.DesignInfo for the RHS (predictors only)
#   model.feature_names: list of predictor column names (fallback)
#   model.cat_levels   : dict mapping categorical column names to their
#                        ordered list of levels seen during training
# -----------------------------------------------------------------------

def predict_align_newdata(model, newdata: pd.DataFrame,
                          na_action="raise") -> pd.DataFrame:
    """
    Python equivalent of:
        Terms    <- delete.response(object$terms)
        newdata  <- model.frame(Terms, newdata, na.action=na.action,
                                xlev=attr(object, "xlevels"))
        .checkMFClasses(attr(Terms, "dataClasses"), newdata, TRUE)
    """

    # --- Option A: patsy workflow (formula-based, closest to R semantics) ---
    if hasattr(model, "design_info"):
        # model.design_info is a patsy DesignInfo saved from training.
        # dmatrix with an existing DesignInfo applies the same encoding
        # (dummy coding, interactions, etc.) to new data — exactly what
        # model.frame(delete.response(terms), newdata, xlev=...) does in R.
        X_new = patsy.dmatrix(model.design_info, newdata,
                              NA_action=na_action, return_type="dataframe")
        return X_new

    # --- Option B: plain pandas/sklearn workflow (no formula object) -------
    # This is the minimal equivalent when the model stores only column names.
    feature_cols = model.feature_names          # list[str], set at fit time

    # 1. Select only the predictor columns (= delete.response semantics)
    missing_cols = set(feature_cols) - set(newdata.columns)
    if missing_cols:
        raise ValueError(
            f"newdata is missing columns required by the model: {missing_cols}"
        )
    X_new = newdata[feature_cols].copy()

    # 2. Re-apply categorical levels seen at training time
    #    (= xlev= argument in R's model.frame)
    if hasattr(model, "cat_levels"):
        for col, levels in model.cat_levels.items():
            if col in X_new.columns:
                X_new[col] = pd.Categorical(
                    X_new[col], categories=levels
                )

    # 3. Type-check each column against training dtypes
    #    (= .checkMFClasses equivalent)
    if hasattr(model, "feature_dtypes"):
        for col, expected_dtype in model.feature_dtypes.items():
            if col in X_new.columns:
                actual_dtype = X_new[col].dtype
                if not pd.api.types.pandas_dtype(expected_dtype) == actual_dtype:
                    raise TypeError(
                        f"Column '{col}': expected dtype {expected_dtype}, "
                        f"got {actual_dtype}"
                    )

    return X_new
```

**How to save `design_info` at training time (patsy workflow):**

```python
import patsy
import pandas as pd

# At fit time — equivalent of fitting the rpart model and storing object$terms
formula = "Species ~ Sepal_Length + Sepal_Width"
y_train, X_train = patsy.dmatrices(formula, data=train_df,
                                   return_type="dataframe")
# Save the RHS DesignInfo on the model object
model.design_info = X_train.design_info
model.fit(X_train, y_train)

# At predict time — equivalent of delete.response + model.frame
X_new = patsy.dmatrix(model.design_info, newdata, return_type="dataframe")
predictions = model.predict(X_new)
```

**Explanation of the translation:**

| R concept | Python equivalent |
|---|---|
| `object$terms` | `model.design_info` (a `patsy.DesignInfo`) saved at fit time |
| `delete.response(object$terms)` | Using `dmatrix` instead of `dmatrices` — `dmatrix` produces only the RHS predictor matrix; the response is never requested |
| `model.frame(Terms, newdata, xlev=...)` | `patsy.dmatrix(model.design_info, newdata)` — applies the identical encoding (factor levels, dummy coding, interactions) used at training time |
| `attr(Terms, "dataClasses")` | `model.design_info.column_name_indexes` combined with `model.feature_dtypes` for manual dtype checks |
| `.checkMFClasses(cl, newdata, TRUE)` | Explicit dtype comparison loop (Option B) or implicit enforcement by patsy's type coercion |
| `attr(object, "xlevels")` | `patsy.DesignInfo` stores factor coding info internally; in Option B, `model.cat_levels` is an explicit dict saved at training time |

Key nuances:
- In R, `delete.response` is purely a metadata operation on the `terms` object — it does not touch any data. The data alignment happens in the subsequent `model.frame` call. In Python, `patsy.dmatrix` with a saved `DesignInfo` performs both steps atomically.
- The `DesignInfo` approach is strongly preferred over manual column selection because it preserves factor level ordering, interaction encoding, and polynomial expansions exactly as seen during training — matching the full semantics of R's `terms` object plus `model.frame`.
- If patsy is not available or the model was fit with a pure scikit-learn pipeline, store `model.feature_names_in_` (set automatically by scikit-learn estimators) and use `newdata[model.feature_names_in_]` as the minimal equivalent.
