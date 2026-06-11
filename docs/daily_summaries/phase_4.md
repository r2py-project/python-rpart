# Phase 4 Research Report: R External Item Conversion Guide Generation

**Date:** 2026-06-11
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session executed a systematic batch generation of `.Call`-to-`.C` API conversion guides for all 51 unique R external identifiers catalogued in `r_extern_analysis/combined.csv` (Phase 3 output). The `generate-r-extern-conversion-guide` subagent was invoked sequentially for each item, producing 51 standalone Markdown guides in `r_extern_analysis/conversion_guides/`. These guides constitute a complete reference for migrating `rpart`'s SEXP-based `.Call` C interface to the raw-pointer-based `.C` interface.

---

### 2. Methodology & Actions Taken

#### 2.1 Input Preparation
The 236-row `r_extern_analysis/combined.csv` (schema: `external_item, header_file, category, file_name, line_number, context_statement`) was parsed to extract all 51 unique `external_item` values. The file was confirmed pre-sorted, allowing linear segmentation without reordering. The output directory `r_extern_analysis/conversion_guides/` was verified to exist prior to processing.

#### 2.2 Sequential Agent Invocations
The `generate-r-extern-conversion-guide` subagent was invoked exactly once per unique `external_item`, strictly sequentially (no parallelism) so that later guides could cross-reference findings from earlier ones. Each invocation received:
- `base_folder`: `rpart/src/`
- `output_directory`: `r_extern_analysis/conversion_guides/`
- A standalone CSV substring containing only the rows for that item, with the full header row prepended.

All 51 invocations completed without error.

#### 2.3 Progress Tracking
A `TodoWrite` task list of 51 items was maintained throughout, with each item marked `completed` immediately after its agent confirmed the guide was written.

#### 2.4 Files Written
51 Markdown files created in `r_extern_analysis/conversion_guides/`:

| Category | Items |
|----------|-------|
| SEXP types | `SEXP.md`, `INTSXP.md`, `REALSXP.md`, `STRSXP.md`, `VECSXP.md` |
| Memory allocation | `allocVector.md`, `allocMatrix.md`, `PROTECT.md`, `UNPROTECT.md`, `R_alloc.md`, `R_chk_calloc.md`, `R_Free.md` |
| Accessor macros | `INTEGER.md`, `REAL.md`, `CHAR.md`, `LENGTH.md`, `ncols.md`, `nrows.md` |
| Object construction | `SET_VECTOR_ELT.md`, `SET_STRING_ELT.md`, `mkChar.md`, `setAttrib.md`, `R_NamesSymbol.md`, `R_NilValue.md` |
| Type coercion | `asInteger.md`, `asReal.md`, `isReal.md`, `Rboolean.md`, `TRUE.md`, `FALSE.md` |
| Arithmetic | `ISNAN.md`, `R_FINITE.md` |
| I/O & errors | `Rprintf.md`, `error.md`, `warning.md`, `R_CheckUserInterrupt.md` |
| Symbol/env (callback) | `eval.md`, `findVar.md`, `findVarInFrame.md`, `install.md`, `PRINTNAME.md`, `R_getVar.md`, `R_UnboundValue.md` |
| DLL registration | `DL_FUNC.md`, `DllInfo.md`, `R_CallMethodDef.md`, `R_registerRoutines.md`, `R_forceSymbols.md`, `R_useDynamicSymbols.md` |
| Version | `R_Version.md`, `R_VERSION.md` |

---

### 3. Key Findings & Results

#### 3.1 Conversion Strategy Summary
Guides produced four distinct outcome categories:

| Strategy | Items | Rationale |
|----------|-------|-----------|
| **Retain unchanged** | `Rprintf`, `error`, `warning`, `R_CheckUserInterrupt`, `R_forceSymbols`, `R_useDynamicSymbols`, `R_Version`, `R_VERSION` | Plain C-callable functions with no SEXP dependency; fully legal in `.C` |
| **Remove entirely from C** | `SEXP`, `PROTECT`, `UNPROTECT`, `allocVector`, `allocMatrix`, `REAL`, `INTEGER`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, `setAttrib`, `R_NamesSymbol`, `REALSXP`, `INTSXP`, `STRSXP`, `VECSXP` | SEXP-bound; replaced by R-side pre-allocation passed via `.C` pointer arguments |
| **Direct substitution** | `ISNAN` → `isnan()`, `R_FINITE` → `isfinite()`, `asInteger(x)` → `x[0]`, `asReal(x)` → `x[0]`, `LENGTH(v)` → explicit `int *n` parameter | Standard C equivalents exist; no SEXP involvement at call site |
| **Remove (`.C`-incompatible)** | `eval`, `findVar`, `findVarInFrame`, `install`, `PRINTNAME`, `R_getVar`, `R_UnboundValue`, `CHAR`, `isReal` (in callback context) | Require live R interpreter or SEXP handles; entire `rpart_callback.c` usage block must remain as `.Call` or be restructured |

#### 3.2 Registration Change
The DLL registration in `init.c` requires a single structural change: `R_CallMethodDef CallEntries[]` → `R_CMethodDef CallEntries[]`, and the slot 2 (`.Call`) argument to `R_registerRoutines` → slot 1 (`.C`). The `DL_FUNC` cast syntax and `R_forceSymbols`/`R_useDynamicSymbols` calls are retained unchanged.

#### 3.3 Matrix Shape Discovery
`nrows(xmat2)` and `ncols(xmat2)` in `rpart.c` and `xpred.c` (lines 108/106 and 109/107 respectively) have no `.C` equivalent, as the flat `double *` buffer carries no embedded shape metadata. Both dimensions must be promoted to explicit `const int *n_obs` and `const int *n_var` parameters, with `nrow(xmat)` and `ncol(xmat)` called on the R side before `.C` dispatch.

#### 3.4 Callback System Constraint
`rpart_callback.c` uses `eval()`, `findVar`, `findVarInFrame`, `install`, and static `SEXP` globals. These are fundamentally incompatible with `.C` and cannot be ported. The callback-based user-defined split interface must either be preserved as a separate `.Call` entry point or restructured to pass pre-evaluated data across the boundary.

#### 3.5 Output Naming Change
`R_CallMethodDef.md` and `R_CMethodDef` share a guide: the `.Call` registration struct is replaced by `R_CMethodDef`, and the guide documents the full slot-mapping change.

---

### 4. Conclusion & Next Steps

All 51 conversion guides are complete and available in `r_extern_analysis/conversion_guides/`. Together they provide item-level instructions sufficient to drive a systematic, file-by-file rewrite of `rpart/src/` from `.Call` to `.C`. The natural next step is to apply these guides to produce the converted C source files, beginning with the simpler utility files (`rundown.c`, `rundown2.c`, `pred_rpart.c`, `rpartexp2.c`) and progressing to the dense output-construction blocks in `rpart.c` and `xpred.c`. The `rpart_callback.c` callback system should be scoped separately as a `.Call`-retained component.
