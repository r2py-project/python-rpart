# Phase 10.2 Research Report: Python Package Assembly, API Restructuring, and Test Validation — `r2py_rpart`

**Date:** 2026-06-26
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session assembled the 47 JSON function definitions produced in Phase 10.1 into a fully importable Python package by invoking `/combine-python-functions-into-folder`. Following assembly, the package's public API was restructured to replace low-level C wrapper exports with R-equivalent high-level Python interfaces. A test suite (`test_rpart.py`, 11 tests) was written for the primary public function `rpart()`, exposing and fixing four categories of runtime bugs in the converted code. A packaging defect in `meson.build` was identified and resolved, ensuring all 37 Python modules are correctly installed by `pip install`. All 11 tests pass at session end.

---

### 2. Methodology & Actions Taken

#### 2.1 Skill Invocation: `/combine-python-functions-into-folder`

The skill was invoked with:

| Parameter | Value |
|---|---|
| `conversion_output_folder` | `conversion_results/R/` |
| `python_output_folder` | `r2py_rpart/r2py_rpart/` |
| `python_package_folder` | `r2py_rpart/r2py_rpart/` |

**Step 1 — Discovery:** 36 qualifying subdirectories identified in `conversion_results/R/`, each containing 1–5 `.json` files with keys `imports`, `function_prototype`, `function_body`.

**Step 2 — Combination:** A Python script read each subdirectory's JSON files, deduplicated imports (preserving order), prepended `from __future__ import annotations` and `from typing import Any`, and assembled functions as `prototype + body` blocks. All 36 files written successfully (0 failures).

**Step 3 — Module name sanitization:** 26 output files contained dots in their stems (e.g., `labels.rpart.py`, `model.frame.rpart.py`), making them unimportable as Python modules. All 26 were renamed by replacing internal dots with underscores (e.g., `labels_rpart.py`, `model_frame_rpart.py`). The full renaming map:

| Original | Renamed |
|---|---|
| `labels.rpart.py` | `labels_rpart.py` |
| `meanvar.rpart.py` | `meanvar_rpart.py` |
| `model.frame.rpart.py` | `model_frame_rpart.py` |
| `na.rpart.py` | `na_rpart.py` |
| `path.rpart.py` | `path_rpart.py` |
| `plot.rpart.py` | `plot_rpart.py` |
| `post.rpart.py` | `post_rpart.py` |
| `pred.rpart.py` | `pred_rpart.py` |
| `predict.rpart.py` | `predict_rpart.py` |
| `print.rpart.py` | `print_rpart.py` |
| `prune.rpart.py` | `prune_rpart.py` |
| `residuals.rpart.py` | `residuals_rpart.py` |
| `roc.rpart.py` | `roc_rpart.py` |
| `rpart.anova.py` | `rpart_anova.py` |
| `rpart.branch.py` | `rpart_branch.py` |
| `rpart.class.py` | `rpart_class.py` |
| `rpart.control.py` | `rpart_control.py` |
| `rpart.exp.py` | `rpart_exp.py` |
| `rpart.matrix.py` | `rpart_matrix.py` |
| `rpart.poisson.py` | `rpart_poisson.py` |
| `rsq.rpart.py` | `rsq_rpart.py` |
| `snip.rpart.mouse.py` | `snip_rpart_mouse.py` |
| `snip.rpart.py` | `snip_rpart.py` |
| `summary.rpart.py` | `summary_rpart.py` |
| `text.rpart.py` | `text_rpart.py` |
| `xpred.rpart.py` | `xpred_rpart.py` |

**Step 4 — Import-time error fixes (pre-audit):**

- **`_MISSING` sentinel undefined (4 files):** `rpart.py`, `rpart_control.py`, `summary_rpart.py`, `xpred_rpart.py` used `_MISSING` as a default argument value (evaluated at function definition time) without defining it. Added `_MISSING = object()` immediately before each function definition. Files `labels_rpart.py`, `post_rpart.py`, `print_rpart.py`, `text_rpart.py` already defined their own module-prefixed sentinels (`_labels_rpart_MISSING`, etc.) and required no changes.

