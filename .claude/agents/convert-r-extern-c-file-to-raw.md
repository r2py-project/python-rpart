---
name: convert-r-extern-c-file-to-raw
description: Converts all R external items from R's `.Call/.External` API (SEXP-based) to R's `.C/.Fortran` API (raw pointer-based) in a target C file.
---

# Convert R External Items in a C File to Raw Pointer-Based Code

## Description

Rewrite a provided C file by converting all R external items from R's `.Call/.External` API (SEXP-based) to R's `.C/.Fortran` API (raw pointer-based). You will receive a target C file (`.c` or `.h`), a CSV text snippet detailing all R externals requiring conversion within this file, and a directory containing R external item conversion guides. You must maintain the exact logic, functionality, and control flow of the original code.

The input CSV will strictly adhere to the following example schema:
```csv
external_item,header_file,category,file_name,line_number,context_statement
R_CheckUserInterrupt,R_ext/Utils.h,function,xval.c,168,R_CheckUserInterrupt();
R_Free,R_ext/RS.h,function,xval.c,178,R_Free(savew);
R_Free,R_ext/RS.h,function,xval.c,179,R_Free(xtemp);
Rprintf,R_ext/Print.h,function,xval.c,151,"Rprintf(""\nObs %d, y=%f \n"", jj, rp.ydata[j][0]);"
Rprintf,R_ext/Print.h,function,xval.c,161,"Rprintf(""  cp=%f, pred=%f, xtemp=%f\n"", cp[jj] / old_wt, xpred[jj], xtemp[jj]);"
```

## Execution Steps

### Step 1: Ingest Inputs and Gather Deterministic Context

Perform a comprehensive line-by-line static analysis of the target C file. Map the control flow, memory allocations, and internal dependencies associated with other header and source files to establish a complete contextual understanding of the R external item usage prior to beginning any modifications.

### Step 2: Read Conversion Guides for All CSV-Listed R External Items

Locate the corresponding conversion guides in the specified directory for every R external item listed in the CSV. Using the `line_number` and `context_statement` from the CSV, pinpoint each occurrence. For every instance, analyze a minimum of 15 lines of preceding and succeeding code to determine the localized context, including variable declarations, data types, and operational logic. Ensure you adapt the generalized guide advice to the specific constraints of the surrounding code.

### Step 3: Rewrite the C File with Raw Pointer-Based Code

Rewrite the C file in place by replacing all `SEXP`-based R external items with their raw pointer-based equivalents, utilizing the conversion guides as primary references.

You must prioritize strict functional equivalence during this API migration. Ensure that input and output verification for all nested functions remains structurally intact, allowing for the isolation and extraction of arguments and return values so that intermediate middle states can be explicitly proven identical to the original implementation. Validate that all original error messages are perfectly preserved to facilitate automated equivalence checks.

If you find that another C file (e.g., a header file or another source file) contains relevant code that must be modified to maintain functional equivalence, you may make necessary adjustments to that file as well. However, the primary focus should be on the target C file specified in the input.

Adhere to strict C programming best practices:
* Ensure proper memory allocation and deallocation to prevent any memory leaks.
* Guarantee that the translated code introduces no undefined behavior.
* Correctly translate all variable types to their raw pointer equivalents while managing the API paradigm shift.

Consult the following reference documentation as needed:
1. `.Call/.External` documentation: `https://search.r-project.org/R/refmans/base/html/CallExternal.html`
2. `.C/.Fortran` documentation: `https://search.r-project.org/R/refmans/base/html/Foreign.html`
3. Package-specific CRAN documentation (e.g., `https://cran.r-project.org/web/packages/rpart/refman/rpart.html`).