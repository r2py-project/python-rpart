# Fake Header Implementation Guide: `R_alloc`

---

### 1. Overview of `R_alloc` in R API

`R_alloc` is the primary arena-style memory allocator in R's C API, declared in `R_ext/Memory.h` (included transitively by `R.h`) as:

```c
char *R_alloc(R_SIZE_T nmemb, int size);
```

It allocates `nmemb * size` bytes from R's internal garbage-collector-managed memory stack (the "vmalloc" arena), returns a `char *` to the zeroed block, and releases all memory allocated since the most recent GC save-point automatically when the `.Call` function returns. Callers cast the result to any target pointer type. It is the preferred scratch allocator in R's C API because no explicit `free` call is ever needed — cleanup is guaranteed at `.Call` return. In rpart, `R_alloc` is surfaced exclusively through the `ALLOC(a, b)` macro defined in `rpart.h` line 25: `#define ALLOC(a,b) R_alloc(a,b)`.

---

### 2. Contextual Usage Analysis

**Definition site.**

| File | Line | Context |
|---|---|---|
| `rpart.h` | 25 | `#define ALLOC(a,b)  R_alloc(a,b)` — the only definition site in the package source |
| `rpart.h` | 19–23 | Comment: "Memory defined with R_alloc is removed automatically. That with CALLOC I have to remove myself." |

**Actual call sites (all via `ALLOC`).**

Every call in the package source is of the form `(TargetType *) ALLOC(nmemb, sizeof(element))`, which expands to `(TargetType *) R_alloc(nmemb, sizeof(element))`. The full list of call sites found across all `.c` files in `/groups/jli9/Yufei/python-rpart/rpart/src/`:

| File | Lines | Element type | nmemb expression | Purpose |
|---|---|---|---|---|
| `rpart.c` | 123 | `double *` | `rp.nvar` | Ragged-array row-pointer vector for `rp.xdata` |
| `rpart.c` | 128 | `double *` | `n` | Ragged-array row-pointer vector for `rp.ydata` |
| `rpart.c` | 138 | `int` | `n` | Scratch integer vector `rp.tempvec` |
| `rpart.c` | 139 | `double` | `n` | Scratch double vector `rp.xtemp` |
| `rpart.c` | 140 | `double *` | `n` | Ragged-array row-pointer vector `rp.ytemp` |
| `rpart.c` | 141 | `double` | `n` | Scratch double vector `rp.wtemp` |
| `rpart.c` | 148 | `int *` | `rp.nvar` | Outer pointer-of-pointer vector for `rp.sorts` |
| `rpart.c` | 149 | `int` | `n * rp.nvar` | Flat backing array for the entire sort matrix |
| `rpart.c` | 174 | `int` | `n * rp.nvar` | Saved copy of sort indices for cross-validation |
| `rpart.c` | 182 | `int` | `3 * maxcat` | Categorical split workspace `rp.csplit` |
| `rpart.c` | 183 | `double` | `2 * maxcat` | Left/right weight scratch `rp.lwt` |
| `rpart.c` | 188 | `int` | `1` | Minimal `rp.csplit` when no categorical variables |
| `rpart.c` | 206 | (struct `Node`) | `1` | Root node of the tree when cross-validation is off |
| `rpart.c` | 219 | (struct `cpTable`) | `1` | Initial cp-table entry |
| `rpart.c` | 262 | `double *` | `3 + rp.num_resp` | Ragged-array row pointers for `ddnode` |
| `rpart.c` | 294 | `int *` | `maxcat` | Categorical split pointer array `ccsplit` |
| `xpred.c` | 122 | `double *` | `rp.nvar` | `rp.xdata` row pointers for cross-prediction |
| `xpred.c` | 127 | `double *` | `n` | `rp.ydata` row pointers |
| `xpred.c` | 137 | `int` | `n` | `rp.tempvec` |
| `xpred.c` | 138 | `double` | `n` | `rp.xtemp` |
| `xpred.c` | 139 | `double *` | `n` | `rp.ytemp` row pointers |
| `xpred.c` | 140 | `double` | `n` | `rp.wtemp` |
| `xpred.c` | 147 | `int *` | `rp.nvar` | `rp.sorts` outer pointers |
| `xpred.c` | 148 | `int` | `n * rp.nvar` | Flat sort matrix |
| `xpred.c` | 172 | `int` | `n * rp.nvar` | `savesort` copy for cross-prediction |
| `xpred.c` | 179 | `int` | `3 * maxcat` | `rp.csplit` |
| `xpred.c` | 180 | `double` | `2 * maxcat` | `rp.lwt` |
| `xpred.c` | 185 | `int` | `1` | Minimal `rp.csplit` |
| `xpred.c` | 191 | `int` | `n` | `rp.which` prediction assignment vector |
| `xpred.c` | 192 | (struct `Node`) | `1` | Root node for cross-prediction tree |
| `pred_rpart.c` | 54 | `int *` | `dimc[1]` | Categorical split column pointers |
| `pred_rpart.c` | 58 | `int *` | `dimx[1]` | Missing-indicator column pointers `xmiss` |
| `pred_rpart.c` | 59 | `double *` | `dimx[1]` | Predictor column pointers `xdata` |
| `gini.c` | 48 | `double` | `numclass * 2` | Per-class left/right count vectors |
| `gini.c` | 51 | `int` | `maxcat * 2` | Split/count integer scratch |
| `gini.c` | 54 | `double` | `maxcat * 2` | Per-category weight scratch |
| `gini.c` | 59 | `double *` | `numclass` | `ccnt` outer pointer vector |
| `gini.c` | 60 | `double` | `numclass * maxcat` | `ccnt` backing matrix |
| `gini.c` | 65 | `double` | `i` (3*numclass+numclass^2) | Prior, frequency, loss vectors |
| `anova.c` | 18 | `int` | `2 * maxcat` | Count scratch vector |
| `anova.c` | 20 | `double` | `3 * maxcat` | Mean scratch vector |
| `poisson.c` | 23 | `double` | `3 * maxcat` | Death count scratch |
| `poisson.c` | 26 | `int` | `3 * maxcat` | Order scratch vector |
| `graycode.c` | 20 | `int` | `maxcat` | Gray code scratch array |
| `make_cp_list.c` | 61 | (struct `cpTable`) | `1` | New cp-table entry during tree traversal |
| `usersplit.c` | 24–25 | `double` | `max(n_return+1, 2*n)` | User split scratch buffer |

