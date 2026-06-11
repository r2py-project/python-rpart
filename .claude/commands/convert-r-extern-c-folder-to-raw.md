---
name: convert-r-extern-c-folder-to-raw
description: Automates the batch conversion of R external items from the `.Call/.External` API (SEXP-based) to the `.C/.Fortran` API (raw pointer-based) across all C files within a target directory.
---

# Convert R External Items in All C Files in a Folder to Raw Pointer-Based Code

## Description

Execute an in-place translation of all C source (`.c`) and header (`.h`) files within a specified target directory by converting all R external items from the `.Call/.External` (SEXP-based) API to the `.C/.Fortran` (raw pointer-based) API.

To execute this operation, you will process four distinct inputs: the target directory containing the C files, a CSV dependency graph mapping function hierarchies, a CSV R external item table detailing all necessary conversions, and a directory containing specific R external item conversion guides. You must parse the dependency graph to establish a strict topological conversion order and sequentially invoke the `@convert-r-extern-c-file-to-raw` agent for each file.

The CSV dependency graph will strictly adhere to the following schema:
```csv
c_file,function,level,parents,children
anova.c,anova,0,,graycode; graycode_init2
anova.c,anovainit,0,,ALLOC; graycode_init0
anova.c,anovass,0 (leaf),,
anovapred.c,anovapred,0 (leaf),,
free_tree.c,free_split,0 (leaf),,
gini.c,gini,0,,ALLOC; graycode; graycode_init1; graycode_init2; impurity
gini.c,gini_impure1,0 (leaf),,
gini.c,gini_impure2,0 (leaf),,
gini.c,ginidev,0 (leaf),,
gini.c,giniinit,0,,ALLOC; graycode_init0
gini.c,ginipred,0 (leaf),,
init.c,R_init_rpart,0 (leaf),,
```

The CSV R external item table will strictly adhere to the following schema:
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

### Step 1: Enumerate All Target Files

Perform a recursive scan of the target directory. Compile an exhaustive, deterministic list of all `.c` and `.h` files present. You must ensure absolute path completeness; omitting any valid source or header file is prohibited.

### Step 2: Establish Topological Dependency Order (Bottom-Up)

Utilize the provided CSV dependency graph to sort the compiled file list topologically, moving strictly from leaves (nodes with no children) to roots (nodes with no parents).

Child functions must be processed before their dependent parent functions. This rigorous bottom-up methodology ensures that as nested functions are converted, their inputs and outputs can be independently isolated and verified. This allows for the precise extraction of arguments and return values to capture middle states, guaranteeing that functional parity is proven at the granular level before integrating the converted components into higher-level functions. If cyclical dependencies or ambiguities prevent a perfect topological sort, optimize the sequence to maximize the number of child functions processed prior to their parents.

### Step 3: Execute Sequential file-by-file Conversions

Iterate sequentially through the topologically sorted list from Step 2. For each identified file, execute the following sub-routine:

1. **Invoke the File Conversion Agent:** Programmatically call the `@convert-r-extern-c-file-to-raw` agent. You must pass the following precise context parameters for the invocation:
   * The absolute file path to the current `.c` or `.h` file.
   * A filtered subset of the CSV R external item table containing *only* the rows where the `file_name` matches the current file being processed.
   * The path to the directory containing the R external item conversion guides.
   * An explicit directive to the agent to preserve all custom testing logic and ensure error messages remain identical to the original implementation to facilitate automated parity testing.

2. **Non-Blocking Error Handling:** If the `@convert-r-extern-c-file-to-raw` agent encounters a failure, throws an exception, or produces syntactically invalid code for a specific file, you must output a detailed error trace to the console (including the file name and the specific external item that caused the failure). **Do not terminate the batch process.** Log the failure and immediately proceed to the next file in the sorted sequence.