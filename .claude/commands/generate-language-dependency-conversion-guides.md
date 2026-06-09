---
name: generate-language-dependency-conversion-guides
description: Orchestrates the generation of conversion guides for translating language dependencies from R to Python based on a provided CSV file.
---

# Generate Language Dependency Conversion Guides

## Description

When provided with a target `base_folder` and a CSV file matching the following schema:
```csv
language_dependency,file_path,function_name,line_number,call_body
Re,all.R,bkde,78,"Re(fft(kappa*gcounts, TRUE))"
Re,all.R,bkde2D,156,"Re(fft(rp*sp, inverse = TRUE)/(P1*P2))"
Re,all.R,bkfe,232,"Re(fft(kappam*Gcounts, TRUE))"
abs,all.R,dpill,531,abs(th24Q)
any,all.R,locpoly,610,any(bandwidth <= 0)
as.double,all.R,blkest,265,as.double(x)
as.double,all.R,blkest,265,as.double(y)
as.double,all.R,blkest,267,as.double(xj)
```
Your task is to orchestrate the batch processing of this CSV. You must extract rows corresponding to each unique `language_dependency` into separate CSV-formatted strings (each including the header row), invoke the `@generate-language-dependency-conversion-guide` agent for each subset, and save the resulting guides into a specified output directory.

## Execution Steps

### Step 1: Identify Unique Dependencies

Parse the input CSV file to identify all unique values in the `language_dependency` column.

*Note: The CSV is pre-sorted so identical dependencies are grouped together, allowing for efficient sequential processing.*

### Step 2: Extract and Process Each Dependency

Iterate through the list of identified unique `language_dependency` values sequentially. For each unique dependency:
1. **Extract the CSV Subset:** Isolate all rows matching the current `language_dependency`. Prepend the standard CSV header row to this subset to create a valid CSV text string.
2. **Execute Conversion Agent:** Invoke the `@generate-language-dependency-conversion-guide` agent. Pass the `base_folder` and the extracted CSV string as inputs to generate the specific conversion guide.
3. **Error Handling:** If the agent fails or throws an error during generation, log a clear error message to the console specifying the failed `language_dependency`, and immediately proceed to the next dependency in your list. Do not halt the overall batch execution.

### Step 3: Save Output as Markdown Files

For every successfully generated conversion guide, save the agent's markdown output to the file system according to these strict rules:
* **Naming Convention:** Name the output file exactly `{language_dependency}.md` (e.g., `Re.md`, `abs.md`).
* **Output Directory:** Save the files to the user-specified output directory. If the user did not explicitly provide one, create and use a default directory path named `language_dependency_analysis/conversion_guides/`.