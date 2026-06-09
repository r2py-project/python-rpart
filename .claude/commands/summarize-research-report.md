---
name: summarize-research-report
description: Summarizes the current session's activities, modifications, and findings into a precise, formal, and concise research report.
---

# Summarize Session into Research Report

This command analyzes the current working session and synthesizes the activities into a formal, concise research report.

## Prompt

Review the history of the current session, including all user requests, tool executions, codebase queries, and file modifications. Based on this context, generate a formal research report summarizing the work accomplished.

The report must adhere strictly to the following parameters:
- **Tone**: Precise, formal, and objective. Avoid conversational filler.
- **Length**: Highly detailed in facts but strictly concise in wording. Do not exceed 500-700 words unless absolutely necessary to capture critical technical details.
- **Specificity**: Explicitly mention specific file names, library versions, metrics, or core architectural decisions discussed or modified during the session. Avoid generic summaries.

Please structure the report using the following markdown format:

### 1. Abstract

Provide a 2-3 sentence high-level overview of the session's primary objective and the final outcome or state of the project.

### 2. Methodology & Actions Taken

Detail the concrete steps taken during the session. Include:
- Which files were created, modified, or analyzed.
- What tools or commands were executed.
- Any bugs investigated and the approach taken to resolve them.

### 3. Key Findings & Results

Highlight the core results of the session:
- Output metrics, successful compilations, or structural changes.
- Key technical insights or discoveries made during the work.
- Resolutions to any problems encountered.

### 4. Conclusion & Next Steps

Briefly conclude the report by stating the final status of the session's goal.