**Official signature.**

From `~/.conda/envs/r-to-python/lib/R/include/R_ext/Memory.h` (confirmed for this installation at `/users/ycai9/.conda/envs/r-to-python/lib/R/include/R_ext/Memory.h`):

```c
char *R_alloc(R_SIZE_T nmemb, int size);
```

- First argument: element count (`R_SIZE_T`, which resolves to `std::size_t` in C++ builds).
- Second argument: element size in bytes (`int`, not `size_t`).
- Return value: `char *` — callers always cast to the target type.

Note that the second argument (`size`) is `int` in the official signature, even though callers always pass `sizeof(T)`. The fake must accept `int` as the second parameter to match the declaration.

**Co-occurring R API items.**

In all call sites, `ALLOC` is used to build scratch arrays and ragged-array pointer vectors. It never co-occurs with `PROTECT`/`UNPROTECT` (those wrap `allocVector`/`allocMatrix`). It co-occurs with:

- `REAL(sexp)`, `INTEGER(sexp)` — accessors used to read input `SEXP` data into variables that are then stored in `ALLOC`-allocated pointer arrays.
- `CALLOC(a, b)` — the heap-allocation counterpart for objects (nodes, splits) that must persist across sub-calls and be freed explicitly with `R_Free`. Both macros are defined in `rpart.h` lines 25–26 and are distinct allocators.
- `allocVector`, `allocMatrix` — SEXP heap allocators used for the output vectors; completely independent from the arena.

**Distinct implementation patterns.**

All call sites share a single pattern: `(TargetType *) ALLOC(nmemb, sizeof(element))`. The element size is always expressed with `sizeof`. There are two minor structural sub-cases:

