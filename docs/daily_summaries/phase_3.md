# Phase 3 Research Report: Fake C++ Header Implementation Guides for R C API External Items

**Date:** 2026-06-17
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session executed batch generation of fake C++ header implementation guides for all 51 unique R C API external items identified in the `rpart/src/` directory. Using the `/generate-r-extern-fake-guides` skill against `r_extern_analysis/combined.csv`, the `generate-r-extern-fake-guide` subagent was invoked sequentially for each external item, producing 51 Markdown guide files in `r_extern_analysis/fake_guides/`. These guides collectively specify how to implement a complete set of drop-in C++ fakes that allow the original rpart C source to compile and link without `libR.so`, enabling direct invocation from Python.

---

### 2. Methodology & Actions Taken

#### 2.1 Input Parsing

The master CSV `r_extern_analysis/combined.csv` (235 data rows, 1 header row) was read and parsed to extract all unique values in the `external_item` column. This yielded 51 unique identifiers drawn from 16 source files (`rpart.c`, `xpred.c`, `pred_rpart.c`, `rpart_callback.c`, `rpartexp2.c`, `init.c`, `branch.c`, `nodesplit.c`, `xval.c`, `print_tree.c`, `free_tree.c`, `insert_split.c`, `rundown.c`, `rundown2.c`, `rpart.h`, `rpartproto.h`) referencing 10 R include headers (`Rinternals.h`, `R_ext/Print.h`, `R_ext/Error.h`, `R_ext/Boolean.h`, `R_ext/RS.h`, `R_ext/Rdynload.h`, `R_ext/Arith.h`, `Rversion.h`, `R.h`, `R_ext/Utils.h`).

#### 2.2 Output Directory Creation

The target output directory `r_extern_analysis/fake_guides/` did not exist and was created via `mkdir -p` before processing began.

#### 2.3 Sequential Subagent Invocation

The 51 external items were processed in strict sequential order — the order in which they appear in the pre-sorted CSV — to ensure foundational fake definitions (e.g., `SEXP` struct, `SEXPTYPE` enum, arena allocator) were available as references when later dependent items were generated. For each item:

1. All CSV rows matching the target `external_item` were isolated and prepended with the CSV header to form a standalone subset string.
2. The `generate-r-extern-fake-guide` subagent was invoked with `base_folder=rpart/src/`, the CSV subset, and `output_directory=r_extern_analysis/fake_guides/`.
3. The agent read the relevant rpart source files, inspected the R include headers at `~/.conda/envs/r-to-python/lib/R/include/`, and produced a Markdown guide file named `<external_item>.md`.

Progress was tracked in real time using the `TodoWrite` tool across all 51 items. No agent invocations failed or required retries.

#### 2.4 Files Created

- `r_extern_analysis/fake_guides/` — new directory
- 51 Markdown guide files totaling approximately 1.07 MB (avg. ~21.5 KB/file)

---

### 3. Key Findings & Results

#### 3.1 Classification Distribution

The 51 guides were categorized according to the fake implementation strategy required:

| Category | Description | Count | Items |
|---|---|---|---|
| A | Type, enum constant, or registration no-op | 19 | `SEXP`, `INTSXP`, `REALSXP`, `STRSXP`, `VECSXP`, `DL_FUNC`, `DllInfo`, `R_CallMethodDef`, `Rboolean`, `TRUE`, `FALSE`, `R_VERSION`, `R_Version`, `R_NilValue`, `R_NamesSymbol`, `R_UnboundValue`, `R_forceSymbols`, `R_registerRoutines`, `R_useDynamicSymbols` |
| B | Accessor macro or inline function | 16 | `INTEGER`, `REAL`, `CHAR`, `PROTECT`, `UNPROTECT`, `LENGTH`, `PRINTNAME`, `ISNAN`, `R_FINITE`, `asInteger`, `asReal`, `isReal`, `ncols`, `nrows`, `SET_STRING_ELT`, `SET_VECTOR_ELT` |
| C | Allocation or memory management | 7 | `allocVector`, `allocMatrix`, `R_alloc`, `R_chk_calloc`, `R_Free`, `mkChar`, `setAttrib` |
| D | Error, warning, or print function | 4 | `error`, `warning`, `Rprintf`, `R_CheckUserInterrupt` |
| E | R interpreter item (Python function-pointer bridge) | 5 | `eval`, `findVar`, `findVarInFrame`, `install`, `R_getVar` |

