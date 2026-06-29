---
name: add-r-interpreter-items
description: Writes the C interpreter-item helper entry point file, updates meson.build, rebuilds _rpart_core.so, patches __init__.py with cffi-based callbacks and ffi.cdef declarations, rewrites rpartcallback.py to use cffi exclusively, and resolves all NotImplementedError stubs to make the Python package functionally equivalent to the R package.
---

# Add R Interpreter Items

## Description

You receive:
- Full text of `eval.md`, `findVar.md`, `findVarInFrame.md` (Category E fake guides, especially their Section 4 Python Interop Notes)
- Full text of `init_rpcallback_c.c` (contains the caller-comment protocol for C helpers)
- Full text of one existing entry point file (style reference)
- Full text of `fake_R.h` (defines SEXPREC struct layout and SEXPTYPE constants)
- Full text of `__init__.py` (cffi setup, existing `ffi.cdef`, existing helpers)
- Full text of `rpartcallback.py` (currently broken: mixes ctypes callbacks with cffi C calls)
- Grep results for `NotImplementedError` and `ctypes` across all `.py` files
- Paths: `c_entry_points_folder`, `python_package_folder`, `r2py_rpart_root`

Your task is to close both the C and Python gaps so the package is fully functional.

## Execution Steps

### Step 1: Write `interpreter_helpers_c.c`

Read `fake_R.h` to confirm the exact `SEXPREC` field order (`type`, `length`, `nrow`, `ncol`, `data`). Read one existing entry point file to match the include order, extern-C bracketing, and noexcept style.

Write `{c_entry_points_folder}/interpreter_helpers_c.c` exporting four functions. The file must follow the exact same structure as the other entry points: include `fake_R.h` before the `extern "C"` block, wrap all exported functions in `extern "C" { ... }`.

**`void *make_real_sexp(void *data, int n)`**
Heap-allocates a `SEXPREC` (via `malloc`) with `type=REALSXP`, `length=n`, `nrow=n`, `ncol=1`, `data=data`. The data buffer is owned by the caller and is not copied. Returns the SEXPREC pointer cast to `void *`. On malloc failure, writes to a `static thread_local char[256]` error buffer and returns `nullptr`; the buffer is exposed via a companion `const char *get_make_sexp_error()` function. Does not use `RError` (this function is called from Python, not from within the C evaluation loop).

**`void *make_int_sexp(void *data, int n)`**
Identical to `make_real_sexp` but with `type=INTSXP`.

**`void *make_env_sexp(void)`**
Allocates a minimal `SEXPREC` with `type=ENVSXP`, `length=0`, `nrow=0`, `ncol=0`, `data=nullptr`. The returned pointer is a stable unique identity key for use as a `rho` handle in the frame registry. On malloc failure, writes to the same error buffer and returns `nullptr`.

**`void *call_install(const char *name)`**
Calls `Rf_install(name)` and returns the resulting SYMSXP pointer cast to `void *`. This exposes the built-in C++ symbol cache to Python so that Python can pre-populate the frame registry with the exact same pointer keys that `install()` will produce inside `init_rpcallback`. Safe to call from Python at any time after library load; does not require `ArenaFrame`.

Also add `const char *get_make_sexp_error(void)` that returns the static error buffer, so Python can check for allocation failures.

### Step 2: Update `meson.build`

Open `meson.build`. Find the `rpart_src = files(...)` list. Add the line:
```
  'c_entry_points/interpreter_helpers_c.c',
```
after the existing `c_entry_points/init_rpcallback_c.c` entry. Do not change any other part of the file.

### Step 3: Build and Verify

Run from `r2py_rpart_root`:
```bash
pip install --no-build-isolation .
```

If the build fails, read the compiler error output, fix `interpreter_helpers_c.c`, and retry. Do not proceed until the build passes.