- **Stale absolute imports (2 files):**
  - `rpart_exp.py` contained `from conversion_results.R.rpart.exp.R.drate2 import drate2` (erroneous — `drate2` is defined in the same file) and `from conversion_results.R.formatg.R.formatg import formatg`. Both lines were removed; `formatg` replaced with `from .formatg import formatg`.
  - `rpart_poisson.py` contained `from conversion_results.R.formatg.R.formatg import formatg`; replaced with `from .formatg import formatg`.

- **`patsy` unavailable at module level (`rpart_matrix.py`):** The top-level `import patsy` was removed. The import was moved inside `rpart_matrix()` (line 38: `X_design = patsy.dmatrix(...)`) as a lazy import, since `patsy` is not installed in the target environment and is only needed at call time for formula-based model matrix construction.

**Step 5 — `__init__.py` audit:**

- Existing `__init__.py` had `__all__ = ["rpart", "pred_rpart", "xpred", "rpartexp2"]` and four corresponding low-level C wrapper function definitions.
- Audit added 45 import lines at the end of `__init__.py`, exposing all 45 non-conflicting public functions from the 36 new modules.
- `__all__` expanded from 4 to 49 entries.
- Two naming conflicts detected: `rpart` (defined both in `__init__.py` as a C wrapper and in `rpart.py` as a high-level interface) and `pred_rpart` (same). These were deferred for resolution in Step 2.2.

#### 2.2 API Restructuring: Demoting C Wrappers

Per user instruction, the four C-level wrapper functions in `__init__.py` were renamed to private names to prevent them from masking the R-equivalent high-level interfaces:

| Old public name | New private name |
|---|---|
| `rpart` | `_rpart_c` |
| `pred_rpart` | `_pred_rpart_c` |
| `xpred` | `_xpred_c` |
| `rpartexp2` | `_rpartexp2_c` |

Section headers in `__init__.py` were updated from "Public API" to "Internal C wrapper".

Three high-level modules imported the C wrappers by their old public names (deferred lazy imports inside function bodies); these were updated:

| File | Old import | New import |
|---|---|---|
| `rpart.py:238` | `from r2py_rpart import rpart as _rpart_c` | `from r2py_rpart import _rpart_c` |
| `pred_rpart.py:12` | `from r2py_rpart import pred_rpart as _C_pred_rpart` | `from r2py_rpart import _pred_rpart_c as _C_pred_rpart` |
| `xpred_rpart.py:183` | `from r2py_rpart import xpred as _C_xpred` | `from r2py_rpart import _xpred_c as _C_xpred` |

The high-level `rpart` and `pred_rpart` were then promoted to top-level package exports via `__init__.py`:
```python
from .rpart import rpart, tfun
from .pred_rpart import pred_rpart
```

`__all__` was updated to include `"rpart"` and `"pred_rpart"` from the high-level modules. `xpred` and `rpartexp2` were removed from `__all__` (private C wrappers); `xpred_rpart` (the high-level Python function) was retained.

#### 2.3 Test File Management

- **Deleted:** `r2py_rpart/tests/test_rpartexp2.py` — tested private C wrapper `rpartexp2`/`_rpartexp2_c`, not a public interface.
- **Created:** `r2py_rpart/tests/test_rpart.py` — 11 tests for the public `rpart()` function.

Prior to writing the test, the following runtime bugs in `rpart.py` were discovered and fixed:

**Bug 1 — Missing imports (`rpart.py`):** The converted `rpart()` function referenced eight sibling-module functions (`rpart_anova`, `rpart_class`, `rpart_control`, `rpart_exp`, `rpart_matrix`, `rpart_poisson`, `rpartcallback`, `importance`) without importing them. These were available in R's namespace automatically but not in Python. Eight relative imports were added to the top of `rpart.py`:
```python
from .importance import importance
from .rpart_anova import rpart_anova
from .rpart_class import rpart_class
from .rpart_control import rpart_control
from .rpart_exp import rpart_exp
from .rpart_matrix import rpart_matrix
from .rpart_poisson import rpart_poisson
from .rpartcallback import rpartcallback
```

