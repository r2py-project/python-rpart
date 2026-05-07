---
name: analyze-c-folder-dependencies
description: Analyzes all C files in a folder to extract structural dependency information file by file, categorizing calls strictly into internal and external dependencies.
---

# Analyze a C Folder for Dependencies

## Description
When provided with a target folder, your task is to recursively scan for all C files (including the header files), use the `@analyze-c-file-dependencies` agent on each file individually, and save the results as structured JSON files.

## Execution Steps

### Step 1: Scan for C Files
Recursively scan the provided target folder and all of its subdirectories for files with `.c` or `.h` extensions. Compile a complete list of their absolute file paths.

### Step 2: Process and Analyze
Iterate through the list of identified C files sequentially. For each file:
1. Invoke the `@analyze-c-file-dependencies` agent against the file and record its final JSON output.
2. If the command fails or throws an error for a specific file, log the error to the console and immediately continue to the next file in your list. Do not halt the entire operation.

### Step 3: Save Output
For every successfully analyzed C file, save the resulting JSON output according to these strict rules:
* **Naming Convention:** Use the exact name of the original C file, but append the extension `.json` (e.g., `init.c` becomes `init.c.json`).
* **Output Location:** If the user did not specify the output folder, save the new `.json` file in `c_refactor_analysis/{folder_name}/`, where the `{folder_name}` is the name of the target folder. The relative path must be the same as its corresponding original C file.