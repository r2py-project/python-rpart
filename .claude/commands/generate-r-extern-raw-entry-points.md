---
name: generate-r-extern-raw-entry-points
description: Scans R source files for .Call/.External invocations, identifies every C function called directly from R, and generates a pure C entry-point wrapper for each that replaces SEXP-based parameters and return values with plain int/double arrays callable from Python.
---

# Generate Pure C Entry Points for R-Callable C Functions

## Description

Given four inputs — an `r_base_folder` containing R source files, a `c_base_folder` containing the package C source files, a `fake_headers_folder` containing the pre-generated fake R C API headers, and an `output_folder` for the resulting `.c` files — your task is to:

1. Recursively scan every `.R` file in `r_base_folder` to locate all `.Call` and `.External` invocations and record the C function name, call type, R call expression, and source location for each one.
2. Identify all unique C functions that are invoked directly from R, consolidating multiple call sites for the same function.
3. Sequentially invoke the `@generate-r-extern-raw-entry-point` agent for each unique C function to produce a `{c_function}_c.c` file in `output_folder` containing a plain-C wrapper that exposes the function to Python without SEXP.

## Execution Steps

### Step 1: Scan R Source Files and Build the Call Site Table

Recursively scan `r_base_folder` for all files with a `.R` or `.r` extension. For every R file found, parse it line by line to locate every `.Call(...)` and `.External(...)` invocation. For each invocation found, extract and record the following four data points:

- **`c_function`**: The name of the C function being called. This is the first argument to `.Call`/`.External`. It may appear as:
  - A registered native symbol object (e.g., `C_rpart`, `C_pred_rpart`) — strip the `C_` prefix to obtain the C function name.
  - A quoted string literal (e.g., `"rpart"`, `"pred_rpart"`) — use the string content directly.
- **`call_type`**: Either `Call` (for `.Call(...)`) or `External` (for `.External(...)`).
- **`r_file`**: The path of the R file, relative to `r_base_folder`.
- **`r_line`**: The line number where the `.Call`/`.External` expression begins.
- **`r_call_expression`**: The complete `.Call`/`.External` expression, including all argument names or expressions passed after the function identifier. If the call spans multiple lines, consolidate it into a single string with internal whitespace collapsed.

Compile all records into an internal call site table adhering to this CSV schema:

```csv
c_function,call_type,r_file,r_line,r_call_expression
rpart,Call,rpart.R,145,".Call(C_rpart, ncat, method, opt, parms, xvals, xgrp, ymat, xmat, wt, ny, cost)"
xpred,Call,xpred.rpart.R,52,".Call(C_xpred, ncat, method, opt, parms, xvals, xgrp, ymat, xmat, wt, ny, cost, all, cp, toprisk, nresp)"
pred_rpart,Call,predict.rpart.R,89,".Call(C_pred_rpart, dimx, nnode, nsplit, dimc, nnum, nodes2, vnum, split2, csplit2, usesur, xdata2, xmiss2)"
rpartexp2,Call,rpart.R,256,".Call(C_rpartexp2, dtimes, eps)"
init_rpcallback,Call,rpart.R,198,".Call(C_init_rpcallback, rho, ny, nr, expr1, expr2)"
```

### Step 2: Identify Unique C Functions and Consolidate Call Sites

From the call site table built in Step 1, extract the definitive ordered list of unique `c_function` values, preserving the first-occurrence order across the scanned R files. For each unique C function, collect all rows from the table that share that `c_function` value into a grouped CSV subset — multiple rows exist when the same C function is called from more than one R file or location.

### Step 3: Generate Entry-Point Files Sequentially

Iterate through the ordered list of unique C functions from Step 2 one at a time. For each function, strictly execute the following sub-steps:

1. **Prepare the CSV Subset:** Take all rows from the call site table where `c_function` matches the current target. Prepend the exact header row (`c_function,call_type,r_file,r_line,r_call_expression`) to form a valid, standalone CSV-formatted string.
2. **Invoke the Entry-Point Agent:** Call the `@generate-r-extern-raw-entry-point` agent, passing the `r_base_folder`, `c_base_folder`, `fake_headers_folder`, `output_folder`, and the CSV subset string.
3. **Non-Blocking Error Handling:** If the agent fails, times out, or produces syntactically invalid C code, you must:
    - Log the precise error to the console: `ERROR: Failed to generate raw entry point for {c_function}. Proceeding to next function.`
    - Immediately continue to the next C function in the list. Do not halt the overall batch.