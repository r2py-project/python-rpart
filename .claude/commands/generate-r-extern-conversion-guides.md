---
name: generate-r-extern-conversion-guides
description: Orchestrates the batch generation of conversion guides for translating R's `.Call/.External` APIs (SEXP-based) to R's `.C/.Fortran` APIs (raw pointer-based).
---

# Generate R External Item Conversion Guides

## Description

When provided with a target `base_folder`, a CSV file matching the schema below, and a target `output_directory`, your task is to orchestrate the batch processing of this dataset. You must segment the CSV by unique `external_item` values and iteratively invoke the `@generate-r-extern-conversion-guide` agent for each subset to generate the resulting guides to the specified output directory.

### Expected CSV Schema

Example:
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

### Step 1: Identify Unique Dependencies

Read and parse the input CSV file. Extract a definitive list of all unique values present in the `external_item` column (e.g., `DL_FUNC`, `DllInfo`, `INTSXP`, `REALSXP`). 

*Note: Assume the CSV is pre-sorted. Identical external items are grouped sequentially to allow for efficient linear processing.*

### Step 2: Extract Segments and Invoke Sub-agents

Iterate sequentially through the list of unique `external_item` values one after another. Since the previous generated conversion guides might be useful for the upcoming ones, you have to execute them sequentially without any parallelism. For each unique item, strictly execute the following sub-steps:

1. **Extract the CSV Subset:** Isolate all rows where the `external_item` column matches the current target. Prepend the exact CSV header row (`external_item,header_file,category,file_name,line_number,context_statement`) to this subset to create a valid, standalone CSV-formatted string.
2. **Execute Conversion Agent:** Invoke the `@generate-r-extern-conversion-guide` agent. Pass the target `base_folder`, the newly created CSV subset string, and the specified output directory as inputs.
3. **Strict Error Handling:** If the agent execution fails, times out, or throws an error at any point, you must:
    - Log a precise error message to the console: `ERROR: Failed to generate guide for {external_item}. Proceeding to next item.`
    - Immediately continue the loop with the next unique `external_item` in the list. Do not halt or abort the overall batch execution.