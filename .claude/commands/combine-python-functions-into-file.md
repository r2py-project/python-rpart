---
name: combine-python-functions-into-file
description: Combines all converted Python functions (stored as JSON) from a specified directory into a unified target Python file, handling import deduplication and project integration.
---

# Combine Converted Python Functions into a File

## Description

Given a source folder containing JSON-formatted function data and a target Python file, your task is to extract, format, and combine these functions into a single Python script. You must resolve duplicate imports, format the code syntactically, and integrate it safely into the target project structure.

## Execution Steps

### Step 1: Discover and Map JSON Files

* Scan the specified source folder for all files ending with `.json`.
* The filename (excluding the `.json` extension) represents the original R function name.

### Step 2: Extract and Format Function Definitions

For each JSON file, extract the `imports`, `function_prototype`, and `function_body`.
* **Concatenation:** Combine the `function_prototype` and the `function_body` array into a single multi-line string.
* **Indentation:** Ensure standard Python indentation. The `function_prototype` should have zero indentation, and every line within the `function_body` must be indented by exactly 4 spaces relative to the prototype.

*Example JSON Structure:*
```json
{
  "imports": [
    "import numpy as np",
    "from . import _KernSmooth"
  ],
  "function_prototype": "def rlbin(X: np.ndarray[np.float64], Y: np.ndarray[np.float64], gpoints: np.ndarray[np.float64], truncate: bool = True) -> dict:",
  "function_body": [
    "    n = len(X)",
    "    M = len(gpoints)",
    "    return {\"xcounts\": xcnts, \"ycounts\": ycnts}"
  ]
}
```

### Step 3: Deduplicate and Sort Imports

* Aggregate all `imports` arrays from every JSON file.
* Remove any duplicate import statements.
* Sort the deduplicated imports logically:
  1. Standard library imports (e.g., `import math`).
  2. Third-party imports (e.g., `import numpy as np`).
  3. Local project imports (e.g., `from .linbin import linbin`).
* Combine the sorted imports and the formatted function definitions into one final multi-line string.

### Step 4: Validate and Output the Combined Program

Do not blindly overwrite the target Python file. You must ensure the generated code aligns with the existing project architecture:
1. **Structural Scan:** Analyze the target project's build and configuration files (e.g., `pyproject.toml`, `meson.build`, `__init__.py`) to verify correct module naming conventions and dependency paths.
2. **Binding Corrections:** If the structural scan reveals discrepancies in how external C/Fortran bindings are exposed (e.g., `_KernSmooth` is built under a different path than what the JSON imports suggest), automatically fix the import paths in your combined string to match the reality of the build system.
3. **Safe Write:** Output the finalized string into the target Python file. If the file already contains code, integrate the new functions safely without breaking existing syntax or overwriting required project-level configurations.