| Pattern | Description | Representative sites |
|---|---|---|
| P1: Flat array scratch | `nmemb` plain elements of a primitive type; the returned pointer is used directly | `rpart.c:138-141`, `gini.c:48,51,54,65`, `anova.c:18,20`, `poisson.c:23,26`, `graycode.c:20` |
| P2: Pointer-of-pointer array | `nmemb` pointers; the allocation holds an array of `T *`; subsequent loop populates each slot | `rpart.c:123,128,140,148`, `gini.c:59`, `rpart.c:262,294` |
| P3: Struct block | `nmemb=1`, `sizeof(cpTable)` or `sizeof(Node)` | `rpart.c:206,219`, `make_cp_list.c:61`, `xpred.c:192` |

All three share the identical fake strategy (delegate to `arena_alloc`). The patterns are distinguished only for contextual clarity — no separate fake implementation is needed per pattern.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`R_alloc` is a pure arena allocator. Its entire fake implementation is a single `inline` function that delegates to `arena_alloc` from `fake_arena.hpp` (Invariant 2). The arena stack holds one `Arena` per active `.Call` invocation; `ArenaFrame` RAII guards push/pop frames at the `.Call` boundary, so all memory obtained by `R_alloc` (and through the `ALLOC` macro) is freed automatically when the `.Call` wrapper returns — exactly matching R's documented behavior.

**Chosen mechanism.**

```cpp
inline char *R_alloc(std::size_t nmemb, int size) {
    return static_cast<char *>(arena_alloc(nmemb * static_cast<std::size_t>(size)));
}
```

The cast of `size` to `std::size_t` before the multiplication prevents signed-integer overflow when `size` is large (though in practice `sizeof(T)` is always small and positive). The result is cast to `char *` to match the declared return type; callers then cast to their target type as they already do in the original source.

**Why arena, not heap.**

The `ALLOC` macro is used for scratch arrays that are:
1. Allocated at the start of a `.Call` entry-point (`rpart`, `xpred`, `pred_rpart`) or in a sub-function it calls.
2. Never freed explicitly within the source — the original code relies entirely on R's GC to reclaim them at `.Call` exit.
3. Never stored in a location that outlives the `.Call` invocation.

This lifecycle maps exactly to Invariant 2's arena-frame model. When the Python-side `.Call` wrapper returns, `ArenaFrame`'s destructor calls `gArenaStack.back().reset()`, which bulk-frees every block in the current frame's `Arena::blocks` vector with a single pass of `std::free` calls — exactly what R's vmalloc arena does.

**ArenaFrame placement.**

Every top-level `.Call`-registered entry point in rpart must declare an `ArenaFrame` as its first local variable. The five such functions are `rpart`, `xpred`, `pred_rpart`, `rpartexp2`, and `init_rpcallback`. Sub-functions called from these (e.g., `gini.c:gini_init`, `anova.c:anova_init`, `partition.c:partition`, `make_cp_list.c`, `graycode.c`) do not need their own `ArenaFrame`; they share the frame of their caller.

**`ALLOC` macro preservation.**

The `#define ALLOC(a,b) R_alloc(a,b)` in `rpart.h` line 25 does not need to be replicated in the fake header. It lives in `rpart.h`, which is included by the original source files unchanged. The fake header only needs to provide the `R_alloc` function definition itself. The `ALLOC` macro then resolves correctly to the fake `R_alloc`.

**`S_alloc` and `vmaxget` / `vmaxset`.**

`R_ext/Memory.h` also declares `S_alloc`, `vmaxget`, and `vmaxset`. None of these appear in rpart's source files. They must be declared in the fake `Memory.h` replacement (as stubs or delegating functions) so that the `#include <R_ext/Memory.h>` chain compiles without errors. `S_alloc(n, size)` behaves identically to `R_alloc(n, size)` (zero-initialized arena allocation); in the fake it can also delegate to `arena_calloc`. `vmaxget` and `vmaxset` are no-ops in the fake because the arena's frame stack replaces the vmax save/restore idiom.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): `arena_alloc` throws `std::bad_alloc` on OOM (from `std::malloc` failure inside the arena). The `.Call` boundary `try/catch` block catches `std::bad_alloc` in addition to `RError`. If the project standardises on `RError` only, the arena block should be wrapped to rethrow as `RError("R_alloc: out of memory")`.
- Invariant 2 (arena memory): directly applicable and fully satisfied. `R_alloc` is the canonical arena function.
- Invariant 3 (R Interpreter Items): not applicable. `R_alloc` is a pure memory allocator with no interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern: Arena-Backed Raw Memory Allocation via ALLOC Macro

