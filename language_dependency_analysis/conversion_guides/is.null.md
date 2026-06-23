# Conversion Guide: `is.null` (R to Python)

## 1. Overview of `is.null` in R

`is.null(x)` is a base R predicate function that tests whether its single argument `x` is the special `NULL` object. It returns a single logical scalar: `TRUE` if `x` is `NULL`, and `FALSE` for every other value, regardless of type (integer, double, character, list, `NA`, `FALSE`, `0`, empty vector, etc.).

Key characteristics:

- Always returns a length-1 logical (never vectorized over the argument itself).
- `NULL` in R represents the absence of a value and is commonly used as a default parameter value, as an unset optional field, or as the absence of an attribute.
- `is.null` is distinct from `is.na`: `NA` represents a missing value within a vector; `NULL` represents the complete absence of an object.
- Checking `is.null(attr(x, "name"))` tests whether a particular attribute is absent from `x`.

Typical signatures:

```r
is.null(x)         # returns TRUE if x is NULL, FALSE otherwise
!is.null(x)        # returns TRUE if x is not NULL
if (is.null(x)) …  # guard pattern: do something when x is absent
```

---

## 2. Contextual Usage Analysis

Across the 62 CSV entries, `is.null` is used in two broad structural roles throughout the rpart R source files:

### Role A: Guard / early-exit on optional function parameters

Functions accept parameters with `NULL` as a default (or with `missing()` check), then use `is.null` to decide whether to apply an offset, validate user input, or branch to a default value. Examples: `rpart.anova`, `rpart.class`, `rpart.poisson`, `rpart.exp`, `na.rpart`, `labels.rpart`.

### Role B: Membership / presence check on object fields and attributes

Named fields of rpart model objects (e.g., `fit$csplit`, `frame$yval2`, `object$na.action`, `x$call`, `x$variable.importance`) and R attributes (e.g., `attr(m, "terms")`, `attr(m, "na.action")`, `attr(x, "ylevels")`) are `NULL` when absent. Code checks `is.null(field)` before branching between two code paths, before reading a value out of the field, or before calling `naresid` to restore missing-value rows. Examples: `pred.rpart`, `predict.rpart`, `print.rpart`, `printcp`, `residuals.rpart`, `rpart`, `snip.rpart.mouse`, `summary.rpart`, `text.rpart`, `xpred.rpart`.

### Role C: Inline assignment-and-test idiom

Several sites use `is.null(var <- expr)` — the assignment is performed as a side effect and then immediately tested for `NULL`. This is an R idiom that combines assignment and guard in a single expression. Examples: `printcp` line 12 (`is.null(cl <- x$call)`), `predict.rpart` line 15 (`is.null(cl <- attr(Terms, "dataClasses"))`), `summary.rpart` line 25 (`is.null(temp <- x$variable.importance)`), `text.rpart` line 18 (`is.null(ylevels <- attr(x, "ylevels"))`), `text.rpart` line 20 (`is.null(srt <- list(...)$srt)`).

Data types involved:

- Scalars and vectors of any type (`offset`, `xval`, `y`)
- Lists and named lists (`parms`, `init`, `functions`)
- Data-frame columns (`frame$yval2`, `frame$csplit`, `fit$csplit`)
- R attributes (`attr(m, "terms")`, `attr(m, "na.action")`, `attr(x, "ylevels")`)
- Named slots of S3 objects (`object$na.action`, `x$call`, `x$variable.importance`, `fit$csplit`)

---

## 3. Python Conversion Strategy

The Python equivalent of R's `NULL` is `None`. The standard Python idiom for testing `None` is the identity comparison `x is None` (preferred over `x == None`). To test that something is not `None`, use `x is not None`.

Because `is.null` always operates on a single object and returns a single boolean, there is no need for NumPy or pandas here. All translations use plain Python:

| R pattern | Python equivalent |
|-----------|-------------------|
| `is.null(x)` | `x is None` |
| `!is.null(x)` | `x is not None` |
| `if (is.null(x)) …` | `if x is None: …` |
| `if (!is.null(x)) …` | `if x is not None: …` |
| `is.null(attr(obj, "name"))` | `obj.get("name") is None` (dict) or `getattr(obj, "name", None) is None` (object) |
| `is.null(var <- expr)` | `var = expr` then `if var is None:` (separate statements) |

No imports are required for any of these translations.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Guard on optional offset parameter

**Locations:** `rpart/R/rpart.anova.R` — `rpart.anova` (line 3); `rpart/R/rpart.poisson.R` — `rpart.poisson` (lines 6, 8); `rpart/R/rpart.class.R` — `rpart.class` (line 3)

**Original R Context:**

`offset` is passed in as a parameter and defaults to `NULL` when the caller provides no offset. The function checks `is.null(offset)` to decide whether to adjust `y` or to substitute a default.

```r
# rpart.anova.R
rpart.anova <- function(y, offset, parms, wt) {
    if (!is.null(offset)) y <- y - offset
    ...
}

# rpart.poisson.R
rpart.poisson <- function(y, offset, parms, wt) {
    if (is.matrix(y)) {
        if (!is.null(offset)) y[, 1L] <- y[, 1L] * exp(offset)
    } else {
        if (is.null(offset)) y <- cbind(1, y)
        else y <- cbind(exp(offset), y)
    }
    ...
}

# rpart.class.R
rpart.class <- function(y, offset, parms, wt) {
    if (!is.null(offset)) stop("No offset allowed in classification models")
    ...
}
```

**Python Equivalent:**

```python
import numpy as np

# rpart_anova equivalent
def rpart_anova(y, offset=None, parms=None, wt=None):
    if offset is not None:
        y = y - offset
    ...

# rpart_poisson equivalent
def rpart_poisson(y, offset=None, parms=None, wt=None):
    if isinstance(y, np.ndarray) and y.ndim == 2:
        if offset is not None:
            y[:, 0] = y[:, 0] * np.exp(offset)
    else:
        if offset is None:
            y = np.column_stack([np.ones(len(y)), y])
        else:
            y = np.column_stack([np.exp(offset), y])
    ...

# rpart_class equivalent
def rpart_class(y, offset=None, parms=None, wt=None):
    if offset is not None:
        raise ValueError("No offset allowed in classification models")
    ...
```

**Explanation:** R's `NULL` maps directly to Python's `None`. The identity tests `x is None` and `x is not None` are the idiomatic Python forms and replace `is.null(x)` and `!is.null(x)` respectively. Default parameter values of `NULL` in R become `= None` in Python function signatures.

---

### 4.2 Guard on optional parms parameter or named list fields

**Locations:** `rpart/R/rpart.class.R` — `rpart.class` (lines 11, 17, 24, 32, 46, 49, 58, 80, 101); `rpart/R/rpart.exp.R` — `rpart.exp` (lines 112, 120, 124); `rpart/R/rpart.poisson.R` — `rpart.poisson` (lines 17, 25, 29)

**Original R Context:**

`parms` is either absent (`missing(parms)`) or a named list whose individual keys (`parms$prior`, `parms$loss`, `parms$split`, `parms$method`, `parms$shrink`) may or may not be set. Accessing a missing key in an R list returns `NULL`, so `is.null(parms$key)` tests whether the caller supplied that sub-parameter.

```r
# rpart.class.R (simplified excerpt)
if (missing(parms) || is.null(parms)) {
    parms <- list(prior = ..., loss = ..., split = 1)
} else if (is.list(parms)) {
    if (is.null(names(parms))) stop("The parms list must have names")
    ...
    if (is.null(parms$prior)) temp  <- c(counts / sum(counts))
    if (is.null(parms$loss))  temp2 <- 1 - diag(numclass)
    if (is.null(parms$split)) temp3 <- 1L
    ...
}

# rpart.exp.R (simplified excerpt)
if (is.null(names(parms))) stop("You must input a named list for parms")
if (is.null(parms$method)) method <- 1L
if (is.null(parms$shrink)) shrink <- 2L - method
```