After a successful build, verify all five new symbols are exported:
```bash
nm -D $(python -c "import r2py_rpart, os; print(os.path.dirname(r2py_rpart.__file__))")/_rpart_core.so \
  | grep -E "make_real_sexp|make_int_sexp|make_env_sexp|call_install|get_make_sexp_error"
```
All five must appear. If any are missing, add `-fkeep-inline-functions` to the compile args for those symbols or restructure the function to have external linkage.

### Step 4: Patch `__init__.py` -- `ffi.cdef` Additions

Append the following block inside the existing `ffi.cdef("""...""")` call, immediately before the closing `""")`. Do not modify any existing declaration:

```c
/* ---- Interpreter-item helpers (Category E support) ---------------------- */
void *make_real_sexp(void *data, int n);
void *make_int_sexp(void *data, int n);
void *make_env_sexp(void);
void *call_install(const char *name);
const char *get_make_sexp_error(void);
```

### Step 5: Patch `__init__.py` -- Module-Level Callback Infrastructure

Insert the following block into `__init__.py` immediately after the `_lib = ffi.dlopen(_find_lib())` line. This registers the `install`, `findVarInFrame`, and `findVar` callbacks at module load time. The `eval` callback is intentionally excluded here -- it is registered per-call inside `rpartcallback()` because it captures user-supplied split functions.

```python
# ---------------------------------------------------------------------------
# Interpreter-item callback infrastructure (Category E, method=4 support)
# ---------------------------------------------------------------------------

# Symbol intern cache: name (str) -> integer address of interned SYMSXP.
# Populated by _py_install; used to pre-populate _frame_registry.
_symbol_handles: dict[str, int] = {}
_symbol_bufs: dict[str, Any] = {}     # keeps ffi buffer objects alive

# Frame registry: rho_ptr (int) -> {sym_ptr (int) -> sexp_ptr (int)}.
# Populated by rpartcallback() before each init_rpcallback_c call.
_frame_registry: dict[int, dict[int, int]] = {}

# Persistent storage for module-level cffi callbacks (prevents GC).
_interp_callbacks: list[Any] = []

# Sentinel value returned by findVarInFrame when a variable is not found.
_R_UNBOUND: int = int(ffi.cast("uintptr_t", _lib.get_R_UnboundValue()))


@ffi.callback("void *(const char *)")
def _install_cb(name_bytes: Any) -> Any:
    name = ffi.string(name_bytes).decode()
    if name not in _symbol_handles:
        buf = ffi.new("char[1]")
        _symbol_bufs[name] = buf
        _symbol_handles[name] = int(ffi.cast("uintptr_t", buf))
    return ffi.cast("void *", _symbol_handles[name])


@ffi.callback("void *(void *, void *)")
def _findVarInFrame_cb(rho: Any, sym: Any) -> Any:
    rho_key = int(ffi.cast("uintptr_t", rho))
    sym_key = int(ffi.cast("uintptr_t", sym))
    val = _frame_registry.get(rho_key, {}).get(sym_key)
    return ffi.cast("void *", val) if val is not None else ffi.cast("void *", _R_UNBOUND)


@ffi.callback("void *(void *, void *)")
def _findVar_cb(sym: Any, rho: Any) -> Any:
    # The inherits=TRUE path through compat_getVar is dead code for all
    # standard rpart methods; this stub returns R_UnboundValue safely.
    return ffi.cast("void *", _R_UNBOUND)


_lib.register_install_fn(_install_cb)
_lib.register_findVarInFrame_fn(_findVarInFrame_cb)
_lib.register_findVar_fn(_findVar_cb)

_interp_callbacks.extend([_install_cb, _findVarInFrame_cb, _findVar_cb])
```

### Step 6: Rewrite `rpartcallback.py`

The existing converted `rpartcallback.py` is broken because it uses `ctypes.CFUNCTYPE` for callback creation while the library is loaded via `cffi`. Rewrite the entire file so it uses only `cffi`.

