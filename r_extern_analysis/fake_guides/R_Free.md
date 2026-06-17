# Fake Header Implementation Guide: `R_Free`

---

### 1. Overview of `R_Free` in R API

`R_Free` is a preprocessor macro defined in `R_ext/RS.h` as:

```c
#define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = NULL)
```

It is the paired deallocation counterpart to `R_Calloc` / `R_chk_calloc`. It calls `R_chk_free` (R's checked wrapper around `free`) to release heap memory that was explicitly allocated by `CALLOC` (`R_chk_calloc`) or `R_Calloc`, and then sets the pointer to `NULL` using the C comma operator. `R_Free` is strictly a heap-deallocation tool: it operates on memory that was obtained through `R_chk_calloc`/`R_chk_realloc`, not through `R_alloc` (which is arena-managed) or through SEXP allocation functions (`allocVector`, `allocMatrix`). In rpart, the canonical comment in `rpart.h` (lines 19-23) explicitly distinguishes the two families: memory from `ALLOC` (`R_alloc`) is freed automatically by R at `.Call` return, while memory from `CALLOC` (`R_chk_calloc`) must be freed manually with `R_Free`.

---

### 2. Contextual Usage Analysis

**Source files and lines examined.**

| File | Line | Context |
|---|---|---|
| `free_tree.c` | 13 | `R_Free(spl);` inside `free_split()` — frees a `pSplit` (pointer to `Split` struct) that was allocated by `CALLOC` in `insert_split.c` |
| `free_tree.c` | 29 | `R_Free(node);` inside `free_tree()` when `freenode == 1` — frees a `pNode` (pointer to `Node` struct) that was allocated by `CALLOC` in `xval.c:134` or `partition.c:98,113` |
| `insert_split.c` | 36 | `R_Free(s3);` — frees a `pSplit` that is being replaced by a newly allocated `CALLOC` block of a different size |
| `insert_split.c` | 63 | `R_Free(s4);` — frees the last element of the split list (`pSplit`) before reallocating it with `CALLOC` at a new size |
| `xval.c` | 178 | `R_Free(savew);` — frees an `int *` scratch array allocated at line 61 by `CALLOC(rp.n, sizeof(int))` |
| `xval.c` | 179 | `R_Free(xtemp);` — frees a `double *` scratch array allocated at line 58 by `CALLOC(3 * rp.num_unique_cp, sizeof(double))` |

**C types of arguments.**

`R_Free` is called with lvalue pointer arguments of three distinct C types:

| Usage | Pointer type | Struct / element |
|---|---|---|
| `R_Free(spl)` | `pSplit` (= `Split *`) | `Split` struct from `node.h` |
| `R_Free(node)` | `pNode` (= `Node *`) | `Node` struct from `node.h` |
| `R_Free(s3)`, `R_Free(s4)` | `pSplit` | `Split` struct |
| `R_Free(savew)` | `int *` | Flat integer array |
| `R_Free(xtemp)` | `double *` | Flat double array |

All arguments are lvalues (local or parameter pointer variables), which is required because the macro's `, (p) = NULL` assignment modifies the pointer variable in place.

**Allocation counterparts observed.**

Every `R_Free` call site in rpart is paired with a `CALLOC` allocation call (which maps to `R_chk_calloc`). The complete pairing in the three files is:

| `CALLOC` site | `R_Free` site |
|---|---|
| `insert_split.c:25` — `s3 = (pSplit) CALLOC(1, splitsize)` | `insert_split.c:36` — `R_Free(s3)` (before realloc) |
| `insert_split.c:37` — `s3 = (pSplit) CALLOC(1, splitsize)` | freed by `free_tree` -> `free_split` via `free_tree.c:13` |
| `insert_split.c:65` — `s4 = (pSplit) CALLOC(1, splitsize)` (after `R_Free(s4)`) | freed by `free_tree` -> `free_split` |
| `insert_split.c:74` — `s4 = (pSplit) CALLOC(1, splitsize)` | freed by `free_tree` -> `free_split` |
| `xval.c:58` — `xtemp = (double *) CALLOC(3 * rp.num_unique_cp, sizeof(double))` | `xval.c:179` — `R_Free(xtemp)` |
| `xval.c:61` — `savew = (int *) CALLOC(rp.n, sizeof(int))` | `xval.c:178` — `R_Free(savew)` |
| `xval.c:134` — `xtree = (pNode) CALLOC(1, nodesize)` | `xval.c:167` — `free_tree(xtree, 1)` -> `free_tree.c:29` |
| `partition.c:98,113` — `CALLOC(1, nodesize)` for left/right sons | `free_tree.c:29` — `R_Free(node)` recursively |

**Co-occurring R API items.**

- `CALLOC` — the mandatory allocation counterpart; expands to `R_chk_calloc((size_t)(a), b)`.
- `free_tree(node, freenode)` — the tree traversal function that calls `free_split` and `R_Free(node)` recursively.
- `free_split(spl)` — the recursive split-list traversal that calls `R_Free(spl)`.
- `ALLOC` — used in the same functions (`xval.c`, `insert_split.c`) but for scratch memory that is arena-managed and is never freed with `R_Free`. The two allocators are completely distinct.

**Distinct implementation patterns.**

All six CSV rows belong to a single underlying pattern: freeing heap memory that was allocated by `CALLOC` and setting the pointer to NULL. Two minor sub-patterns exist based on what is freed:

| Pattern | CSV rows | Description |
|---|---|---|
| Pattern A: Free and null a struct pointer | `free_tree.c:13`, `free_tree.c:29`, `insert_split.c:36`, `insert_split.c:63` | `R_Free` applied to a `pSplit` or `pNode` pointer; the pointer variable is set to NULL by the macro |
| Pattern B: Free and null a flat array pointer | `xval.c:178`, `xval.c:179` | `R_Free` applied to `int *` or `double *` scratch arrays; pointer variable is set to NULL |

Both patterns share the identical fake strategy: `R_Free(p)` expands to `(std::free((void*)(p)), (p) = nullptr)`.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`R_Free` is the deallocation half of the `R_Calloc` / `R_Free` heap pair. It calls `R_chk_free` (which ultimately calls `free`) and nulls the pointer. In the fake runtime, `R_chk_calloc` is reimplemented to call `std::calloc` (NOT the arena), so `R_chk_free` must call `std::free` on the same heap block.

**Chosen mechanism.**

The fake implementation mirrors the real macro exactly, substituting `std::free` for `R_chk_free`:

```c
#define R_Free(p)  (std::free((void *)(p)), (p) = nullptr)
```

This preserves three observable behaviors of the original macro:

1. **The deallocation**: `std::free((void *)(p))` releases the heap block that `std::calloc` (inside the fake `R_chk_calloc`) allocated.
2. **The null assignment**: `(p) = nullptr` sets the pointer variable to null, which is required because `R_Free` is a macro applied to an lvalue. This means the fake must remain a macro (not an inline function), because an inline function receives the pointer by value and cannot null the caller's variable.
3. **The comma-expression semantics**: The entire `(expr1, expr2)` evaluates as a void expression, identical to a void function call at the call site.

**Why R_Free must not touch the arena.**

The arena (from `fake_arena.hpp`, Invariant 2) governs memory allocated by `R_alloc` / `ALLOC`. In rpart, `ALLOC` is `#define ALLOC(a,b) R_alloc(a,b)` (rpart.h line 25). This arena memory is freed in bulk when the `ArenaFrame` destructs at `.Call` exit — the individual allocations are never freed by `R_chk_free` or `R_Free`.

`CALLOC` is `#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)` (rpart.h line 26). `R_chk_calloc` allocates heap memory (not arena memory). This memory persists across multiple `.Call`-internal function calls (e.g., `Split` nodes built by `insert_split.c` and later freed by `free_tree.c`). It must be freed with `R_Free` before the `.Call` wrapper returns, otherwise it leaks. The `ArenaFrame` destructor does NOT free it.

The two allocators are completely orthogonal:

| Allocator | Where memory lives | How it is freed |
|---|---|---|
| `ALLOC` / `R_alloc` | Arena (`gArenaStack`) | Automatically at `ArenaFrame` destruction |
| `CALLOC` / `R_chk_calloc` | Heap (`std::calloc`) | Explicitly by `R_Free` |

**The `CALLOC` fake must also be documented here** because `R_Free` is meaningless without its allocation counterpart. The fake `R_chk_calloc` is:

```cpp
inline void *R_chk_calloc(std::size_t nmemb, std::size_t size) {
    void *p = std::calloc(nmemb, size);
    if (!p) throw RError("R_chk_calloc: out of memory");
    return p;
}
```

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `R_Free` itself, as it never fails. `R_chk_calloc` (the paired allocator) throws `RError` on allocation failure rather than calling `Rf_error`.
- Invariant 2 (arena memory): explicitly inapplicable. `R_Free` must call `std::free`, not any arena function. The arena is exclusively for `R_alloc`-family memory.
- Invariant 3 (R Interpreter Items): not applicable. `R_Free` is a pure heap operation.

**`#define` aliases from `R_ext/RS.h` that must be preserved.**

The real `RS.h` defines:

```c
#define R_Free(p)        (R_chk_free( (void *)(p) ), (p) = NULL)
#define R_Calloc(n, t)   (t *) R_chk_calloc( (R_SIZE_T) (n), sizeof(t) )
#define R_Realloc(p,n,t) (t *) R_chk_realloc( (void *)(p), (R_SIZE_T)((n) * sizeof(t)) )
#define Memcpy(p,q,n)    R_chk_memcpy( p, q, (R_SIZE_T)(n) * sizeof(*p) )
#define Memzero(p,n)     R_chk_memset(p, 0, (R_SIZE_T)(n) * sizeof(*p))
#define CallocCharBuf(n) (char *) R_chk_calloc(((R_SIZE_T)(n))+1, sizeof(char))
```

In rpart, the source files do not call `R_Calloc` or `R_Realloc` directly — they use the internal `CALLOC` and `ALLOC` macros from `rpart.h`. However, `R_Calloc`, `R_Realloc`, `Memcpy`, `Memzero`, and `CallocCharBuf` must still be defined in the fake `RS.h` replacement so that the header-inclusion chain compiles without error.

---

### 4. Fake Implementation Examples

#### Pattern A: Free and Null a Struct Pointer

- **Locations:** `free_tree.c:13`, `free_tree.c:29`, `insert_split.c:36`, `insert_split.c:63`

- **Original R API Usage:**

```c
/* free_tree.c:8-15 — recursive split freeing */
static void
free_split(pSplit spl)
{
    if (spl) {
        free_split(spl->nextsplit);
        R_Free(spl);    /* spl is set to NULL after this call */
    }
}

/* free_tree.c:17-37 — recursive node freeing */
void
free_tree(pNode node, int freenode)
{
    if (node->rightson)
        free_tree(node->rightson, 1);
    if (node->leftson)
        free_tree(node->leftson, 1);
    free_split(node->surrogate);
    free_split(node->primary);
    if (freenode == 1)
        R_Free(node);    /* node is set to NULL after this call */
    else {
        node->primary   = (pSplit) NULL;
        node->surrogate = (pSplit) NULL;
        node->rightson  = (pNode) NULL;
        node->leftson   = (pNode) NULL;
    }
}

/* insert_split.c:30-41 — free before realloc at new size */
if (max < 2) {
    s3 = *listhead;
    if (improve <= s3->improve)
        return NULL;
    if (ncat > 1) {
        R_Free(s3);    /* release old block; s3 set to NULL */
        s3 = (pSplit) CALLOC(1, splitsize);  /* allocate new, larger block */
        s3->nextsplit = NULL;
        *listhead = s3;
    }
    return s3;
}

/* insert_split.c:58-66 — free last-in-list before realloc */
if (nlist == max) {
    if (s2 == 0)
        return NULL;
    if (ncat > 1) {
        R_Free(s4);    /* release s4; s4 set to NULL */
        s4 = (pSplit) CALLOC(1, splitsize);  /* allocate new block */
    }
    ...
}
```

- **C++ Fake Implementation:**

```cpp
// fake_RS.hpp
// Drop-in replacement for R_ext/RS.h.
// Provides: R_chk_calloc, R_chk_realloc, R_chk_free, R_chk_memcpy,
//           R_chk_memset, R_Free, R_Calloc, R_Realloc, Memcpy, Memzero,
//           CallocCharBuf.
//
// Include order: include after fake_arena.hpp (for ArenaFrame) and after
// fake_Rinternals.hpp (for RError).  In practice both are pulled in by
// the fake R.h replacement before this file is needed.

#pragma once
#ifndef FAKE_RS_H
#define FAKE_RS_H

#include <cstdlib>   // std::calloc, std::realloc, std::free, std::malloc
#include <cstring>   // std::memcpy, std::memset
#include <cstddef>   // std::size_t
#include <stdexcept> // std::bad_alloc
// RError must already be defined (from fake_Rinternals.hpp or fake_error.hpp).
// A forward declaration guard is provided below in case the order varies.
#ifndef FAKE_RERROR_DEFINED
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};
#define FAKE_RERROR_DEFINED 1
#endif

// -----------------------------------------------------------------------
// R_chk_calloc — zero-initialized heap allocation.
// Replaces R's checked calloc.  On failure throws RError (Invariant 1).
// This is the backend for CALLOC(a, b) = R_chk_calloc((size_t)(a), b).
//
// IMPORTANT: this allocates from the HEAP, not the arena.
// Memory allocated here must be freed explicitly with R_Free / R_chk_free.
// It is NOT freed by ArenaFrame destruction.
// -----------------------------------------------------------------------
inline void *R_chk_calloc(std::size_t nmemb, std::size_t size) {
    if (nmemb == 0 || size == 0) return nullptr;
    void *p = std::calloc(nmemb, size);
    if (!p) throw RError("R_chk_calloc: out of memory");
    return p;
}

// -----------------------------------------------------------------------
// R_chk_realloc — heap reallocation.
// Replaces R's checked realloc.  On failure throws RError (Invariant 1).
// Not called directly in rpart source, but required by R_Realloc macro.
// -----------------------------------------------------------------------
inline void *R_chk_realloc(void *ptr, std::size_t size) {
    if (size == 0) { std::free(ptr); return nullptr; }
    void *p = std::realloc(ptr, size);
    if (!p) throw RError("R_chk_realloc: out of memory");
    return p;
}

// -----------------------------------------------------------------------
// R_chk_free — heap deallocation.
// Replaces R's checked free.  Accepts nullptr safely (std::free contract).
// NOT called directly in rpart source — called through the R_Free macro.
// -----------------------------------------------------------------------
inline void R_chk_free(void *ptr) {
    std::free(ptr);
}

// -----------------------------------------------------------------------
// R_chk_memcpy — checked memcpy wrapper.
// -----------------------------------------------------------------------
inline void *R_chk_memcpy(void *dest, const void *src, std::size_t n) {
    return std::memcpy(dest, src, n);
}

// -----------------------------------------------------------------------
// R_chk_memset — checked memset wrapper.
// -----------------------------------------------------------------------
inline void *R_chk_memset(void *dest, int c, std::size_t n) {
    return std::memset(dest, c, n);
}

// -----------------------------------------------------------------------
// R_Free — the primary deallocation macro used by rpart source.
//
// Real RS.h definition (line 57):
//   #define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = NULL)
//
// Fake definition (functionally identical, uses nullptr):
//   #define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = nullptr)
//
// WHY IT MUST REMAIN A MACRO:
//   The original source writes:
//       pSplit spl = ...;
//       R_Free(spl);
//   After this call, spl must equal nullptr in the caller's scope.
//   The real macro achieves this via the comma operator: (p) = NULL
//   assigns back to the lvalue 'p'.  An inline function cannot do this
//   because it receives the pointer by value.
//
// WHY std::free AND NOT THE ARENA:
//   CALLOC(a, b) maps to R_chk_calloc(a, b) which calls std::calloc.
//   The arena (gArenaStack) is used only for ALLOC(a,b) = R_alloc(a,b).
//   Calling arena_alloc's reset() on a CALLOC block would be incorrect;
//   calling std::free on an arena block would be a heap corruption.
//   The two allocators are completely independent.
// -----------------------------------------------------------------------
#define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = nullptr)

// -----------------------------------------------------------------------
// R_Calloc / R_Realloc — typed allocation macros.
// Not used directly in rpart source (which uses CALLOC instead), but
// required for completeness so that the header chain compiles.
// -----------------------------------------------------------------------
#define R_Calloc(n, t)    ((t *) R_chk_calloc( (std::size_t)(n), sizeof(t) ))
#define R_Realloc(p, n, t) ((t *) R_chk_realloc( (void *)(p), \
                            (std::size_t)((n) * sizeof(t)) ))

// -----------------------------------------------------------------------
// Memcpy / Memzero / CallocCharBuf — utility macros from RS.h.
// Preserved so that the original source compiles without modification.
// -----------------------------------------------------------------------
#define Memcpy(p, q, n)  R_chk_memcpy((p), (q), (std::size_t)(n) * sizeof(*(p)))
#define Memzero(p, n)    R_chk_memset((p), 0, (std::size_t)(n) * sizeof(*(p)))
#define CallocCharBuf(n) ((char *) R_chk_calloc(((std::size_t)(n)) + 1, sizeof(char)))

#endif // FAKE_RS_H
```

- **Arena / Memory Notes:**

  All pointers passed to `R_Free` in Pattern A are `CALLOC`-allocated heap blocks. The call chain is:

  1. `CALLOC(1, splitsize)` in `insert_split.c` calls `R_chk_calloc(1, splitsize)`, which calls `std::calloc(1, splitsize)`. The returned block is on the heap.
  2. The `Split` struct is populated and the pointer is stored in a linked list (`spl->nextsplit` chain) or in a node (`node->primary`, `node->surrogate`).
  3. At cleanup time, `free_split(spl)` recurses to the end of the list and then calls `R_Free(spl)` on the way back. The macro expands to `(R_chk_free((void*)(spl)), (spl) = nullptr)`, which calls `std::free(spl_block)` and sets the local parameter `spl` to `nullptr`.
  4. Similarly for `pNode` blocks: `free_tree(node, 1)` recurses and calls `R_Free(node)` after freeing both children and all splits.

  The `ArenaFrame` guard placed at the `.Call` entry point (e.g., in the `xval`-containing `.Call` wrapper) does NOT free any of these `CALLOC` blocks. They must all be freed by the explicit `free_tree` / `free_split` / `R_Free` calls that the original source already contains. If a `CALLOC` block escapes `R_Free` (e.g., due to an early error exit), it will leak. The `try/catch` boundary wrapper should call any necessary cleanup before rethrowing or returning `R_NilValue` if this becomes an issue in practice.

  One subtlety: in `insert_split.c:36`, `R_Free(s3)` sets the local `s3` to `nullptr`, and the very next line allocates a new block and assigns it back to `s3`. The null assignment from `R_Free` is immediately overwritten — this is intentional and safe.

- **Explanation:**

  The fake macro `#define R_Free(p) (R_chk_free((void*)(p)), (p) = nullptr)` is a token-for-token replacement for the original `#define R_Free(p) (R_chk_free((void*)(p)), (p) = NULL)` with `NULL` replaced by `nullptr`. In C++ this is identical in effect for pointer types. The `R_chk_free` inline function calls `std::free`, which is the correct deallocator for blocks obtained via `std::calloc` in the fake `R_chk_calloc`. The original source files `free_tree.c` and `insert_split.c` compile without modification because both macros expand to the same syntactic form.

---

#### Pattern B: Free and Null a Flat Array Pointer

- **Locations:** `xval.c:178`, `xval.c:179`

- **Original R API Usage:**

```c
/* xval.c:43-44 — declaration of arrays to be freed */
double *xtemp, *xpred;
int    *savew;

/* xval.c:58-63 — CALLOC allocations at function entry */
xtemp = (double *) CALLOC(3 * rp.num_unique_cp, sizeof(double));
xpred = xtemp + rp.num_unique_cp;       /* xpred and cp are interior pointers */
cp    = xpred + rp.num_unique_cp;       /* into the same xtemp block */
savew = (int *) CALLOC(rp.n, sizeof(int));
for (i = 0; i < rp.n; i++)
    savew[i] = rp.which[i];

/* ... main cross-validation loop (lines 81-168) ... */

/* xval.c:176-179 — explicit cleanup at function exit */
rp.alpha = alphasave;
for (i = 0; i < rp.n; i++)
    rp.which[i] = savew[i];
R_Free(savew);    /* savew set to nullptr after this */
R_Free(xtemp);   /* xtemp set to nullptr after this; xpred and cp also become dangling */
```

- **C++ Fake Implementation:**

```cpp
// No additional fake code beyond fake_RS.hpp above is needed for Pattern B.
// The same R_Free macro handles flat array pointers identically to struct
// pointers: std::free releases the heap block and the pointer is nulled.
//
// The .Call boundary wrapper for the function that calls xval() must
// declare an ArenaFrame for the ALLOC-allocated scratch arrays inside xval.
// However, savew and xtemp are CALLOC-allocated (heap), so they are freed
// by R_Free at xval.c:178-179 — not by the ArenaFrame.
//
// Representative .Call wrapper (for context — xval() is called from
// within rpart(), which has the ArenaFrame at its own wrapper level):
//
//   extern "C" SEXP rpart_wrapper(
//           SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
//           SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
//           SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;   // covers ALLOC() calls in rpart() and xval()
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//       } catch (const RError &e) {
//           // CALLOC-allocated savew and xtemp may be leaked here if
//           // xval() throws before reaching its R_Free calls.
//           // In practice, RError is only thrown by R_chk_calloc (on
//           // OOM) or by error() (on bad inputs), so the leak is
//           // acceptable for the error path.
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// The interior pointers xpred and cp (xval.c:59-60) are arithmetic offsets
// into the xtemp block.  R_Free(xtemp) frees the entire block.  After that
// call, xtemp is nullptr but xpred and cp remain dangling pointers (they
// are not passed to R_Free).  This matches the behavior of the original code
// exactly; neither xpred nor cp is accessed after line 179.
```

- **Arena / Memory Notes:**

  `savew` and `xtemp` are `CALLOC`-allocated heap blocks. They persist for the entire duration of the `xval()` function call (lines 61 and 58 respectively) and are freed at lines 178-179 by `R_Free`. They are not arena memory and are not freed by `ArenaFrame` destruction.

  Note that `xval.c` also uses `CALLOC` for `xtree` at line 134 (`xtree = (pNode) CALLOC(1, nodesize)`), and then frees it via `free_tree(xtree, 1)` at line 167. This `pNode` block, and all the `pSplit` blocks allocated by `insert_split()` during the tree-building loop, are all heap-allocated via `CALLOC` and freed recursively by `free_tree` / `free_split` before `R_Free(savew)` and `R_Free(xtemp)` are reached.

  The `ALLOC`-allocated scratch arrays used inside `xval.c` (e.g., the sorts matrix `rp.sorts` allocated in `rpart.c`) are governed exclusively by the `ArenaFrame` at the `.Call` wrapper level. They must not be passed to `R_Free`.

- **Explanation:**

  The two `R_Free` calls at `xval.c:178-179` use the same macro expansion as Pattern A. The only difference is the pointer type (`int *` and `double *` rather than `pSplit` or `pNode`). The `(p) = nullptr` assignment correctly null-terminates both `savew` and `xtemp` as lvalue pointer variables after `std::free` releases the block. No modification to the source file is needed. The guard condition in `free_split` — `if (spl)` — means that calling `free_split(nullptr)` (which could occur if `R_Free` nulled a pointer that is later passed again) is safe; the same guard pattern is available to callers of `free_tree`.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the complete `fake_Rinternals.hpp` including the `RError` struct (`struct RError : public std::runtime_error`). The fake `R_chk_calloc` throws `RError` on allocation failure (Invariant 1); `RError` must be defined before `fake_RS.hpp` is processed. `fake_Rinternals.hpp` (from `SEXP.md`) also defines `R_NilValue` used in the `.Call` wrapper's error return. |
| `fake_arena.hpp` (canonical definition referenced in `SEXP.md` and Invariant 2) | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required at the `.Call` wrapper level because the same functions that use `CALLOC` / `R_Free` also use `ALLOC` (arena-backed). `R_Free` itself does not call arena functions, but the `ArenaFrame` guard in the wrapper must be declared so that `ALLOC`-allocated scratch memory is freed. `fake_arena.hpp` must be included before `fake_RS.hpp`. |
| `PROTECT.md` | Documents the no-op `PROTECT` / `UNPROTECT` stubs in `fake_Rinternals.hpp`. Not a direct dependency of `R_Free`, but all three source files that use `R_Free` also include `rpart.h` which includes `R.h` and `Rinternals.h`. The full fake header chain must be present and internally consistent. |
| `ISNAN.md` | Documents the `RPARTNA(a) = ISNAN(a)` macro stub. Same reasoning as `PROTECT.md` — transitively included by `rpart.h` in all three source files. |