#### 3.2 Key Technical Decisions

**Memory model split.** The guides establish a two-tier heap/arena model: `R_alloc`/`ALLOC` scratch allocations delegate to a per-frame `ArenaFrame` (freed automatically at `.Call` exit), while `CALLOC`/`std::malloc`-based allocations for `SEXP` nodes, SEXP data buffers, and `Node`/`Split` structs live on the process heap and are freed explicitly via `R_Free` or `free_sexp()`.

**R version pinning.** `R_VERSION` must be faked as `R_Version(4, 4, 0) = 263168`. This value satisfies two conflicting preprocessor guards simultaneously: `R_VERSION >= R_Version(2, 16, 0)` in `init.c:27` (enabling `R_forceSymbols`) and `R_VERSION < R_Version(4, 5, 0)` in `rpart_callback.c:19` (selecting the `compat_getVar` shim, which avoids the native `R_getVar` symbol that would require `libR.so`).

**`R_getVar` is a macro, not a symbol.** For R < 4.5.0, `R_getVar` expands to the local shim `compat_getVar`, meaning no direct function pointer stub is needed for `R_getVar` itself. At runtime, it always resolves to `findVarInFrame` (all four call sites pass `inherits=FALSE`).

**Category E items are `method=4` only.** The five R interpreter items (`eval`, `findVar`, `findVarInFrame`, `install`, `R_getVar`) are only reachable when `rpart()` is called with `method=4` (user-defined splits). All four standard methods (anova, poisson, class, exp) execute without any Python callback registration.

**`PROTECT`/`UNPROTECT` are no-ops.** Without a garbage collector, the entire GC protection protocol reduces to identity functions. SEXP lifetime is managed by the Python caller via explicit `free_sexp()` after the `.Call` boundary returns.

**`install` is self-contained.** Unlike `eval`/`findVar`, `install` can be fully faked in C++ using a `thread_local std::unordered_map<std::string, SEXP>` string-interning cache, with no Python callback bridge required.

#### 3.3 Header Architecture Established

The guides collectively specify a layered fake header hierarchy:

```
fake_Rversion.hpp       ← R_VERSION, R_Version (must be first)
fake_Boolean.hpp        ← Rboolean, TRUE, FALSE
fake_arena.hpp          ← ArenaFrame, arena_alloc
fake_Arith.hpp          ← ISNAN, R_FINITE, R_NaReal, NA_REAL
fake_Print.hpp          ← Rprintf, REprintf
fake_error.hpp          ← RError, Rf_error, Rf_warning
fake_Rinternals.hpp     ← SEXP/SEXPREC, SEXPTYPE enum, all accessors, sentinels
fake_Rdynload.hpp       ← DL_FUNC, R_CallMethodDef, DllInfo, registration stubs
fake_R.hpp              ← R_alloc (ALLOC), R_chk_calloc (CALLOC)
fake_RS.hpp             ← R_Free, R_chk_free
fake_Utils.hpp          ← R_CheckUserInterrupt, R_CheckStack
fake_interpreter.hpp    ← eval, findVar, findVarInFrame, install (function-pointer bridges)
```

---

### 4. Conclusion & Next Steps

All 51 fake header implementation guides have been successfully generated in `r_extern_analysis/fake_guides/`. The guides provide a complete, self-consistent blueprint for building `fake_rpart.hpp` — a single master header that replaces `R.h`, `Rinternals.h`, and all transitively included R API headers, enabling the rpart C source files to compile as a standalone shared library without `libR.so`.

The immediate next step is Phase 4: implementing the actual fake header files (`fake_Rinternals.hpp`, `fake_arena.hpp`, etc.) by translating each guide's C++ code specifications into compilable header files, then assembling `fake_rpart.hpp` as the master entry-point header. This will be followed by a build test (`g++ -std=c++17 -shared -fPIC`) to validate that all 16 source files compile cleanly under the fake headers.
