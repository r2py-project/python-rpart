# Phase 7 Research Report: R Package Structural Dependency Analysis

**Date:** 2026-06-19
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session performed a complete structural dependency analysis of the rpart R package's source layer (`rpart/R/`), producing machine-readable JSON dependency maps for all 36 R scripts. The `analyze-r-file-dependencies` agent was applied to each file individually to classify every function call as a language dependency (base R), internal dependency (intra-package), or external dependency (`.Call`/`.External` to compiled C). The resulting JSON corpus was then processed by two pre-existing graph tools to yield a full dependency graph (PNG/PDF/HTML) and a topologically ordered function-level CSV.

---

### 2. Methodology & Actions Taken

#### 2.1 R File Discovery

The `/analyze-r-folder-dependencies` skill was invoked with argument `rpart/R/`. A recursive `find` scan identified **36 R source files** (`.R` extension only; no `.r` variants present). The target output directory `structural_analysis/R/` was created to receive all results.

#### 2.2 Per-File Dependency Analysis

The `analyze-r-file-dependencies` sub-agent was invoked sequentially for each of the 36 files. For every file the agent:
- Read the full source text.
- Enumerated all function calls (including calls inside anonymous closures and nested functions).
- Classified each call into one of three categories:
  - **`language_dependencies`**: base R or standard library functions (e.g., `match`, `attr`, `lapply`).
  - **`internal_dependencies`**: functions defined in sibling `.R` files within the same package.
  - **`external_dependencies`**: `.Call`/`.External` invocations targeting compiled C routines.
- Returned a JSON object keyed by function name.

Results were saved with the naming convention `structural_analysis/R/<stem>.json`, e.g., `rpart.R` → `rpart.json`.

#### 2.3 Graph and Level Computation

Two scripts were executed sequentially in the `r-to-python` conda environment:

1. **`structural_analysis/dependency_graph.py`** — Loaded all 36 JSON files, constructed a three-level NetworkX graph (file → function → language/external nodes), and rendered outputs to `dependency_graph.png`, `dependency_graph.pdf`, and `dependency_graph.html`.
2. **`structural_analysis/dependency_levels.py`** — Built a directed call graph over internal dependencies only, applied BFS topological layering, and wrote `dependency_levels.csv`.

---

### 3. Key Findings & Results

#### 3.1 JSON Output Corpus

36 JSON files were written to `structural_analysis/R/`. Key per-file statistics:

| File | Functions Defined | External C Calls |
|------|------------------|-----------------|
| `rpart.R` | 2 (`rpart`, `tfun`) | `.Call("C_rpart")` |
| `pred.rpart.R` | 1 (`pred.rpart`) | `.Call("C_pred_rpart")` |
| `xpred.rpart.R` | 1 (`xpred.rpart`) | `.Call("C_xpred")` |
| `rpart.exp.R` | 2 (`rpart.exp`, `drate2`) | `.Call("C_rpartexp2")` |
| `rpartcallback.R` | 1 (`rpartcallback`) | `.Call("C_init_rpcallback")` |

All other 31 files contained zero external dependencies.

#### 3.2 Dependency Graph Metrics

The graph produced by `dependency_graph.py` contains:
- **262 nodes** total: 36 file nodes, 49 function nodes, 172 language-dependency nodes, 5 external-dependency nodes.
- **745 edges** total across all three levels.

#### 3.3 Internal Dependency Hub Functions

The most widely referenced internal functions (called by the most other package functions):
- **`formatg`** (`formatg.R`) — called by `labels.rpart`, `rpart.anova`, `rpart.class`, `rpart.exp`, `rpart.poisson`.
- **`na.rpart`** (`na.rpart.R`) — called by `model.frame.rpart`, `rpart`, `xpred.rpart`.
- **`rpart.control`**, **`rpart.matrix`**, **`rpartcallback`** — each called by both `rpart` and `xpred.rpart`.
- **`rpartco`** and **`rpart.branch`** — shared by `plot.rpart`, `snip.rpart.mouse`, and `text.rpart`.

#### 3.4 Topological Level Distribution (`dependency_levels.csv`)

47 functions were stratified across 6 dependency levels:

| Level | Count | Description |
|-------|-------|-------------|
| 0 | 20 | Entry points — no other internal function calls these |
| 1 | 18 | Called by level-0 functions |
| 2 | 4 | Called by level-1 functions |
| 3 | 1 | Called by level-2 functions |
| 4 | 2 | Called by level-3 functions |
| 5 | 2 | Deepest leaves in the call DAG |

28 of the 47 functions are leaves (make no internal calls themselves).

#### 3.5 Notable Structural Observations

- The `rpart` and `xpred.rpart` functions are the two primary orchestrators, each pulling in `na.rpart`, `rpart.matrix`, `rpartcallback`, and all four method-dispatch targets (`rpart.anova`, `rpart.class`, `rpart.poisson`, `rpart.exp`) dynamically via `get(paste("rpart", method, sep="."))`.
- `zzz.R` defines five package-utility functions (`tree.depth`, `string.bounding.box`, `node.match`, `descendants`, `.onUnload`) that are consumed by the visualization layer (`rpartco.R`, `text.rpart.R`, `path.rpart.R`) but have no internal dependencies of their own.
- Only 5 of 36 files invoke C routines, confirming that the R-to-C interface is narrow and already captured in the entry-point wrappers generated in Phase 6.

---

### 4. Conclusion & Next Steps

The session successfully produced a complete, machine-readable structural analysis of the rpart R package's 36 source files, covering 47 functions with fully classified dependency inventories. The outputs (`structural_analysis/R/*.json`, `dependency_graph.{png,pdf,html}`, `dependency_levels.csv`) provide the foundation for sequenced Python conversion: functions at level 5 (deepest dependencies) should be converted first, progressing upward to level 0. The next phase should use these JSONs as inputs to the `/convert-r-file-to-python` skill, beginning with the leaf functions identified in `dependency_levels.csv`.
