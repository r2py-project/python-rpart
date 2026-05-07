---
name: analyze-r-folder-dependencies
description: Analyzes all R scripts in a folder to extract structural dependency information file by file, categorizing function calls into language, internal, and external dependencies.
---

# Analyze an R Folder for Dependencies

## Description
When provided with a target folder, your task is to recursively scan for all R scripts, execute the `/analyze-r-file-dependencies` command on each file individually, and save the results as structured JSON files.

## Execution Steps

### Step 1: Scan for R Files
Recursively scan the provided target folder and all of its subdirectories for files with `.R` or `.r` extensions. Compile a complete list of their absolute file paths.

### Step 2: Process and Analyze
Iterate through the list of identified R files sequentially. For each file:
1. Run the `/analyze-r-file-dependencies` command against the file.
2. If the command fails or throws an error for a specific file, log the error to the console and immediately continue to the next file in your list. Do not halt the entire operation.

### Step 3: Save Output
For every successfully analyzed R file, save the resulting JSON output according to these strict rules:
* **Naming Convention:** Use the exact name of the original R script, but replace the `.R` or `.r` extension with `.json` (e.g., `data_cleaning.R` becomes `data_cleaning.json`).
* **Output Location:** If the user did not specify the output folder, save the new `.json` file in `structural_analysis/{folder_name}/`, where the `{folder_name}` is the name of the target folder. The relative path must be the same as its corresponding original R file.