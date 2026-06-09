---
name: extract-r-folder-language-dependencies
description: Recursively processes a folder of R files, utilizing pre-calculated structural analysis JSONs to generate detailed CSV reports of language dependency locations.
---

# Extract Language Dependencies from an R Folder

## Description

When provided with a target directory containing R source files and a separate directory containing their corresponding structural analysis results (in JSON format), your task is to process every R script recursively. You will invoke the `@extract-r-file-language-dependencies` agent on each matched file pair (the `.R` file and its corresponding `.json` analysis), and save the extracted dependency data strictly as `.csv` files in a mirrored output directory.

## Execution Steps

### Step 1: Scan for R Source Files

Recursively scan the provided target directory and all of its subdirectories. Compile a complete list of absolute file paths for every file with an `.R` or `.r` extension.

### Step 2: Map to JSON and Process

Iterate through the list of identified R files sequentially. For each R file:
1. **Locate the JSON Input:** Find the corresponding dependency analysis JSON file. It will be located in the provided structural analysis directory, sharing the exact same relative path as the R file, but with the `.R`/`.r` extension replaced by `.json`.
2. **Execute File-Level Agent:** Invoke the `@extract-r-file-language-dependencies` agent, providing it with the R file and its paired JSON file to generate the dependency data.
3. **Error Handling:** If the agent fails, throws an error, or if the required JSON file is missing, log a clear error to the console for that specific file and immediately proceed to the next R file in the list. Do not halt the batch execution.

### Step 3: Save Output as CSV

For every successfully analyzed file pair, save the resulting output from the agent according to these strict rules:
* **Data Format:** The output must be saved strictly as a CSV file.
* **Naming Convention:** Use the exact base name of the original R script, but replace the `.R` or `.r` extension with `.csv` (e.g., `data_cleaning.R` becomes `data_cleaning.csv`).
* **Output Directory:** Maintain the original directory structure. Save the `.csv` file into the user-specified output directory, using the exact same relative path as the original R file.
* **Default Output Directory:** If the user did not explicitly specify an output directory, create a default directory path named `language_dependency_analysis/{target_folder_name}/` (where `{target_folder_name}` is the base name of the target R folder) and mirror the relative paths there.