- **Locations:** `rpart.h:25` (macro definition); all `ALLOC(...)` call sites listed in Section 2 across `rpart.c`, `xpred.c`, `pred_rpart.c`, `gini.c`, `anova.c`, `poisson.c`, `graycode.c`, `make_cp_list.c`, `usersplit.c`

- **Original R API Usage:**

```c
/* rpart.h:25 — the only place R_alloc is named directly */
#define ALLOC(a,b)  R_alloc(a,b)

/* rpart.c:123-141 — representative flat array and pointer-array allocations */
rp.xdata  = (double **) ALLOC(rp.nvar, sizeof(double *));
rp.ydata  = (double **) ALLOC(n, sizeof(double *));
rp.tempvec = (int *)    ALLOC(n, sizeof(int));
rp.xtemp  = (double *)  ALLOC(n, sizeof(double));
rp.ytemp  = (double **) ALLOC(n, sizeof(double *));
rp.wtemp  = (double *)  ALLOC(n, sizeof(double));

/* rpart.c:206 — struct allocation */
tree = (pNode) ALLOC(1, nodesize);

/* pred_rpart.c:54-59 — ragged-array pointer setup */
csplit = (const int **)   ALLOC((int) dimc[1], sizeof(int *));
xmiss  = (const int **)   ALLOC((int) dimx[1], sizeof(int *));
xdata  = (const double **) ALLOC((int) dimx[1], sizeof(double *));

/* usersplit.c:24-25 — conditional size expression */
uscratch = (double *) ALLOC(
    n_return + 1 > 2 * n ? n_return + 1 : 2 * n,
    sizeof(double));
```

- **C++ Fake Implementation:**