**Bug 2 — Off-by-one errors in `isplit[:, 0]` variable indices (`rpart.py`):** The C entry point `rpart_c` returns `isplit[:, 0]` as **1-based** variable indices (R convention). The converted code treated them as 0-based in three locations:

- Line 291 (split row names): `tname[i + 1]` → `tname[i]`
  (with tname = `["<leaf>", var1, var2, ...]`, 1-based index `i=1` correctly maps to `tname[1]`)
- Line 305 (`isord` array indexing): `_cvar = rpfit["isplit"][:, 0].astype(int)` → `_cvar = rpfit["isplit"][:, 0].astype(int) - 1`
  (converting to 0-based before indexing `_isord_arr`)
- Line 361 (frame `var` column): `tname[sv + 1]` → `tname[sv]`
  (`_svar` holds 1-based variable indices from `isplit[:, 0]`; leaf nodes carry `sv=0` which maps to `tname[0] = "<leaf>"`)

Diagnostic confirmation: with 1 predictor variable (`nvar=1`), `isplit[:, 0]` = `[1]`; `_isord_arr` has size 1; the original `_isord_arr[1]` raised `IndexError: index 1 is out of bounds for axis 0 with size 1`.

**Bug 3 — `parms` dict serialization for classification method (`rpart.py:219`):** `rpart_class` returns `init["parms"]` as a `dict` (`{"prior": array([...]), "loss": array([[...]]), "split": 1}`). The original serialization `np.asarray(list(np.array(init["parms"]).ravel()), dtype=np.float64)` raises `TypeError` since `np.array()` on a dict produces a 0-d object array. Replaced with dict-aware flattening mirroring R's `unlist()` semantics:
```python
if isinstance(init["parms"], dict):
    _flat = []
    for v in init["parms"].values():
        _flat.extend(np.asarray(v, dtype=np.float64).ravel().tolist())
    _parms_flat = np.array(_flat, dtype=np.float64) if _flat else np.array([0.0])
```
This correctly serializes `prior` (shape `[nclass]`), `loss` (shape `[nclass, nclass]`), and `split` (scalar) into a contiguous `float64` vector.

**Test design note — `where` semantics:** `rpfit["which"]` from the C layer contains **1-based row indices into `inode`**, not actual binary-tree node numbers. Verified by comparing `which.max() = 11` against `inode.shape[0] = 11` for a test case with 11 nodes. Consequently, `fit["where"]` follows R's `$where` semantics: 1-based row index into `fit["frame"]`. The test asserting node membership was rewritten as:
```python
assert np.all(fit["where"] >= 1)
assert np.all(fit["where"] <= len(fit["frame"]))
```

#### 2.4 Build System Fix: `meson.build` `py.install_sources`

After reinstalling with `pip install --no-build-isolation .` and running the test suite directly, the following error appeared:

```
ModuleNotFoundError: No module named 'r2py_rpart.formatg'
  File "/users/ycai9/.conda/envs/r-to-python/lib/python3.14/site-packages/r2py_rpart/__init__.py", line 581, in <module>
    from .formatg import formatg
```

Inspecting the installed site-packages directory (`/users/ycai9/.conda/envs/r-to-python/lib/python3.14/site-packages/r2py_rpart/`) showed three entries: `__init__.py`, `__pycache__/`, and `_rpart_core.so`. All 36 new Python modules were absent.

**Root cause:** `r2py_rpart/meson.build` uses `py.install_sources(...)` to declare which files are copied into site-packages. The original listing contained only one entry:

```meson
py.install_sources(
  'r2py_rpart/__init__.py',
  subdir: 'r2py_rpart',
)
```

The `meson-python` build backend does not auto-discover Python source files — every file must be enumerated explicitly. Because the 36 new modules were never added, `pip install` installed only `__init__.py`.

**Fix:** All 36 new modules were added to `py.install_sources`, bringing the total to 37 entries:

