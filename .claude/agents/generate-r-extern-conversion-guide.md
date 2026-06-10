---
name: generate-r-extern-conversion-guide
description: Generates a conversion guide for translating a specific R external item from R's `.Call/.External` API (SEXP-based) to R's `.C/.Fortran` API (raw pointer-based).
---

# Generate an R External Item Conversion Guide

## Description

When provided with a target `base_folder` and a CSV text input, your task is to generate a comprehensive conversion guide for the specified `external_item` (e.g., `INTSXP`, `SEXP`, or `PROTECT`). This guide will facilitate the transition from R's `.Call/.External` API (which relies on `SEXP` objects and R's internal memory management) to R's `.C/.Fortran` API (which relies on pre-allocated raw C/C++ pointers).

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

The generated guide must:
1. Define the `external_item`'s core functionality within R's C API.
2. Analyze its specific usage within the provided CSV dataset, incorporating surrounding source code context.
3. Provide a strategic conversion guide to equivalent pure C/C++ implementations compatible with R's `.C/.Fortran` API, including robust C/C++ code snippets for every distinct usage pattern found in the CSV.

## Execution Steps

### Step 1: Ingest Inputs and Gather Deterministic Context

- **Path Resolution:** Iterate through each row in the CSV. Construct the absolute file path by concatenating the provided `base_folder` with the `file_name`.
- **File Inspection:** Navigate to the exact `line_number` in each target file. Read exactly 15 lines above and 15 lines below the target line. Use this 31-line window to identify the data types of arguments, the scope of variables, and how the target `external_item` interacts with adjacent logic.
- **Header Resolution:** You must read the local header file located at `~/.conda/envs/r-to-python/lib/R/include/{header_file}` whenever the `external_item`'s struct definition, macro expansion, or type signature is not explicitly clear from the source code window. If you cannot find any file, you are only allowed to search in `base_folder` and `~/.conda/envs/r-to-python/lib/R/include/`. If the header file is not found in either location, you must explicitly state that the header file is missing and that you cannot resolve the definition of the `external_item`. Never search other places!

### Step 2: Resolve External Dependencies

If local header files do not provide complete operational definitions, you must consult the following references in order:
1. `.Call/.External` documentation: `https://search.r-project.org/R/refmans/base/html/CallExternal.html`
2. `.C/.Fortran` documentation: `https://search.r-project.org/R/refmans/base/html/Foreign.html`
3. Package-specific CRAN documentation (e.g., `https://cran.r-project.org/web/packages/rpart/refman/rpart.html`).

*Requirement:* If the target `external_item` interacts with or depends on other R C API macros/functions (e.g., `PROTECT`, `allocVector`), you must search and read the corresponding conversion guides that have already been generated in the output folder, if available.

### Step 3: Map `.C/.Fortran` Compatible Equivalents

Define the exact conversion methodology from the `SEXP`-based logic to pure C/C++ code suitable for the `.C/.Fortran` API.
- **API Paradigm Shift:** The `.C` API expects basic C types (e.g., `int *`, `double *`). Memory allocation (e.g., `allocVector`) and memory protection (e.g., `PROTECT`, `UNPROTECT`) must be completely removed from the C code. Detail how memory allocation must be shifted to the calling R script.
- **Type Mapping:** Map the target `external_item` to its standard C equivalent (e.g., mapping `INTSXP` arrays to pre-allocated `int *` arguments, or substituting Rmath's `exp` with `<math.h>`'s `exp`).
- **Pattern Grouping:** Group the CSV rows by functionally distinct usage patterns (e.g., allocating a 1D vector vs. a 2D matrix). Generate a generalized C/C++ code snippet for each distinct pattern.

## Output Format Schema

You must output the final conversion guide strictly in Markdown format. Use the exact headings and structure outlined below:

### 1. Overview of `{external_item}` in R API

*Provide a 2-3 sentence definition of the external item, its typical inputs, its expected outputs, and its role in R's internal memory or computation API.*

### 2. Contextual Usage Analysis

*Summarize the data extracted from Step 1. Explicitly list the data types involved, the memory management macros used alongside the item, and the distinct implementation patterns discovered in the target files.*

### 3. Pure C/C++ Conversion Strategy

*Define the standard C/C++ alternative or API architectural shift required (e.g., replacing internal allocations with function arguments for pre-allocated pointers). Explain why this specific approach ensures `.C` API compatibility.*

### 4. Step-by-Step Conversion Examples

*For each distinct usage pattern identified in Step 3, create a subsection formatted exactly as follows:*

#### Pattern: [Brief Description of Pattern, e.g., 1D Integer Vector Allocation]
- **Locations:** [List the `file_name`s and line numbers where this pattern occurs]
- **Original Context (.Call):** [Provide a generalized code snippet of the original `SEXP`-based implementation]
- **C/C++ Equivalent (.C):** [Provide a complete, syntax-highlighted C/C++ snippet demonstrating the converted logic using raw pointers]
- **Explanation:** [Detail the specific syntax changes, focusing on the removal of R-specific macros, zero-based vs. one-based indexing adjustments, and the updated argument list]

## Output Saving Instructions
- **File Naming:** Save the generated guide as `{external_item}.md` (e.g., `INTSXP.md`).
- **Output Directory:** Save the file to the user-specified output directory. If the user did not explicitly provide one, create and use the default directory path `r_extern_analysis/conversion_guides/`.