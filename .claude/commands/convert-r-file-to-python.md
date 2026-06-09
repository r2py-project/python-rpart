---
name: convert-r-file-to-python
description: Converts all functions in an R file to Python by parsing dependency graphs and sequentially invoking the function conversion agent.
---

# Convert an R File to Python

## Description

Translate all functions in an entire R file into Python. You will use the R source file, a comprehensive JSON dependency map, a CSV dependency graph, and a language dependency conversion guide folder. You must parse the dependencies, establish the correct conversion order, and invoke the `@convert-r-function-to-python` agent for each function.

## Execution Steps

### Step 1: Extract Function Definitions and Dependencies

* Parse the provided JSON file. The top-level keys represent all the function names within the target R file.
* For each identified function, extract its corresponding R code definition from the R source file.
* Isolate the JSON value associated with each function key to serve as its specific dependency map.

### Step 2: Sort Functions by Dependency Order (Leaves to Roots)

* Filter the provided dependency CSV file by the `r_file` column to isolate entries relevant only to the current target file.
* Sort the functions identified in Step 1 topologically, from leaves to roots. Ensure that child functions always precede their parent functions in the sorted execution list.
* *Note:* If a child function listed in the CSV is not found in the current R file's JSON/source, assume it has been converted elsewhere. Ignore it for the purposes of sorting the current file.

### Step 3: Execute Sequential Conversions

Iterate through the sorted function list from Step 2 sequentially. For each function:
1. **Invoke Conversion Agent:** Call `@convert-r-function-to-python`. Provide the following context:
   * The extracted R code definition.
   * The extracted JSON dependency map.
   * The folder containing language dependency conversion guides.
   * The target output folder for the specific R file. It should be `{target_output_folder}/{R_file_name}/`. For example, `{target_output_folder}/all.R/`. If the `{target_output_folder}` is not specified, the default should be `conversion_results/R/`.
2. **Error Handling:** If the agent fails or throws an error for a specific function, log a clear error message to the console. **Do not halt** the overall batch execution; proceed to the next function.