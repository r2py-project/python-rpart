# Phase 8 Research Report: Python Build Infrastructure — Bug Fixes, CI/CD Pipeline

**Date:** 2026-06-19
**Working Directory:** `/groups/jli9/Yufei/python-rpart/r2py_rpart`

---

### 1. Abstract

This session completed the Python build infrastructure for the `r2py_rpart` package. Starting from a partially broken state inherited from Phase 6 (the build failed with C++17-specific undefined references and the test suite could not import the installed library), five distinct bugs were diagnosed and fixed across `meson.build`, `r2py_rpart/__init__.py`, and supporting build files. After establishing a clean, passing test baseline, a full CI/CD publication pipeline was designed and implemented, mirroring the structure of the reference project `/users/ycai9/Yufei/python-KernSmooth/r2py_kernsmooth/`. The session ended with all local tests passing and a three-file CI/CD artifact (`python-publish.yml`, updated `pyproject.toml`, updated `meson.build`) ready for deployment when the package is published as an independent GitHub repository via `git subtree`.

---

### 2. Methodology & Actions Taken

#### 2.1 Bug 1: C++17 Math Built-in Undefined References

**Root cause.** `meson.build` compiled all `.c` sources with `-std=c++17`. On the project's GCC 11 / glibc system, `-std=c++17` causes `<cmath>` to declare `std::iscanonical`, `std::issignaling`, `std::iseqsig`, and ~30 related overloads. These symbols reference GCC built-ins (`__iscanonicall`, `__issignalingf`, `__iseqsig`, etc.) that are absent from this system's glibc, causing linker failures.

**Diagnosis.** A manual test compile with `-std=c++14` confirmed zero undefined references:
```bash
g++ -x c++ -std=c++14 -fPIC -I r_fake_headers -I src \
    -shared -o /tmp/test_c14.so src/anova.c src/rpart.c \
    src/rpartexp2.c c_entry_points/rpartexp2_c.c
```

**Fix applied to `r2py_rpart/meson.build`.**
- `default_options: ['cpp_std=c++17']` → `['cpp_std=c++14']`
- `c_args: ['-std=c++17', ...]` → `c_args: ['-std=c++14', ...]`
- Note: the fake headers use `inline` variables (`inline eval_fn_t g_eval_fn = nullptr;` in `r_fake_headers/eval.h:124`, `inline thread_local ArenaFrame *g_current_arena_frame = nullptr;` in `r_fake_headers/fake_arena.h:95`, etc.), a C++17 feature. GCC 11 accepts these in C++14 mode as a language extension (warning, not error), so the downgrade is safe.

#### 2.2 Bug 2: Math Library Not Linked

**Root cause.** After the C++14 fix, a new link failure appeared: `undefined reference to 'log'`, `'sqrt'`, `'pow'`, `'nextafterf'`, `'roundf'`, `'tgammaf'`, and ~20 more standard math functions. In C++17 mode, many of these were being inlined by the compiler; in C++14 mode they resolve to real library calls requiring `-lm`.

**Fix applied to `r2py_rpart/meson.build`.**
```meson
link_args: ['-lstdc++', '-lm'],
```

**Result.** `pip install --no-build-isolation .` succeeded, producing wheel `r2py_rpart-0.1.0-cp314-cp314-linux_x86_64.whl` (179,418 bytes).

#### 2.3 Bug 3: `_find_lib()` Searched the Source Tree, Not Site-Packages

**Root cause.** `r2py_rpart/r2py_rpart/__init__.py`'s `_find_lib()` function computed the search path as `os.path.dirname(os.path.abspath(__file__))`. When pytest runs from `/groups/jli9/Yufei/python-rpart/r2py_rpart/`, Python resolves `r2py_rpart` as the source-tree package (at `r2py_rpart/r2py_rpart/__init__.py`), not the installed package. `__file__` therefore pointed into the source directory where `_rpart_core.so` was never placed. The installed library resided at `/users/ycai9/.conda/envs/r-to-python/lib/python3.14/site-packages/r2py_rpart/_rpart_core.so`.

