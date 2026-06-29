# Phase 9.3 Research Report: R Interpreter Item Bridge, cffi Migration, and Build Verification — `r2py_rpart`

**Date:** 2026-06-29
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session implemented the missing Category E R interpreter item bridge for the `r2py_rpart` package, enabling the `method=4` (user-defined splits) code path of the rpart C library to be driven entirely from Python without a running R interpreter. A new C helper file was written and compiled into `_rpart_core.so`, and `rpartcallback.py` was fully rewritten to replace an incompatible mixed `ctypes`/`cffi` implementation with a pure cffi implementation. All 11 existing tests continue to pass after these changes.

---

### 2. Methodology & Actions Taken

#### 2.1 Skill Invocation: `/add-r-interpreter-items`

The skill was invoked with:

| Parameter | Value |
|---|---|
| `fake_guides_folder` | `r_extern_analysis/fake_guides/` |
| `c_entry_points_folder` | `r2py_rpart/c_entry_points/` |
| `python_package_folder` | `r2py_rpart/r2py_rpart/` |
| `r2py_rpart_root` | `r2py_rpart/` |

**Step 1 — Discovery:** Three Category E guides were identified by inspecting line 3 (the opening blockquote) of each guide in `r_extern_analysis/fake_guides/`:

| Guide | Status |
|---|---|
| `eval.md` | Included — opens with `**R Interpreter Item.**` |
| `findVar.md` | Included — opens with `**R Interpreter Item.**` |
| `findVarInFrame.md` | Included — opens with `**R Interpreter Item.**` |
| `install.md` | Excluded — opens with `**R Interpreter Item (best-effort fakeable).** ... no Python function pointer is required` |

Discovery grep results:
- `NotImplementedError` hits: 4 across `rpart.py` (lines 37, 258) and `xpred_rpart.py` (lines 39, 185)
- `ctypes` usage hits: ~30 in `rpartcallback.py` (all ctypes FFI calls, incompatible with cffi `_lib`), plus 3 in `__init__.py` (numpy `.ctypes.data` attribute — legitimate, retained)

**Step 2 — Agent Invocation:** The `@add-r-interpreter-items` agent was invoked once with:
- Full content of `eval.md`, `findVar.md`, `findVarInFrame.md`
- Full content of `init_rpcallback_c.c` (authoritative Python usage protocol in caller-comment section)
- Full content of `rpart_c.c` (style reference)
- Full content of `fake_R.h` (master fake header confirming SEXPREC layout and SEXPTYPE constants)
- Full content of `__init__.py` and `rpartcallback.py`
- Grep results for `NotImplementedError` and `ctypes`
- Paths and `meson.build` content

#### 2.2 C Helper File: `interpreter_helpers_c.c`

File written to `r2py_rpart/c_entry_points/interpreter_helpers_c.c`. It exports five C-linkage `noexcept` functions:

| Function | Signature | Purpose |
|---|---|---|
| `make_real_sexp` | `void *(void *data, int length)` | Heap-allocate SEXPREC of type REALSXP; data NOT copied |
| `make_int_sexp` | `void *(void *data, int length)` | Heap-allocate SEXPREC of type INTSXP; data NOT copied |
| `make_env_sexp` | `void *(void)` | Heap-allocate minimal ENVSXP identity shell |
| `free_sexp_helper` | `void(void *sexp)` | Free SEXPREC node only (not the data buffer) |
| `get_make_sexp_error` | `const char *(void)` | Return thread-local error string from allocation failures |

`call_install` was **not** added: `install.h` already defines it as `extern "C" inline` and exports it as a weak symbol (`W`) from the `.so`; redefining it would cause a linker conflict.

SEXPREC layout (from `r2py_rpart/r_fake_headers/INTSXP.h`):
```c
struct SEXPREC { int type; int length; int nrow; int ncol; void *data; };
typedef SEXPREC *SEXP;
```
Constants used: `REALSXP=14`, `INTSXP=13`, `ENVSXP=4`.

#### 2.3 Build System Update

`r2py_rpart/meson.build`: added `'c_entry_points/interpreter_helpers_c.c'` to the `rpart_src = files(...)` block after `init_rpcallback_c.c`.

