---
name: add-r-interpreter-items
description: Writes C helper entry points for Category E R interpreter items, rebuilds the shared library, patches __init__.py with cffi callbacks, rewrites rpartcallback.py to use cffi exclusively, and resolves all remaining NotImplementedError stubs to make the Python package functionally equivalent to the R package.
---

# Add R Interpreter Items

## Description

After `/combine-python-functions-into-folder`, two layers required for full functional equivalence are missing:

1. **C side** — `make_real_sexp`, `make_int_sexp`, `make_env_sexp`, and `call_install` are referenced in `init_rpcallback_c.c`'s caller comment but not yet exported from `_rpart_core.so`.
2. **Python side** — The converted `rpartcallback.py` mixes `ctypes` (for callbacks) with `cffi` (for C calls), which is incompatible. All callbacks must be rewritten using `ffi.callback` to match the rest of the package.

This command writes the missing C file, rebuilds the library, patches `__init__.py`, rewrites `rpartcallback.py`, and resolves all `NotImplementedError` stubs so that no stub is silently reachable at runtime.

## Parameters

| Parameter | Required | Description |
|---|---|---|
| `fake_guides_folder` | Yes | Path to the fake header guides (e.g., `r_extern_analysis/fake_guides/`). Provides Python Interop Notes for each Category E item. |
| `c_entry_points_folder` | Yes | Folder containing existing C entry point files (e.g., `r2py_rpart/c_entry_points/`). The new helper file is written here. |
| `python_package_folder` | Yes | Python package folder containing `__init__.py` and the converted `.py` modules (e.g., `r2py_rpart/r2py_rpart/`). |
| `r2py_rpart_root` | Yes | Root of the installable Python package (e.g., `r2py_rpart/`), used for building via `pip install --no-build-isolation .`. |

## Execution Steps

### Step 1: Identify Inputs

1. **Category E guides** — In `fake_guides_folder`, find guides whose **opening blockquote (line 3)** begins with `**R Interpreter Item.`** (strict prefix match). Exclude any guide whose opening blockquote contains `best-effort fakeable without a Python function pointer`. For rpart this yields `eval.md`, `findVar.md`, `findVarInFrame.md`. (`install.md` is excluded — its built-in C++ hash-map requires no Python bridge in normal use.)

2. **Existing entry points** — Collect the full text of `init_rpcallback_c.c` from `c_entry_points_folder` (contains the caller-comment protocol for `make_real_sexp` etc.) and one representative existing entry point (e.g., `rpart_c.c`) for style reference.

3. **Existing package files** — Collect the full text of `__init__.py` and `rpartcallback.py` from `python_package_folder`. Also grep every `.py` file in `python_package_folder` for `NotImplementedError` and `ctypes` to identify all stubs and FFI mismatches.

Log a discovery summary:
```
Category E guides found : eval.md, findVar.md, findVarInFrame.md
Files to patch          : __init__.py, rpartcallback.py
NotImplementedError hits: <N> across <files>
ctypes usage hits       : <N> across <files>
```

### Step 2: Invoke the Agent

Invoke `@add-r-interpreter-items` exactly once, providing all of the following as context:

- The three Category E guide texts (full content of `eval.md`, `findVar.md`, `findVarInFrame.md`)
- The full text of `init_rpcallback_c.c`
- The full text of one existing entry point file (style reference)
- The full text of `fake_R.h` (located in `r2py_rpart/r_fake_headers/` or adjacent)
- The full text of `__init__.py`
- The full text of `rpartcallback.py` (converted module in `python_package_folder`)
- The grep results for `NotImplementedError` and `ctypes` across all `.py` files
- The paths: `c_entry_points_folder`, `python_package_folder`, `r2py_rpart_root`

The agent handles all file writes, the build step, and all verification. Do not proceed past the agent invocation until it returns.

### Step 3: Report Summary

Print the agent's reported results in the following format:

```
========================================
 Add R Interpreter Items — Summary
========================================
 C file written          : c_entry_points/interpreter_helpers_c.c
 meson.build updated     : YES / NO
 Build                   : PASSED / FAILED
 New symbols verified    : make_real_sexp, make_int_sexp,
                           make_env_sexp, call_install
 __init__.py patched     : YES / NO  (<N> additions)
 rpartcallback.py fixed  : YES / NO  (ctypes → cffi)
 NotImplementedError stubs resolved : <N>
 NotImplementedError stubs remaining (intentional) : <N>
 Import check            : PASSED / FAILED
========================================
```

If the build or import check failed, print the full error output and do not mark the step as succeeded. If any `NotImplementedError` stubs remain, each must be listed with its file, function, and a one-line explanation of why it is intentional (e.g., interactive terminal function with no Python equivalent).