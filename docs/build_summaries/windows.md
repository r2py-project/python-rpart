# Research Report — Windows (MinGW/PE-COFF) Wheel Build Failure in `r2py_rpart`

**Date:** 2026-08-08
**Repository:** `/groups/jli9/Yufei/python-rpart` (branch `main`)
**Affected component:** `r2py_rpart/r_fake_headers/install.h`
**CI workflow:** `r2py_rpart/.github/workflows/python-publish.yml` — job `build_wheels`, matrix leg `windows-latest`

---

### 1. Abstract

The `Upload Python Package` GitHub Actions workflow for the `r2py_rpart` package failed on the `windows-latest` matrix leg only, during the link step of the `_rpart_core.dll` shared library, with repeated `multiple definition of 'TLS init function for gSymbolCache[abi:cxx11]'` errors from MinGW `ld.exe`. The failure was traced to a namespace-scope `inline thread_local std::unordered_map` in the fake R header `install.h`, whose dynamic initialization forces GCC to emit a per-translation-unit TLS initialization function that receives vague (WEAK/COMDAT) linkage on ELF and Mach-O but strong global linkage on PE-COFF. The declaration was replaced with a constant-initialized thread-local pointer plus a lazily allocating accessor, eliminating the TLS init function entirely while preserving per-thread symbol-cache semantics; the fix was verified by full compilation and linkage of all 37 translation units and by a behavioral test of the symbol-interning invariants.

---

### 2. Methodology & Actions Taken

#### 2.1 Fault localization

1. Searched the repository for the offending symbol `gSymbolCache`; all references were confined to a single file, `r2py_rpart/r_fake_headers/install.h` (lines 58, 85–86, 131, 153, 172–173, 192, 203, 214, 346). No `.c`, `.py`, or `meson.build` file referenced it.
2. Inspected the declaration at `install.h:153`:
   ```cpp
   inline thread_local std::unordered_map<std::string, SEXP> gSymbolCache;
   ```
   and the three consumers in the same header: `create_symbol()` (lookup + insert), `clear_symbol_cache()` (iterate, `std::free` each `SYMSXP`/`CHARSXP` pair, then `.clear()`), and the C-linkage bridge `call_install()`.
3. Enumerated all `inline thread_local` declarations across `r_fake_headers/` to establish why the linker named exactly one of them:
   - `r_fake_headers/fake_arena.h:95` — `inline thread_local ArenaFrame *g_current_arena_frame = nullptr;`
   - `r_fake_headers/R_CheckUserInterrupt.h:105` — `inline thread_local std::atomic<bool> g_interrupt_requested{false};`
   - `r_fake_headers/install.h:153` — the failing `std::unordered_map`.
4. Reviewed `r2py_rpart/meson.build` to recover the exact compilation model: 32 `src/*.c` files plus 6 `c_entry_points/*_c.c` files are compiled by the **C** compiler driver with `c_args: ['-x', 'c++', '-std=c++14', '-fkeep-inline-functions', '-fPIC']`, linked with `-lstdc++ -lm` (`-lc++` on Darwin), `name_prefix: ''`.
5. Reviewed `.github/workflows/python-publish.yml`: matrix is `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-latest`, `windows-latest`; the Windows leg installs `mingw-w64-x86_64-gcc` via `msys2/setup-msys2@v2` (MINGW64) and points `cibuildwheel` (`pypa/cibuildwheel@v4.2.0`) at it via `CIBW_ENVIRONMENT_WINDOWS=PATH=...`. The failing target was `cp310-win_amd64`; the toolchain in the log is GCC 16.1.0 (`x86_64-w64-mingw32`, ninja backend).

#### 2.2 Empirical diagnosis (local, ELF/x86-64, GCC on Linux)

Two synthetic translation units, each including `install.h` and calling `create_symbol()`, were compiled with the project's flags; object symbol tables were then dumped.

- `nm -C` on the object produced:
  ```
  U __tls_get_addr
  0000000000000000 b __tls_guard
  000000000000006e t __tls_init
  0000000000000000 u gSymbolCache[abi:cxx11]
  0000000000000000 u guard variable for gSymbolCache[abi:cxx11]
  000000000000006e W TLS init function for gSymbolCache[abi:cxx11]
  0000000000000000 W TLS wrapper function for gSymbolCache[abi:cxx11]
  ```