**Fix applied to `r2py_rpart/r2py_rpart/__init__.py` (`_find_lib()`, lines 151–178).**

The function was extended with a two-stage search:
1. Check `os.path.join(here, name)` — works for a normal installed layout.
2. If absent, iterate `sysconfig.get_path(scheme)` for `scheme` in `('platlib', 'purelib')` and check `<site-packages>/r2py_rpart/<name>`. This covers the case where the source-tree package is imported during testing.

```python
import sysconfig
for scheme in ("platlib", "purelib"):
    site = sysconfig.get_path(scheme)
    if site:
        path = os.path.join(site, "r2py_rpart", name)
        if os.path.exists(path):
            return path
```

#### 2.4 Bug 4: `_check_error()` Passed numpy Array to `ffi.string()`

**Root cause.** All public wrapper functions (`rpartexp2`, `rpart`, `pred_rpart`, `xpred`) allocate the error buffer as `np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)` and pass `_cptr(err_buf)` (a cffi `char *` pointer) to the C function, but then call `_check_error(err_buf)` with the original numpy array — not the cffi pointer. `cffi.FFI.string()` requires a `_cffi_backend._CDataBase` object; receiving a `numpy.ndarray` raised `TypeError`.

**Fix applied to `r2py_rpart/r2py_rpart/__init__.py` (`_check_error()`, lines 191–197).**

```python
def _check_error(buf: Any) -> None:
    if isinstance(buf, np.ndarray):
        msg = bytes(buf).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    else:
        msg = ffi.string(buf).decode("utf-8", errors="replace")
    if msg:
        raise RuntimeError(msg)
```

The numpy branch splits the byte sequence at the first null terminator, which is the correct semantics for a null-terminated C error string stored in a uint8 array.

#### 2.5 Test Validation

After the four fixes above, `python -m pytest tests/test_rpartexp2.py -v` reported:
```
tests/test_rpartexp2.py::test_rpartexp2_basic       PASSED
tests/test_rpartexp2.py::test_rpartexp2_all_unique  PASSED
2 passed in 0.73s
```

#### 2.6 Reference Architecture Study: KernSmooth

The reference project `/users/ycai9/Yufei/python-KernSmooth/r2py_kernsmooth/` was read in full to establish the target build/publish structure. Key observations:

- **Build system**: `meson.build` uses `py.extension_module('_KernSmooth', [fortranobject_c, fortran_sources, f2py_gen], ...)` to produce a proper CPython extension module (`_KernSmooth.cpython-314-x86_64-linux-gnu.so`) installed into `r2py_kernsmooth/` via `subdir: 'r2py_kernsmooth'`.
- **f2py**: A `custom_target` runs `python -m numpy.f2py src/_KernSmooth.pyf` to generate `_KernSmoothmodule.c` and `_KernSmooth-f2pywrappers.f` at build time.
- **Python interface**: `r2py_kernsmooth/__init__.py` does `from . import _KernSmooth` and calls routines as `_KernSmooth.linbin(...)`, `_KernSmooth.locpol(...)`, etc.
- **External dependency**: BLAS (`libopenblas`) is required for Fortran LAPACK calls; installed via `openblas-devel` on Linux, `brew install openblas` on macOS.
- **pyproject.toml**: Contains a complete `[tool.cibuildwheel]` section with `before-all` hooks for BLAS on Linux/macOS and `delvewheel` repair on Windows.
- **Workflow**: `.github/workflows/python-publish.yml` builds on 5 platforms (`ubuntu-latest`, `ubuntu-24.04-arm`, `macos-13`, `macos-latest`, `windows-latest`). Windows requires MSYS2 MinGW64 for `gfortran` and `openblas`.

The user confirmed that rpart's existing `cffi.dlopen()` approach (distinct from KernSmooth's `py.extension_module` approach) should be retained as-is; only the CI/CD publishing infrastructure needed to mirror KernSmooth.

