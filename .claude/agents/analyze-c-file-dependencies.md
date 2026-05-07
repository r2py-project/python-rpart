---
name: analyze-c-file-dependencies
description: Analyzes a provided C file to extract structural dependency information function by function (including function-like macros), categorizing calls strictly into internal and external dependencies.
---

# Analyze a C File for Dependencies

## Description

When provided with a C file (`.c` or `.h`), your task is to parse the file, identify every user-defined function or function-like macro, and trace all function-like calls (functions and function-like macros) made within their bodies. You must categorize these dependencies into strict groups and output the result as a structured JSON object.

## Execution Steps

### Step 1: Extract Function or Macro Declarations

Scan the target C file and identify every user-defined function or function-like macro defined within it (e.g., `int my_func() { ... }`). Create a list of these function or macro identifiers.

### Step 2: Analyze Function or Macro Bodies and Trace Calls

For every function or macro identified in Step 1, thoroughly analyze its execution body. Extract the identifier of every function or function-like macro invoked within that body. 

**Exclusions:**
* Completely ignore functions or macros that are part of the C standard library (e.g., `printf`, `malloc`, `strlen`, `size_t`).
* Extract **only the identifier** (e.g., `PyArg_ParseTuple`, `.Call`), never the arguments or the parentheses.

Categorize the extracted identifiers into the following two mutually exclusive lists. You may need to traverse and scan other files in the same project folder according to the included header files, and you have to use the following heuristics:

* **Internal Dependencies:**
    * *Definition:* Identifiers for functions or macros defined within the same C file, or those that appear in other `.c` or `.h` files within the same project folder, which are included via `#include` directives into the target file.
* **External Dependencies:**
    * *Definition:* Identifiers for functions or macros belonging to known external, third-party libraries or language bindings (for example, R API calls like `Rf_protect`, Python C API calls like `Py_Initialize`, etc.). Only if you cannot find the definition of the function or macro in the same file or any other file in the same project folder, you should classify it as an external dependency.

### Step 3: Generate JSON Output

Construct a JSON object where each key is the name of a function or macro identified in Step 1. The value for each key must be an object containing exactly two arrays of strings: `internal_dependencies` and `external_dependencies`. Deduplicate all identifiers within these arrays.

## Output Format Schema

You must output valid JSON strictly adhering to this structure. Do not include markdown code blocks if the system expects raw JSON.

{
  "my_custom_algorithm": {
    "internal_dependencies": ["helper_function_within_file", "project_utils_init"],
    "external_dependencies": ["Rf_protect", "PyArg_ParseTuple"]
  },
  "helper_function_within_file": {
    "internal_dependencies": [],
    "external_dependencies": []
  }
}