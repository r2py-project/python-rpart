---
name: modify-c-file-with-fake-headers
description: Modifies a single C source or header file in-place to replace all R API header includes with a single fake_R.h include, validates every R external symbol used in the file against the fake symbol inventory, and comments out (never removes) any statement that references a symbol absent from the fake headers -- while never commenting out function parameter declarations.
---

# Modify a C File to Use Fake R Headers

## Description

When provided with a `c_file` (absolute path to a `.c` or `.h` file) and a `fake_r_header` (absolute path to `fake_R.h`), your task is to modify the file **in-place** so it compiles correctly with `g++ -x c++` using the fake R API instead of `libR.so`. Three categories of change are applied:

1. **Include replacement** -- every `#include` line that references a real R API header is commented out and replaced by a single `#include "fake_R.h"` directive.
2. **Symbol validation** -- every R external symbol used in the file is cross-referenced against the complete fake symbol inventory derived from `fake_R.h` and all its transitively included headers.
3. **Unfakeable-symbol suppression** -- any statement whose only function is to call or assign a symbol that is absent from the fake headers is commented out (not deleted) with an explanatory note. The one inviolable exception: **lines that are part of a function parameter declaration must never be commented out**, regardless of which symbols appear on them.

If the file contains no R API includes and no R API symbols, it is left unchanged.

### The Non-Negotiable Parameter Rule

A line is a **function parameter line** if it appears inside the parameter list of a function definition -- between the opening `(` that immediately follows the function name and the matching `)` that precedes the opening `{` of the function body. This applies equally to:
- Single-line signatures: `SEXP foo(SEXP x, SEXP y) {`
- Multi-line signatures:
  ```c
  SEXP foo(SEXP x,
            SEXP y,
            int n) {
  ```

Function parameter lines **must never be commented out**, even when they reference an unfakeable symbol. Instead, append a trailing `/* NOTE: parameter references unfakeable symbol '{symbol}' -- ensure fake_R.h provides a compatible type */` comment to that line.

This rule exists because commenting out a parameter declaration corrupts the function's ABI and prevents all callers from compiling -- a far worse outcome than leaving an unfakeable type in a parameter position.

### Recognised R API Headers

The following include patterns identify real R API headers that must be replaced. Both angle-bracket and quoted forms are recognised:

```
<R.h>              "R.h"
<Rinternals.h>     "Rinternals.h"
<Rdefines.h>       "Rdefines.h"
<Rversion.h>       "Rversion.h"
<Rmath.h>          "Rmath.h"
<R_ext/Rdynload.h> "R_ext/Rdynload.h"
<R_ext/Error.h>    "R_ext/Error.h"
<R_ext/Memory.h>   "R_ext/Memory.h"
<R_ext/RS.h>       "R_ext/RS.h"
<R_ext/Utils.h>    "R_ext/Utils.h"
<R_ext/Arith.h>    "R_ext/Arith.h"
<R_ext/Boolean.h>  "R_ext/Boolean.h"
<R_ext/Print.h>    "R_ext/Print.h"
```

Additionally, any `#include` whose path matches `R_ext/` or starts with `Rinternals`, `Rdefines`, `Rversion`, `Rmath` is treated as an R API header.

`#include <libintl.h>` is **not** an R API header and must **never** be touched, even when it appears inside an `#ifdef ENABLE_NLS` block alongside real R headers.

## Execution Steps

### Step 1: Build the Fake Symbol Inventory

Read `fake_r_header` (the `fake_R.h` file). Collect every `#include "..."` directive it contains and recursively read each referenced header from the same directory. For every header file read, extract the names of all symbols defined: `typedef`s, `struct` tags, `enum` constants, `#define` macro names, `inline` function names, and `extern` variable names. Accumulate all of these into a single flat set: the **fake symbol inventory**.

This inventory is the ground truth for Step 4. A symbol is considered **fakeable** if and only if its name appears in this inventory. A symbol is **unfakeable** if it appears in none of the fake headers despite being an R API symbol (i.e., it would have been provided by one of the real R headers listed above).

**Important:** The following Category E R Interpreter Items are present in the fake headers as function-pointer stubs. They are therefore **fakeable** for compilation purposes (they compile and link; at runtime they throw `RError` if no Python callback has been registered). Do **not** comment out their usage sites:
- `eval`, `Rf_eval`
- `findVar`, `Rf_findVar`
- `findVarInFrame`, `Rf_findVarInFrame`
- `install`, `Rf_install`
- `R_getVar`, `compat_getVar`

Only symbols that are **genuinely absent** from the fake symbol inventory are candidates for suppression in Step 4.

### Step 2: Read the Target File

Read the entire contents of `c_file` into a line-indexed buffer. Do not modify anything yet. Classify every line as one of the following:
- **R-include line** -- matches one of the R API header patterns from the Description.
- **Non-R-include line** -- any other `#include`.
- **Preprocessor line** -- `#ifdef`, `#endif`, `#define`, etc.
- **Function signature line** -- part of a function definition's parameter list (apply the parameter rule from the Description; see also Step 3 for detection logic).
- **Code line** -- any other line inside a function body or at file scope.
- **Comment line** -- already wrapped in `/* */` or `//`.

### Step 3: Replace R Header Includes

Iterate through the line buffer. For each **R-include line**:

