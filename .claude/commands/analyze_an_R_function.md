
---
name: analyze-an-R-function
description: Guide for analyzing an R function to extract information about the parameters and return values.
---

# Analyze an R file

## Description

You need to analyze a specific R file given by the user or the context. For every function in the R file, read it through and then output the dependencies of all functions defined in the file into a JSON.

## Execution Steps

### Step 1: Extract Function Names

Sweep through the file and extract names of all functions defined in it.

### Step 2: Infer Parameter Types

For each function found in step 1, look at the body carefully to infer possible types of each input parameter. You may get several possible types for the same parameter.

### Step 3: Infer Return Types

For each function found in step 1, look at the body carefully to infer possible return types of the function. You may get several possible return types for the same function.

### Step 4: 