**Python Equivalent:**

```python
# rpart_class equivalent
def rpart_class(y, offset=None, parms=None, wt=None):
    ...
    if parms is None:
        parms = {"prior": counts / counts.sum(),
                 "loss": 1 - np.eye(numclass),
                 "split": 1}
    elif isinstance(parms, dict):
        if not parms:  # empty dict — no names
            raise ValueError("The parms list must have names")
        prior  = parms.get("prior")
        loss   = parms.get("loss")
        split  = parms.get("split")

        temp  = counts / counts.sum() if prior is None else prior
        temp2 = 1 - np.eye(numclass)  if loss  is None else np.array(loss)
        temp3 = 1                      if split is None else split
        ...
    else:
        raise ValueError("Parameter argument must be a list")

# rpart_exp / rpart_poisson equivalent
def rpart_exp(y, offset=None, parms=None, wt=None):
    ...
    if parms is None:
        parms = {"shrink": 1, "method": 1}
    else:
        parms = dict(parms)
        if not parms:
            raise ValueError("You must input a named list for parms")
        method = 1     if parms.get("method") is None else _match_method(parms["method"])
        shrink = 2 - method if parms.get("shrink") is None else parms["shrink"]
        ...
```

**Explanation:** R named lists map to Python `dict`. Accessing a missing key in an R list returns `NULL`; the Python equivalent is `dict.get("key")`, which returns `None` when the key is absent. The test `is.null(parms$key)` becomes `parms.get("key") is None`. Testing `is.null(names(parms))` (whether the list has names at all) corresponds to checking whether the dict is empty or has no keys.

---

### 4.3 Check for absence of object slot or model field

**Locations:** `rpart/R/pred.rpart.R` — `pred.rpart` (line 20); `rpart/R/rpart.R` — `rpart` (lines 84, 175, 294); `rpart/R/xpred.rpart.R` — `xpred.rpart` (lines 54, 88)

**Original R Context:**

Named slots of the rpart S3 object (e.g., `fit$csplit`, `xlevels`) are `NULL` when not populated — for instance, when the tree has no categorical splits. Code tests this before branching or before indexing.

```r
# pred.rpart.R
as.integer(if (is.null(fit$csplit)) rep(0L, 2L) else dim(fit$csplit))

# rpart.R
if (!is.null(xlevels)) {
    indx <- match(names(xlevels), colnames(X), nomatch = 0)
    cats[indx] <- (unlist(lapply(xlevels, length)))[indx > 0]
}

ncat <- if (!is.null(rpfit$csplit)) nrow(rpfit$csplit) else 0L

# xpred.rpart.R
xlevels <- attr(fit, "xlevels")
if (!is.null(xlevels)) {
    xlevels <- xlevels[names(xlevels) %in% colnames(X)]
    cats[match(names(xlevels), colnames(X))] <- ...
}

costs <- fit$call$costs
if (is.null(costs)) costs <- rep(1, nvar)
```

**Python Equivalent:**

```python
import numpy as np

# pred_rpart equivalent
csplit_dim = np.array([0, 0], dtype=np.int32) if fit.csplit is None else np.array(fit.csplit.shape, dtype=np.int32)

# rpart equivalent — xlevels check
if xlevels is not None:
    indx = [colnames_X.index(name) for name in xlevels if name in colnames_X]
    for i in indx:
        cats[i] = len(xlevels[colnames_X[i]])

ncat = 0 if rpfit_csplit is None else rpfit_csplit.shape[0]

# xpred_rpart equivalent
xlevels = getattr(fit, "xlevels", None)
if xlevels is not None:
    xlevels = {k: v for k, v in xlevels.items() if k in colnames_X}
    for name, levels in xlevels.items():
        cats[colnames_X.index(name)] = len(levels)

costs = getattr(fit.call, "costs", None)
if costs is None:
    costs = np.ones(nvar)
```