The rewritten function must preserve all input validation and all `eval1`/`eval2` computation logic from the existing conversion -- those are correct. Replace only the C-interface section (Steps 1-9 in the existing comments) with cffi equivalents following the rules below.

**Replace ctypes constructs with cffi equivalents:**

| Broken pattern (ctypes) | Correct pattern (cffi) |
|---|---|
| `ctypes.CFUNCTYPE(ret, *args)` | `ffi.callback("ret (args)")` |
| `ctypes.cast(x, ctypes.c_void_p).value` | `int(ffi.cast("uintptr_t", x))` |
| `_SEXPREC(ctypes.Structure)` local struct | `_lib.make_real_sexp(...)` / `_lib.make_int_sexp(...)` |
| `_lib.register_X_fn.restype = None` (ctypes API on cffi lib) | Remove -- cffi does not use `.restype` |
| `_lib.register_X_fn.argtypes = [...]` (ctypes API on cffi lib) | Remove -- cffi resolves from `ffi.cdef` |
| `_lib.register_X_fn(cb)` | `_lib.register_X_fn(cb)` (valid in cffi too, keep) |

**SEXP construction:** Use the new C helpers instead of local ctypes structs:
```python
sexp_y = _lib.make_real_sexp(ffi.cast("void *", rho["yback"].ctypes.data), rho["yback"].size)
sexp_w = _lib.make_real_sexp(ffi.cast("void *", rho["wback"].ctypes.data), rho["wback"].size)
sexp_x = _lib.make_real_sexp(ffi.cast("void *", rho["xback"].ctypes.data), rho["xback"].size)
sexp_n = _lib.make_int_sexp(ffi.cast("void *", rho["nback"].ctypes.data), rho["nback"].size)
```
After each call, check `ffi.string(_lib.get_make_sexp_error())` and raise `RuntimeError` if non-empty.

**Symbol pointers:** Use the module-level `_symbol_handles` dict (already populated by `_install_cb`) rather than a local `_py_install`:
```python
# Trigger install() for each name so _symbol_handles is populated.
for name in (b"yback", b"wback", b"xback", b"nback"):
    _lib.call_install(name)
```
Then use `_symbol_handles["yback"]` etc. as the frame registry keys.

**Rho handle:** Use `make_env_sexp()` instead of a ctypes 1-byte placeholder:
```python
_rho_sexp = _lib.make_env_sexp()
_rho_ptr  = int(ffi.cast("uintptr_t", _rho_sexp))
```

**Frame registry population:** Write directly to `_frame_registry` (module-level dict imported from `__init__.py`, or accessed as `from r2py_rpart import _frame_registry`):
```python
_frame_registry[_rho_ptr] = {
    _symbol_handles["yback"]: int(ffi.cast("uintptr_t", sexp_y)),
    _symbol_handles["wback"]: int(ffi.cast("uintptr_t", sexp_w)),
    _symbol_handles["xback"]: int(ffi.cast("uintptr_t", sexp_x)),
    _symbol_handles["nback"]: int(ffi.cast("uintptr_t", sexp_n)),
}
```

**Expr handles:** Use `ffi.new("char[1]")` instead of ctypes 1-byte buffers:
```python
_expr1_buf = ffi.new("char[1]")
_expr2_buf = ffi.new("char[1]")
_expr1_ptr = int(ffi.cast("uintptr_t", _expr1_buf))
_expr2_ptr = int(ffi.cast("uintptr_t", _expr2_buf))
```

**Eval callback:** Define using `ffi.callback`. The callback must catch all Python exceptions and return `ffi.NULL` on failure (cffi will not propagate Python exceptions across the C boundary; returning NULL causes the C-side `isReal(NULL)` check to fail with a readable `RError`):
```python
_eval_result_keeper: list[Any] = []

@ffi.callback("void *(void *, void *)")
def _eval_cb(expr: Any, rho: Any) -> Any:
    try:
        expr_p = int(ffi.cast("uintptr_t", expr))
        if expr_p == _expr2_ptr:
            result = eval2()
        else:
            result = eval1()
        result = np.ascontiguousarray(result, dtype=np.float64)
        sexp = _lib.make_real_sexp(ffi.cast("void *", result.ctypes.data), result.size)
        _eval_result_keeper.append(result)   # keep numpy array alive
        return sexp
    except Exception:
        return ffi.NULL

_lib.register_eval_fn(_eval_cb)
```

