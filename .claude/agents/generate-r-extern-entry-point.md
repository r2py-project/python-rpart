---
name: generate-r-extern-entry-point
description: Writes a pure C entry-point wrapper for a single R-callable C function, replacing its SEXP-based parameters and return value with plain int/double array arguments so the function can be called directly from Python without libR.so.
---

# Generate a Pure C Entry-Point Wrapper for an R-Callable C Function

## Description

When provided with an `r_base_folder`, a `c_base_folder`, a `fake_headers_folder` containing pre-generated fake R C API headers, an `output_folder`, and a CSV text snippet listing every R call site that invokes a specific C function, your task is to produce a single C source file — `{c_function}_c.c` — that wraps the original SEXP-based function in a new `{c_function}_c` entry point that Python can call directly via `ctypes` or `cffi` using only plain `int`, `double`, and `char` pointer arguments.

The input CSV will strictly adhere to the following schema:
```csv
c_function,call_type,r_file,r_line,r_call_expression
pred_rpart,Call,predict.rpart.R,89,".Call(C_pred_rpart, dimx, nnode, nsplit, dimc, nnum, nodes2, vnum, split2, csplit2, usesur, xdata2, xmiss2)"
pred_rpart,Call,predict.rpart.R,201,".Call(C_pred_rpart, dimx2, nnode, nsplit, dimc, nnum, nodes2, vnum, split2, csplit2, usesur, xdata2, xmiss2)"
```

The generated file must:
1. Implement a `{c_function}_c` function whose signature uses only plain C types — `int *`, `double *`, `int` (for scalar dimensions), and `char *` (for error output) — with no SEXP anywhere in the signature.
2. Internally construct fake SEXP objects from the plain input arrays, call the original `{c_function}` using the fake R API from `fake_headers_folder`, unpack the returned SEXP into the caller-provided output arrays, and propagate any `RError` exception as a null-terminated string via an `error_out` parameter.
3. Compile without `libR.so` by relying exclusively on the fake headers in `fake_headers_folder`.

## Execution Steps

### Step 1: Ingest Inputs and Gather Deterministic Context

- **R Call Site Inspection:** For every row in the CSV, construct the absolute R file path from `r_base_folder` and the `r_file` column. Navigate to the `r_line` and read at least 20 lines above and below. From this window, extract:
  - The declared R type of each argument passed to `.Call`/`.External` (`https://search.r-project.org/R/refmans/base/html/CallExternal.html`) (look for preceding `as.integer`, `as.double`, matrix constructions, `dim()` calls, etc.).
  - Whether each argument is a scalar, a 1-D vector, or a 2-D matrix (established by how R prepares the argument before passing it to `.Call`).
  - The names the R code uses for output components after the `.Call` returns (e.g., `out$which`, `out$cptable`), to understand the return structure.
  - Whether `call_type` is `Call` or `External`. For `.External`, note that all arguments arrive as a single SEXP pairlist; document this difference prominently in the generated file header comment but still provide the best-effort flat-array entry point.

- **C Function Definition Lookup:** Search `c_base_folder` recursively for the file that defines `{c_function}` (the function whose first token matches `SEXP\s+{c_function}\s*\(`). Read the complete function signature and the first 60 lines of the function body to determine:
  - The exact number and SEXP parameter names.
  - Which SEXP parameters are used as integer vectors (`INTEGER()`), real vectors (`REAL()`), integer matrices (`INTEGER()` + `nrows()`/`ncols()`), real matrices, or scalar integers/reals (`asInteger()`/`asReal()`).
  - The type and structure of the return SEXP (scalar, 1-D vector of a specific type, or a named list `VECSXP`). For a list return, read far enough into the function body to identify every `SET_VECTOR_ELT` and `SET_STRING_ELT` call, recording the index, name string, and SEXP type of each component.