**Explanation:** In the Python translation, rpart model fields that may be absent are represented as `None`. The pattern `if (!is.null(x))` becomes `if x is not None:`, and `if (is.null(x)) x <- default` becomes a ternary or `if x is None: x = default`. `attr(fit, "xlevels")` translates to `getattr(fit, "xlevels", None)`, which also returns `None` when the attribute is not set.

---

### 4.4 Check for optional yval2 column in frame

**Locations:** `rpart/R/predict.rpart.R` — `predict.rpart` (line 24); `rpart/R/print.rpart.R` — `print.rpart` (lines 19–20); `rpart/R/snip.rpart.mouse.R` — `snip.rpart.mouse` (line 35); `rpart/R/summary.rpart.R` — `summary.rpart` (line 63); `rpart/R/text.rpart.R` — `text.rpart` (line 53)

**Original R Context:**

`frame$yval2` is a matrix column of the frame data frame, present only for multiclass or multi-response trees. Code consistently branches on `is.null(frame$yval2)` to select either `frame$yval` (scalar) or `frame$yval2` (matrix).

```r
# predict.rpart.R
if (type == "vector" || (type == "matrix" && is.null(frame$yval2))) {
    pred <- frame$yval[where]
} else if (type == "matrix") {
    pred <- frame$yval2[where, ]
}

# print.rpart.R
yval <- if (!is.null(tfun)) {
    if (is.null(frame$yval2)) tfun(frame$yval, ylevel, digits, nsmall)
    else tfun(frame$yval2, ylevel, digits, nsmall)
} else format(signif(frame$yval, digits))

# summary.rpart.R
tmp <- if (is.null(ff$yval2)) ff$yval[rows] else ff$yval2[rows, , drop = FALSE]

# text.rpart.R
stat = x.functions.text(
    yval=frame.yval[leaves] if frame.get("yval2") is None else frame.yval2[leaves, :],
    ...
)
```

**Python Equivalent:**

```python
import numpy as np

# predict_rpart equivalent
yval2 = frame.get("yval2")  # None if not present
if pred_type == "vector" or (pred_type == "matrix" and yval2 is None):
    pred = frame["yval"][where]
elif pred_type == "matrix":
    pred = yval2[where, :]

# print_rpart equivalent
tfun = x_functions.get("print")
yval2 = frame.get("yval2")
if tfun is not None:
    yval = tfun(frame["yval"], ylevel, digits, nsmall) if yval2 is None \
           else tfun(yval2, ylevel, digits, nsmall)
else:
    yval = np.format_float_scientific(np.round(frame["yval"], digits))

# summary_rpart equivalent
tmp = ff["yval"][rows] if ff.get("yval2") is None else ff["yval2"][rows, :]

# text_rpart equivalent (using a dict for frame)
yval2 = frame.get("yval2")
yval_arg = frame["yval"][leaves] if yval2 is None else yval2[leaves, :]
stat = x_functions["text"](yval=yval_arg, ...)
```

**Explanation:** When the rpart frame is represented as a Python `dict`, `frame.get("yval2")` returns `None` if the key does not exist, matching R's behavior of returning `NULL` for absent list slots. The ternary `a if cond else b` replaces R's `if (is.null(...)) a else b` inline form.

---

### 4.5 Check for optional na.action slot (post-prediction NA restoration)

**Locations:** `rpart/R/predict.rpart.R` — `predict.rpart` (line 42); `rpart/R/residuals.rpart.R` — `residuals.rpart` (line 47); `rpart/R/xpred.rpart.R` — `xpred.rpart` (lines 23, 76)

**Original R Context:**

`object$na.action` (or `fit$na.action`) records which observations were dropped due to missing values. It is `NULL` when no observations were removed. After computing predictions or residuals, the code expands the result back to the full original length only when `na.action` is not `NULL`.

