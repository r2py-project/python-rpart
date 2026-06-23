# Conversion Guide: `library.dynam.unload` (R to Python)

---

### 1. Overview of `library.dynam.unload` in R

`library.dynam.unload` is a base R function designed exclusively for use inside a package's `.onUnload()` hook. Its sole responsibility is to unload a native shared library (DLL on Windows, `.so` on Linux/macOS) that was previously loaded via `library.dynam`, and to remove the library's entry from R's internal registry of loaded DLLs (`.dynLibs()`).

**Function signature:**

```r
library.dynam.unload(chname, libpath,
                     verbose = getOption("verbose"),
                     file.ext = .Platform$dynlib.ext)
```

**Parameters:**

| Parameter  | Type              | Description                                                                 |
|------------|-------------------|-----------------------------------------------------------------------------|
| `chname`   | character string  | The bare name of the DLL/shared library (e.g., `"rpart"`, without extension). |
| `libpath`  | character string  | The file-system path to the installed package directory.                    |
| `verbose`  | logical           | Whether to print a message on unload. Defaults to `getOption("verbose")`.  |
| `file.ext` | character string  | Platform-appropriate shared library extension. Defaults to `.Platform$dynlib.ext`. |

**Return value:** Invisibly returns a `"DLLInfo"` object identifying the unloaded library.

The function is the authoritative counterpart to `library.dynam`. R's documentation explicitly warns against using the lower-level `dyn.unload` on a library loaded with `library.dynam`, because doing so would leave the `.dynLibs()` registry out of sync and prevent correct subsequent reloads.

---

### 2. Contextual Usage Analysis

There is exactly one call site in the rpart package:

| File     | Function    | Line | Call body                                        |
|----------|-------------|------|--------------------------------------------------|
| `zzz.R`  | `.onUnload` | 1    | `library.dynam.unload("rpart", libpath)`         |

The entire `.onUnload` function is a single-line lambda:

```r
.onUnload <- function(libpath) library.dynam.unload("rpart", libpath)
```

R invokes `.onUnload(libpath)` automatically when the package namespace is unloaded (e.g., via `unloadNamespace("rpart")` or when the R session ends). The `libpath` argument is the path to the package's installed directory, supplied automatically by R's namespace machinery.

The call passes only the two required arguments (`chname = "rpart"` and `libpath`), relying on the defaults for `verbose` and `file.ext`. Its sole effect is to unload the compiled C shared library that implements rpart's tree-building and prediction routines, and to deregister it from R's DLL table.

**Key observations:**

- Both arguments are plain character scalars; no vectors or complex types are involved.
- The function has a side effect only (unloading the library); its return value is never used.
- This is pure lifecycle/housekeeping code with no numerical or data-processing logic.

---

### 3. Python Conversion Strategy

In Python, the direct equivalent mechanism is `ctypes.CDLL` / `ctypes.cdll` for loading shared libraries, and the OS-level `dlclose` (accessed through `ctypes`) for unloading them. However, the idiomatic Python approach — and the one used by most Python extension packages — is to rely on the **`ctypes`** standard library together with Python's own import/extension module system.

Because rpart's compiled C code is exposed to Python as a CPython extension module (a `.so` file built with the Python C API or via `cffi`/`ctypes`), the correct Python translation of `.onUnload` is an **`atexit`** cleanup function (or a module-level finalizer) that:

1. Unloads the shared library handle using `ctypes` (if the library was loaded manually via `ctypes.CDLL`).
2. Or simply does nothing, because CPython extension modules loaded via `import` are unloaded automatically when the interpreter shuts down.

**Why not `numpy` or `scipy`?** This dependency has no numerical computation and no vectorization concern. It is purely a shared-library lifecycle hook. The appropriate Python tool is the standard library's `ctypes` and/or `atexit` modules.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 The `.onUnload` / `library.dynam.unload` Pattern

**Locations:** `rpart/R/zzz.R`, function `.onUnload`

**Original R Context:**

- `libpath` — character scalar; the file-system path to the installed package root, provided automatically by R.
- `"rpart"` — character scalar; the bare library name, without a platform extension.
- Return value — a `DLLInfo` object, used only for its side effect; the value is discarded.

Generalized R pattern:

```r
# Called automatically by R when the package namespace is unloaded.
.onUnload <- function(libpath) {
    library.dynam.unload("rpart", libpath)
}
```

**Python Equivalent (ctypes manual-load pattern):**

If the shared library is loaded manually via `ctypes`, the Python equivalent is:

```python
import ctypes
import atexit
import os

# Module-level: load the shared library once at import time,
# mirroring what library.dynam does on the R side.
_lib_path = os.path.join(os.path.dirname(__file__), "rpart.so")
_rpart_lib = ctypes.CDLL(_lib_path)

def _on_unload() -> None:
    """
    Unload the rpart shared library.
    Mirrors R's .onUnload -> library.dynam.unload("rpart", libpath).
    """
    if _rpart_lib is not None:
        # ctypes does not expose dlclose directly; use the private handle.
        ctypes.cdll.LoadLibrary("")  # no-op placeholder
        del _rpart_lib  # releases the reference; OS may unload when refcount hits 0

atexit.register(_on_unload)
```

**Python Equivalent (CPython extension module pattern):**

If the rpart C code is compiled as a CPython extension module (the standard approach for production Python packages), no explicit unload hook is needed. CPython manages extension module lifetimes automatically. The `PyInit_rpart` entry point and module deallocation handle cleanup:

```python
# In rpart/__init__.py — no explicit unload hook required.
# CPython unloads extension modules (.so / .pyd) automatically
# when the interpreter finalizes or the module reference count drops to zero.

# If custom C-level cleanup is needed, implement it in the C extension:
#
#   static void rpart_module_free(void *m) {
#       /* C-level teardown logic here */
#   }
#
#   static struct PyModuleDef moduledef = {
#       PyModuleDef_HEAD_INIT, "rpart", NULL, sizeof(struct module_state),
#       rpart_methods, NULL, NULL, NULL, rpart_module_free
#   };
```

**Explanation of the translation:**

| R concept | Python equivalent |
|---|---|
| `.onUnload(libpath)` hook | `atexit.register(fn)` or CPython's module free function |
| `library.dynam.unload("rpart", libpath)` | `ctypes` handle deletion, or automatic CPython cleanup |
| `libpath` (package install dir) | `os.path.dirname(__file__)` or the package's `__file__` attribute |
| DLL name `"rpart"` + platform extension | `"rpart.so"` (Linux), `"rpart.pyd"` (Windows) via `ctypes.util.find_library` |
| Invisible `DLLInfo` return value | `None`; the return value is not used in either language |

**Key nuances:**

- R's `library.dynam.unload` keeps an internal registry (`.dynLibs()`) consistent. Python has no equivalent global registry for `ctypes`-loaded libraries; each module is responsible for tracking its own handles.
- `ctypes.CDLL` does not guarantee an immediate `dlclose` on deletion — the OS may keep the library mapped if other handles exist. This mirrors R's behavior on some platforms.
- In practice, for a project that translates rpart's C code into a proper CPython extension, the `.onUnload` function has **no Python translation needed**: CPython's reference-counting garbage collector and interpreter shutdown sequence handle native library unloading automatically. The `.onUnload` / `library.dynam.unload` pattern simply does not exist as a user-space concern in Python extension packages.