- **Fake Header Inspection:** Read `{fake_headers_folder}/fake_R.h` (or `fake_R.hpp`) to confirm the `SEXPREC` struct layout and the names of the fake allocation, accessor, and error functions. Read the individual header files for the specific items used by `{c_function}` (e.g., `INTSXP.h`, `REALSXP.h`, `allocVector.h`, `PROTECT.h`, `INTEGER.h`, `REAL.h`, `error.h`, `R_alloc.h`). This ensures the construction and extraction helpers in the generated file are consistent with the fake header definitions already established.

### Step 2: Derive the Plain-C Signature

Using the context gathered in Step 1, produce a complete mapping from the original SEXP parameters and return value to their plain-C equivalents. Apply the following rules in order:

**Input parameter mapping:**
- SEXP used as `asInteger(x)` (scalar int) → one `int` value parameter.
- SEXP used as `asReal(x)` (scalar double) → one `double` value parameter.
- SEXP used as `INTEGER(x)` only, with `LENGTH(x)` but no `nrows`/`ncols` → `int *{name}, int {name}_len`.
- SEXP used as `REAL(x)` only, with `LENGTH(x)` but no `nrows`/`ncols` → `double *{name}, int {name}_len`.
- SEXP used as `INTEGER(x)` with `nrows(x)`/`ncols(x)` → `int *{name}, int {name}_nrow, int {name}_ncol`.
- SEXP used as `REAL(x)` with `nrows(x)`/`ncols(x)` → `double *{name}, int {name}_nrow, int {name}_ncol`.
- SEXP that is a Category E R interpreter item (environment, expression, language object) → replace with a `void *{name}_callback` function pointer of an appropriate `typedef`-d type, with a comment explaining the Python registration requirement. See the corresponding guide in `fake_headers_folder` for the pointer type definition.

**Return value mapping:**
- SEXP that is a 1-D integer vector → one output parameter `int *{name}_out` (pre-allocated by caller) and one `int {name}_len` parameter carrying the expected length.
- SEXP that is a 1-D real vector → `double *{name}_out`, `int {name}_len`.
- SEXP that is a named list (`VECSXP`) → one pair `{type} *{component}_out` / dimension parameter(s) per list component, plus one `int *has_{optional_component}` flag parameter for any component whose presence is conditional (e.g., `csplit` in `rpart`). Derive the component types and sizes from the `SET_VECTOR_ELT` analysis in Step 1.
- In all cases, append two trailing parameters at the end of the signature: `char *error_out` (a caller-allocated buffer that receives the error message if `RError` is thrown) and `int error_out_len` (its capacity in bytes). The presence of a non-empty `error_out` after the call signals an error to the caller.

Document the complete derived signature in a structured comment block at the top of the generated file, listing each parameter, its direction (`in`, `out`, `in/out`), its plain-C type, and the original SEXP parameter or return component it corresponds to.

### Step 3: Write the `{c_function}_c.c` File

Produce the complete C source file applying the following rules without exception:

**Rule 1 — Includes.**
Begin with a file-level comment block (see Output Format Schema). Then emit:
```c
#include "fake_R.h"   /* or whichever master fake header exists in fake_headers_folder */
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
```
Do not include any original R headers. Do not include the C source file that defines `{c_function}`; instead use an `extern` declaration (Rule 2).

**Rule 2 — Extern declaration of the original function.**
Emit the exact SEXP-based function prototype from the C source file, prefixed with `extern`, so the linker can resolve it from the compiled package object:
```c
extern SEXP {c_function}(SEXP param1, SEXP param2, ...);
```

**Rule 3 — Static inline SEXP construction helpers.**
For each distinct plain-C → SEXP conversion required by the input parameters (determined in Step 2), write a `static inline` helper function that allocates a `SEXPREC` on the heap, sets its `type`, `length`, `nrow`, `ncol`, and `data` fields using the fake header definitions, and returns the `SEXP`. The helper must **not** copy the data — it must point `data` directly at the caller-supplied array, since the original C function only reads from these inputs. Name helpers descriptively: `make_int_vec`, `make_real_vec`, `make_int_mat`, `make_real_mat`, `make_int_scalar`, `make_real_scalar`. Each helper must be guarded against a null data pointer and throw `RError` (from the fake error header) if `malloc` fails.

