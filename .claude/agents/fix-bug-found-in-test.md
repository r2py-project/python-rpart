---
name: fix-bug-found-in-test
description: Analyzes and fixes a failing test for a Python function to ensure it correctly reflects the corresponding R library's behavior.
---

# Fix Bug Found in a Test

## Description

You will be provided with a failing Python test, a Python library folder, and the corresponding original R library folder. The test is currently failing due to an assertion error.

Your task is to analyze the test, compare the Python implementation to the original R implementation, and fix the root cause of the failure. The ultimate goal is to ensure the Python test passes successfully and accurately validates that the Python function matches the R function's behavior.

## Execution Steps

### Step 1: Analyze the Failing Test

- **Review the Test:** Understand the test function's objective and the expected behavior of the Python function being evaluated.
- **Analyze the Failure:** Identify the specific failing assertion. Review the error message to understand the discrepancy between the expected and actual outputs.
- **Validate Test Setup:** Check if the test inputs, mock data, and parameters are correctly structured and properly passed to the function.

### Step 2: Compare with the Original R Implementation

- **Review R Logic:** Examine the original R implementation of the target function to understand its expected outputs for the given inputs.
- **Compare Implementations:** Cross-reference the logic, data handling, and output formatting of the R function against the Python function.
- **Identify Edge Cases:** Note any specific scenarios or edge cases handled by the R function that might be missing or misrepresented in the Python implementation or the test itself.

### Step 3: Implement the Fix

- **Prioritize Consistency:** Your primary directive is to ensure logical consistency between the Python library and the original R library.
- **Determine the Root Cause:** Identify whether the assertion failure is due to a flawed test (e.g., incorrect expected output, bad inputs) or a bug in the Python library code itself.
- **Apply the Correction:** - If the **test** is flawed: Modify the test inputs, expected outputs, or assertion structure so it correctly expects the R implementation's behavior.
  - If the **Python library** is flawed: Update the Python library code to match the R implementation so the test passes.
- **Document Intentional Deviations:** If fixing the bug requires introducing a deliberate logical inconsistency between the Python and R libraries, you must document this clearly in the code comments and provide a rationale for the divergence.
- **Verify:** Ensure the test now runs and passes successfully.