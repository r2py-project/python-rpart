---
name: extract-c-file-r-extern-items
description: Extracts detailed location and usage data for R external references (macros, types, functions) in a C file.
---

# Extract R External Items from a C File

## Description

When provided with a C source file (`.c` or `.h`), your task is to locate every instance where an R external item is referenced. An R external item is defined as any type identifier, struct, macro, or function name that is declared in a header file located in the folder `~/.conda/envs/r-to-python/lib/R/include/`.

You must extract the exact line numbers, the containing code statements, and the specific R header file where each item is declared. The final output must be a strictly formatted, sorted CSV.

## Execution Steps

### Step 1: Identify Non-Local C Identifiers

Parse the provided C file to identify all macros, type definitions, structs, and function calls. Exclude any identifiers that are clearly defined within the provided C file itself or are part of the standard C library (e.g., `stdio.h`, `stdlib.h` elements).

### Step 2: Cross-Reference with R Headers

For the identifiers flagged in Step 1, use your search tools (e.g., `grep` or file-reading capabilities) to search both the C files that the current C file includes and the directory `~/.conda/envs/r-to-python/lib/R/include/`. Identify which of these items are declared in those R header files in `~/.conda/envs/r-to-python/lib/R/include/`.

For every matched R external item, record the following six data points:
* **`external_item`**: The exact name of the referenced item (e.g., `SEXP`, `PROTECT`, `ALLOC`).
* **`header_file`**: The specific header file within `~/.conda/envs/r-to-python/lib/R/include/` where the item is declared (e.g., `R.h`, `Rinternals.h`).
* **`category`**: A string flag indicating the category of the item, which can only be among "type", "variable", "function". Types include those defined by typedefs, structs, enums, or type-like macros. Variables are identifiers that represent values. Functions are identifiers that are invoked with parentheses `()`, which can be either functions or function-like macros. Note that there is no category for macros since they are always crafted to mimic the behavior of the three categories above.
* **`file_name`**: The name of the provided `.c` or `.h` file you are currently analyzing.
* **`line_number`**: The exact line number in the analyzed file where the statement containing the reference begins.
* **`context_statement`**: The complete code snippet containing the reference.
    * If the statement spans multiple lines, capture the entire complete statement from start to the terminating semicolon `;`, or the complete function prototype/macro definition.
    * Consolidate multi-line statements into a single string by escaping internal line breaks or replacing them with spaces.

### Step 3: Format and Sort Output

Compile the extracted data points into a CSV format. Sort the output primarily by `line_number` (ascending), and secondarily by `external_item` (alphabetically).

## Output Format Schema

You must output valid CSV data strictly adhering to the structure below. Include the exact header row. **CRITICAL:** You must enclose the `context_statement` strings in double quotes (`"`) to prevent commas or formatting elements within the C code from breaking the CSV structure.

```csv
external_item,header_file,category,file_name,line_number,context_statement
SEXP,R.h,type,rpart.c,40,"SEXP x = PROTECT(ALLOC(REALSXP, n));"
PROTECT,R.h,function,rpart.c,40,"SEXP x = PROTECT(ALLOC(REALSXP, n));"
ALLOC,R.h,function,rpart.c,40,"SEXP x = PROTECT(ALLOC(REALSXP, n));"
REALSXP,Rinternals.h,type,rpart.c,40,"SEXP x = PROTECT(ALLOC(REALSXP, n));"
```