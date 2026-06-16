---
name: generate-r-extern-fake-header
description: Writes a fake C++ header file for a specific R C API external item by translating the implementation blueprint from its pre-generated Markdown guide into compilable C++ code, so the original package source files build without libR.so.
---

# Generate a Fake C++ Header File for an R C API External Item

## Description

When provided with a `base_folder`, a CSV text snippet, a `guides_folder` containing pre-generated Markdown fake implementation guides, and an `output_folder`, your task is to produce a single self-contained C++ header file — `{external_item}.h` — that provides a drop-in fake implementation of the target R C API item. The original package C source files must be able to `#include` this header (transitively through `fake_R.h`) and compile without any modification and without linking against `libR.so`.

The input CSV will strictly adhere to the following example schema:
```csv
external_item,header_file,category,file_name,line_number,context_statement
INTSXP,Rinternals.h,type,pred_rpart.c,139,"SEXP where = PROTECT(allocVector(INTSXP, n));"
INTSXP,Rinternals.h,type,rpart.c,194,"which3 = PROTECT(allocVector(INTSXP, n));"
INTSXP,Rinternals.h,type,rpart.c,278,"inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));"
INTSXP,Rinternals.h,type,rpart.c,285,"isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));"
INTSXP,Rinternals.h,type,rpart.c,293,"csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));"
INTSXP,Rinternals.h,type,rpartexp2.c,47,"SEXP keep = PROTECT(allocVector(INTSXP, n));"
```

The generated header must:
1. Implement every function, macro, type, or constant that the `external_item` represents, exactly as specified in the corresponding Markdown guide in `guides_folder`.
2. Preserve every `#define` alias that the original R header defined for the item (e.g., `#define error Rf_error`, `#define PROTECT(s) Rf_protect(s)`) so that the original source files compile without any textual changes.
3. Satisfy the three invariants stated in the Markdown guide: C++ exception-based errors, arena-backed memory management without source modification, and best-effort Python function-pointer bridges for R interpreter items.

## Execution Steps

### Step 1: Ingest Inputs and Gather Deterministic Context

- **Guide Ingestion:** Read the Markdown guide at `{guides_folder}/{external_item}.md`. Extract and fully understand all five sections: Overview, Contextual Usage Analysis, Fake C++ Implementation Strategy, Fake Implementation Examples, and Integration Requirements. The guide is the authoritative blueprint; the steps below gather additional context to ensure the generated header is correct.
- **Source File Inspection:** Iterate through each row in the CSV. Construct the absolute source file path from `base_folder` and the `file_name` column. Navigate to the `line_number` and read at least 15 lines above and below. Use these windows to confirm: the exact C types of arguments and return values that the item is used with, the scope and lifetime of surrounding variables, whether the item appears inside a function body or at file scope, and any adjacent R API calls that interact with it. If the source context reveals usage patterns not covered by the guide, note them explicitly in the generated header as code comments.
- **Original Header Resolution:** Read the original R header at `~/.conda/envs/r-to-python/lib/R/include/{header_file}` to extract the exact function signature, macro definition, or type layout declared there. Also check sub-headers under `~/.conda/envs/r-to-python/lib/R/include/R_ext/` for any transitively included definitions. If the header cannot be found in either `base_folder` or the conda include path `~/.conda/envs/r-to-python/lib/R/include/`, state this in a comment within the generated `.h` file and proceed with the definition from the Markdown guide. Never search other locations.

### Step 2: Resolve Header Dependencies

- **Read Integration Requirements:** Locate the "Integration Requirements" section (Section 5) of the Markdown guide. This section lists every other `external_item` whose fake header must be included before the current one. For each listed dependency, verify that the corresponding `{dependency}.h` file exists in the `output_folder`.
- **Inspect Existing Headers:** For each dependency that exists, read its content. Confirm that the types, structs, and function signatures it exposes are consistent with what the current item's guide expects. If a dependency is missing from `output_folder`, include a `// WARNING: dependency {dependency}.h not found in output_folder` comment in the generated header at the point of its `#include` directive and continue; do not abort.
- **Check for Conflicts:** Scan all existing headers in `output_folder` to ensure the current item does not redefine a symbol already declared there. If a conflict exists, emit the new definition conditionally using `#ifndef` guards rather than duplicating it.

### Step 3: Write the Fake Header File

Translate the Markdown guide's "Fake C++ Implementation Strategy" (Section 3) and "Fake Implementation Examples" (Section 4) into a complete, compilable C++ header file. Apply the following rules without exception:

**Rule 1 — Use both `#ifndef` `#define` `#endif` header guards and `#pragma once`.**
You have to add traditional `#ifndef`/`#define`/`#endif` include guards to prevent multiple inclusions. Also, place `#pragma once` as the very first non-comment line.

**Rule 2 — Dependency includes come first.**
After the header guards, emit one `#include "{dependency}.h"` line per dependency identified in Step 2, in the order listed by the guide's Integration Requirements. If the item is in Category C (memory allocation), also emit `#include "fake_arena.h"` before all other includes.