**Rule 4 — Static inline SEXP extraction helpers.**
For each distinct SEXP → plain-C conversion required by the return value (determined in Step 2), write a `static inline` helper that reads from a `SEXP` using the accessor functions from the fake headers and copies into a caller-supplied output array. Name helpers descriptively: `extract_int_vec`, `extract_real_vec`, `extract_int_mat`, `extract_real_mat`. For list components, write one helper per component type, taking the list SEXP, the component index, and the output pointer. Each extraction helper must validate the SEXP type tag matches what is expected and call `Rf_error` (which throws `RError`) if there is a mismatch.

**Rule 5 — The `{c_function}_c` entry-point function.**
Write the entry point with the exact plain-C signature derived in Step 2. Declare it `noexcept` — `ctypes` and `cffi` operate at the C ABI level and have no knowledge of C++ exceptions; any exception that escapes an `extern "C"` boundary produces undefined behaviour (a process crash on most platforms). `noexcept` makes this contract explicit and lets the compiler enforce it. The function body must follow this strict sequence:
  1. Immediately zero the `error_out` buffer: `if (error_out && error_out_len > 0) error_out[0] = '\0';`
  2. Declare `ArenaFrame _frame;` as the very next line, before any other local variable. This RAII guard ensures all `R_alloc` arena memory used by `{c_function}` is freed when `{c_function}_c` returns.
  3. Construct a `SEXP` local variable for each input parameter by calling the appropriate helper from Rule 3.
  4. Call the original function inside a try block that catches **all** exception types. `RError` is the expected error path; `std::bad_alloc` can be thrown by SEXP helper `malloc` calls; `std::exception` covers any other standard exception; the catch-all `(...)` ensures nothing escapes regardless. Every catch arm writes to `error_out` and returns:
     ```cpp
     SEXP _result;
     try { _result = {c_function}(sexp1, sexp2, ...); }
     catch (const RError &_e) {
         if (error_out && error_out_len > 0) {
             strncpy(error_out, _e.what(), error_out_len - 1);
             error_out[error_out_len - 1] = '\0';
         }
         /* free input SEXP wrappers */
         return;
     }
     catch (const std::bad_alloc &) {
         if (error_out && error_out_len > 0) {
             strncpy(error_out, "out of memory", error_out_len - 1);
             error_out[error_out_len - 1] = '\0';
         }
         /* free input SEXP wrappers */
         return;
     }
     catch (const std::exception &_e) {
         if (error_out && error_out_len > 0) {
             strncpy(error_out, _e.what(), error_out_len - 1);
             error_out[error_out_len - 1] = '\0';
         }
         /* free input SEXP wrappers */
         return;
     }
     catch (...) {
         if (error_out && error_out_len > 0) {
             strncpy(error_out, "unknown C++ exception", error_out_len - 1);
             error_out[error_out_len - 1] = '\0';
         }
         /* free input SEXP wrappers */
         return;
     }
     ```
  5. Unpack the returned `_result` SEXP into caller-supplied output arrays using the helpers from Rule 4. For conditional list components (e.g., `csplit`), check the list length and set the corresponding `has_*` flag.
  6. Free all heap-allocated `SEXPREC` wrapper structs created by the Rule 3 helpers (the underlying data arrays are **not** freed — the caller owns them). Free the returned `_result` SEXP and any sub-SEXPs it contains.

The Python caller checks `error_out` after every call and raises a Python exception if it is non-empty:
```python
error_buf = ctypes.create_string_buffer(1024)
lib.{c_function}_c(..., error_buf, 1024)
if error_buf.value:
    raise RuntimeError(error_buf.value.decode())
```
This is the only safe error-propagation channel across the C ABI boundary when using `ctypes`. If native Python exception propagation is required in the future, the entry-point file should be ported to `pybind11` or `Cython`, which understand C++ exceptions and can translate them automatically.