- `readelf -SW` showed the wrapper in a COMDAT group section (`AXG` flags):
  ```
  [199] .text._ZTW12gSymbolCacheB5cxx11 PROGBITS ... AXG
  [184] .tbss._Z12gSymbolCacheB5cxx11   NOBITS   ... WAGT
  [403] .tbss._ZGV12gSymbolCacheB5cxx11 NOBITS   ... WAGT
  ```
- `readelf -sW` confirmed the binding of the init function itself:
  ```
  3940: 0000000000000eae   169 FUNC    WEAK   DEFAULT 1243 _ZTH12gSymbolCacheB5cxx11
  ```
- Eight real project sources (`src/anova.c`, `src/bsplit.c`, `src/gini.c`, `src/xpred.c`, `src/xval.c`, `src/rpart.c`, `c_entry_points/rpart_c.c`, `c_entry_points/interpreter_helpers_c.c`) were compiled with the production flags; **every** object carried `TLS init function for gSymbolCache[abi:cxx11]` with `W` (weak) binding.
- A control build of `src/anova.c` **without** `-fkeep-inline-functions` still emitted the symbol, disproving the hypothesis that the flag was the root cause (it is not; the symbol is emitted regardless).
- `nm -C` on the same object showed `g_current_arena_frame` and `g_interrupt_requested` present only as plain thread-local data symbols, with **no** associated init function.
- Grep established that `create_symbol` / `clear_symbol_cache` / `call_install` are actually *called* from only one file, `c_entry_points/interpreter_helpers_c.c`; the symbol is nevertheless emitted by every TU that includes the header.

#### 2.3 Remediation

`r_fake_headers/install.h` was modified in place (single file, 5 edits):

1. Added `#include <new>` (for `std::nothrow`) to the standard-library include block.
2. Replaced the namespace-scope map with a constant-initialized thread-local pointer and an accessor, preceded by a ~20-line comment recording the PE-COFF rationale:
   ```cpp
   inline thread_local std::unordered_map<std::string, SEXP> *gSymbolCachePtr = nullptr;

   inline std::unordered_map<std::string, SEXP> &gSymbolCache() {
       if (!gSymbolCachePtr) {
           gSymbolCachePtr = new (std::nothrow) std::unordered_map<std::string, SEXP>();
           if (!gSymbolCachePtr)
               throw RError("install: out of memory allocating symbol cache");
       }
       return *gSymbolCachePtr;
   }
   ```
   The `RError` on allocation failure matches the header's Invariant 1 (never return a bad handle), consistent with the existing `std::malloc` failure path for `SEXPREC` nodes.
3. `create_symbol()` now binds `auto &cache = gSymbolCache();` once and uses it for both the `find` and the `cache[key] = sym` insert.
4. `clear_symbol_cache()` returns early when `gSymbolCachePtr` is null (nothing interned on this thread), then iterates `*gSymbolCachePtr`.
5. The terminal `gSymbolCache.clear()` became `gSymbolCachePtr->clear()`.

The map is intentionally never `delete`d at thread exit: `SYMSXP` node pointers serve as `_frame_registry` lookup keys and must remain stable across `.Call` invocations, with `clear_symbol_cache()` as the explicit reclamation path.

#### 2.4 Verification

- Recompiled `src/anova.c`, `src/xval.c`, `c_entry_points/interpreter_helpers_c.c` with production flags: **0** `TLS init function` symbols each, **1** `gSymbolCachePtr` symbol each.
- Compiled all 37 translation units (`src/*.c` + `c_entry_points/*.c`) with `g++ -x c++ -std=c++14 -fkeep-inline-functions -fPIC -Ir_fake_headers -Isrc` and linked them into a shared object with `-lstdc++ -lm`. Link succeeded. `nm -C` on the library shows only:
  ```
  0000000000033afd W gSymbolCache[abi:cxx11]()
  0000000000000010 u gSymbolCachePtr[abi:cxx11]
  ```
  with zero `TLS init function` entries.
- Behavioral test (`-pthread`) against the header confirmed all pre-existing invariants: pointer identity for repeated `create_symbol("yback")`; distinct pointers for distinct names; `R_CHAR(PRINTNAME(sym))` round-trips `"yback"` / `"wback"`; a second `std::thread` receives its own node (per-thread isolation preserved); re-interning after `clear_symbol_cache()` succeeds; a repeated `clear_symbol_cache()` is a safe no-op. Exit code 0.
- Meson was unavailable on `PATH` in the session environment (it lives in the `r-to-python` conda environment referenced by `pip_install.sh`), so the manual compile-and-link reproduction above was used in place of `meson setup` / `ninja`.

