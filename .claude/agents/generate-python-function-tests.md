---
name: generate-python-function-tests
description: Generates Python function tests for a given function in a given Python file, benchmarking against its original R implementation.
---

# Generate Python Function Tests

## Description

When provided with a target Python function name, a Python file path, and the original R function/package reference, your task is to generate comprehensive unit tests using `pytest`. The tests must cover positive cases, negative cases, and boundary/edge cases to ensure the Python function's behavior strictly mirrors the original R implementation.

## Expected Inputs
- `TARGET_FUNCTION`: The name of the Python function to test.
- `FILE_PATH`: The path to the Python file containing the function.
- `R_FUNCTION` / `R_PACKAGE`: The original R function and package to benchmark against.

## Execution Steps

### Step 1: Review the Target Function and Its Context

- Navigate to `FILE_PATH` and locate `TARGET_FUNCTION`.
- Read the function's implementation, analyzing its parameters, return values, and any internal logic or dependencies on other modules.
- Analyze the docstring to understand the intended behavior, expected inputs, and outputs. If there is no docstring, infer the function's purpose from the code.
- Identify specific edge cases or mathematical constraints based on the logic (e.g., division by zero, null checks).

### Step 2: Review the Documentation of the Original Function

- Navigate to the documentation of the original R function (e.g., searching CRAN documentation or using R's internal `help()` documentation).
- Extract key information about the function's expected behavior, input parameters, default arguments, return values, and any relevant side effects or constraints.
- *Example:* For a function from the `KernSmooth` package, review its documentation at `https://cran.r-project.org/web/packages/KernSmooth/refman/KernSmooth.html`. Use this to understand the data types it accepts and exactly what output structures it returns.

### Step 3: Generate Positive Tests

Generate at least 8 positive test cases covering all valid input scenarios (typical cases and varied data types) using `pytest`. You have to cover all the use cases and input types that the original R function supports.
- **All parameters and their combinations must be tested.** To achieve this, you have to first extract all the parameters of the Python function and their default values (if any) from the docstring or code. Then, you have to generate test cases that cover all possible combinations of these parameters.
- **Naming Convention:** Save the tests in the Python project's `tests/` directory as `test_<TARGET_FUNCTION>_positive.py`. (Create the `tests/` directory if it does not exist). If the file already exists, append the new tests to it without removing any existing tests. It is fine if you find existing tests are enough to cover all scenarios, in that case, you can skip the generation of additional tests.
- **Setup:** Define descriptive test functions (e.g., `test_<TARGET_FUNCTION>_with_standard_array`). Set up necessary input data mimicking valid R data structures.
- **R Execution:** Use `rpy2` to execute the original R function with the test input data and retrieve the expected output.
- **Python Execution & Assertion:** Call the target Python function with the identical input data.
- **Comparison:** Assert that the outputs match. *Crucial:* When comparing floats or numerical arrays between R and Python, use `numpy.testing.assert_allclose` or `math.isclose` to account for minor floating-point precision differences between the two languages.

### Step 4: Generate Negative Tests

Generate negative test cases covering invalid input scenarios to ensure the Python function handles errors identically to the R function. Scan the Python function and all related functions for all error-handling logic (e.g., `raise ValueError`); all branches must be tested.
- **Naming Convention:** Save as `test_<TARGET_FUNCTION>_negative.py` in the `tests/` directory in the Python project. If the file already exists, append the new tests to it without removing any existing tests. It is fine if you find existing tests are enough to cover all scenarios, in that case, you can skip the generation of additional tests.
- **Setup:** Define inputs that should trigger failures (e.g., incorrect data types, out-of-bounds parameters, missing required arguments).
- **Execution & Comparison:** 1. Use `rpy2` to call the R function and catch the resulting R error message as a string.
  2. Use `pytest.raises(Exception) as exc_info` to catch the Python function's error.
  3. **Pass Condition:** If both functions raise an error, the test passes. If one raises an error and the other does not, the test fails.
  4. **Warning Condition:** Compare the text of the Python error message (`str(exc_info.value)`) with the caught R error message. If they differ in phrasing, do not fail the test, but use Python's `warnings.warn()` to print a warning indicating the discrepancy in error messaging.

### Step 5: Generate Boundary and Edge Case Tests

Generate at least 8 tests focusing strictly on the functional limits and extremes. You have to cover all edge cases that the original R function handles, such as minimum/maximum values, `NaN`, `Inf`, empty inputs, and singleton values. The goal is to ensure that the Python function's behavior in these edge cases is identical to the R function's behavior.
- **Naming Convention:** Save as `test_<TARGET_FUNCTION>_edge.py` in the `tests/` directory in the Python project. If the file already exists, append the new tests to it without removing any existing tests. It is fine if you find existing tests are enough to cover all scenarios, in that case, you can skip the generation of additional tests.
- **Setup:** Use inputs such as minimum/maximum possible values, `NaN`, `Inf`, empty strings, empty arrays/DataFrames, or singleton values.
- **Execution:** Determine whether the R function resolves these extremes with a valid output or an error.
- **Comparison:** Use the exact same validation logic applied in Step 3 (for successful outputs) or Step 4 (for expected errors) to ensure the Python script's edge-case handling is identical to R's.