# r2py_rpart

A Python port of the R package [`rpart`](https://github.com/bethatkinson/rpart) (Recursive Partitioning and Regression Trees). `r2py_rpart` reimplements rpart's original C recursive-partitioning engine — compiled directly from a lightly adapted copy of the C sources and driven from Python via [`cffi`](https://cffi.readthedocs.io/) — and translates rpart's R-level functions (formula handling, pruning, printing, plotting, prediction, cross-validation, ...) into Python with `numpy`/`pandas`, aiming for output that matches R's `rpart` as closely as possible.

Trees are fit using the same recursive-partitioning algorithm as R's `rpart`: classification, regression (anova), Poisson/exponential (survival), and user-defined splitting methods are all supported, along with cost-complexity pruning, surrogate splits for missing data, and cross-validated complexity tables.

## Installation

```bash
pip install r2py_rpart
```

Prebuilt wheels are published for Python 3.10–3.14 on Linux (x86_64/aarch64), macOS (Intel/Apple Silicon), and Windows (x86_64). If a wheel isn't available for your platform, `pip` will build from source, which requires a C/C++ compiler (GCC, Clang, or MinGW-w64 on Windows) — no R installation is needed.

## Quick start

```python
import pandas as pd
from r2py_rpart import rpart, print_rpart, printcp, prune, plot_rpart, text_rpart

iris = pd.read_csv("iris.csv")
iris["species"] = iris["species"].astype("category")

# Classification tree
fit = rpart("species ~ .", data=iris, method="class", control={"cp": 0.0001, "minsplit": 5})
print_rpart(fit)
printcp(fit)

# Prune with a chosen complexity parameter
pruned = prune(fit, cp=0.02)

import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 8))
plot_rpart(pruned, ax=ax)
text_rpart(pruned, ax=ax)
fig.savefig("tree.pdf")
```

See [`examples/classification_tree.py`](examples/classification_tree.py) and [`examples/regression_tree.py`](examples/regression_tree.py) for complete, runnable end-to-end examples (each paired with the equivalent R script and side-by-side R/Python output for comparison).

## API overview

`r2py_rpart` mirrors the public functions of R's `rpart` package by name:

| Purpose | Function(s) |
|---|---|
| Fit a tree | `rpart`, `rpart_control` |
| Prune | `prune`, `prune_rpart`, `snip_rpart`, `snip_rpart_mouse` |
| Predict | `predict_rpart`, `pred_rpart`, `xpred_rpart` |
| Inspect / summarize | `print_rpart`, `summary_rpart`, `printcp`, `path_rpart`, `labels_rpart` |
| Plot | `plot_rpart`, `text_rpart`, `plotcp`, `meanvar_rpart`, `post_rpart`, `rsq_rpart` |
| Diagnostics | `residuals_rpart`, `importance`, `roc_rpart` |

## Testing

```bash
pip install -e . pytest
pytest tests/
```

Many tests compare `r2py_rpart` output against R's `rpart` running via `rpy2`, so an R installation with the `rpart` package is required to run the full parity suite.

## License

`r2py_rpart` is a derivative work of R's `rpart` package and is distributed, like its upstream, under the GNU General Public License v2 or later (GPL-2.0-or-later). See [`LICENSE`](LICENSE) for the full text and [`NOTICE`](NOTICE) for attribution to the original `rpart` authors.

## Authors

- Yufei Cai (ycai9@nd.edu)
- Jun Li (jun.li@nd.edu)

University of Notre Dame