```r
# predict.rpart.R
if (missing(newdata) && !is.null(object$na.action))
    pred <- naresid(object$na.action, pred)

# residuals.rpart.R
if (!is.null(object$na.action)) naresid(object$na.action, resid) else resid

# xpred.rpart.R
if (is.null(m$na.action)) m$na.action <- na.rpart
...
if (!is.null(fit$na.action)) {
    temp <- as.integer(fit$na.action)
    xval <- xval[-temp]
    ...
}
```

**Python Equivalent:**

```python
# predict_rpart equivalent
if newdata is None and object.na_action is not None:
    pred = naresid(object.na_action, pred)

# residuals_rpart equivalent
resid = naresid(object.na_action, resid) if object.na_action is not None else resid

# xpred_rpart equivalent
if m.get("na_action") is None:
    m["na_action"] = na_rpart

...
if fit.na_action is not None:
    temp = np.array(fit.na_action, dtype=int)
    xval = np.delete(xval, temp - 1)  # R is 1-indexed; Python is 0-indexed
```

**Explanation:** `is.null(object$na.action)` maps to `object.na_action is None`. When the rpart model is a Python object, absent optional slots are initialized to `None`. Note the index adjustment: R uses 1-based indexing when recording dropped observation numbers, so subtract 1 when using them as Python 0-based indices.

---

### 4.6 Check for optional R attribute on a data object

**Locations:** `rpart/R/model.frame.rpart.R` — `model.frame.rpart` (lines 4, 8); `rpart/R/na.rpart.R` — `na.rpart` (line 4); `rpart/R/predict.rpart.R` — `predict.rpart` (line 11); `rpart/R/rpart.R` — `rpart` (lines 125, 293); `rpart/R/rpart.matrix.R` — `rpart.matrix` (line 12)

**Original R Context:**

R objects carry arbitrary named attributes. `attr(x, "name")` returns `NULL` when the attribute is absent. These attributes include `"terms"` (model formula metadata), `"na.action"` (dropped row indices), and `"dataClasses"` (column type annotations).

```r
# model.frame.rpart.R
m <- formula$model
if (!is.null(m)) return(m)
...
if (is.null(attr(m, "terms"))) {
    object <- eval(oc$object)
    m <- model.frame(object$terms, m, na.rpart)
}

# na.rpart.R
Terms <- attr(x, "terms")
if (!is.null(Terms)) yvar <- attr(Terms, "response") else yvar <- 0L

# predict.rpart.R
if (is.null(attr(newdata, "terms"))) {
    Terms <- delete.response(object$terms)
    newdata <- model.frame(Terms, newdata, ...)
    if (!is.null(cl <- attr(Terms, "dataClasses")))
        .checkMFClasses(cl, newdata, TRUE)
}

# rpart.R
if (!is.null(attr(m, "na.action"))) ans$na.action <- attr(m, "na.action")
```

**Python Equivalent:**

```python
import pandas as pd

# model_frame_rpart equivalent
m = formula.get("model")  # None if absent
if m is not None:
    return m
...
terms_attr = getattr(m, "attrs", {}).get("terms")  # or m.attrs.get("terms") for pandas
if terms_attr is None:
    obj = eval_context["object"]
    m = model_frame(obj.terms, m, na_rpart)

# na_rpart equivalent (pandas DataFrame with .attrs dict)
terms = m.attrs.get("terms")  # None if not set
yvar = terms.attrs.get("response") if terms is not None else 0

# predict_rpart equivalent
terms_attr = getattr(newdata, "attrs", {}).get("terms")
if terms_attr is None:
    Terms = delete_response(object.terms)
    newdata = model_frame(Terms, newdata, na_action=na_pass)
    cl = getattr(Terms, "attrs", {}).get("dataClasses")
    if cl is not None:
        check_mf_classes(cl, newdata, strict=True)

# rpart equivalent
na_action_attr = getattr(m, "attrs", {}).get("na.action")
if na_action_attr is not None:
    ans["na_action"] = na_action_attr
```