#### 2.7 macOS C++ Runtime Fix (`meson.build`)

**Root cause (prospective).** On macOS, Apple clang links against `libc++` (LLVM's C++ standard library). The existing `link_args: ['-lstdc++']` references GCC's `libstdc++`, which does not exist on macOS without an explicit `brew install gcc`. On all Linux and Windows/MinGW builds `-lstdc++` is correct.

**Fix applied to `r2py_rpart/meson.build`.**

Added a Meson conditional before the `shared_library()` call:
```meson
if host_machine.system() == 'darwin'
  cxx_stdlib_link = ['-lc++']
else
  cxx_stdlib_link = ['-lstdc++']
endif
```

The `link_args` line was updated to:
```meson
link_args: cxx_stdlib_link + ['-lm'],
```

#### 2.8 `pyproject.toml` — cibuildwheel Configuration

`[tool.cibuildwheel]` section added, mirroring KernSmooth's structure with the following platform-specific adaptations:

```toml
[tool.cibuildwheel]
build = "cp310-* cp311-* cp312-* cp313-* cp314-*"
skip = ["*-manylinux_i686"]
build-frontend = "build"

[tool.cibuildwheel.windows]
before-build = "pip install delvewheel"
repair-wheel-command = "delvewheel repair -w {dest_dir} {wheel}"

[tool.cibuildwheel.windows.environment]
PATH = "C:\\msys64\\mingw64\\bin;{PATH}"
```

- **No `[tool.cibuildwheel.linux]` section**: GCC and G++ are pre-installed in all manylinux images. rpart requires no external system library (no BLAS, no Fortran runtime).
- **No `[tool.cibuildwheel.macos]` section**: Apple clang supports `-x c++`, `-std=c++14`, and `-fkeep-inline-functions`. The `meson.build` Darwin conditional handles `-lc++` automatically.
- **Windows**: Same `delvewheel` repair pattern as KernSmooth (bundles any MinGW runtime DLLs such as `libstdc++-6.dll`, `libgcc_s_seh-1.dll` into the wheel). PATH is set to prioritize MinGW64 so meson discovers GCC instead of MSVC.

#### 2.9 GitHub Actions Workflow (`.github/workflows/python-publish.yml`)

**Created**: `/groups/jli9/Yufei/python-rpart/r2py_rpart/.github/workflows/python-publish.yml`

Structure mirrors KernSmooth's workflow exactly, with two adaptations:

| KernSmooth | rpart |
|---|---|
| **Windows step name**: "Install Fortran and BLAS (Windows)" | "Install GCC (Windows)" |
| **Windows MSYS2 packages**: `mingw-w64-x86_64-gcc-fortran`, `mingw-w64-x86_64-openblas`, `mingw-w64-x86_64-pkg-config` | `mingw-w64-x86_64-gcc` only |
| **sdist job**: `sudo apt-get install -y libopenblas-dev` before `python -m build --sdist` | No system-package step (no BLAS) |

Shared structure preserved verbatim:
- **Trigger**: `on: release: types: [published]`
- **`build_wheels` job**: 5-platform matrix with `fail-fast: false`, `cibuildwheel@v2`, artifact upload named `cibw-wheels-${{ matrix.os }}-${{ strategy.job-index }}`
- **`build_sdist` job**: `actions/setup-python@v5` + `pip install build` + `python -m build --sdist`, artifact named `cibw-sdist`
- **`pypi-publish` job**: depends on both prior jobs, uses trusted publisher (`id-token: write`) with `pypa/gh-action-pypi-publish@release/v1`, downloads artifacts via `actions/download-artifact@v4` with `pattern: cibw-*` and `merge-multiple: true`

---

### 3. Key Findings & Results

#### 3.1 Build Success

Post-fix `pip install --no-build-isolation .` completed successfully on the local Linux x86_64 system:
- Wheel filename: `r2py_rpart-0.1.0-cp314-cp314-linux_x86_64.whl`
- Wheel size: 179,418 bytes
- `_rpart_core.so` installed to: `/users/ycai9/.conda/envs/r-to-python/lib/python3.14/site-packages/r2py_rpart/_rpart_core.so`

#### 3.2 Test Passage

```
tests/test_rpartexp2.py::test_rpartexp2_basic       PASSED
tests/test_rpartexp2.py::test_rpartexp2_all_unique  PASSED
2 passed in 0.73s
```

`test_rpartexp2_basic` verifies: input `[1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 5.0]`, output is int32 array of same length with values in `{0, 1}`.  
`test_rpartexp2_all_unique` verifies: input `[1.0, 2.0, 4.0, 8.0]`, all unique, all kept.

#### 3.3 C++ Standard Compatibility

The root cause of the original C++17 build failures was confirmed as a glibc/GCC 11 incompatibility: `__iscanonicall`, `__issignalingf`, `__iseqsig`, and ~28 related math classification built-ins are declared by GCC 11's C++17 `<cmath>` but not implemented in the system's glibc. C++14 avoids pulling in these declarations. The `inline` variable declarations in fake headers (C++17 feature) continue to compile under GCC 11 in C++14 mode as an accepted extension.

#### 3.4 Platform-Specific C++ Runtime Differences

| Platform | C++ Runtime | Required link flag |
|---|---|---|
| Linux (manylinux, native) | `libstdc++` (GCC) | `-lstdc++` |
| Windows (MinGW64) | `libstdc++` (GCC) | `-lstdc++` |
| macOS (Apple clang) | `libc++` (LLVM) | `-lc++` |

Without the `host_machine.system() == 'darwin'` conditional in meson.build, the macOS wheels in CI would fail to link.

#### 3.5 KernSmooth Architecture vs. rpart Architecture

| Aspect | KernSmooth | rpart |
|---|---|---|
| Source language | Fortran | C (compiled as C++) |
| Binding tool | f2py (numpy built-in) | cffi ABI mode (`dlopen`) |
| Meson build target | `py.extension_module()` → `.cpython-*.so` | `shared_library()` → `_rpart_core.so` |
| Python import | `from . import _KernSmooth` | `ffi.dlopen(path)` |
| External system dep | openblas (BLAS) | none |
| macOS linker flag | automatic (C++ linker) | `-lc++` (explicitly required) |
| Windows GCC dep | `gcc-fortran` + `openblas` + `pkg-config` | `gcc` only |

#### 3.6 Files Modified / Created

| File | Change Type | Summary |
|---|---|---|
| `r2py_rpart/meson.build` | Modified (×2) | `-std=c++17` → `-std=c++14`; `-lm` added; Darwin `-lc++` conditional added |
| `r2py_rpart/r2py_rpart/__init__.py` | Modified (×2) | `_find_lib()` site-packages fallback; `_check_error()` numpy branch |
| `r2py_rpart/pyproject.toml` | Modified | Added `[tool.cibuildwheel]` section with `build`, `skip`, `windows` entries |
| `r2py_rpart/.github/workflows/python-publish.yml` | Created | 5-platform wheel build + sdist + trusted-publisher PyPI deploy |

---

### 4. Conclusion & Next Steps

The `r2py_rpart` package is now fully buildable and testable on the local Linux system, and the CI/CD infrastructure required for multi-platform PyPI publication is complete. The package will be published as an independent GitHub repository via `git subtree`; when a GitHub Release is created, the workflow will automatically build wheels for Linux x86_64, Linux aarch64, macOS Intel, macOS Apple Silicon, and Windows x86_64, build a source distribution, and publish all artifacts to PyPI using the trusted-publisher (OIDC) mechanism.

The next phase should focus on implementing the Python-level wrappers for the remaining four public entry points (`rpart`, `pred_rpart`, `xpred`, `init_rpcallback`) that are declared in `__init__.py` but not yet exercised by tests, and writing a comprehensive test suite benchmarked against R's reference output to validate numerical correctness across all five functions.
