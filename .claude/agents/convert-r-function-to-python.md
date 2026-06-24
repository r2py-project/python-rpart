---
name: convert-r-function-to-python
description: Converts an R function to its Python equivalent using a provided JSON dependency map and conversion guides.
---

# Convert an R Function to Python

## Description

Rewrite a provided R function into Python. You will receive the R function code, a JSON file detailing its dependencies, a folder of language dependency conversion guides, and a target output folder. You must maintain the exact logic and functionality of the original code.

## Execution Steps

### Step 1: Infer Types and Define Prototype

Identify all parameters and return types by referencing the R function's CRAN documentation (e.g., the `rpart` reference manual `https://cran.r-project.org/web/packages/rpart/refman/rpart.html`).
* Create a Python function prototype using complete type annotations.
* **Never omit any types or subtypes inside type annotations.** For example, `dict[str, int]` or `np.ndarray[Any, np.dtype[np.float64]]` cannot be simplified as `dict` or `np.ndarray` if the subtypes are known. Also, if there are multiple possible types for a parameter, include all of them in the annotation (e.g., `str | None`).
* *Example:* `def example_function(param1: int, param2: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:`

### Step 2: Resolve Dependencies

Analyze the provided JSON dependency map. Handle each dependency category as follows:
* **Language Dependencies:** Find the corresponding `{language_dependency}.md` files (e.g., `min.md`, `seq.md`) in the conversion guides folder for Python translation strategies and examples. You don't have to follow them strictly, but they should guide your translation of R constructs to Python.
* **Internal Dependencies:** Locate and review the previously converted definitions in the output folder (`{function_name}.json`). Strictly follow their Python logic to ensure correct integration.
* **External Dependencies:** Call C entry points directly via the `cffi` `_lib` object already set up in the module. *Example: Map `.Call(C_rpart, ...)` directly to `_lib.rpart_c(...)`. The available C entry points are `rpart_c`, `pred_rpart_c`, `xpred_c`, `rpartexp2_c`, and `init_rpcallback_c`, all loaded from `_rpart_core.so`. Use the module-level helpers `_iptr`, `_dptr`, `_cptr`, `_int32`, and `_float64` for array preparation, and always check errors with `_check_error` after each call.* If you are not familiar with R's `.Call` interface, refer to the R Internals manual: `https://search.r-project.org/R/refmans/base/html/CallExternal.html`. If you are not familiar with `cffi` in Python, refer to the documentation: `https://cffi.readthedocs.io/en/latest/`. Feel free to look up the project folder `r2py_rpart` for the implementation details of the C entry points and examples of how to call C entry points from Python.

### Step 3: Rewrite Function Body

Translate the R function body into Python syntax.
* Strictly preserve the original logic and functional intent.
* Apply the patterns learned from the language conversion guides.
* Handle R-to-Python structural differences (e.g., 1-based vs. 0-based indexing, data structures, control flow) appropriately.

## Output Format

Output strictly valid JSON to `{function_name}.json` in the output folder. **Do not wrap the output in markdown code blocks.** The function body may contain multiple lines, and you should include every line as a separate string in the array. Follow the following structure strictly (even if there are no imports, you must include an empty array for imports):
```json
{
  "imports": [
    "import numpy as np"
  ],
  "function_prototype": "def converted_function(param1: int, param2: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:",
  "function_body": [
    "    # Function body goes here",
    "    pass"
  ]
}
```