**Keep-alive:** Store all cffi objects that must outlive the function call in `rho["_cffi_keep_alive"]`:
```python
rho["_cffi_keep_alive"] = [
    _eval_cb, _expr1_buf, _expr2_buf,
    _rho_sexp, sexp_y, sexp_w, sexp_x, sexp_n,
    _eval_result_keeper,
]
```
This replaces the `_ctypes_keep_alive` list in the existing conversion.

**Return value:** Keep the same return structure as the existing conversion:
```python
return {"eval1": eval1, "eval2": eval2, "rho": rho}
```

### Step 7: Resolve All Remaining `NotImplementedError` Stubs

Scan every `.py` file in `python_package_folder` for `NotImplementedError`. For each occurrence, classify it and act:

**Class A -- Stubs caused by missing interpreter-item wiring (must be fixed):**
Any stub that says something like "C_init_rpcallback not available", "callbacks not registered", or similar. These should not exist after Step 6, but verify and fix any that remain.

**Class B -- `UseMethod` dispatch stubs (must be fixed):**
Stubs in `post.py`, `prune.py`, and `meanvar.py` (or wherever `UseMethod` was converted to `NotImplementedError`). Replace each with a direct dispatch based on `tree.get("_rpart_class")`:
```python
def post(tree: dict, *args, **kwargs):
    if tree.get("_rpart_class") == "rpart":
        return post_rpart(tree, *args, **kwargs)
    raise TypeError(f"no applicable method for 'post' on object of class "
                    f"'{tree.get(\"_rpart_class\", type(tree).__name__)}'")
```
Apply the same pattern to `prune` and `meanvar`.

**Class C -- Interactive or environment-specific stubs (annotate, do not silence):**
Stubs in `snip_rpart_mouse.py` (uses R's `identify()` for interactive terminal tree pruning -- no Python equivalent). Keep `NotImplementedError` but ensure the message is specific:
```python
raise NotImplementedError(
    "snip.rpart.mouse requires interactive terminal graphics (R's identify()); "
    "use snip.rpart() with explicit node indices instead."
)
```

**Class D -- Formula/model.frame stubs (annotate precisely):**
Stubs where `eval.parent(model.frame(...))` was replaced with `NotImplementedError`. Keep the stub but ensure the message names the specific R function and suggests the Python alternative:
```python
raise NotImplementedError(
    "model.frame.rpart requires a formula parser (R's model.frame/eval.parent); "
    "pass a pre-built numpy matrix as 'data' to rpart() instead of a formula string."
)
```

After processing all stubs, verify: every remaining `NotImplementedError` has a non-empty, specific string message. A bare `raise NotImplementedError` with no message is not acceptable.

### Step 8: Verify

1. **Import check:**
   ```bash
   python -c "import r2py_rpart; print('OK')"
   ```
   Must print `OK` with no exception.

2. **Callback registration check:**
   ```bash
   python -c "import r2py_rpart; assert len(r2py_rpart._interp_callbacks) == 3, r2py_rpart._interp_callbacks"
   ```
   Must pass (three module-level callbacks registered: install, findVarInFrame, findVar).

3. **No silent stubs:**
   ```bash
   grep -rn "raise NotImplementedError()" {python_package_folder}
   ```
   Must return no output. Every `NotImplementedError` must have a message.

4. **No ctypes usage:**
   ```bash
   grep -rn "import ctypes\|ctypes\." {python_package_folder}
   ```
   Must return no output. All FFI must go through cffi.

Report pass/fail for each check. If any check fails, diagnose and fix before reporting completion.