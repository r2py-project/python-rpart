---
name: generate-r-extern-fake-guides
description: Orchestrates the batch generation of fake C++ header implementation guides for R's C API external items, enabling R package C source files to compile and run without linking against libR.so.
---

# Generate R External Item Fake Header Guides

## Description

When provided with a target `base_folder`, a CSV file matching the schema below, and a target `output_directory`, your task is to orchestrate the batch processing of this dataset. You must segment the CSV by unique `external_item` values and iteratively invoke the `@generate-r-extern-fake-guide` agent for each subset to generate the resulting guides to the specified output directory.

The goal of each guide is to document how to implement a drop-in C++ fake for a given R C API external item — a type, macro, constant, or function — so that the original package C source files can be compiled and linked without `libR.so`, and called directly from Python.

### Expected CSV Schema

Example:
```csv
external_item,header_file,category,file_name,line_number,context_statement
DL_FUNC,R_ext/Rdynload.h,type,init.c,12,"static const R_CallMethodDef CallEntries[] = { {""init_rpcallback"", (DL_FUNC) &init_rpcallback, 5}, {""rpart"", (DL_FUNC) &rpart, 11}, {""xpred"", (DL_FUNC) &xpred, 15}, {""rpartexp2"", (DL_FUNC) &rpartexp2, 2}, {""pred_rpart"", (DL_FUNC) &pred_rpart, 12}, {NULL, NULL, 0} };"
DllInfo,R_ext/Rdynload.h,type,init.c,23,R_init_rpart(DllInfo * dll)
SEXP,Rinternals.h,type,rpart.c,41,"SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2, SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)"
INTSXP,Rinternals.h,type,pred_rpart.c,139,"SEXP where = PROTECT(allocVector(INTSXP, n));"
REALSXP,Rinternals.h,type,rpart.c,241,"cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));"
PROTECT,Rinternals.h,macro,rpart.c,194,"which3 = PROTECT(allocVector(INTSXP, n));"
allocVector,Rinternals.h,function,rpart.c,194,"which3 = PROTECT(allocVector(INTSXP, n));"
error,R_ext/Error.h,function,rpart.c,203,"error(""%s"", errmsg);"
R_alloc,R_ext/Memory.h,function,rpart.c,123,"rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));"
```

## Execution Steps

### Step 1: Identify Unique Dependencies

Read and parse the input CSV file. Extract a definitive list of all unique values present in the `external_item` column (e.g., `DL_FUNC`, `SEXP`, `INTSXP`, `PROTECT`, `allocVector`, `error`, `R_alloc`).

*Note: Assume the CSV is pre-sorted. Identical external items are grouped sequentially to allow for efficient linear processing.*

### Step 2: Extract Segments and Invoke Sub-agents

Iterate sequentially through the list of unique `external_item` values one after another. Sequential execution is mandatory here: foundational fake definitions (e.g., the `SEXP` struct, the `SEXPTYPE` enum, the arena allocator) must be generated before the items that depend on them (e.g., `allocVector`, `INTEGER`, `REAL`), and each newly generated guide may be referenced by the agent processing the next item. For each unique item, strictly execute the following sub-steps:

1. **Extract the CSV Subset:** Isolate all rows where the `external_item` column matches the current target. Prepend the exact CSV header row (`external_item,header_file,category,file_name,line_number,context_statement`) to this subset to create a valid, standalone CSV-formatted string.
2. **Execute Fake Guide Agent:** Invoke the `@generate-r-extern-fake-guide` agent. Pass the target `base_folder`, the newly created CSV subset string, and the specified output directory as inputs.
3. **Strict Error Handling:** If the agent execution fails, times out, or throws an error at any point, you must:
    - Log a precise error message to the console: `ERROR: Failed to generate fake guide for {external_item}. Proceeding to next item.`
    - Immediately continue the loop with the next unique `external_item` in the list. Do not halt or abort the overall batch execution.