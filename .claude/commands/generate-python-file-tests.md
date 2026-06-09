---
name: generate-python-file-tests
description: Generates Python unit tests for all public interfaces in a given Python file by parsing the file, referencing R documentation, and invoking the function test generator agent sequentially.
---

# Generate Python File Tests

## Description

When provided with a target Python file path and its corresponding R package documentation reference, your task is to parse the file for all function definitions, filter out internal helpers to isolate public interfaces, and sequentially invoke the `@generate-python-function-tests` agent to build comprehensive `pytest` suites for each public function.

## Execution Steps

### Step 1: Extract All Python Function Definitions

* Parse the target Python source file to identify and extract all function definitions.
* Compile a comprehensive list of all function names present in the file, regardless of their naming conventions (e.g., ignoring leading underscores for now).

### Step 2: Filter Public Interfaces via R Documentation

* Navigate to the documentation of the original R package (e.g., via CRAN, local `.Rd` files, or the package's reference manual).
* Cross-reference the comprehensive list of Python functions from Step 1 against the exported (public) functions detailed in the R documentation.
* Filter the list to retain *only* the functions that are documented as public interfaces in the original R package. Discard internal or private helper functions from the execution queue.

### Step 3: Execute Sequential Test Generation

Iterate through the filtered list of public functions from Step 2 sequentially. For each function:
1. **Invoke Test Generation Agent:** Call the `@generate-python-function-tests` agent. Provide the following context:
   * The target Python function name.
   * The target Python file path.
   * The original R package/function reference for functional equivalence benchmarking.
2. **Error Handling:** If the agent fails, times out, or throws an error while generating tests for a specific function, log a clear error message to the console. **Do not halt** the overall batch execution; proceed immediately to the next function in the queue.