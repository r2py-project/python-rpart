---
name: extract-c-folder-r-extern-items
description: Recursively processes a folder of C files to generate detailed CSV reports of R external references (macros, types, functions).
---

# Extract R External Items from a C Folder

## Description

When provided with a target directory containing C source or header files, your task is to process every C file (`.c` or `.h`) recursively. You will invoke the `@extract-c-file-r-extern-items` agent on each identified C file and save the extracted dependency data strictly as `.csv` files in a mirrored output directory.

## Execution Steps

### Step 1: Scan for C Source and Header Files

Recursively scan the provided target directory and all of its subdirectories. Compile a complete list of absolute file paths for every file with a `.c` or `.h` extension.

### Step 2: Sequential Processing and Error Isolation

Iterate through the compiled list of identified C files sequentially. For each file:
1. **Execute File-Level Agent:** Invoke the `@extract-c-file-r-extern-items` agent, providing it with the current `.c` or `.h` file path as its target.
2. **Error Handling:** If the sub-agent fails, times out, or throws an error for a specific file, log a clear warning to the console containing the file's path. Immediately proceed to the next C file in the list. Do not halt the entire batch execution due to individual file failures.

### Step 3: Save Output as CSV

For every successfully analyzed C file, save the tabular string output returned by the sub-agent according to these strict rules:
* **Data Format:** The output content must be saved strictly as a flat CSV file matching the schema defined by the sub-agent.
* **Naming Convention:** Use the exact base name of the original C file, but append it with `.csv` (e.g., `rpart.c` becomes `rpart.c.csv` and `rpart.h` becomes `rpart.h.csv`).
* **Output Directory Mapping:** Maintain the original directory hierarchy. Save the `.csv` file into the user-specified output directory, mirroring the exact relative path of the source C file relative to the input target folder.
* **Default Output Directory:** If the user did not explicitly specify an output directory, create a default directory path named `r_extern_analysis/{target_folder_name}/` (where `{target_folder_name}` is the base name of the target folder being scanned) and mirror the relative paths there.