```cpp
// fake_Memory.hpp
// Drop-in replacement for R_ext/Memory.h.
// Provides: R_alloc, S_alloc, S_realloc, vmaxget, vmaxset,
//           R_malloc_gc, R_calloc_gc, R_realloc_gc.
//
// Include order: must be included after fake_arena.hpp (which defines
// arena_alloc, arena_calloc, and gArenaStack) and after fake_Rinternals.hpp
// (which defines RError). In practice both are pulled in by the fake R.h
// before this file is reached.

#pragma once
#ifndef FAKE_MEMORY_H
#define FAKE_MEMORY_H

#include <cstddef>    // std::size_t
#include <cstring>    // std::memset
#include <stdexcept>  // std::bad_alloc
#include "fake_arena.hpp"  // ArenaFrame, gArenaStack, arena_alloc, arena_calloc

// RError guard — may already be defined by fake_Rinternals.hpp.
#ifndef FAKE_RERROR_DEFINED
#include <stdexcept>
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};
#define FAKE_RERROR_DEFINED 1
#endif

// -----------------------------------------------------------------------
// R_alloc — arena-backed raw memory allocator.
//
// Official signature (R_ext/Memory.h):
//   char *R_alloc(R_SIZE_T nmemb, int size);
//
// Behavior: allocates nmemb*size bytes from the thread-local arena frame
// (gArenaStack.back()), returns a char* to the block. The memory is
// automatically freed when the enclosing ArenaFrame destructs.
//
// The second argument (size) is int in the official R signature. The cast
// to std::size_t before multiplication prevents signed overflow and matches
// what sizeof() expressions actually produce at call sites.
//
// On OOM: arena_alloc throws std::bad_alloc (from std::malloc failure).
// The .Call boundary wrapper should catch std::bad_alloc and either
// rethrow as RError or handle it alongside RError.
//
// ALLOC(a,b) in rpart.h expands to R_alloc(a,b); no change to rpart.h
// is needed — the macro resolves to this fake inline function.
// -----------------------------------------------------------------------
inline char *R_alloc(std::size_t nmemb, int size) {
    std::size_t bytes = nmemb * static_cast<std::size_t>(size);
    return static_cast<char *>(arena_alloc(bytes));
}

// -----------------------------------------------------------------------
// S_alloc — like R_alloc but zero-initialises the block.
// Declared in R_ext/Memory.h as: char *S_alloc(long, int);
// Rare in modern code; delegates to arena_calloc.
// -----------------------------------------------------------------------
inline char *S_alloc(long nmemb, int size) {
    std::size_t bytes = static_cast<std::size_t>(nmemb)
                        * static_cast<std::size_t>(size);
    return static_cast<char *>(arena_calloc(
        static_cast<std::size_t>(nmemb),
        static_cast<std::size_t>(size)));
}

// -----------------------------------------------------------------------
// S_realloc — resize an arena block.
// Declared in R_ext/Memory.h as: char *S_realloc(char*, long, long, int);
// In R's real implementation this allocates a new arena block, copies the
// old data, and zero-fills the remainder. The old block is not freed (arena
// semantics). The fake does the same: allocate new block via arena_alloc,
// copy old data, zero-fill extension.
// Not called in rpart source, but required for the header chain to compile.
// -----------------------------------------------------------------------
inline char *S_realloc(char *old_ptr, long new_n, long old_n, int size) {
    std::size_t new_bytes = static_cast<std::size_t>(new_n)
                            * static_cast<std::size_t>(size);
    std::size_t old_bytes = static_cast<std::size_t>(old_n)
                            * static_cast<std::size_t>(size);
    char *new_ptr = static_cast<char *>(arena_alloc(new_bytes));
    if (old_ptr && old_bytes > 0) {
        std::size_t copy_bytes = old_bytes < new_bytes ? old_bytes : new_bytes;
        std::memcpy(new_ptr, old_ptr, copy_bytes);
    }
    if (new_bytes > old_bytes)
        std::memset(new_ptr + old_bytes, 0, new_bytes - old_bytes);
    return new_ptr;
}

// -----------------------------------------------------------------------
// vmaxget / vmaxset — save/restore the arena high-water mark.
// In real R these allow callers to free everything allocated since the
// save point. In the fake, the ArenaFrame mechanism provides an equivalent
// guarantee at .Call boundaries, so these are no-ops. Returning nullptr
// from vmaxget is safe because no rpart code calls vmaxset with the result.
// -----------------------------------------------------------------------
inline void *vmaxget(void) { return nullptr; }
inline void  vmaxset(const void * /*saved*/) {}

// -----------------------------------------------------------------------
// R_gc / R_gc_running — garbage collector interface.
// R_gc() is a no-op in the fake (no GC). R_gc_running() returns 0.
// Not called in rpart source; required for completeness.
// -----------------------------------------------------------------------
inline void R_gc(void) {}
inline int  R_gc_running(void) { return 0; }

// -----------------------------------------------------------------------
// R_malloc_gc, R_calloc_gc, R_realloc_gc — GC-aware heap allocators.
// Added in R 4.2. Not used by rpart source. Delegate to arena for
// consistency (they are GC-managed in the real runtime; the arena
// is the closest analog in the fake).
// -----------------------------------------------------------------------
inline void *R_malloc_gc(std::size_t n) {
    return arena_alloc(n);
}
inline void *R_calloc_gc(std::size_t n, std::size_t size) {
    return arena_calloc(n, size);
}
inline void *R_realloc_gc(void *ptr, std::size_t size) {
    // Arena blocks cannot be resized in place. Allocate new block and
    // copy. Old block is still in the arena and will be freed at frame
    // exit (acceptable waste; this function is not called in rpart).
    void *new_ptr = arena_alloc(size);
    if (ptr) std::memcpy(new_ptr, ptr, size);
    return new_ptr;
}

// -----------------------------------------------------------------------
// R_allocLD — long double array allocator.
// Declared in R_ext/Memory.h. Not used by rpart. Delegates to arena.
// -----------------------------------------------------------------------
inline long double *R_allocLD(std::size_t nelem) {
    return static_cast<long double *>(
        arena_alloc(nelem * sizeof(long double)));
}

#endif // FAKE_MEMORY_H
```

