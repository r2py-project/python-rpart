---
name: generate-r-extern-fake-headers
description: Generates fake C++ header files for all R C API external items listed in a CSV table, using pre-generated Markdown fake guides as implementation blueprints, and assembles a master entry-point header that replaces R.h and Rinternals.h for standalone builds.
---

# Generate Fake C++ Header Files for R C API External Items

## Description

Given four inputs -- a C source `base_folder`, a `csv_file` mapping all R external items that need faking, a `guides_folder` containing the pre-generated Markdown fake implementation guides (one per `external_item`), and an `output_folder` for the resulting `.h` files -- your task is to:

1. Parse the CSV to determine the ordered list of unique `external_item` values.
2. Sequentially invoke the `@generate-r-extern-fake-header` agent for each item to produce a corresponding `{external_item}.h` file in the `output_folder`.
3. After all individual header files have been generated, write a master entry-point header (`fake_R.h`) in the `output_folder` that `#include`s every generated header in the correct dependency order, so that package C source files need only add one include directive to compile without `libR.so`.

### Expected CSV Schema

The `csv_file` must adhere to the following example schema:
```csv
external_item,header_file,category,file_name,line_number,context_statement
DL_FUNC,R_ext/Rdynload.h,type,init.c,12,"static const R_CallMethodDef CallEntries[] = { {""init_rpcallback"", (DL_FUNC) &init_rpcallback, 5}, {""rpart"", (DL_FUNC) &rpart, 11}, {""xpred"", (DL_FUNC) &xpred, 15}, {""rpartexp2"", (DL_FUNC) &rpartexp2, 2}, {""pred_rpart"", (DL_FUNC) &pred_rpart, 12}, {NULL, NULL, 0} };"
DllInfo,R_ext/Rdynload.h,type,init.c,23,R_init_rpart(DllInfo * dll)
INTSXP,Rinternals.h,type,pred_rpart.c,139,"SEXP where = PROTECT(allocVector(INTSXP, n));"
INTSXP,Rinternals.h,type,rpart.c,194,"which3 = PROTECT(allocVector(INTSXP, n));"
INTSXP,Rinternals.h,type,rpart.c,278,"inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));"
INTSXP,Rinternals.h,type,rpart.c,285,"isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));"
INTSXP,Rinternals.h,type,rpart.c,293,"csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));"
INTSXP,Rinternals.h,type,rpartexp2.c,47,"SEXP keep = PROTECT(allocVector(INTSXP, n));"
REALSXP,Rinternals.h,type,rpart.c,241,"cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));"
REALSXP,Rinternals.h,type,rpart.c,261,"dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));"
REALSXP,Rinternals.h,type,rpart.c,269,"dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));"
REALSXP,Rinternals.h,type,xpred.c,209,"predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));"
```

## Execution Steps

### Step 1: Identify and Order Unique External Items

Read and parse the `csv_file`. Extract the definitive ordered list of all unique values in the `external_item` column, preserving their first-occurrence order within the file.

### Step 2: Generate Individual Fake Header Files

Iterate sequentially through the ordered list from Step 1. Sequential execution is mandatory: earlier items (e.g., `SEXP`, `SEXPTYPE`, `fake_arena`) define types and memory structures that later items (e.g., `allocVector`, `INTEGER`, `REAL`, `error`) must reference. Each item's generated header must exist and be readable before the next agent is invoked. For each unique `external_item`, strictly execute the following sub-steps:

1. **Extract the CSV Subset:** Isolate all rows where the `external_item` column matches the current target. Prepend the exact CSV header row (`external_item,header_file,category,file_name,line_number,context_statement`) to form a valid, standalone CSV-formatted string.
2. **Invoke the Header Generation Agent:** Call the `@generate-r-extern-fake-header` agent, passing the `base_folder`, the CSV subset string, the `guides_folder`, and the `output_folder`.
3. **Non-Blocking Error Handling:** If the agent fails, times out, or produces a syntactically invalid header, you must:
    - Log the precise error to the console: `ERROR: Failed to generate fake header for {external_item}. Proceeding to next item.`
    - Immediately continue to the next `external_item`. Do not halt the overall batch.

### Step 3: Assemble the Master Entry-Point Header

After all individual agents have completed (including any that were skipped due to errors), assemble a master header file named `fake_R.h` in the `output_folder`. This file serves as the single drop-in replacement for R's standard includes (`R.h`, `Rinternals.h`, `Rdefines.h`, `R_ext/Error.h`, etc.) in the package source files.

To build `fake_R.h`:

1. **Scan the output folder** for all `.h` files that were successfully generated in Step 2. Collect their filenames in the same order they were produced (which preserves the dependency-safe generation order from Step 1).
2. **Write the master header** with the following structure:
    - A file-level comment block identifying this as the fake R API entry point, listing the real R headers it replaces, and noting that it was auto-generated.
    - `#ifndef`/`#define`/`#endif` header guards and a `#pragma once` guard.
    - An `#include "fake_arena.h"` directive as the first include, since the arena underpins all memory allocation fakes. Add a comment noting that `fake_arena.h` must be present in the same directory and is not auto-generated by this tool.
    - One `#include` line per successfully generated `{external_item}.h` file, in generation order.
    - A trailing comment block summarizing which original R headers are now covered and which `external_item` values (if any) were skipped due to agent errors.
3. **Do not include** any `{external_item}.h` that was not successfully written to disk; only reference files that actually exist in the output folder.