```meson
py.install_sources(
  'r2py_rpart/__init__.py',
  'r2py_rpart/formatg.py',
  'r2py_rpart/importance.py',
  'r2py_rpart/labels_rpart.py',
  ...
  'r2py_rpart/xpred_rpart.py',
  'r2py_rpart/zzz.py',
  subdir: 'r2py_rpart',
)
```

After running `pip install --no-build-isolation .` with the updated `meson.build`, all 37 `.py` files were present in site-packages and all 11 tests passed.

Two approaches were considered and rejected before the root-cause fix:

- **Manual copy of `.py` files to site-packages:** Addressed the immediate error but required manual repetition after every reinstall.
- **Editable install (`pip install -e .`):** A workaround that bypasses the install manifest entirely; rejected because `pip_install.sh` is designed to produce a proper non-editable install and the underlying defect would remain latent.

---

### 3. Key Findings & Results

#### 3.1 Assembly Metrics

| Metric | Value |
|---|---|
| Conversion subdirectories processed | 36 |
| Python modules written | 36 |
| Functions assembled | 47 |
| Files renamed (dot → underscore) | 26 |
| Files with `_MISSING` sentinel fixed | 4 |
| Files with stale absolute imports fixed | 2 |
| Imports added to `__init__.py` | 45 |
| `__all__` entries (before → after) | 4 → 49 |
| Import check result | PASSED |
| Modules added to `meson.build` `py.install_sources` | 36 |
| Total `.py` files in install manifest (before → after) | 1 → 37 |

#### 3.2 Package Public API (final state)

After restructuring, `r2py_rpart.__all__` contains 49 entries. Primary user-facing exports:

| Symbol | Source module | R equivalent |
|---|---|---|
| `rpart` | `rpart.py` | `rpart::rpart()` |
| `pred_rpart` | `pred_rpart.py` | `rpart:::pred.rpart()` |
| `predict_rpart` | `predict_rpart.py` | `predict.rpart()` |
| `xpred_rpart` | `xpred_rpart.py` | `rpart:::xpred.rpart()` |
| `rpart_control` | `rpart_control.py` | `rpart::rpart.control()` |
| `rpart_class` | `rpart_class.py` | `rpart:::rpart.class()` |
| `rpart_anova` | `rpart_anova.py` | `rpart:::rpart.anova()` |
| `rpart_poisson` | `rpart_poisson.py` | `rpart:::rpart.poisson()` |
| `rpart_exp` | `rpart_exp.py` | `rpart:::rpart.exp()` |
| `rpartcallback` | `rpartcallback.py` | `rpart:::rpartcallback()` |
| `summary_rpart` | `summary_rpart.py` | `summary.rpart()` |
| `print_rpart` | `print_rpart.py` | `print.rpart()` |
| `plot_rpart` | `plot_rpart.py` | `plot.rpart()` |
| `text_rpart` | `text_rpart.py` | `text.rpart()` |
| `labels_rpart` | `labels_rpart.py` | `labels.rpart()` |
| `prune_rpart` | `prune_rpart.py` | `prune.rpart()` |
| `path_rpart` | `path_rpart.py` | `path.rpart()` |
| `importance` | `importance.py` | `rpart:::importance()` |

C wrappers retained as private: `_rpart_c`, `_pred_rpart_c`, `_xpred_c`, `_rpartexp2_c`.

#### 3.3 Test Results

```
r2py_rpart/tests/test_rpart.py — 11 tests, 0 failures
```