- **Arena / Memory Notes:**

  All allocations made through `R_alloc` (and thus `ALLOC`) go into the thread-local arena frame at `gArenaStack.back()`. They are **never** freed individually — the entire frame is freed at once when the `ArenaFrame` destructor runs at `.Call` return.

  The `ArenaFrame` guard must be the first local variable declared in each `.Call`-registered entry-point wrapper. For the five rpart entry points, the wrappers look like this:

  ```cpp
  // Example: rpart entry-point wrapper
  extern "C" SEXP rpart_wrapper(
          SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
          SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
          SEXP wt2, SEXP ny2, SEXP cost2) {
      ArenaFrame _frame;   // pushed on gArenaStack; all ALLOC calls within
                           // rpart(), xval(), partition(), gini_init(), etc.
                           // allocate into this frame
      try {
          return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                       ymat2, xmat2, wt2, ny2, cost2);
          // _frame destructs here: all ALLOC'd blocks freed
      } catch (const RError &e) {
          set_python_error(e.what());
          return R_NilValue;
          // _frame also destructs on this path
      } catch (const std::bad_alloc &) {
          set_python_error("R_alloc: out of memory");
          return R_NilValue;
      }
  }
  ```

  The SEXP objects returned from the function (`which3`, `rlist`, etc.) are **heap-allocated** by `allocVector`/`allocMatrix` (via `std::malloc`), not by the arena. They survive `ArenaFrame` destruction. Python reads their contents after the wrapper returns and then calls `free_sexp()` to release them.

  If `R_alloc` is called before the first `ArenaFrame` has been pushed (i.e., from outside any `.Call` wrapper), `gArenaStack.back()` will throw `std::out_of_range` or invoke undefined behavior on an empty vector. To guard against this, the arena's `alloc()` method can check `gArenaStack.empty()` and throw `RError("R_alloc called outside .Call boundary")`.

- **Explanation:**

  The `#define ALLOC(a,b) R_alloc(a,b)` at `rpart.h:25` is preserved in the original source file without any modification. The fake provides only the `R_alloc` function definition in `fake_Memory.hpp`. When the compiler processes `rpart.c`, it encounters `ALLOC(rp.nvar, sizeof(double *))`, expands it to `R_alloc(rp.nvar, sizeof(double *))`, and resolves the call to the inline function above. The result is cast from `char *` to `double **` by the surrounding cast in the source — no change to any source file is needed.

  The distinction between `ALLOC` and `CALLOC` is critical and is preserved faithfully:

  | Macro | Expands to | Fake implementation | Freed by |
  |---|---|---|---|
  | `ALLOC(a,b)` | `R_alloc(a,b)` | `arena_alloc(a*b)` — arena | `ArenaFrame` destructor at `.Call` exit |
  | `CALLOC(a,b)` | `R_chk_calloc((size_t)(a), b)` | `std::calloc(a, b)` — heap | `R_Free(ptr)` called explicitly in source |

  The original `rpart.h` comment (lines 19–23) documents this distinction from the package author's perspective; the fake honors it exactly. No `R_Free` call in the source will ever receive an arena pointer, and no `ArenaFrame` destruction will ever free a heap block allocated by `CALLOC`.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `fake_arena.hpp` (no separate guide; generated once as the foundational arena header) | Provides `ArenaBlock`, `Arena`, `gArenaStack` (thread-local), `ArenaFrame`, `arena_alloc(bytes)`, and `arena_calloc(n, size)`. `R_alloc` delegates entirely to `arena_alloc`; the fake is meaningless without this header. `fake_arena.hpp` must be included before `fake_Memory.hpp` in the master entry-point header. The canonical definition of `fake_arena.hpp` is given in Invariant 2 of the system prompt. |
| `SEXP.md` — provides `fake_Rinternals.hpp` | Provides the `RError` struct (`struct RError : public std::runtime_error`). The `fake_Memory.hpp` guard block references `RError` for the error-path comment in the `.Call` wrapper and for the `#ifndef FAKE_RERROR_DEFINED` guard that avoids a duplicate-definition error when both headers are included. Also provides `R_NilValue` used in the `.Call` wrapper's error return. |
| `R_Free.md` — provides `fake_RS.hpp` | Provides `R_chk_calloc`, `R_chk_free`, and the `R_Free` macro. Required because `rpart.h` line 26 defines `CALLOC(a,b) R_chk_calloc((size_t)(a), b)`, and many source files that use `ALLOC` also use `CALLOC` and `R_Free` in the same function body. `fake_RS.hpp` must be included in the same master header as `fake_Memory.hpp`. Neither header depends on the other; they can be included in either order after `fake_arena.hpp`. |
