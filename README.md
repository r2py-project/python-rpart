# python-rpart

**A systematic, AI-assisted conversion of the R package `rpart` to Python.**

This repository documents and contains the complete conversion of [`rpart`](https://cran.r-project.org/package=rpart) (version 4.1.27) — the reference implementation of the CART (Classification and Regression Trees) methodology of Breiman, Friedman, Olshen, and Stone (1984) — into an installable Python package, `r2py_rpart`. The full methodology, findings, and results are documented in the accompanying technical report, [`docs/report/main.pdf`](docs/report/main.pdf).

## Overview

`rpart` is one of the most widely used machine learning libraries in the R ecosystem: a *recommended* package shipped with every R installation, providing decision-tree fitting for continuous, categorical, count, and survival responses. Despite the centrality of decision trees to modern machine learning, no faithful Python port of `rpart` existed that preserved its full feature set — surrogate splits for missing-data handling, four built-in splitting methods, a user-defined split callback mechanism, cost-complexity pruning, and the complete cross-validation and visualization infrastructure.

Rather than reimplementing the CART algorithm from scratch, this project reuses `rpart`'s original, validated C source code directly. The C sources are compiled as a standalone shared library — behind a layer of fake R C API headers that removes the runtime dependency on `libR.so` — and called from Python via [`cffi`](https://cffi.readthedocs.io/). The R source layer, all 47 functions across 36 files, is separately converted to Python function by function, in a dependency-aware order, guided by 172 machine-generated language-construct conversion guides. This strategy confines the entire correctness burden to the narrow, five-entry-point R-to-C interface, and produces a self-contained package that requires neither an R runtime nor any external bridging layer such as `rpy2` or `reticulate` at run time.

The resulting package's test suite comprises 846 tests spanning its full public interface, of which 844 pass and 2 are permanently marked `xfail`, documenting a single, structurally unfixable formatting divergence from R (R's `dput()`-based unevaluated-call-expression printing).

## Repository Structure

| Path | Contents |
|---|---|
| [`rpart/`](rpart/) | Unmodified R package source (`rpart` version 4.1.27), as obtained from CRAN; the canonical reference against which every phase of the conversion is checked. |
| [`r2py_rpart/`](r2py_rpart/) | The installable Python package. Managed as a git subtree linked to [`github.com/r2py-project/r2py_rpart`](https://github.com/r2py-project/r2py_rpart), so it can be versioned and published to PyPI independently of this repository. |
| [`c_refactor_analysis/`](c_refactor_analysis/) | C dependency-graph analysis artifacts (Phase 1). |
| [`r_extern_analysis/`](r_extern_analysis/) | R external item extraction CSVs, fake-header implementation guides, and fake-header conversion guides (Phases 2–4). |
| [`structural_analysis/`](structural_analysis/) | R structural dependency analysis JSONs and dependency-graph artifacts (Phase 6). |
| [`language_dependency_analysis/`](language_dependency_analysis/) | Per-file language-dependency CSVs and 172 R-to-Python conversion guides (Phase 8). |
| [`conversion_results/`](conversion_results/) | Per-function JSON translation artifacts (Phase 9.1). |
| [`docs/`](docs/) | Architecture notes, planning documents, per-phase summaries (`daily_summaries/`), and the technical report (`report/`). |
| [`rpart-test/`](rpart-test/) | A debug-instrumented working copy of `rpart`, used during the Phase 11 forensic investigation of a cross-validation discrepancy. |
| [`.claude/agents/`](.claude/agents/), [`.claude/commands/`](.claude/commands/) | Sub-agent and skill (slash command) specifications for the AI-assisted development workflow used throughout this project. |
| [`git_pull.sh`](git_pull.sh), [`git_push.sh`](git_push.sh) | Cluster batch scripts encapsulating the `git subtree` synchronization commands that keep the `python-rpart` and `r2py_rpart` remotes in sync. |
| [`install_environments.sh`](install_environments.sh) | Cluster batch script provisioning the `r-to-python` conda environment used throughout every phase of the conversion. |

Further detail on the conversion methodology, the thirteen-phase project timeline, and the internal layout of the `r2py_rpart` package itself is given in the [technical report](docs/report/main.pdf).

## The Python Package

```bash
pip install r2py_rpart
```

See [`r2py_rpart/README.md`](r2py_rpart/README.md) for installation details, a quick-start example, and the full public API.

## Documentation

- [`docs/report/main.pdf`](docs/report/main.pdf) — the technical report: full methodology, phase-by-phase findings, and discussion.
- [`docs/daily_summaries/`](docs/daily_summaries/) — per-session activity summaries, the primary source material for the technical report.
- [`docs/architecture-analysis.md`](docs/architecture-analysis.md) — architectural notes on the `rpart` package.

## License

This repository bundles the unmodified `rpart` R package source (`rpart/`), which is distributed by CRAN under the GNU General Public License, version 2 or 3 (GPL-2 | GPL-3). The `r2py_rpart` Python package and all original project artifacts in this repository are, consistently, distributed under the GNU General Public License, version 2 or later (GPL-2.0-or-later). See [`LICENSE`](LICENSE) for the full text and [`r2py_rpart/NOTICE`](r2py_rpart/NOTICE) for attribution to the original `rpart` authors.

## Citation and Acknowledgments

The full methodology and findings are documented in the technical report *"Converting the R Package `rpart` to Python: A Technical Report"* (2026), included at [`docs/report/main.pdf`](docs/report/main.pdf).

This project was developed using **Claude Code** (Anthropic) as an AI-assisted development environment, and used computational resources provided by the HPC facility of the University of Notre Dame.

## Authors

- Yufei Cai (ycai9@nd.edu)
- Jun Li (jun.li@nd.edu)

University of Notre Dame