---

### 3. Key Findings & Results

1. **Root cause.** `std::unordered_map` has a non-trivial constructor, so a `thread_local` instance requires *dynamic* initialization. GCC therefore synthesizes `_ZTH12gSymbolCacheB5cxx11` ("TLS init function"), `_ZTW…` ("TLS wrapper"), and a `__tls_guard` in every translation unit that includes the header — 30+ objects in this build.

2. **Platform asymmetry explained.** On ELF the init function is emitted as a `WEAK` alias to a local `__tls_init`, with the wrapper in a COMDAT group; duplicate weak definitions are legal and the linker silently discards all but one. Mach-O achieves the same via coalesced/weak-definition sections. PE-COFF can express neither construct: its "weak" is a *weak external* (an undefined symbol with a fallback target, not a discardable definition), and it cannot express a weak alias to a local symbol inside a COMDAT group. MinGW GCC consequently emits the init function as an ordinary strong global, so the second and every subsequent object collide — hence a single-platform failure with all four non-Windows legs green.

3. **Why only one of the three `inline thread_local`s failed.** `g_current_arena_frame` (`nullptr`) and `g_interrupt_requested` (`std::atomic<bool>{false}`) are constant-initialized and emit no init function at all; verified by symbol dump. Only the dynamically-initialized map is affected.

4. **Two hypotheses eliminated.** (a) `-fkeep-inline-functions` is not the trigger — the symbol is emitted with or without it. (b) The `-std=c++14` setting (under which `inline` variables are a GCC extension, warned about on every include) is orthogonal; raising the standard to C++17 would not alter the PE-COFF emission, and `meson.build` documents that C++17 was avoided because of `<cmath>` builtins (`__iscanonical`, etc.) undefined against GCC 11's glibc.

5. **Log interpretation.** The pasted CI excerpt begins mid-stream at `src_xpred.c.obj`; earlier duplicate-definition lines were truncated. `src_anova.c.obj` is reported as "first defined here" for all of them, consistent with every object carrying its own strong copy.

6. **Result.** The fix is confined to one header, requires no `meson.build`, workflow, or toolchain changes, is a no-op on the four already-passing platforms, and preserves the exact per-thread interning contract required by `findVarInFrame` / `_frame_registry`.

7. **Scope of applicability.** Only `method=4` (user-defined splits, `src/rpart_callback.c:59,62,65,68`) reaches this code at runtime; the standard `anova` / `poisson` / `class` / `exp` methods never call `install`. The defect was therefore purely a link-time obstruction, not a runtime correctness issue.

---

### 4. Conclusion & Next Steps

The Windows wheel build failure is diagnosed and remediated in `r2py_rpart/r_fake_headers/install.h`. Local evidence is conclusive at the source of the error — the symbol class that MinGW `ld.exe` rejected is no longer emitted by any translation unit, and the full 37-unit library links cleanly — but the MinGW/PE-COFF link itself could not be reproduced in this environment (no PE-COFF toolchain available), so the `windows-latest` leg remains confirmed only by construction, not by a green CI run.

Outstanding actions:

1. **Commit and propagate.** The change is uncommitted (`M r2py_rpart/r_fake_headers/install.h`). `r2py_rpart/` is a git subtree; the failing CI builds from the standalone `https://github.com/r2py-project/r2py_rpart.git` repository, so `git_push.sh` (`git push origin main` followed by `git subtree push --prefix=r2py_rpart r2py_rpart main`) must be run before the workflow will observe the fix.
2. **Re-run the release workflow** (triggered on `release: published`) and confirm the `cp310-win_amd64` wheel builds, along with the other `cp3xx-win_amd64` targets.
3. **Preventive audit.** Any future namespace-scope `inline thread_local` of non-trivially-constructible type added to `r_fake_headers/` will reintroduce this failure mode on MinGW. A cheap CI guard is to assert that no object emits a `TLS init function` symbol, or to restrict such declarations to constant-initialized types.
4. **Optional runtime check.** Exercise the `method=4` / `init_rpcallback` path (the only consumer of `create_symbol`) against the installed wheel once built, to confirm end-to-end symbol interning through the cffi bridge on Windows.