1. **Comment it out in place.** Replace the line with:
   ```c
   /* [FAKE_R] <original_line_content_trimmed> */
   ```
   The original text is preserved inside the comment so the replacement is auditable and reversible.

2. **Mark the insertion point.** After processing all consecutive R-include lines in a block, record the line index immediately following the last commented-out include in that block as the **insertion point** for `fake_R.h`. If R-include lines appear in more than one location in the file (e.g., one group near the top and one after `#ifdef ENABLE_NLS`), use the position immediately after the **first** group as the insertion point.

3. **Insert the fake_R.h include.** At the recorded insertion point, insert the following new line:
   ```c
   #include "fake_R.h"  /* replaces all R API headers above */
   ```
   where `"fake_R.h"` is the **basename only**. The full directory path is supplied to the compiler via the `-I` flag during the verification step in the command; do not embed an absolute path in the source file.

4. **Idempotency guard.** Before inserting, scan the entire file for any existing `#include "fake_R.h"` or `#include <fake_R.h>` line. If one is already present (from a previous run of this agent), do not insert a second copy.

5. **Files with no R includes.** If the file contains no R-include lines at all, skip this step entirely and proceed to Step 4 without any include modifications.

### Step 4: Validate and Suppress Unfakeable Symbols

Walk through every non-comment line in the modified buffer (after Step 3). For each line, tokenise it and check each identifier against the fake symbol inventory built in Step 1. If an identifier is both an R API symbol (i.e., it would have been provided by one of the real R headers) and **absent** from the fake symbol inventory, apply the following rules:

**Rule 1 -- Detect the containing syntactic context.**

Before deciding whether to comment out the line, determine whether it is part of a function parameter list:
- Parse backwards from the suspicious identifier to find the most recently opened `(` that has not yet been closed by a matching `)`.
- Then parse backwards further to find whether that `(` is immediately preceded by an identifier followed by optional whitespace -- the signature of a function call or function definition.
- If the `(` is part of a **function definition** (i.e., it is followed eventually by `{` at the same brace depth, with no intervening `;`), the line is a **parameter line**. Apply the parameter rule: append a trailing warning comment and do not comment out the line.
- If the `(` is part of a **function call** or the line is a regular statement in a function body, the line is a **code line** and may be commented out.

**Rule 2 -- Comment out single-line statements.**

If the line is a code line that forms a complete C statement (ends with `;`, or is a `return` statement, or is a stand-alone expression), comment it out by wrapping the entire original line:
```c
/* [UNFAKEABLE: {symbol}] <original_line_content> */
```

**Rule 3 -- Comment out multi-line statements.**

If the unfakeable symbol appears on a line that is the start of a multi-line statement (opening expression does not end with `;` and the next line continues the expression), gather all lines belonging to that statement and replace them with a block comment:
```c
/* [UNFAKEABLE: {symbol}] begin
   <original_line_1>
   <original_line_2>
   ...
   [UNFAKEABLE: {symbol}] end */
```

**Rule 4 -- Cascade suppression for dangling references.**

If a variable is assigned only in a statement that was suppressed by Rule 2 or Rule 3, and the same variable is subsequently used on another line in the same scope, that subsequent line must also be commented out (with the annotation `/* [UNFAKEABLE: cascaded from {symbol}] ... */`). Apply this rule recursively until no active code line references a variable that has only ever been assigned in suppressed statements.

**Rule 5 -- Preprocessor blocks.**

If the unfakeable symbol appears inside a `#if`/`#ifdef`/`#elif` block (e.g., `#if R_VERSION < R_Version(4, 5, 0)`), evaluate whether the block as a whole should be suppressed. If the block defines a helper function or macro that itself uses only unfakeable items, comment out the entire block from `#if` to the matching `#endif`, replacing it with:
```c
/* [UNFAKEABLE: {symbol} -- entire preprocessor block suppressed]
   <original_block_content>
*/
```
If the block contains a mix of fakeable and unfakeable items, suppress only the specific lines that reference unfakeable symbols within the block, following Rules 1-4.

**Rule 6 -- Static file-scope variable declarations.**

A line of the form `static T var;` where `T` is an unfakeable type is a variable declaration at file scope -- not a function parameter. It may be commented out. If doing so creates dangling references within function bodies, apply Rule 4.

### Step 5: Write the Modified File

Overwrite `c_file` in-place with the modified line buffer. The file's line count must be **identical** to the original: no lines are inserted without offsetting, and no lines are deleted -- only replaced or commented out. (The single `#include "fake_R.h"` line inserted in Step 3 is the only net addition; it is injected by replacing one blank line or by shifting subsequent lines down by exactly one position.)

> Implementation note: the simplest approach is to build the modified file as a list of strings, where each original line is either kept verbatim, replaced by a comment variant, or in the case of the insertion point, preceded by the new include line. The resulting file will have at most one more line than the original (the inserted `#include "fake_R.h"`).

### Step 6: Report Changes

After writing, print a structured summary to the console:

```
FILE: <c_file>
  R headers replaced    : <count>
    - <original_include_1>
    - <original_include_2>
    ...
  fake_R.h inserted at  : line <N> (after <last_replaced_header>)
  Unfakeable symbols    : <count>
    - <symbol>: <file>:<line_numbers> [commented out | parameter -- warned]
  Lines commented out   : <count>
  Status                : OK | WARNINGS (see above)
```

If the file required no changes (no R includes and no unfakeable symbols), print:

```
FILE: <c_file> -- no changes required
```