**Explanation:** R attributes on objects (set via `attr(x, "name") <- value`) have no direct Python equivalent. When translating rpart, model frames are typically represented as pandas DataFrames whose `.attrs` dict stores named metadata. `attr(x, "name")` becomes `x.attrs.get("name")`, returning `None` when absent. For plain Python objects, use `getattr(obj, "name", None)`. The idiom `is.null(attr(x, "name"))` becomes `x.attrs.get("name") is None`.

---

### 4.7 Inline assignment-and-test idiom

**Locations:** `rpart/R/printcp.R` — `printcp` (lines 12, 20); `rpart/R/predict.rpart.R` — `predict.rpart` (line 15); `rpart/R/summary.rpart.R` — `summary.rpart` (line 25); `rpart/R/text.rpart.R` — `text.rpart` (lines 18, 20)

**Original R Context:**

R permits assignment inside an expression. `is.null(var <- expr)` assigns `expr` to `var` and simultaneously tests whether the result is `NULL`. This is a common R idiom to avoid repeating the expression.

```r
# printcp.R
if (!is.null(cl <- x$call)) {
    dput(cl, control = NULL)
    cat("\n")
}

if (!is.null(used)) {
    cat("Variables actually used in tree construction:\n")
    print(sort(as.character(used)), quote = FALSE)
}

# predict.rpart.R
if (!is.null(cl <- attr(Terms, "dataClasses")))
    .checkMFClasses(cl, newdata, TRUE)

# summary.rpart.R
if (!is.null(temp <- x$variable.importance)) {
    temp <- round(100 * temp / sum(temp))
    ...
}

# text.rpart.R
if (!is.null(ylevels <- attr(x, "ylevels"))) col <- c(col, ylevels)
if (!is.null(srt <- list(...)$srt) && srt == 90) cxy <- rev(cxy)
```

**Python Equivalent:**

Python does not support assignment inside an `if` condition (walrus operator `:=` is available from Python 3.8+, though conventional style prefers a separate assignment line).

```python
# printcp equivalent — conventional two-line form
cl = x.get("call")  # or x.call
if cl is not None:
    dput(cl, control=None)
    print()

used = unique_used  # already computed above
if used is not None:
    print("Variables actually used in tree construction:")
    print(sorted(str(u) for u in used))

# predict_rpart equivalent
cl = getattr(Terms, "attrs", {}).get("dataClasses")
if cl is not None:
    check_mf_classes(cl, newdata, strict=True)

# summary_rpart equivalent
temp = getattr(x, "variable_importance", None)
if temp is not None:
    temp = np.round(100 * temp / temp.sum()).astype(int)
    ...

# text_rpart equivalent
ylevels = getattr(x, "attrs", {}).get("ylevels")
if ylevels is not None:
    col = col + list(ylevels)

srt = kwargs.get("srt")
if srt is not None and srt == 90:
    cxy = cxy[::-1]

# Alternative using walrus operator (Python 3.8+)
if (cl := x.get("call")) is not None:
    dput(cl, control=None)
    print()

if (temp := getattr(x, "variable_importance", None)) is not None:
    temp = np.round(100 * temp / temp.sum()).astype(int)
```

**Explanation:** The R pattern `is.null(var <- expr)` must be split into two Python statements: first assign the value, then test it. The walrus operator `:=` (Python 3.8+) allows the single-expression form `if (var := expr) is not None:`, which is the closest syntactic equivalent. Either style is acceptable; the two-line form is more readable and works on all Python 3 versions.

---

### 4.8 Check for model-level optional y field

**Locations:** `rpart/R/residuals.rpart.R` — `residuals.rpart` (line 8); `rpart/R/xpred.rpart.R` — `xpred.rpart` (lines 18, 27, 29)

**Original R Context:**