Rebuild executed from `r2py_rpart/`:
```bash
pip install --no-build-isolation .
```

#### 2.4 cffi Declaration Update: `__init__.py`

Six declarations added to the `ffi.cdef("""...""")` block in `r2py_rpart/r2py_rpart/__init__.py`:

```c
void *make_real_sexp(void *data, int length);
void *make_int_sexp(void *data, int length);
void *make_env_sexp(void);
void  free_sexp_helper(void *sexp);
void *call_install(const char *name);
const char *get_make_sexp_error(void);
```

#### 2.5 `rpartcallback.py` Rewrite: ctypes → cffi

The pre-existing `rpartcallback.py` had two fundamental defects:
1. It used `ctypes.CFUNCTYPE(...)` for callback registration and `ctypes.Structure` for SEXP construction, which are incompatible with the cffi `_lib` object (cffi library objects do not accept `.restype`/`.argtypes` assignments).
2. It referenced `_lib` (the cffi dlopen object) without importing it from the package.

The file was rewritten in full. Key substitutions:

| Old (ctypes) | New (cffi) |
|---|---|
| `ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)` | `ffi.callback("void *(char *)", fn)` |
| `ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)` | `ffi.callback("void *(void *, void *)", fn)` |
| `class _SEXPREC(ctypes.Structure): ...` | `_lib.make_real_sexp(buf, size)` / `_lib.make_int_sexp(buf, size)` |
| `(ctypes.c_char * 1)()` for opaque handles | `ffi.new("char[1]")` |
| `ctypes.cast(node, ctypes.c_void_p).value` | `int(ffi.cast("uintptr_t", node))` |
| `ctypes.cast(ctypes.byref(sexp), ctypes.c_void_p).value` | direct cffi void* from `_lib.make_real_sexp` |
| `arr.ctypes.data_as(ctypes.c_void_p)` | `ffi.from_buffer(arr)` |
| `_lib.register_*_fn.restype = None; ...argtypes = [...]` | `_lib.register_*_fn(ffi.cast("void *", cb))` |
| `rho["_ctypes_keep_alive"]` | `rho["_cffi_keep_alive"]` |

Imports added at top of `rpartcallback.py`:
```python
from . import ffi, _lib, _check_error, _cptr, _ERR_BUF_SIZE
```
`import ctypes` removed entirely.

#### 2.6 NotImplementedError Stub Analysis

All four stubs were found to be intentional; none were modified:

| Location | Type | Reason retained |
|---|---|---|
| `rpart.py:37` | formula/model.frame path | patsy/formula integration not yet implemented (Class D gap) |
| `rpart.py:258` | C extension ImportError guard | Guard is unreachable now that `_rpart_core.so` loads cleanly |
| `xpred_rpart.py:39` | formula/model.frame path | Same as rpart.py:37 |
| `xpred_rpart.py:185` | C extension ImportError guard | Same as rpart.py:258 |

#### 2.7 Test Execution

```bash
cd r2py_rpart && python -m pytest tests/ -v
```
Result: **11 passed in 2.61 s** (no changes to test file required).

---

### 3. Key Findings & Results

#### 3.1 Build Metrics

| Metric | Value |
|---|---|
| Category E guides processed | 3 (eval, findVar, findVarInFrame) |
| C functions exported (new) | 5 (strong T symbols) |
| Pre-existing weak symbol reused | 1 (`call_install`, W from `install.h`) |
| `ffi.cdef` declarations added | 6 |
| Build result | PASSED |
| `rpartcallback.py` lines touching ctypes (before) | ~30 |
| `rpartcallback.py` ctypes lines remaining (after) | 0 |
| Tests passing (before → after) | 11 → 11 |

#### 3.2 Symbol Verification

Post-build symbol table (via `nm -D _rpart_core.so`):

