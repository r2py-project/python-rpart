---
name: convert-r-tests-to-python
description: Batch converts all R test files in a specified folder to Python by invoking the convert-r-test-to-python agent.
---

# Convert all R Test Files in a Folder to Python

## Description

Translate an entire directory of R test files into Python. You will require the paths to the R test source folder, the source R library folder, and the corresponding Python library folder. For every R test file discovered, you must invoke the `@convert-r-test-to-python` agent to handle the individual translation.

## Execution Steps

### Step 1: Discover All R Test Files

- Scan the provided R test source folder recursively.
- Identify and compile a list of all R scripts (files ending with `.R` or `.r`). Pay special attention to standard test naming conventions (e.g., files starting with `test-` or `test_`).

### Step 2: Execute Conversions Iteratively

- Iterate through the compiled list of R files from Step 1 sequentially.
- For each file, invoke the conversion agent by calling the `@convert-r-test-to-python` agent.
- Pass the following explicit context to the agent for each invocation:
  1. The exact path to the current R test file.
  2. The path to the source R library folder.
  3. The path to the corresponding Python library folder (e.g., the root of the `r2py_kernsmooth` package, ensuring the agent can correctly locate or create the `tests/` directory as per its instructions).
  4. The output folder if specified.
  
### Step 3: Error Handling and Logging

- Monitor the output of the `@convert-r-test-to-python` agent.
- If the agent fails, hallucinates, or throws an error for a specific file, output a clear error message to the console noting the specific file that failed.
- **Do not halt** the batch execution. Catch the exception and proceed immediately to the next file in the list until all files have been attempted.