The rpart fit object optionally stores `y` (response) and `X` (predictor matrix) only when `y = TRUE` or `x = TRUE` was passed to `rpart()`. Code tests `is.null(fit$y)` and `is.null(fit$x)` before falling back to re-extracting from the original data.

```r
# residuals.rpart.R
y <- object$y
if (is.null(y)) y <- model.extract(model.frame(object), "response")

# xpred.rpart.R
Y <- fit$y
X <- fit$x
...
if (is.null(Y) || is.null(X)) {
    m <- fit$model
    if (is.null(m)) {
        m <- ...
        if (is.null(m$na.action)) m$na.action <- na.rpart
        ...
    }
    if (is.null(X)) X <- rpart.matrix(m)
    if (is.null(Y)) {
        Y <- model.extract(m, "response")
        ...
    }
}
```

**Python Equivalent:**

```python
# residuals_rpart equivalent
y = getattr(object, "y", None)
if y is None:
    y = model_extract(model_frame(object), "response")

# xpred_rpart equivalent
Y = getattr(fit, "y", None)
X = getattr(fit, "x", None)

if Y is None or X is None:
    m = getattr(fit, "model", None)
    if m is None:
        m = build_model_frame(fit)
        if m.get("na_action") is None:
            m["na_action"] = na_rpart
        m = eval_model_frame(m)
    if X is None:
        X = rpart_matrix(m)
    if Y is None:
        yflag = True
        Y = model_extract(m, "response")
        ...
    else:
        yflag = False
```

**Explanation:** Optional stored data on the rpart object that may or may not be present is represented in Python as `None`. `getattr(obj, "field", None)` safely retrieves the field and returns `None` if it is absent, mirroring R's behavior of returning `NULL` for unset list slots. The logical combination `is.null(Y) || is.null(X)` translates directly to `Y is None or X is None`.

---

### 4.9 Check for init sub-functions (summary, print, text)

**Locations:** `rpart/R/rpart.R` — `rpart` (lines 261, 263, 265)

**Original R Context:**

The `init` object returned by method-specific init functions (`rpart.anova`, `rpart.class`, etc.) may optionally contain `summary`, `print`, and `text` function slots. The main `rpart` function tests each with `is.null` and constructs the `functions` list accordingly.

```r
if (is.null(init$summary))
    stop("Initialization routine is missing the 'summary' function")
functions <- if (is.null(init$print)) list(summary = init$summary)
             else list(summary = init$summary, print = init$print)
if (!is.null(init$text)) functions <- c(functions, list(text = init$text))
```

**Python Equivalent:**

```python
# rpart equivalent
if init.get("summary") is None:
    raise ValueError("Initialization routine is missing the 'summary' function")

functions = {"summary": init["summary"]}
if init.get("print") is not None:
    functions["print"] = init["print"]
if init.get("text") is not None:
    functions["text"] = init["text"]
```

**Explanation:** When `init` is a Python `dict`, `init.get("key")` returns `None` if the key is absent, matching R's `NULL` for missing list slots. The R idiom of building the `functions` list conditionally maps cleanly to Python `dict` construction with `if key is not None:` guards.

---

### 4.10 Guard on optional xval parameter

**Locations:** `rpart/R/rpart.R` — `rpart` (line 114)

**Original R Context:**

`xval` comes from `rpart.control()`. When the control object returns `NULL` or `0`, cross-validation is skipped entirely.

```r
xval <- controls$xval
if (is.null(xval) || (length(xval) == 1L && xval == 0L) || method == "user") {
    xgroups <- 0L
    xval    <- 0L
}
```

**Python Equivalent:**

```python
xval = controls.get("xval")
if xval is None or (np.isscalar(xval) and xval == 0) or method == "user":
    xgroups = 0
    xval    = 0
```

**Explanation:** `is.null(xval)` becomes `xval is None`. The compound condition is otherwise a direct translation. `np.isscalar` guards the scalar comparison before testing `xval == 0`, since `xval` could be an array when provided as a group vector.