| Symbol | Type | Source |
|---|---|---|
| `make_real_sexp` | T (strong) | `interpreter_helpers_c.c` |
| `make_int_sexp` | T (strong) | `interpreter_helpers_c.c` |
| `make_env_sexp` | T (strong) | `interpreter_helpers_c.c` |
| `free_sexp_helper` | T (strong) | `interpreter_helpers_c.c` |
| `call_install` | W (weak) | `install.h` inline |
| `register_eval_fn` | T | `eval.h` |
| `register_install_fn` | T | `R_getVar.h` |
| `register_findVar_fn` | T | `R_getVar.h` |
| `register_findVarInFrame_fn` | T | `R_getVar.h` |
| `get_R_UnboundValue` | T | `R_UnboundValue.h` |

#### 3.3 Technical Insights

- **`call_install` linker conflict:** `install.h` already emits `call_install` as a weak `extern "C" inline` symbol via `-fkeep-inline-functions`. Defining it again in a `.c` entry-point file would cause a duplicate-symbol linker error. The correct approach is to reuse the existing weak symbol by declaring it in `ffi.cdef` only.

- **cffi callbacks and void* registration:** The registration functions in `fake_R.h` (`register_eval_fn`, etc.) all take `void *fn`. To pass a cffi callback object, it must be cast: `_lib.register_eval_fn(ffi.cast("void *", cb))`. Passing the cffi callback cdata object directly without a cast would cause a type error in cffi's argument marshalling.

- **SEXP lifetime for `findVarInFrame` SEXPs:** The SEXPREC nodes created by `_lib.make_real_sexp` for `yback`/`wback`/`xback`/`nback` only need to survive for the duration of the `init_rpcallback_c` call. After return, the C static globals `ydata`, `wdata`, `xdata`, `ndata` point directly into the numpy buffers (extracted via `REAL(stemp)` / `INTEGER(stemp)` inside `init_rpcallback`), not into the SEXP nodes themselves. Keeping the SEXP node pointers in `rho["_cffi_keep_alive"]` is therefore conservative but not strictly required beyond the call.

- **`ffi.from_buffer` lifetime:** cffi's `ffi.from_buffer(arr)` returns a cdata object that pins the numpy buffer but does not extend its refcount independently. The buffer object (`arr`) and the `from_buffer` result (`buf`) must both be kept in the `_cffi_keep_alive` list to prevent premature GC during the C call.

- **numpy `.ctypes.data` is not Python's ctypes module:** The three helper functions `_iptr`, `_dptr`, `_cptr` in `__init__.py` call `arr.ctypes.data` (numpy's ctypes interface, returning an integer address) and pass the result to `ffi.cast(...)`. This is valid cffi usage and was correctly retained without modification.

---

### 4. Conclusion & Next Steps

The `r2py_rpart` package now has a complete, cffi-only FFI layer. `rpartcallback.py` is fully rewritten to use `ffi.callback`, `ffi.from_buffer`, `ffi.new`, and `ffi.cast`, with no remaining `ctypes` FFI dependencies. Five new C-ABI helper functions (`make_real_sexp`, `make_int_sexp`, `make_env_sexp`, `free_sexp_helper`, `get_make_sexp_error`) are compiled into `_rpart_core.so` and declared in `ffi.cdef`. All 11 regression tests pass. The `method=4` user-defined splits code path is architecturally complete at the FFI layer; its correctness under actual user-defined split functions has not yet been tested end-to-end.

Suggested next steps:

1. **End-to-end `method=4` test:** Write a test that defines a minimal user split method (`init`, `split`, `eval` functions) and calls `rpart(method=mlist, ...)`. This would exercise `rpartcallback()`, `init_rpcallback_c`, `register_eval_fn`, `register_findVarInFrame_fn`, and the `eval` callback path in `rpart_callback.c`.
2. **`make_real_sexp` memory management audit:** Confirm that SEXP nodes allocated by `make_real_sexp` for `eval` callback results (inside `_py_eval`) are not accumulating across tree-fitting iterations. The `_eval_result_keeper` list grows monotonically; consider bounding its size or clearing it between `rpart_c` calls.
3. **Extended test coverage:** Run `/generate-python-file-tests` against `predict_rpart.py`, `xpred_rpart.py`, `prune_rpart.py`, and `labels_rpart.py`.
4. **`model.frame` / patsy integration:** Implement the formula-based input path in `rpart.py:37` and `xpred_rpart.py:39` (currently `NotImplementedError`) to support `rpart(formula, data=df)` without requiring a pre-built model frame.