**Rule 3 — Implement exactly what the guide specifies for the item's category.**
- **Category A (type or enum constant):** Emit the C++ `struct`, `typedef`, or `enum` definition. For `SEXP`/`SEXPREC`, output the full struct with `SEXPTYPE type`, `int length`, `int nrow`, `int ncol`, and a `union` of typed data pointers.
- **Category B (accessor macro or inline function):** Emit `inline` C++ functions, not macros, for type safety. The function body casts `sexp->data` or reads scalar fields from the `SEXPREC` struct. Preserve any `#define` alias from the original header beneath the `inline` definition.
- **Category C (allocation or memory function):** Implement heap-allocating functions (`allocVector`, `allocMatrix`, `mkChar`) as `inline` functions using `new` / `std::malloc`. Implement arena-delegating functions (`R_alloc`, `R_chk_calloc`, `S_alloc`) as `inline` functions calling `arena_alloc` / `arena_calloc` from `fake_arena.h`. Implement `PROTECT` and `UNPROTECT` as no-op `inline` functions. Place an `ArenaFrame` usage comment block showing callers exactly where to declare `ArenaFrame _frame;` at their function entry.
- **Category D (error, warning, or print function):** Define the `RError` struct exactly once (guard with `#ifndef FAKE_R_RERROR_DEFINED`). Implement `Rf_error` as a `[[noreturn]]` `inline` function that formats its variadic arguments into a `std::string` via `vsnprintf` and throws `RError`. Implement `Rf_warning` as an `inline` function that writes to `stderr` via `std::fprintf`. Implement `Rprintf` and `REprintf` as `inline` forwarding functions. Emit all `#define` aliases from the original R error header (`#define error Rf_error`, `#define warning Rf_warning`).
- **Category E (R interpreter item):** Emit the function pointer declaration as a global `extern "C"` variable, the registration function with C linkage, and the stub body that calls the pointer or throws `RError("...")` if the pointer is null. Wrap the entire block in a `// *** R INTERPRETER ITEM — requires Python callback registration ***` comment block.

**Rule 4 — Preserve all original R header `#define` aliases.**
After the implementation code, emit a block labelled `// --- Compatibility aliases (preserve original R API names) ---` containing every `#define` the original R header declared for this item. These ensure the unchanged package source files see the same names they used before (e.g., `#define allocVector Rf_allocVector` if the original header used that remapping).

**Rule 5 — Emit an `ArenaFrame` usage note for any Category C header.**
After the alias block, emit a comment block titled `// --- ArenaFrame usage ---` that shows the exact one-liner a caller must add at the top of any `.Call`-style function body that calls arena-backed functions defined in this header.

**Rule 6 — No runtime R linkage.**
The generated header must introduce zero dependencies on `libR.so`. Do not `#include` any original R headers. The only permitted system includes are from the c/C++ standard library (`<stdlib.h>`, `<stddef.h>`, `<string.h>`, `<stdexcept>`, `<stdio.h>`, `<stdarg.h>`, `<vector>`, `<string>`, `<unordered_map>`, etc.) and from other fake headers already in the `output_folder`.

## Output Format Schema

The generated `.h` file must follow this exact structure, in order:

```
// =============================================================
// {external_item}.h — Fake R API: {external_item}
// Original R header: {header_file}
// Category: {A|B|C|D|E} — {category description}
// Auto-generated by generate-r-extern-fake-header agent.
// =============================================================
#pragma once

// --- Standard library includes ---
#include <...>

// --- Fake R header dependencies ---
// (from Integration Requirements in {external_item}.md)
#include "fake_arena.h"        // if Category C
#include "{dependency_1}.h"
#include "{dependency_2}.h"

// --- R Interpreter Item warning block (Category E only) ---
// *** R INTERPRETER ITEM — {external_item} ***
// A complete fake is impossible without an R interpreter.
// Register a Python callback via {external_item}_register() before use.
// Affected code paths: [list from guide]

// --- Core fake implementation ---
// [struct / typedef / enum / inline function / function pointer stub]
// One block per usage pattern from Section 4 of the Markdown guide.
// Each block is preceded by a comment citing the guide pattern name
// and the source file locations it covers.

// --- Compatibility aliases (preserve original R API names) ---
// [#define aliases from the original R header]

// --- ArenaFrame usage (Category C only) ---
// Declare `ArenaFrame _frame;` as the first statement of any
// .Call-entry function that invokes arena-backed functions from
// this header. Example:
//   SEXP my_entry(SEXP x) { ArenaFrame _frame; ... }
```

If the `external_item` belongs to Category E (R interpreter item), the file must additionally contain, after the core fake implementation block, a Python-side usage note formatted as a multi-line C++ comment block that reproduces the full `ctypes` registration snippet from the Markdown guide's "Python Interop Notes" section.

## Output Saving Instructions
- **File Naming:** Save the generated header as `{external_item}.h` (e.g., `allocVector.h`, `INTSXP.h`, `error.h`).
- **Output Directory:** Save the file to the user-specified `output_folder`. If the user did not explicitly provide one, create and use the default directory `r2py_rpart/r_fake_headers/`.