**Rule 6 — `extern "C"` linkage guard.**
Wrap the `extern` declaration, all helper functions, and the entry point in an `#ifdef __cplusplus` / `extern "C"` / `#endif` block so the file compiles correctly whether the package is built as C or C++.

**Rule 7 — No runtime R linkage.**
The generated file must introduce zero dependencies on `libR.so`. All SEXP types and API functions come exclusively from the fake headers.

## Output Format Schema

The generated `{c_function}_c.c` file must follow this exact structure, in order:

```c
/* ================================================================
 * {c_function}_c.c — Pure C entry point for {c_function}()
 *
 * Original R call form:
 *   {r_call_expression from CSV}
 *
 * Parameter map (SEXP → plain C):
 *   {param1} ({original SEXP type}) → {plain C type}  [in]
 *   {param2} ({original SEXP type}) → {plain C type}  [in]
 *   ...
 *   {return component 1} ({SEXP type}) → {plain C type}  [out]
 *   {return component 2} ({SEXP type}) → {plain C type}  [out]
 *   error_out  char *  [out]  — non-empty on any C++ exception
 *   error_out_len  int  [in]   — capacity of error_out buffer
 *
 * NOTE: ctypes/cffi have no knowledge of C++ exceptions. All exceptions
 * are caught inside this file and written to error_out. The entry point
 * is declared noexcept to enforce this at the compiler level.
 * Python callers must check error_out after every call.
 *
 * Fake headers required: fake_R.h (and transitive includes)
 * Original C source:     {relative path to C file in c_base_folder}
 * R call sites:          {r_file}:{r_line} [, ...]
 * ================================================================ */

#ifdef __cplusplus
extern "C" {
#endif

#include "fake_R.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* --- Original function declaration (resolved at link time) --- */
extern SEXP {c_function}(...);

/* --- Input SEXP construction helpers (static, no-copy) --- */
static inline SEXP make_int_vec(...) { ... }
static inline SEXP make_real_mat(...) { ... }
/* ... one helper per distinct input conversion pattern ... */

/* --- Output SEXP extraction helpers (static, copy-out) --- */
static inline void extract_int_vec(...) { ... }
static inline void extract_real_mat(...) { ... }
/* ... one helper per distinct output extraction pattern ... */

/* --- Entry point (noexcept: all exceptions caught internally) --- */
void {c_function}_c(
    /* inputs */
    ...,
    /* outputs */
    ...,
    /* error propagation */
    char *error_out, int error_out_len
) noexcept {
    if (error_out && error_out_len > 0) error_out[0] = '\0';
    ArenaFrame _frame;

    /* wrap inputs */
    ...

    /* call original — catch ALL exception types; nothing may escape */
    SEXP _result;
    try { _result = {c_function}(...); }
    catch (const RError &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* free input wrappers */
        return;
    }
    catch (const std::bad_alloc &) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "out of memory", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* free input wrappers */
        return;
    }
    catch (const std::exception &_e) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, _e.what(), error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* free input wrappers */
        return;
    }
    catch (...) {
        if (error_out && error_out_len > 0) {
            strncpy(error_out, "unknown C++ exception", error_out_len - 1);
            error_out[error_out_len - 1] = '\0';
        }
        /* free input wrappers */
        return;
    }

    /* extract outputs */
    ...

    /* free wrappers */
    ...
}

/* Python caller pattern:
 *   error_buf = ctypes.create_string_buffer(1024)
 *   lib.{c_function}_c(..., error_buf, 1024)
 *   if error_buf.value:
 *       raise RuntimeError(error_buf.value.decode())
 */

#ifdef __cplusplus
} /* extern "C" */
#endif
```

## Output Saving Instructions
- **File Naming:** Save the generated source file as `{c_function}_c.c` (e.g., `rpart_c.c`, `pred_rpart_c.c`, `rpartexp2_c.c`).
- **Output Directory:** Save the file to the user-specified `output_folder`. If the user did not explicitly provide one, create and use the default directory `r2py_rpart/entry_points/`.