| Test | Assertion |
|---|---|
| `test_rpart_returns_dict_with_required_keys` | Output contains `frame`, `where`, `cptable`, `method`, `parms`, `control`, `functions` |
| `test_rpart_frame_is_dataframe` | `fit["frame"]` is `pd.DataFrame` |
| `test_rpart_cptable_has_expected_columns` | cptable has `CP`, `nsplit`, `rel error` columns |
| `test_rpart_where_length_matches_observations` | `fit["where"].shape == (n,)` |
| `test_rpart_where_values_are_valid_row_indices` | `1 ≤ where[i] ≤ len(frame)` |
| `test_rpart_method_anova_recorded` | `fit["method"] == "anova"` |
| `test_rpart_method_class_recorded` | `fit["method"] == "class"` |
| `test_rpart_anova_produces_split_on_clear_signal` | `len(frame) > 1` and `"splits" in fit` when signal-to-noise ratio is high |
| `test_rpart_constant_response_produces_no_split` | `len(frame) == 1` when Y is constant |
| `test_rpart_raises_without_prebuilt_model` | `NotImplementedError` when `model` is not a `pd.DataFrame` |
| `test_rpart_raises_on_negative_weights` | `ValueError("negative weights")` when `attrs["weights"]` is negative |

#### 3.4 Technical Insights

- **`isplit[:, 0]` is 1-based:** The C entry point `rpart_c` (entry point file `rpart_c.c`) stores variable indices using R's 1-based convention. `tname[0] = "<leaf>"` serves as the sentinel for leaf nodes; `tname[k]` for `k ≥ 1` gives the name of the k-th predictor.
- **`which` = row index, not node number:** `rpfit["which"][i]` is a 1-based row index into `rpfit["inode"]`, not the binary-tree node number stored in `inode[:, 0]`. This matches R's `$where` semantics and requires `inode[which[i]-1, 0]` to recover the actual node number.
- **`parms` is method-dependent:** For `method="anova"` and `method="poisson"`, `init["parms"]` is a flat numeric array or scalar. For `method="class"`, it is a `dict` with keys `prior`, `loss`, `split`. A single serialization path using `np.asarray(...).ravel()` was insufficient; dict-valued parms require iteration over `.values()`.
- **Circular import avoidance:** `rpart.py` imports `_rpart_c` lazily inside the function body (`from r2py_rpart import _rpart_c`) to avoid a circular import that would arise from a module-level import, since `__init__.py` imports `rpart` from `rpart.py`.
- **`meson-python` requires explicit source enumeration:** Unlike `setuptools`, which can auto-discover packages via `find_packages()`, the `meson-python` build backend (`mesonpy`) requires every `.py` file to be listed in `py.install_sources()`. Files present in the source tree but absent from that call are silently excluded from the built distribution and site-packages. Any session that adds new Python modules to a `meson-python` package must also update `meson.build` in the same change.

---

### 4. Conclusion & Next Steps

The `r2py_rpart` package is now fully assembled, correctly packaged, and importable, exposing 49 public symbols from 37 Python modules. The `meson.build` install manifest was updated to enumerate all 37 `.py` modules in `py.install_sources`, making `pip install --no-build-isolation .` the authoritative and complete installation path with no manual post-install steps required. The primary entry point `rpart()` passes 11 unit tests covering structural output correctness, method selection, splitting behaviour, and error handling for both `anova` and `class` methods.

Suggested next steps:

1. **Extend test coverage:** Write tests for `rpart_control`, `predict_rpart`, `xpred_rpart`, `prune_rpart`, and `labels_rpart`. Run `/generate-python-file-tests` against each new module.
2. **`rpart_class` classification validation:** Benchmark `rpart(method="class")` output (frame `var`, `yval`, `yval2`, `cptable`) against R's `rpart::rpart()` on standard datasets (e.g., the `iris` or `kyphosis` datasets).
3. **`parms` serialization audit for `method="exp"` and `method="poisson"`:** Confirm that `rpart_exp` and `rpart_poisson` return `parms` in a format compatible with the updated serialization path.
4. **`model.frame` / patsy integration:** Implement the `model.frame` construction path in `rpart.py` (currently `NotImplementedError`) using `patsy.dmatrix` or a pandas-based formula parser to allow `rpart(formula, data=df)` to work without a pre-built model frame.
5. **`rpartcallback` linkage fix:** The `rpartcallback()` function body references `_lib`, `ffi`, `_ERR_BUF_SIZE`, `_check_error`, `_cptr` (defined in `__init__.py`) without importing them. These will raise `NameError` at call time when `method="user"` is used. Fix by adding deferred imports inside the function body.
