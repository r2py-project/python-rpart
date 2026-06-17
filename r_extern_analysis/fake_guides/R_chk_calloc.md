# Fake Header Implementation Guide: `R_chk_calloc`

---

### 1. Overview of `R_chk_calloc` in R API

`R_chk_calloc` is R's checked, zero-initializing heap allocator declared in `R_ext/RS.h` (included transitively by `R.h`) as:

```c
void *R_chk_calloc(R_SIZE_T nmemb, R_SIZE_T size);
```

It allocates `nmemb * size` bytes of zero-initialized memory from the process heap (via `calloc`), validates that the allocation succeeded, and — in the real R runtime — calls `R_Suicide` (an unrecoverable fatal abort) if `calloc` returns `NULL`. Unlike `R_alloc` (which allocates from R's GC-managed arena and is freed automatically at `.Call` return), memory from `R_chk_calloc` persists across sub-function calls until explicitly released by a paired `R_chk_free` call (exposed to package source through the `R_Free` macro). In rpart, `R_chk_calloc` is used exclusively via the `CALLOC(a, b)` macro defined in `rpart.h` line 26:

```c
#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)
```

---

### 2. Contextual Usage Analysis

**Definition site.**

| File | Line | Context |
|---|---|---|
| `rpart.h` | 26 | `#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)` — the only site where `R_chk_calloc` is named directly in the package source |
| `rpart.h` | 19–23 | Comment: "Memory defined with R_alloc is removed automatically. That with CALLOC I have to remove myself." |
| `rpart.h` | 25 | `#define ALLOC(a,b) R_alloc(a,b)` — the arena-backed counterpart; never freed with `R_Free` |

**Actual call sites (all via `CALLOC`).**

All calls in the package source are of the form `(TargetType *) CALLOC(nmemb, sizeof(element))` or `(TargetType *) CALLOC(1, struct_size)`. Unlike `ALLOC`/`R_alloc` (arena), `CALLOC`/`R_chk_calloc` allocations are intended to persist across sub-calls and must be freed explicitly.

| File | Line | Target type | Expression | Purpose |
|---|---|---|---|---|
| `xval.c` | 58 | `double *` | `CALLOC(3 * rp.num_unique_cp, sizeof(double))` | Scratch buffer `xtemp` (shared with `xpred` and `cp` interior pointers) |
| `xval.c` | 61 | `int *` | `CALLOC(rp.n, sizeof(int))` | Scratch integer array `savew` for saving `rp.which` |
| `xval.c` | 134 | `pNode` | `CALLOC(1, nodesize)` | Root node of a per-fold cross-validation tree (`xtree`) |
| `partition.c` | 98 | `pNode` | `CALLOC(1, nodesize)` | Left child node allocated during recursive tree partitioning |
| `partition.c` | 113 | `pNode` | `CALLOC(1, nodesize)` | Right child node allocated during recursive tree partitioning |
| `insert_split.c` | 25 | `pSplit` | `CALLOC(1, splitsize)` | First split entry in an empty list |
| `insert_split.c` | 37 | `pSplit` | `CALLOC(1, splitsize)` | Replacement split after `R_Free(s3)` when `ncat > 1` |
| `insert_split.c` | 65 | `pSplit` | `CALLOC(1, splitsize)` | Replacement split after `R_Free(s4)` for list-full case |
| `insert_split.c` | 74 | `pSplit` | `CALLOC(1, splitsize)` | New split appended to list when list is not yet full |

**Official signature.**

The `R_ext/RS.h` header was not found at `/home/users/ycai37/.conda/envs/r-to-python/lib/R/include/R_ext/RS.h` in this installation. Based on the CRAN source for R and the `R_Free.md` guide (which documents the paired deallocation counterpart), the signature is:

```c
void *R_chk_calloc(R_SIZE_T nmemb, R_SIZE_T size);
```

where `R_SIZE_T` resolves to `size_t`. The first argument is the element count and the second is the element size in bytes. The return value is a `void *` to a zero-initialized heap block; callers cast to the target type.

Note: the `CALLOC(a, b)` macro in `rpart.h` casts the first argument to `(size_t)` before passing it: `R_chk_calloc((size_t)(a), b)`. This matches `R_SIZE_T`; the second argument `b` is always a `sizeof()` expression (which is already `size_t`).

**C types of all arguments and return values observed.**

| Call-site argument `a` (nmemb) | Call-site argument `b` (size) | Cast applied to return | Struct/element |
|---|---|---|---|
| `3 * rp.num_unique_cp` (`int` expr) | `sizeof(double)` | `(double *)` | Flat double array |
| `rp.n` (`int`) | `sizeof(int)` | `(int *)` | Flat integer array |
| `1` | `nodesize` (`int` var = `sizeof(Node)+...`) | `(pNode)` = `(Node *)` | `Node` struct from `node.h` |
| `1` | `splitsize` (`int` var = `sizeof(Split)+...`) | `(pSplit)` = `(Split *)` | `Split` struct from `node.h` |

**Co-occurring R API items.**

All `CALLOC` call sites in rpart co-occur with:

- `R_Free(ptr)` — the mandatory deallocation counterpart (documented in `R_Free.md`). Every `CALLOC` block is eventually freed either directly (`xval.c:178-179`) or via `free_tree` / `free_split` recursion (`free_tree.c:13,29`).
- `ALLOC(a,b)` — the arena-backed allocator used in the same source files for scratch arrays that do not need to persist. The two allocators are completely independent; `R_Free` must never be called on an `ALLOC`-obtained pointer.
- `ArenaFrame` — must be declared at each `.Call` entry-point wrapper so that `ALLOC`-allocated scratch memory is freed at `.Call` exit. `CALLOC` memory is not governed by `ArenaFrame`.

**Distinct implementation patterns.**

All nine call sites share a single underlying fake strategy: `std::calloc` on the heap, throwing `RError` on failure. Two structural sub-patterns exist based on what is allocated:

| Pattern | Call sites | Description |
|---|---|---|
| P1: Zero-initialized flat array | `xval.c:58`, `xval.c:61` | Allocate a contiguous array of primitive elements (`double`, `int`); freed by `R_Free` at function exit |
| P2: Zero-initialized struct block | `xval.c:134`, `partition.c:98`, `partition.c:113`, `insert_split.c:25,37,65,74` | Allocate exactly 1 block of `nodesize` or `splitsize` bytes for a `Node` or `Split` struct; freed recursively by `free_tree` / `free_split` |

Both patterns share the identical fake implementation. The distinction is noted only for contextual clarity.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`R_chk_calloc` allocates from the **heap** (not the arena). This is the critical design distinction from `R_alloc`. The `R_Free.md` guide documents this in full: memory from `CALLOC` must persist across multiple sub-function calls (e.g., `Split` nodes built in `insert_split.c` and later freed in `free_tree.c`), so it cannot live in an arena frame that is destroyed at `.Call` exit. The fake must use `std::calloc` and not `arena_calloc`.

**Chosen mechanism.**

```cpp
inline void *R_chk_calloc(std::size_t nmemb, std::size_t size) {
    if (nmemb == 0 || size == 0) return nullptr;
    void *p = std::calloc(nmemb, size);
    if (!p) throw RError("R_chk_calloc: out of memory");
    return p;
}
```

This satisfies all three invariants:

- **Invariant 1** (C++ error/warning): the real `R_chk_calloc` calls `R_Suicide` (a fatal `longjmp`-based abort) on failure. The fake replaces this with `throw RError(...)`, which is a catchable C++ exception. The `.Call` boundary `try/catch` block in the Python interop wrapper catches `RError` and translates it to a Python exception. Under no circumstances is `abort()`, `longjmp`, or `R_Suicide` used.
- **Invariant 2** (arena-based memory management): `R_chk_calloc` deliberately does NOT use the arena. The `R_Free.md` guide establishes that `CALLOC`-allocated memory is heap-managed and freed explicitly. The arena (from `fake_arena.hpp`) is exclusively for `R_alloc`/`ALLOC` memory. Using `arena_calloc` here would be incorrect because the arena frame is destroyed at `.Call` exit while `Split` and `Node` blocks must survive multiple nested function calls within the same `.Call` invocation.
- **Invariant 3** (R Interpreter Items): not applicable. `R_chk_calloc` is a pure memory function.

**Why heap (std::calloc), not arena.**

The `rpart.h` comment (lines 19–23) is definitive:

> "Memory defined with R_alloc is removed automatically. That with CALLOC I have to remove myself."

`CALLOC`-allocated blocks (particularly `Node` and `Split` structs) are built up incrementally during recursive tree construction (`partition.c`, `insert_split.c`) and torn down by `free_tree`/`free_split` at the end of the cross-validation fold or at `.Call` return. Their lifetimes are shorter than one `.Call` invocation but longer than any single function call — exactly the profile that requires heap allocation and explicit `R_Free`.

**ArenaFrame interaction.**

The `ArenaFrame` guard at each `.Call` entry-point wrapper manages only `ALLOC`/`R_alloc` memory. It does not interact with `CALLOC`/`R_chk_calloc` memory at all. However, the `ArenaFrame` must still be declared at the entry point because the same functions that call `CALLOC` also call `ALLOC`. The two allocators coexist without interference.

**`CALLOC` macro preservation.**

The `#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)` at `rpart.h:26` does not need to be replicated in the fake header — it lives in `rpart.h`, which the original source files include unchanged. The fake header only needs to provide the `R_chk_calloc` function definition. The macro then expands correctly to the fake inline function.

**`#define` aliases from `R_ext/RS.h` that must be preserved.**

The real `RS.h` defines several macros that depend on `R_chk_calloc`. All of these must appear in the fake `RS.h` replacement so that the header-inclusion chain compiles without errors. The full set (taken from the `R_Free.md` guide) is:

```c
#define R_Calloc(n, t)    ((t *) R_chk_calloc( (R_SIZE_T) (n), sizeof(t) ))
#define CallocCharBuf(n)  ((char *) R_chk_calloc(((R_SIZE_T)(n)) + 1, sizeof(char)))
```

The rpart source files use `CALLOC` from `rpart.h` rather than `R_Calloc` directly, but these macros must still be defined in `fake_RS.hpp` for completeness.

---

### 4. Fake Implementation Examples

#### Pattern: Macro Definition Site — CALLOC Expanding to R_chk_calloc

- **Locations:** `rpart.h:26`

- **Original R API Usage:**

```c
/* rpart.h:26 — the only site where R_chk_calloc is named directly */
#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)

/* Companion macro on rpart.h:25 — arena-backed, distinct allocator */
#define ALLOC(a,b)  R_alloc(a,b)
```

- **C++ Fake Implementation:**

```cpp
// fake_RS.hpp  (excerpt — the R_chk_calloc entry)
// Full fake_RS.hpp is documented in R_Free.md; this guide documents
// the R_chk_calloc function specifically.
//
// Include order: include after fake_arena.hpp and fake_Rinternals.hpp
// (or fake_error.hpp) so that RError is already defined.

#pragma once
#ifndef FAKE_RS_H
#define FAKE_RS_H

#include <cstdlib>    // std::calloc, std::realloc, std::free
#include <cstring>    // std::memcpy, std::memset
#include <cstddef>    // std::size_t
#include <stdexcept>  // std::runtime_error

// RError guard — may already be defined by fake_Rinternals.hpp or fake_error.hpp.
#ifndef FAKE_RERROR_DEFINED
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};
#define FAKE_RERROR_DEFINED 1
#endif

// -----------------------------------------------------------------------
// R_chk_calloc — zero-initialized heap allocation.
//
// Official signature (R_ext/RS.h):
//   void *R_chk_calloc(R_SIZE_T nmemb, R_SIZE_T size);
//
// Behavior: allocates nmemb*size zero-initialized bytes from the process
// heap via std::calloc. On failure throws RError (Invariant 1) instead of
// calling R_Suicide / longjmp.
//
// IMPORTANT: this allocates from the HEAP, not the arena (fake_arena.hpp).
// Memory allocated here must be freed explicitly with R_Free / R_chk_free.
// It is NOT freed by ArenaFrame destruction.
//
// The CALLOC(a,b) macro in rpart.h expands to:
//   R_chk_calloc((size_t)(a), b)
// No change to rpart.h is needed; the macro resolves to this fake inline
// function.
// -----------------------------------------------------------------------
inline void *R_chk_calloc(std::size_t nmemb, std::size_t size) {
    if (nmemb == 0 || size == 0) return nullptr;
    void *p = std::calloc(nmemb, size);
    if (!p) throw RError("R_chk_calloc: out of memory");
    return p;
}

// -----------------------------------------------------------------------
// R_chk_realloc — heap reallocation.
// Replaces R's checked realloc. On failure throws RError (Invariant 1).
// Not called directly in rpart source, but required for R_Realloc macro.
// -----------------------------------------------------------------------
inline void *R_chk_realloc(void *ptr, std::size_t size) {
    if (size == 0) { std::free(ptr); return nullptr; }
    void *p = std::realloc(ptr, size);
    if (!p) throw RError("R_chk_realloc: out of memory");
    return p;
}

// -----------------------------------------------------------------------
// R_chk_free — heap deallocation.
// Replaces R's checked free. Accepts nullptr safely (std::free contract).
// Not called directly in rpart source — called through the R_Free macro.
// -----------------------------------------------------------------------
inline void R_chk_free(void *ptr) {
    std::free(ptr);
}

// -----------------------------------------------------------------------
// R_chk_memcpy / R_chk_memset — checked buffer utilities.
// -----------------------------------------------------------------------
inline void *R_chk_memcpy(void *dest, const void *src, std::size_t n) {
    return std::memcpy(dest, src, n);
}
inline void *R_chk_memset(void *dest, int c, std::size_t n) {
    return std::memset(dest, c, n);
}

// -----------------------------------------------------------------------
// R_Free — the primary deallocation macro used by rpart source.
// Documented in detail in R_Free.md. Listed here for completeness.
//
// WHY A MACRO (NOT inline function):
//   The original source writes:  R_Free(spl);
//   After this call, spl must be nullptr in the caller's scope.
//   The real macro achieves this via the comma operator: (p) = NULL.
//   An inline function receives the pointer by value and cannot null
//   the caller's variable.
// -----------------------------------------------------------------------
#define R_Free(p)  (R_chk_free( (void *)(p) ), (p) = nullptr)

// -----------------------------------------------------------------------
// R_Calloc / R_Realloc — typed allocation macros (from RS.h).
// rpart source uses CALLOC from rpart.h instead, but these must be
// defined so the header chain compiles without errors.
// -----------------------------------------------------------------------
#define R_Calloc(n, t)      ((t *) R_chk_calloc( (std::size_t)(n), sizeof(t) ))
#define R_Realloc(p, n, t)  ((t *) R_chk_realloc( (void *)(p), \
                             (std::size_t)((n) * sizeof(t)) ))

// -----------------------------------------------------------------------
// Memcpy / Memzero / CallocCharBuf — utility macros from RS.h.
// -----------------------------------------------------------------------
#define Memcpy(p, q, n)     R_chk_memcpy((p), (q), (std::size_t)(n) * sizeof(*(p)))
#define Memzero(p, n)       R_chk_memset((p), 0, (std::size_t)(n) * sizeof(*(p)))
#define CallocCharBuf(n)    ((char *) R_chk_calloc(((std::size_t)(n)) + 1, sizeof(char)))

#endif // FAKE_RS_H
```

- **Arena / Memory Notes:**

  All memory allocated by `R_chk_calloc` (via `CALLOC`) lives on the **heap** and must be freed explicitly with `R_Free` / `R_chk_free`. It is not governed by `ArenaFrame` or the `gArenaStack` arena.

  The `ArenaFrame` guard at the `.Call` entry-point wrapper still must be declared for the `ALLOC`/`R_alloc` scratch memory used in the same functions. However, the `ArenaFrame` destructor only frees arena blocks — it does not touch any `CALLOC`-allocated block.

  Representative `.Call` boundary wrapper showing the coexistence of both allocators:

  ```cpp
  // Example: rpart entry-point wrapper
  extern "C" SEXP rpart_wrapper(
          SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
          SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
          SEXP wt2, SEXP ny2, SEXP cost2) {
      ArenaFrame _frame;  // governs ALLOC/R_alloc memory only
      try {
          return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                       ymat2, xmat2, wt2, ny2, cost2);
          // On normal return:
          //   - _frame destructs: all ALLOC'd arena blocks freed
          //   - All CALLOC'd Node/Split blocks have been freed by
          //     free_tree()/free_split() calls inside xval()
          //   - xval()'s xtemp and savew freed by R_Free at xval.c:178-179
      } catch (const RError &e) {
          // _frame destructs: ALLOC blocks freed
          // Any CALLOC blocks not yet freed by R_Free will leak on this path.
          // In practice RError is thrown only by R_chk_calloc (OOM) or
          // error() (bad inputs), so a leak here is acceptable.
          set_python_error(e.what());
          return R_NilValue;
      } catch (const std::bad_alloc &) {
          set_python_error("R_chk_calloc: out of memory");
          return R_NilValue;
      }
  }
  ```

  If `R_chk_calloc` is called before the first `ArenaFrame` has been pushed (i.e., from outside any `.Call` wrapper), `R_chk_calloc` still functions correctly because it does not interact with `gArenaStack` at all.

- **Explanation:**

  The `#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)` at `rpart.h:26` is preserved in the original source file without any modification. The fake provides the `R_chk_calloc` inline function in `fake_RS.hpp`. When the compiler processes a source file that writes `(pNode) CALLOC(1, nodesize)`, the preprocessor expands it to `(pNode) R_chk_calloc((size_t)(1), nodesize)`, which resolves to the fake inline that calls `std::calloc(1, nodesize)` and returns a zero-initialized heap block of `nodesize` bytes. The `(pNode)` cast in the source then converts the `void *` to `Node *` — exactly as in the original R runtime.

  The key distinction preserved by the fake:

  | Macro | Expands to | Fake implementation | Freed by |
  |---|---|---|---|
  | `ALLOC(a,b)` | `R_alloc(a,b)` | `arena_alloc(a*b)` | `ArenaFrame` destructor at `.Call` exit |
  | `CALLOC(a,b)` | `R_chk_calloc((size_t)(a), b)` | `std::calloc(a, b)` — heap | `R_Free(ptr)` called explicitly in source |

  No source file in rpart passes a `CALLOC` pointer to `R_alloc` or an `ALLOC` pointer to `R_Free`. The original code maintains this invariant, and the fake preserves it exactly.

---

#### Pattern P1: Zero-Initialized Flat Array Allocation

- **Locations:** `xval.c:58`, `xval.c:61`

- **Original R API Usage:**

```c
/* xval.c:58-63 — flat array allocations at xval() entry */
double *xtemp, *xpred;
int    *savew;
double *cp;

xtemp = (double *) CALLOC(3 * rp.num_unique_cp, sizeof(double));
xpred = xtemp + rp.num_unique_cp;   /* interior pointer into xtemp block */
cp    = xpred + rp.num_unique_cp;   /* interior pointer into xtemp block */
savew = (int *) CALLOC(rp.n, sizeof(int));

/* ... cross-validation loop ... */

/* xval.c:178-179 — explicit cleanup at xval() exit */
R_Free(savew);   /* std::free(savew); savew = nullptr */
R_Free(xtemp);   /* std::free(xtemp); xtemp = nullptr */
/* xpred and cp are interior pointers; they become dangling but are
   not accessed after the R_Free(xtemp) call */
```

- **C++ Fake Implementation:**

  No additional code beyond the `fake_RS.hpp` shown above is required. The `CALLOC` macro expands to `R_chk_calloc`, which calls `std::calloc`. `R_Free` calls `std::free` and nulls the pointer. The two interior pointers `xpred` and `cp` are arithmetic offsets into the `xtemp` block; `R_Free(xtemp)` frees the entire block. This is identical behavior to the original R runtime.

- **Arena / Memory Notes:**

  `xtemp` and `savew` are heap blocks. They persist for the full duration of `xval()` and are freed explicitly at lines 178–179. The `ArenaFrame` at the enclosing `.Call` wrapper (for `rpart()`, which calls `xval()`) does not free these blocks. On an error exit (e.g., if `R_chk_calloc` throws `RError` during a subsequent allocation inside the cross-validation loop), `xtemp` and `savew` will leak. This is acceptable for the error path because the process is about to signal a Python exception.

- **Explanation:**

  `(double *) CALLOC(3 * rp.num_unique_cp, sizeof(double))` expands to `(double *) R_chk_calloc((size_t)(3 * rp.num_unique_cp), sizeof(double))`. The fake inline calls `std::calloc(n, sizeof(double))`, which returns zero-initialized heap memory. The `(double *)` cast converts the `void *` return. Because the block is zero-initialized, all three sub-regions (`xtemp`, `xpred`, `cp`) start at 0.0, matching the behavior of the real `R_chk_calloc`.

---

#### Pattern P2: Zero-Initialized Struct Block Allocation

- **Locations:** `xval.c:134`, `partition.c:98`, `partition.c:113`, `insert_split.c:25`, `insert_split.c:37`, `insert_split.c:65`, `insert_split.c:74`

- **Original R API Usage:**

```c
/* xval.c:134 — root node for a per-fold cross-validation tree */
xtree = (pNode) CALLOC(1, nodesize);
xtree->num_obs = k;
/* ... build and traverse tree ... */
free_tree(xtree, 1);   /* recursive CALLOC cleanup via free_tree/free_split */

/* partition.c:98,113 — child nodes during recursive tree partitioning */
me->leftson  = (pNode) CALLOC(1, nodesize);
me->rightson = (pNode) CALLOC(1, nodesize);
/* freed later by free_tree(root, 1) called from xval.c:167 or rpart.c cleanup */

/* insert_split.c:25 — first split in an empty list */
s3 = (pSplit) CALLOC(1, splitsize);
s3->nextsplit = NULL;
*listhead = s3;

/* insert_split.c:36-37 — free old split, allocate new one at different size */
R_Free(s3);
s3 = (pSplit) CALLOC(1, splitsize);
s3->nextsplit = NULL;
*listhead = s3;

/* insert_split.c:65,74 — add or replace split in a full/non-full list */
R_Free(s4);
s4 = (pSplit) CALLOC(1, splitsize);
```

- **C++ Fake Implementation:**

  No additional code beyond the `fake_RS.hpp` shown in the first pattern is required. `CALLOC(1, nodesize)` expands to `R_chk_calloc((size_t)(1), nodesize)`, which calls `std::calloc(1, nodesize)`. The returned block is zero-initialized: all pointer fields (`leftson`, `rightson`, `primary`, `surrogate`, `nextsplit`) start as `NULL`/`nullptr`, and all numeric fields start at 0. This matches R's real `R_chk_calloc` behavior exactly.

  The `ArenaFrame` guard at the `.Call` entry-point wrapper must still be declared for the `ALLOC`-based scratch memory (sorts matrix, etc.), but it has no effect on these `CALLOC` blocks:

  ```cpp
  extern "C" SEXP rpart_wrapper(/* ... SEXP params ... */) {
      ArenaFrame _frame;   // for ALLOC/R_alloc scratch arrays only
      try {
          return rpart(/* ... */);
          // Node and Split blocks freed by free_tree/free_split before return
          // _frame destructs: arena blocks freed
      } catch (const RError &e) {
          set_python_error(e.what());
          return R_NilValue;
      }
  }
  ```

- **Arena / Memory Notes:**

  All `Node` and `Split` struct blocks are heap-allocated via `std::calloc`. Their lifetimes are:

  - `partition.c` left/right child nodes: allocated during recursive `partition()` calls; freed when `free_tree(root, 1)` is called (from `xval.c:167` for cross-validation trees, or from the rpart cleanup path for the main tree).
  - `insert_split.c` split nodes: allocated by `insert_split()` and stored in linked lists hanging off tree nodes; freed by `free_split()` which is called by `free_tree()`.
  - `xval.c:134` xtree root: allocated at loop entry (`xval.c:134`) and explicitly freed at loop exit (`xval.c:167`) via `free_tree(xtree, 1)`.

  The zero-initialization of `std::calloc` is critical: because `nodesize` may be larger than `sizeof(Node)` (it accounts for a variable-length `response_est` field), and `splitsize` accounts for a variable-length `csplit` array, zero-initializing the entire block ensures that fields beyond the fixed-size struct portion start at zero — matching the behavior of `R_chk_calloc` in the real R runtime.

- **Explanation:**

  `nodesize` is computed at `rpart.c` entry as:

  ```c
  nodesize = sizeof(Node) + (rp.num_resp - 1) * sizeof(double);
  ```

  and `splitsize` in `insert_split.c:20` as:

  ```c
  int splitsize = sizeof(Split) + (ncat - 20) * sizeof(int);
  ```

  Both are variable-length struct idioms. `std::calloc(1, nodesize)` allocates and zeros the entire block. The cast `(pNode)` / `(pSplit)` interprets the block as the struct. Fields beyond the declared struct size (the variable-length tail) start at zero because of the zero-initialization. No modification to the source files is needed.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `fake_arena.hpp` (no separate guide; generated once as the foundational arena header per Invariant 2) | Provides `ArenaBlock`, `Arena`, `gArenaStack` (thread-local), `ArenaFrame`, `arena_alloc`, and `arena_calloc`. `R_chk_calloc` itself does NOT call any arena functions, but the same `.Call` entry-point wrappers that govern `CALLOC` memory also must declare `ArenaFrame` for the `ALLOC`/`R_alloc` scratch memory used in the same code paths. `fake_arena.hpp` must be included before `fake_RS.hpp` in the master entry-point header. |
| `SEXP.md` — provides `fake_Rinternals.hpp` | Provides the `RError` struct (`struct RError : public std::runtime_error`). The fake `R_chk_calloc` throws `RError("R_chk_calloc: out of memory")` on allocation failure (Invariant 1). `RError` must be defined before `fake_RS.hpp` is processed. `fake_Rinternals.hpp` also defines `R_NilValue` used in the `.Call` boundary wrapper's error return. |
| `R_alloc.md` — provides `fake_Memory.hpp` | Documents the `R_alloc` arena allocator and the `ALLOC(a,b)` macro. Required for understanding the allocator duality: `ALLOC` (arena, freed by `ArenaFrame`) versus `CALLOC` (heap, freed by `R_Free`). `fake_Memory.hpp` must be included in the same master header as `fake_RS.hpp`, after `fake_arena.hpp`. |
| `R_Free.md` — provides `fake_RS.hpp` (shared file) | `R_chk_calloc` and `R_Free` / `R_chk_free` are defined in the same `fake_RS.hpp` file. The `R_Free.md` guide documents the deallocation side; this guide documents the allocation side. Both must be consistent: `R_chk_calloc` uses `std::calloc` and `R_chk_free` uses `std::free`. The implementation in this guide is the authoritative definition of `R_chk_calloc` within `fake_RS.hpp`. |
