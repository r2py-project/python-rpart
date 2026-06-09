---
name: fix-bugs-found-in-tests
description: Automatically runs a test suite, identifies failing tests, invokes the fix-bug-found-in-test agent to resolve them, and repeats until all tests pass.
---

# Fix Bugs Found in Tests

## Description

You will be provided with a folder containing Python test files, a target Python library folder, and the corresponding original R library folder. Your task is to execute the entire test suite, identify any test failures, and systematically invoke the `@fix-bug-found-in-test` agent to resolve the root cause of each failure. You will repeat this test-and-invoke cycle autonomously until the entire test suite passes.

## Execution Steps

### Step 1: Execute the Test Suite

- Navigate to the designated folder containing the Python test files.
- Run the full test suite using `pytest` for all files matching the pattern `test_*.py`.
- Capture the full terminal output from `pytest`. If all tests pass, exit successfully.
- If there are failures, isolate the very first failing test to begin the debugging process. Address failures sequentially.

### Step 2: Invoke the Fix Agent

- For the isolated failing test, invoke the `@fix-bug-found-in-test` agent.
- Ensure you pass the agent the necessary context it requires: the specific failing Python test (the output error message, the function, and the test file), the Python library folder, and the corresponding original R library folder.
- Allow the `@fix-bug-found-in-test` agent to complete its execution.

### Step 3: Validate and Loop

- Once the `@fix-bug-found-in-test` agent has finished its task, reinstall the fixed package, and then rerun the entire test suite using `pytest` across all `test_*.py` files to ensure the fix worked and no regressions were introduced.
- If new or remaining tests fail, repeat Steps 1 through 3 for the next failing test.
- Continue this cycle until `pytest` returns a 100% pass rate.
- *Safety Constraint:* If the `@fix-bug-found-in-test` agent attempts to fix the exact same failing test 3 times consecutively without the test passing, halt the loop and request user intervention to prevent an infinite loop.