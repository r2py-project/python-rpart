---
name: generate-language-dependency-conversion-guide
description: Generates a conversion guide for translating a specific language dependency from R to Python.
---

# Generate Language Dependency Conversion Guide

## Description

When provided with a target `base_folder` and a CSV text input matching the following schema:
```csv
language_dependency,file_path,function_name,line_number,call_body
exp,all.R,locpoly,663,"exp(seq(log(hlow), log(hupp), length.out = Q))"
exp,all.R,sdiag,768,"exp(seq(log(hlow), log(hupp), length.out = Q))"
exp,all.R,sstdiag,845,"exp(seq(log(hlow), log(hupp), length.out = Q))"
```
Your task is to generate a comprehensive conversion guide for the specified `language_dependency` (e.g., `exp`). The guide must include:
1. A clear explanation of the `language_dependency`'s core functionality in R.
2. A detailed analysis of its usage within the provided CSV data, including the surrounding context retrieved directly from the source R files.
3. A conversion guide to equivalent Python functions/methods, providing general Python code snippets for all scenarios in the CSV.

## Execution Steps

### Step 1: Ingest Inputs and Gather Context

- Iterate through each row in the CSV. Using the provided `base_folder`, navigate to the exact `file_path` and `line_number`.
- Read the target line and the surrounding code blocks. You must read enough lines to fully capture multi-line function calls, identify the data types of arguments being passed (e.g., scalars vs. vectors), and understand how the result interacts with adjacent logic.
- If the R dependency's behavior is complex or ambiguous, search `https://www.rdocumentation.org/` to confirm its official functionality, default arguments, and edge cases.
- If there is ambiguity about the valid types of the functions' parameters or return values, you can also look them up in the document `https://cran.r-project.org/web/packages/rpart/refman/rpart.html`.

### Step 2: Determine Python Equivalents

- **Prioritize Vectorization:** Because R inherently vectorizes operations, you must default to evaluating `numpy`, `scipy`, or `pandas` as the primary Python equivalents.
- Choose the library that best matches R's vectorized nature. For example, if translating R's `exp`, strongly prefer `numpy.exp()` over the standard library `math.exp()` unless the context explicitly proves only a scalar is being processed.
- Carefully map R arguments to Python kwargs (e.g., translating R's `seq(..., length.out=Q)` to Python's `np.linspace()`).
- You are free to search online documentation for the chosen Python libraries to ensure you are using the most efficient and idiomatic functions.

## Output Format Schema

You must output the final conversion guide strictly in well-structured Markdown format. Use the following outline to ensure consistency and readability:

### 1. Overview of `{language_dependency}` in R

*Provide a concise explanation of what the dependency does, its typical inputs, and expected outputs.*

### 2. Contextual Usage Analysis

*Summarize how the dependency is applied across the provided dataset. Mention the data types involved and any recurring patterns found in the source files.*

### 3. Python Conversion Strategy

*State the chosen Python library (e.g., `numpy`) and explain why it is the most robust equivalent for these specific usage contexts.*

### 4. Step-by-Step Conversion Examples

*For every functional-distinct usage found in the CSV, provide a subsection containing:*
- **Locations:** Files and Function names.
- **Original R Context:** The types of input parameters and return values, and a generalized code snippet for demonstration.
- **Python Equivalent:** A complete, executable Python code snippet demonstrating the converted logic.
- **Explanation:** A brief breakdown of the syntax translation, addressing any nuances like zero-based indexing, argument mapping, or library imports.