---
name: analyze-r-file-dependencies
description: Analyzes an R script to extract structural dependency information function by function, categorizing calls into language, internal, and external dependencies.
---

# Analyze an R File for Dependencies

## Description

When provided with an R file (`.R`), your task is to parse the file, identify every user-defined function, and trace all function calls made within their bodies. You must categorize these dependencies into strict groups and output the result as a structured JSON object.

## Execution Steps

### Step 1: Extract Function Declarations

Scan the target R file and identify every user-defined function declared within it (e.g., `my_func <- function(...) { ... }`). Create a list of these function names.

### Step 2: Analyze Function Bodies and Trace Calls

For every function identified in Step 1, thoroughly analyze its execution body. Extract every function call made within that body and categorize it into one of the following three mutually exclusive lists:

* **Language Dependencies:**
    * *Definition:* Functions provided by Base R (e.g., `c()`, `lapply()`, `print()`) or functions from installed CRAN/Bioconductor packages (e.g., `mutate()`, `ggplot()`). 
    * *Heuristic:* Include any function call that includes a package namespace prefix (e.g., `dplyr::select`) or any standard function that is not defined locally.
* **Internal Dependencies:**
    * *Definition:* Functions that are defined within the exact same R file, or functions that are explicitly defined in other `.R` files within the same project directory.
* **External Dependencies:**
    * *Definition:* Foreign language interfaces (typically C, C++, or Fortran) invoked from within the R code.
    * *Heuristic:* Look specifically for calls to `.Call()`, `.C()`, `.Fortran()`, `.External()`, or `useDynLib()`. Extract the name of the compiled routine being invoked (usually the first string argument passed to these interfaces).

### Step 3: Generate JSON Output

Construct a JSON object where each key is the name of a function identified in Step 1. The value for each key must be an object containing exactly three arrays of strings: `language_dependencies`, `internal_dependencies`, and `external_dependencies`. Deduplicate all function names within these arrays.

## Output Format Schema

You must output valid JSON strictly adhering to this structure. Do not include markdown code blocks if the system expects raw JSON.

```json
{
  "function_name_1": {
    "language_dependencies": ["c", "lapply", "dplyr::filter"],
    "internal_dependencies": ["helper_function_within_file"],
    "external_dependencies": [".Call(\"c_routine_name\")"]
  },
  "function_name_2": {
    "language_dependencies": ["print"],
    "internal_dependencies": ["function_name_1"],
    "external_dependencies": []
  }
}
```