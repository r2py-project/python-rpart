# Architecture Analysis: rpart R Package

**Version:** 4.1.27 (2026-03-26)  
**Analysis date:** 2026-05-05  
**Source:** `rpart/R/` (36 source files), `structural_analysis/R/` (JSON dependency maps),
`structural_analysis/dependency_levels.csv`, `rpart/man/` (28 Rd pages),
`rpart/vignettes/` (2 vignettes)

---

## Table of Contents

1. [Package Metadata and Dependencies](#1-package-metadata-and-dependencies)
2. [Public API Surface](#2-public-api-surface)
3. [Architectural Overview](#3-architectural-overview)
4. [Source File Inventory](#4-source-file-inventory)
5. [Internal Dependency Graph](#5-internal-dependency-graph)
6. [Topological Layer Analysis](#6-topological-layer-analysis)
7. [The `rpart` Object Structure](#7-the-rpart-object-structure)
8. [Splitting Methods and Plug-in Architecture](#8-splitting-methods-and-plug-in-architecture)
9. [Tree Construction Algorithm](#9-tree-construction-algorithm)
10. [Pruning Subsystem](#10-pruning-subsystem)
11. [Visualization Subsystem](#11-visualization-subsystem)
12. [Missing-Data Handling](#12-missing-data-handling)
13. [User-Defined Split Functions](#13-user-defined-split-functions)
14. [Cross-Validation Machinery](#14-cross-validation-machinery)
15. [Design Patterns and Observations](#15-design-patterns-and-observations)

---

## 1. Package Metadata and Dependencies

### Identity

| Field | Value |
|---|---|
| Package | rpart |
| Title | Recursive Partitioning and Regression Trees |
| Version | 4.1.27 |
| Date | 2026-03-26 |
| License | GPL-2 \| GPL-3 |
| Priority | recommended (ships with base R) |
| Repository | CRAN |
| URL | https://github.com/bethatkinson/rpart |

### Authors

| Name | Role |
|---|---|
| Terry M. Therneau | Author (algorithmic core, vignettes) |
| Beth Atkinson | Author and current maintainer |
| Brian Ripley | Translator — produced the initial R port; maintained 1999–2017 |

The package is a direct R implementation of the CART methodology introduced by Breiman, Friedman, Olshen, and Stone (1984).

### R-Level Dependencies

| Type | Package | Purpose |
|---|---|---|
| `Depends` | R ≥ 2.15.0 | Baseline runtime |
| `Depends` | `graphics` | High-level plotting (`plot`, `text`, `lines`, …) |
| `Depends` | `stats` | Model-frame machinery, `model.matrix`, `naresid`, etc. |
| `Depends` | `grDevices` | Device management (`dev.cur`, `postscript`, `col2rgb`) |
| `Suggests` | `survival` | Required only for survival-tree method (`rpart.exp`); not a hard dependency |

### Compiled Code

The `DESCRIPTION` field `NeedsCompilation: yes` reflects a non-trivial C back-end. Five compiled entry points are registered via `useDynLib(rpart, .registration = TRUE, .fixes = "C_")`:

| C Symbol | Called from | Purpose |
|---|---|---|
| `C_rpart` | `rpart.R` | Full tree growth (splitting, surrogate selection, cross-validation bookkeeping) |
| `C_pred_rpart` | `pred.rpart.R` | Navigate a new observation down the grown tree |
| `C_xpred` | `xpred.rpart.R` | Cross-validated predictions across a grid of complexity parameters |
| `C_rpartexp2` | `rpart.exp.R` | Amalgamate near-duplicate death times for exponential rescaling |
| `C_init_rpcallback` | `rpartcallback.R` | Wire up R environments for user-defined split callbacks |

---

## 2. Public API Surface

### Exported Functions (`NAMESPACE`)

```
export(meanvar, na.rpart, path.rpart, plotcp, post, printcp, prune,
       prune.rpart, rpart, rpart.control, rsq.rpart, snip.rpart, xpred.rpart)
export(rpart.exp)   # additionally exported for the test suite
```

Thirteen functions are exported, grouped by purpose:

| Category | Functions |
|---|---|
| **Fitting** | `rpart`, `rpart.control` |
| **Pruning** | `prune` (generic), `prune.rpart`, `snip.rpart` |
| **Prediction / Validation** | `xpred.rpart` |
| **Inspection / Diagnostics** | `printcp`, `path.rpart`, `na.rpart`, `rsq.rpart`, `meanvar` |
| **Visualisation** | `plotcp`, `post` |
| **Survival initialisation** | `rpart.exp` |

### S3 Method Dispatch Table

The package registers eleven S3 methods for the `"rpart"` class:

| Generic | Concrete method | Description |
|---|---|---|
| `labels` | `labels.rpart` | Generate branch-split label strings |
| `meanvar` | `meanvar.rpart` | Mean vs. deviance scatter plot (anova trees only) |
| `model.frame` | `model.frame.rpart` | Reconstruct the model frame from a fitted object |
| `plot` | `plot.rpart` | Draw the tree dendrogram |
| `post` | `post.rpart` | Export a PostScript presentation plot |
| `predict` | `predict.rpart` | Predict class / value / probability for new data |
| `print` | `print.rpart` | Textual tree display with indented node structure |
| `prune` | `prune.rpart` | Cost-complexity pruning at a given `cp` value |
| `residuals` | `residuals.rpart` | Compute usual, Pearson, or deviance residuals |
| `summary` | `summary.rpart` | Verbose per-node report including surrogates |
| `text` | `text.rpart` | Add node/edge labels to an existing `plot.rpart` |

### Semi-Internal Functions

Several functions are documented under `rpart-internal.Rd` and are technically exported or accessible but not intended for general use; they serve as a stable interface for the `ipred` package:

`pred.rpart`, `rpart.anova`, `rpart.class`, `rpart.matrix`, `rpart.poisson`, `rpartco`

---

## 3. Architectural Overview

rpart follows a three-tier design:

```
┌──────────────────────────────────────────────────────────────┐
│  Tier 1 – Public R API                                       │
│  rpart()  prune()  predict()  plot()  text()  summary()  …  │
└──────────────────────┬───────────────────────────────────────┘
                       │ calls
┌──────────────────────▼───────────────────────────────────────┐
│  Tier 2 – R Infrastructure                                   │
│  rpart.control   rpart.matrix   rpart.{anova,class,         │
│  poisson,exp}    rpartcallback  importance                   │
│  rpartco  rpart.branch  labels.rpart  formatg  …            │
└──────────────────────┬───────────────────────────────────────┘
                       │ .Call()
┌──────────────────────▼───────────────────────────────────────┐
│  Tier 3 – C Back-End                                         │
│  C_rpart   C_pred_rpart   C_xpred   C_rpartexp2             │
│  C_init_rpcallback                                           │
└──────────────────────────────────────────────────────────────┘
```

**Tier 1** provides the user-facing API: formula-based model fitting, generic S3 dispatch, and diagnostic/plotting utilities.

**Tier 2** handles data preparation (formula → numeric matrix, missing-value treatment), method-specific initialisation (four pluggable split methods plus user-defined), coordinate geometry for tree plotting, and the numeric formatting utility `formatg`.

**Tier 3** performs computationally intensive work in C: greedy recursive partitioning, surrogate-split search, cross-validation across the full cp sequence, and prediction routing down the fitted tree. The C code is structured around a dispatch table (`func_table.h`) that holds four function pointers per splitting method (init, split, eval, error), keeping the bookkeeping C code completely method-agnostic.

---

## 4. Source File Inventory

The 36 R source files and 47 user-defined functions (including nested helpers) are grouped below by subsystem.

### Fitting Core

| File | Functions | Role |
|---|---|---|
| `rpart.R` | `rpart` | Main entry point: formula parsing, method detection, calls C_rpart |
| `rpart.control.R` | `rpart.control` | Validate and bundle the nine tuning parameters |
| `rpart.matrix.R` | `rpart.matrix` | Convert a model frame to a numeric predictor matrix; handles factors and ordered factors |
| `importance.R` | `importance` | Compute variable-importance scores from primary and surrogate split records |
| `na.rpart.R` | `na.rpart` | Default `na.action`: drop rows missing the response or all predictors |

### Splitting Method Initialisers

Each method initialiser returns a list with components `y`, `parms`, `numresp`, `numy`, and optional `summary`/`print`/`text` functions that are stored in `fit$functions` and later invoked by `summary.rpart` and `text.rpart`.

| File | Function | Split strategy |
|---|---|---|
| `rpart.anova.R` | `rpart.anova` | Continuous response — minimise within-node MSE |
| `rpart.class.R` | `rpart.class` | Categorical response — minimise Gini or information impurity with alterable priors and a loss matrix |
| `rpart.poisson.R` | `rpart.poisson` | Count/rate response — Poisson deviance |
| `rpart.exp.R` | `rpart.exp`, `drate2` | Survival response (`Surv` object) — rescale time axis to approximate exponential hazard, then apply Poisson methods |

### Pruning Subsystem

| File | Functions | Role |
|---|---|---|
| `prune.R` | `prune` (generic) | S3 generic; dispatches to `prune.rpart` |
| `prune.rpart.R` | `prune.rpart` | Cost-complexity pruning: remove all nodes whose `complexity ≤ cp`, rebuild `cptable`, recompute `variable.importance` |
| `snip.rpart.R` | `snip.rpart` | Programmatic or interactive node removal: expand node ids to descendants, rebuild frame/splits/csplit/where |
| `snip.rpart.mouse.R` | `snip.rpart.mouse` | Interactive mouse-click node selection backed by `identify()` |

### Prediction

| File | Functions | Role |
|---|---|---|
| `predict.rpart.R` | `predict.rpart` | S3 predict: handle `newdata`, call `pred.rpart`, format output as vector/matrix/class/prob |
| `pred.rpart.R` | `pred.rpart` | Thin R wrapper around `C_pred_rpart`; builds index vectors into the frame |
| `xpred.rpart.R` | `xpred.rpart` | Cross-validated predictions: assemble the data, call `C_xpred`, return prediction matrix |

### Visualisation

| File | Functions | Role |
|---|---|---|
| `plot.rpart.R` | `plot.rpart` | Compute layout via `rpartco`, draw branches via `rpart.branch`, save parms in `rpart_env` |
| `text.rpart.R` | `text.rpart`, `oval`, `rectangle` | Label nodes and split edges; supports standard and "fancy" (ellipse/box) modes |
| `rpartco.R` | `rpartco`, `compress` | Compute (x, y) node coordinates; optionally apply the `compress` subtree-overlap algorithm |
| `rpart.branch.R` | `rpart.branch` | Compute horseshoe branch geometry (x, y vectors with NA pen-lifts) |
| `plotcp.R` | `plotcp` | Plot `cptable` cross-validation error ± 1-SE with optional 1-SE reference line |
| `post.R` | `post` (generic) | S3 generic |
| `post.rpart.R` | `post.rpart` | PostScript output via `plot.rpart` + `text.rpart` with `fancy = TRUE` |
| `meanvar.rpart.R` | `meanvar.rpart`, `meanvar` | Mean-vs-deviance scatter for leaf nodes (anova trees only) |
| `rsq.rpart.R` | `rsq.rpart` | Two-panel R² and relative cross-validation error plots |

### Inspection and Reporting

| File | Functions | Role |
|---|---|---|
| `print.rpart.R` | `print.rpart` | Compact indented text display of frame rows |
| `summary.rpart.R` | `summary.rpart` | Verbose per-node report: node stats, primary splits, surrogate splits |
| `printcp.R` | `printcp` | Tabular display of the `cptable` with root-node error header |
| `labels.rpart.R` | `labels.rpart` | Produce split-label strings for continuous and categorical splits; supports factor abbreviation |
| `path.rpart.R` | `path.rpart` | Return (or interactively select) the sequence of split labels from root to a node |
| `residuals.rpart.R` | `residuals.rpart` | Compute residuals; dispatches on method type (anova, class, poisson/exp) |
| `roc.rpart.R` | `roc.rpart`, `ss.compare` | ROC analysis for two-class classification trees |

### User-Defined Split Callback

| File | Functions | Role |
|---|---|---|
| `rpartcallback.R` | `rpartcallback` | Validate a user-supplied `list(init, split, eval)`, create isolated R environments, call `C_init_rpcallback` to wire the environments into the C callback mechanism |

### Package Utilities (`zzz.R`)

| Function | Purpose |
|---|---|
| `.onUnload` | Unload the shared library on package detach |
| `tree.depth` | Compute integer depth of each node from its binary node number (`floor(log2(node))`) |
| `string.bounding.box` | Measure multi-line string dimensions for the fancy plot layout |
| `node.match` | Match user-supplied node numbers to the fitted frame, with informative warnings |
| `descendants` | Build a Boolean ancestor matrix used by `path.rpart` |
| `rpart_env` | Package-level environment for persisting plot parameters across `plot`/`text` calls |

### Formatting Utility

| File | Function | Role |
|---|---|---|
| `formatg.R` | `formatg` | Apply C-style `%g` formatting to numeric vectors and matrices; used by all four method initialisers and `labels.rpart` |

### Model-Frame Method

| File | Function | Role |
|---|---|---|
| `model.frame.rpart.R` | `model.frame.rpart` | Reconstruct the model frame from a fitted object or from a `predict` call, navigating through the original call chain |

---

## 5. Internal Dependency Graph

Internal dependencies (function calling function within the package) form a directed acyclic graph with one self-recursive node (`compress`). The table below summarises the adjacency of each function.

### Notable Dependency Chains

```
rpart ──► rpart.matrix
      ──► rpart.control
      ──► rpartcallback
      ──► importance
      ──► rpart.anova / rpart.class / rpart.poisson / rpart.exp
               └──► formatg
               └──► drate2  (rpart.exp only)

predict.rpart ──► pred.rpart        (→ C_pred_rpart)
              ──► rpart.matrix

prune.rpart ──► snip.rpart ──► snip.rpart.mouse ──► rpartco ──► tree.depth
                                                 └──► rpart.branch
            └──► importance

plot.rpart ──► rpartco ──► tree.depth
           └──► rpart.branch

text.rpart ──► rpartco
           ──► labels.rpart ──► formatg
           ──► rpart.branch
           ──► string.bounding.box
           ──► oval / rectangle

print.rpart ──► prune.rpart (optional, when cp supplied)
            ──► tree.depth
            ──► labels.rpart

path.rpart ──► labels.rpart
           ──► rpartco
           ──► descendants
           ──► node.match
```

### Unique Language Dependencies by Category

The R functions collectively depend on approximately 100 distinct base-R functions. The most frequently used across the codebase are:

- **Type coercion / testing:** `is.null`, `is.na`, `is.numeric`, `is.matrix`, `is.list`, `is.character`, `as.integer`, `as.double`, `as.character`, `as.numeric`
- **Vector / matrix operations:** `c`, `cbind`, `rbind`, `match`, `which`, `any`, `all`, `length`, `nrow`, `ncol`, `names`, `attr`, `cumsum`, `seq`, `rep`, `sort`, `unique`, `tapply`, `lapply`, `unlist`
- **Control / environment:** `stop`, `warning`, `missing`, `return`, `on.exit`, `list`, `get`, `assign`
- **Formatting / output:** `cat`, `format`, `paste0`, `sprintf`, `paste`, `signif`, `print`, `format`
- **Modelling infrastructure:** `model.frame`, `model.matrix`, `model.response`, `model.weights`, `model.offset`, `model.extract`, `delete.response`, `naresid`, `na.pass`
- **Graphics:** `plot`, `text`, `lines`, `segments`, `axis`, `par`, `polygon`, `abline`, `legend`, `dev.cur`, `col2rgb`

---

## 6. Topological Layer Analysis

The dependency-level analysis (`structural_analysis/dependency_levels.csv`) stratifies all 47 functions into 6 layers based on the internal call graph (longest-path from any entry point). Layer 0 contains the entry points; deeper layers are more fundamental utilities called by higher layers.

### Layer 0 — Entry Points (18 functions)

These functions have no internal callers; they are the direct targets of user code or S3 dispatch.

| Function | File | Leaf? | Children (internal calls) |
|---|---|---|---|
| `rpart` | `rpart.R` | No | `rpart.matrix`, `rpartcallback`, `rpart.control`, `importance`, `rpart.anova`, `rpart.class`, `rpart.exp`, `rpart.poisson` |
| `predict.rpart` | `predict.rpart.R` | No | `pred.rpart`, `rpart.matrix` |
| `print.rpart` | `print.rpart.R` | No | `prune.rpart`, `tree.depth`, `labels.rpart` |
| `plot.rpart` | `plot.rpart.R` | No | `rpartco`, `rpart.branch` |
| `text.rpart` | `text.rpart.R` | No | `rpartco`, `labels.rpart`, `rpart.branch`, `string.bounding.box`, `oval`, `rectangle` |
| `path.rpart` | `path.rpart.R` | No | `labels.rpart`, `descendants`, `rpartco`, `node.match` |
| `residuals.rpart` | `residuals.rpart.R` | No | `model.frame.rpart` |
| `roc.rpart` | `roc.rpart.R` | No | `ss.compare` |
| `rsq.rpart` | `rsq.rpart.R` | No | `printcp` |
| `xpred.rpart` | `xpred.rpart.R` | No | `rpart.matrix`, `na.rpart`, `rpartcallback`, `rpart.anova`, `rpart.class`, `rpart.exp`, `rpart.poisson` |
| `summary.rpart` | `summary.rpart.R` | **Leaf** | — |
| `meanvar.rpart` | `meanvar.rpart.R` | **Leaf** | — |
| `meanvar` | `meanvar.rpart.R` | **Leaf** | — |
| `plotcp` | `plotcp.R` | **Leaf** | — |
| `post` | `post.R` | **Leaf** | — |
| `post.rpart` | `post.rpart.R` | **Leaf** | — |
| `prune` | `prune.R` | **Leaf** | — |
| `.onUnload` | `zzz.R` | **Leaf** | — |

**Observation:** `summary.rpart` and `post.rpart` are leaves at level 0 because they call only base-R functions (`dput`, `cat`, `plot`, `text`) directly without invoking any other internal rpart function. This means they directly encode formatting and layout logic rather than delegating it.

### Layer 1 — First-Order Dependencies (18 functions)

Called by level-0 functions; many are method initialisers or infrastructure pieces.

| Function | File | Leaf? | Called by |
|---|---|---|---|
| `labels.rpart` | `labels.rpart.R` | No | `path.rpart`, `print.rpart`, `text.rpart` |
| `model.frame.rpart` | `model.frame.rpart.R` | No | `residuals.rpart` |
| `prune.rpart` | `prune.rpart.R` | No | `print.rpart` |
| `rpart.anova` | `rpart.anova.R` | No | `rpart`, `xpred.rpart` |
| `rpart.class` | `rpart.class.R` | No | `rpart`, `xpred.rpart` |
| `rpart.exp` | `rpart.exp.R` | No | `rpart`, `xpred.rpart` |
| `rpart.poisson` | `rpart.poisson.R` | No | `rpart`, `xpred.rpart` |
| `pred.rpart` | `pred.rpart.R` | **Leaf** | `predict.rpart` |
| `printcp` | `printcp.R` | **Leaf** | `rsq.rpart` |
| `rpart.control` | `rpart.control.R` | **Leaf** | `rpart` |
| `rpart.matrix` | `rpart.matrix.R` | **Leaf** | `predict.rpart`, `rpart`, `xpred.rpart` |
| `rpartcallback` | `rpartcallback.R` | **Leaf** | `rpart`, `xpred.rpart` |
| `ss.compare` | `roc.rpart.R` | **Leaf** | `roc.rpart` |
| `oval` | `text.rpart.R` | **Leaf** | `text.rpart` |
| `rectangle` | `text.rpart.R` | **Leaf** | `text.rpart` |
| `descendants` | `zzz.R` | **Leaf** | `path.rpart` |
| `node.match` | `zzz.R` | **Leaf** | `path.rpart` |
| `string.bounding.box` | `zzz.R` | **Leaf** | `text.rpart` |

### Layer 2 — Second-Order Dependencies (5 functions)

| Function | File | Leaf? | Called by |
|---|---|---|---|
| `formatg` | `formatg.R` | **Leaf** | `labels.rpart`, `rpart.anova`, `rpart.class`, `rpart.exp`, `rpart.poisson` |
| `importance` | `importance.R` | **Leaf** | `prune.rpart`, `rpart` |
| `na.rpart` | `na.rpart.R` | **Leaf** | `model.frame.rpart`, `xpred.rpart` |
| `drate2` | `rpart.exp.R` | **Leaf** | `rpart.exp` |
| `snip.rpart` | `snip.rpart.R` | No | `prune.rpart` |

### Layer 3 — Third-Order Dependencies (1 function)

| Function | File | Leaf? | Called by |
|---|---|---|---|
| `snip.rpart.mouse` | `snip.rpart.mouse.R` | No | `snip.rpart` |

### Layer 4 — Fourth-Order Dependencies (2 functions)

| Function | File | Leaf? | Called by |
|---|---|---|---|
| `rpart.branch` | `rpart.branch.R` | **Leaf** | `plot.rpart`, `snip.rpart.mouse`, `text.rpart` |
| `rpartco` | `rpartco.R` | No | `path.rpart`, `plot.rpart`, `snip.rpart.mouse`, `text.rpart` |

**Observation:** `rpartco` and `rpart.branch` sit at layer 4 despite being called by several level-0 functions (`plot.rpart`, `text.rpart`, `path.rpart`). They receive this layer assignment because `snip.rpart.mouse` (layer 3) is their deepest caller, which is reachable from `prune.rpart` (layer 1) via `snip.rpart` (layer 2). The coordinate-computation infrastructure is thus the deepest reusable layer under the visualisation and interactive editing subsystems.

### Layer 5 — Deepest Utilities (2 functions)

| Function | File | Leaf? | Called by |
|---|---|---|---|
| `compress` | `rpartco.R` | **Leaf** | `rpartco` (also self-recursive) |
| `tree.depth` | `zzz.R` | **Leaf** | `print.rpart`, `rpartco` |

`tree.depth` computes node depths from binary node numbering via `floor(log2(node))`. It is the single most-fundamental utility in the package's geometry and display stack.

`compress` is a self-recursive function that implements the subtree-overlap elimination algorithm inside `rpartco`. It operates on the x-coordinate array by walking the tree in a depth-first manner and sliding right-hand subtrees leftward to eliminate unnecessary gaps.

### Summary Statistics

| Layer | Function count | Leaf count | Leaf % |
|---|---|---|---|
| 0 | 18 | 8 | 44% |
| 1 | 18 | 11 | 61% |
| 2 | 5 | 4 | 80% |
| 3 | 1 | 0 | 0% |
| 4 | 2 | 1 | 50% |
| 5 | 2 | 2 | 100% |
| **Total** | **47** | **26** | **55%** |

More than half of all functions are leaves (no internal dependencies), reflecting good single-responsibility design for the utility functions.

---

## 7. The `rpart` Object Structure

The S3 object of class `"rpart"` returned by `rpart()` is a named list. The mandatory components are:

| Component | Type | Description |
|---|---|---|
| `frame` | `data.frame` | One row per node; columns: `var` (split variable name, `<leaf>` for terminal nodes), `n` (observations), `wt` (sum of weights), `dev` (node deviance), `yval` (fitted response), `complexity`, `ncompete`, `nsurrogate` |
| `frame$yval2` | matrix | Present for class and Poisson trees; contains class counts, probabilities, and node probability |
| `where` | integer vector | Maps each training observation to its leaf row in `frame` |
| `call` | `call` | The original call (fully named) |
| `terms` | `terms` object | Formula summary for model-frame reconstruction |
| `splits` | numeric matrix | One row per split (primary + competitor + surrogate); columns: `count`, `ncat`, `improve`, `index`, `adj` |
| `csplit` | integer matrix | Category assignments (1=left, 2=absent, 3=right) for factor splits |
| `method` | character | `"anova"`, `"poisson"`, `"class"`, `"exp"`, or `"user"` |
| `cptable` | matrix | Cross-validation results indexed by cp values; columns: CP, nsplit, rel error, xerror, xstd |
| `variable.importance` | named numeric | Summed primary-split improvement + surrogate-adjusted contributions |
| `numresp` | integer | Length of the per-node response vector |
| `parms` | list | Parameters recorded from the method initialiser |
| `control` | list | Parameters as returned by `rpart.control()` |
| `functions` | list | The method's `summary`, `print`, and `text` functions stored for generic dispatch |
| `ordered` | logical vector | Which predictor variables were ordered factors |

Optional components stored conditionally:
- `model` — the full model frame (if `model = TRUE`)
- `x` — predictor matrix (if `x = TRUE`)
- `y` — response vector (if `y = TRUE`)
- `na.action` — NA action record

Attributes:
- `attr(fit, "xlevels")` — factor levels for each categorical predictor
- `attr(fit, "ylevels")` — factor levels for the response (classification trees)

The binary node numbering scheme used in `rownames(frame)` (root = 1, left child of n = 2n, right child = 2n+1) is a key architectural invariant used throughout the codebase for parent lookup (`node %/% 2`), depth computation (`floor(log2(node))`), and descendant testing.

---

## 8. Splitting Methods and Plug-in Architecture

### Built-In Methods

The four built-in splitting methods each supply an initialisation function that returns a standardised list consumed by `rpart()`.

#### `anova` — Regression Trees
- **Response:** continuous numeric
- **Impurity:** within-node mean squared error (MSE)
- **Node prediction:** mean of response values
- **Variable importance:** scaled by total SS (unique to this method; others report raw improvement)

#### `class` — Classification Trees
- **Response:** factor
- **Impurity:** Gini index or information gain (configurable via `parms$split`)
- **Prior handling:** altered-priors technique to incorporate asymmetric misclassification losses
- **Node prediction:** plurality class; `yval2` stores class counts, class probabilities, and node probability
- **Loss matrix:** symmetric or asymmetric; diagonal must be zero

#### `poisson` — Rate Trees
- **Response:** two-column matrix of (exposure-time, event-count), or a single count with optional offset
- **Impurity:** Poisson deviance
- **Node prediction:** estimated event rate

#### `exp` — Survival Trees
- **Response:** `Surv` object (from the `survival` package)
- **Strategy:** rescale the time axis to an approximately exponential baseline hazard using `C_rpartexp2`, then treat the problem as Poisson
- **Rescaling:** piecewise constant hazard estimated on unique death times; cumulative hazard is used to stretch time so that the baseline rate is 1.0 throughout the observation period
- **Benefits:** makes early splits equivalent to the local full-likelihood method of LeBlanc and Crowley

### Plug-in Architecture

The C back-end is extensible via a dispatch table (`func_table.h`) that maps method integers to four function-pointer slots: `init_split`, `choose_split`, `eval`, `error`. Method integer 4 is reserved for user-defined (R-level callback) splits.

At the R level, a user-defined method is supplied as `method = list(init, split, eval)` and dispatched via `rpartcallback`, which:
1. Validates that all three functions are present
2. Constructs isolated R environments containing persistent `yback`, `xback`, `wback`, `nback` buffers
3. Calls `C_init_rpcallback` to bind these environments into the C callback mechanism

This architecture allows user-written splitting logic to run inside the same bookkeeping framework as built-in methods, at the cost of significantly higher overhead due to repeated R→C→R round-trips during node evaluation.

---

## 9. Tree Construction Algorithm

The complete workflow of `rpart()` is:

1. **Model frame construction** — Parse the formula; apply the `na.action` (default: `na.rpart`, which drops rows missing the response or all predictors while preserving rows missing only predictors); extract response, weights, offset, and the predictor matrix via `rpart.matrix`.

2. **Method detection** — If `method` is not supplied, infer: `Surv` response → `"exp"`, matrix response → `"poisson"`, factor → `"class"`, otherwise → `"anova"`.

3. **Method initialisation** — Call the appropriate `rpart.<method>()` function (or, for user splits, call `mlist$init()`). This validates the response, incorporates the offset, sets method parameters, and returns the standardised `init` list including embedded `summary`/`print`/`text` closures.

4. **Factor encoding** — Identify categorical predictor levels via `.getXlevels`; encode factor columns in `X` as integer category counts. Ordered factors are treated as continuous by setting their category count to 0.

5. **Cross-validation group assignment** — Create random fold membership `xgroups` based on `controls$xval` (default 10). If `xval = 0`, cross-validation is skipped.

6. **C_rpart call** — The main tree-growing routine receives the encoded predictor matrix, response, weights, category counts, method integer, control parameters, cross-validation groups, and variable costs. It returns `rpfit`: raw node data, split records, and cross-validation error estimates.

7. **Post-processing** — Reconstruct R objects: build `frame` data frame, create `splits` matrix with proper row labels, handle ordered-factor splits (which are stored in C as continuous but must be re-encoded as categorical for display), create `csplit` matrix, attach `yval2` for class/Poisson responses, and compute `variable.importance` via `importance()`.

8. **Object assembly** — Bundle all components into the `rpart` list, attach attributes (`xlevels`, `ylevels`), and assign class `"rpart"`.

### Surrogate Splits

When a primary split variable is missing for an observation, rpart uses surrogate splits in order of their adjusted agreement with the primary. The number of surrogates retained is controlled by `maxsurrogate`; searching for surrogates accounts for approximately half of the C computation time and can be disabled by setting `maxsurrogate = 0`.

### Variable Importance Computation

The `importance()` function accumulates, for each variable, the sum of:
- The deviance improvement of every primary split where the variable was chosen (scaled by total node deviance for `anova`, unscaled otherwise)
- The improvement of each primary split where the variable appeared as a surrogate, multiplied by the surrogate's adjusted concordance with the primary

This ensures that variables which frequently appear as reliable surrogates are credited even when they are not chosen as primary splitters — an important distinction from simple split-count importance.

---

## 10. Pruning Subsystem

### Cost-Complexity Pruning (`prune.rpart`)

The `cptable` stored in the fitted object encodes a sequence of nested subtrees, each optimal for a range of the complexity parameter `cp`. `prune.rpart` operates as follows:

1. Identify all non-leaf nodes in `frame` whose `complexity ≤ cp` — these are to be collapsed.
2. Call `snip.rpart(tree, toss)` to produce the structurally smaller tree.
3. Trim the `cptable` to the rows that remain relevant, setting the last row's cp value to the requested level.
4. Recompute `variable.importance` on the pruned tree.

### Node Removal (`snip.rpart`)

`snip.rpart` is a general-purpose subtree removal routine used both by `prune.rpart` and directly by users (programmatically or interactively via `snip.rpart.mouse`):

1. Expand the target node set by finding all descendants via the binary parent relationship (`node %/% 2`).
2. Determine which rows become new leaves and which are simply discarded.
3. Thin the `splits` and `csplit` matrices to remove irrelevant rows.
4. Rebuild the `where` vector by walking the original leaf assignments upward to the nearest surviving node.

### Interactive Pruning (`snip.rpart.mouse`)

`snip.rpart.mouse` uses `identify()` to let users click on nodes in a live plot. A single click on a non-leaf node displays its statistics; a double-click (second click on the same node) erases its subtree visually by overplotting in the background colour and adds the node to the toss list.

### Choosing a cp Value

The `plotcp()` function visualises the cross-validation error (`xerror ± xstd`) against cp values from `cptable`. The `1-SE rule` (choose the simplest tree within one standard error of the minimum cross-validation error) is recommended by the CART authors and is visually supported by the horizontal reference line drawn at `xerror[min] + xstd[min]`. The leftmost cp value whose mean error falls at or below this line is the recommended choice.

---

## 11. Visualization Subsystem

### Coordinate Computation (`rpartco`)

Node coordinates are computed in two stages:

**Vertical (y) coordinates:**
- `uniform = TRUE`: nodes at depth `d` receive `y = (max_depth + 1 − d) / max(max_depth, 4)` — equal spacing.
- `uniform = FALSE` (default): y-coordinates are proportional to the deviation from the parent, so branches are scaled by split improvement. A minimum branch length of `minbranch × average_step` prevents splits with zero improvement from producing invisible branches.

**Horizontal (x) coordinates:**
1. Leaf nodes are spaced at integer positions `1, 2, …, n_leaves`.
2. Interior nodes are placed at the midpoint of their children.
3. Optionally (`compress = TRUE`), the `compress()` recursive subroutine slides right-hand subtrees leftward by the minimum gap needed to avoid overlap, using a slab-metaphor algorithm that propagates left/right extent vectors up the tree.

Plot parameters are persisted in the package-level `rpart_env` environment (keyed by device number via `paste0("device", dev.cur())`), enabling `text.rpart` and `rpart.branch` to recover the layout from a preceding `plot.rpart` call without requiring parameter re-specification.

### Branch Drawing (`rpart.branch`)

Branches are drawn as horseshoe or V-shapes depending on the `branch` parameter (0 = V, 1 = square shoulder). The geometry is encoded as a matrix of x and y columns with `NA` entries as pen-lift signals, passed directly to `lines()`.

### Label Generation (`labels.rpart`)

`labels.rpart` produces one label per node representing the decision rule on the incoming edge:
- **Continuous variables:** `"< cutpoint"` or `">= cutpoint"` (direction encoded by the sign of `ncat` in the splits matrix)
- **Factor variables:** a comma-separated or single-letter set of factor levels assigned to each side, optionally abbreviated via `abbreviate()`

The `fancy` mode in `text.rpart` places labels on the edges (computed as midpoints of the horseshoe geometry) rather than at node centres, and renders interior nodes as ellipses and terminal nodes as rectangles.

---

## 12. Missing-Data Handling

rpart's NA strategy is one of its architectural differentiators from simpler tree implementations.

**During fitting:**
- `na.rpart` (the default `na.action`) removes rows where the response is missing but retains rows with missing predictor values. These rows contribute to node counts but are routed via surrogate splits when their primary split variable is absent.
- Surrogate splits are searched automatically during tree construction and stored in the `splits` matrix (after the primary and competitor splits for each node). The `usesurrogate` control parameter determines what happens when all surrogates are also missing: `0` = observation stays at current node, `1` = no further routing, `2` = send to the majority child direction (recommended by Breiman et al.).

**During prediction:**
- `predict.rpart` uses `na.action = na.pass` by default, passing observations with missing values down the tree using the same surrogate mechanism as during fitting.
- The `naresid()` function from base R is used to reinsert missing observations into the result vector at their original positions after prediction.

---

## 13. User-Defined Split Functions

As documented in the vignette *"User written splitting functions for RPART"* (Terry Therneau), a user can supply `method = list(init, split, eval)` to `rpart()`. The three functions play the following roles:

| Function | Called | Purpose |
|---|---|---|
| `init(y, offset, parms, wt)` | Once at start | Validate/transform response; return standardised list including `y`, `numy`, `numresp`, and optional `summary`/`print`/`text` closures |
| `eval(y, wt, parms)` | Once per node | Compute the node's fitted value (`label`) and impurity measure (`deviance`) |
| `split(y, wt, x, parms, continuous)` | Once per covariate per potential split | Return `goodness` (vector of split utilities) and `direction` (±1 for continuous, ordered levels for categorical) |

The `rpartcallback` function creates fixed-size R vectors (`yback`, `xback`, `wback`, `nback`) in an isolated environment. The C code refills these buffers on each callback invocation, avoiding repeated R object allocation. Expressions (`expr1` for split, `expr2` for eval) are quoted and evaluated in this environment, providing a performance compromise between fully compiled splits (10–100× faster) and fully interpreted R loops.

Cross-validation does not run automatically for user-defined splits (because it would require calling the user's slow R functions many more times); `xpred.rpart` must be used explicitly.

**Constraint for categorical predictors:** The split function must return goodness values for the `k−1` ordered groupings of category levels by their within-group mean response. This is guaranteed to be optimal for a large class of loss functions (squared error, Poisson deviance, Gini, information); for general loss functions it is an approximation.

---

## 14. Cross-Validation Machinery

Cross-validation in rpart deviates from the simple "refit on each fold" pattern:

1. **Single full fit:** `C_rpart` receives the fold-membership vector `xgroups`. The C code, during tree growth, simultaneously builds the full tree and computes held-out predictions for each observation in its fold, across all cp values in the nested-subtree sequence.

2. **Complexity parameter grid:** The grid is the set of geometric means of adjacent cp breakpoints (so that each value lies in the interior of its interval). The full sequence of nested subtrees is enumerated efficiently during tree construction.

3. **Output:** The `cptable` matrix contains, for each cp value, the mean and standard deviation of relative cross-validation error across all folds.

4. **Standalone cross-validation:** `xpred.rpart(fit, xval, cp)` re-executes cross-validation (via `C_xpred`) outside the initial fit, using the already-fitted object's data or reconstructed data. It returns a matrix with one row per observation and one column per cp value, enabling the user to compute custom loss functions on the held-out predictions.

---

## 15. Design Patterns and Observations

### Extensibility via Method Initialisers

The four built-in splitting methods (anova, class, poisson, exp) and the user-defined split mechanism all share the same initialisation contract. `rpart()` is agnostic to the method beyond the integer index passed to C; all method-specific logic is encapsulated in the initialiser's return value. This is analogous to the strategy pattern: the algorithm skeleton resides in C, and the impurity function is swapped in at setup time.

### Closure-Based Polymorphism

The `summary`, `print`, and `text` functions returned by each method initialiser are stored as closures in `fit$functions`. When `summary.rpart`, `print.rpart`, or `text.rpart` need to format node values, they retrieve and call the appropriate closure without any method dispatch — effectively a manually managed vtable. The vignette notes a subtle environment management concern: closures created inside an initialiser retain references to all local variables in their enclosing frame. To prevent large data objects from being accidentally retained in the fitted model, initialisers reset the environment of these closures to `.GlobalEnv` or, in `rpart()`, to the package namespace (`asNamespace("rpart")`).

### Device-Scoped Plot State

The `rpart_env` package environment stores the current plot parameters keyed by `paste0("device", dev.cur())`. This allows `text.rpart`, `rpart.branch`, `snip.rpart.mouse`, and `rpartco` to recover the layout established by a preceding `plot.rpart` call, enabling the standard R idiom:

```r
plot(fit)
text(fit)
```

where `text` "remembers" the coordinate system without requiring re-computation.

### Binary Node Numbering

The decision to number nodes as `root=1, left=2n, right=2n+1` (Breiman et al.'s original convention) is load-bearing throughout the codebase:
- Parent lookup: `node %/% 2`
- Depth: `floor(log2(node))`
- Sibling: `ifelse(node %% 2, node-1, node+1)`
- Ancestor testing: repeated halving until reaching 1

This scheme limits maximum depth to 30 (as nodes must fit in a 32-bit signed integer); this constraint is enforced in `rpart.control`.

### Separation of Display and Data

The `frame` data frame in the fitted object is designed to be self-contained for display: it records variable names, counts, deviances, and fitted values. The raw predictor matrix and response are not stored by default (`x = FALSE`, `y = TRUE` by default). This keeps fitted objects compact — a deliberate choice in a package intended to handle large datasets.

### Functional Depth vs. Call Frequency

The deepest functions (`tree.depth` at layer 5, `compress` at layer 5) are called infrequently (only during coordinate computation), while the broadest entry points (`rpart` at layer 0) are the most-used. The design correctly places the most-reused utilities deepest in the dependency stack without incurring the overhead that depth would suggest — coordinate computation is O(n_nodes), while the C-based tree growth is the computational bottleneck.

### C Extension Points

The `func_table.h` dispatch table in the C code is the primary extension mechanism for adding new splitting methods natively. As noted in the user-code vignette, adding a new built-in method requires four C functions (init, split, eval, error) plus expanding the table and updating the method integer mapping in `rpart()`. The R-level callback mechanism (`method = list(...)`) provides a slower but significantly simpler alternative that requires no C programming.

---

*End of analysis. Generated from source reading, structural JSON analysis, topological level computation, and vignette narrative.*
