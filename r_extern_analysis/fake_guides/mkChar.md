# Fake Header Implementation Guide: `mkChar`

---

### 1. Overview of `mkChar` in R API

`mkChar` is a macro alias defined in `Rinternals.h` as `#define mkChar Rf_mkChar`, where `Rf_mkChar` is declared as `SEXP Rf_mkChar(const char *)` (line 564 of the real `Rinternals.h`). Its role in R's C API is to construct a `CHARSXP` — an internal scalar-string node (type tag `9`) — from a null-terminated C string. The resulting `SEXP` is not a general-purpose string vector; it is R's internal atom for a single string value, intended to be stored as an element of a `STRSXP` string vector via `SET_STRING_ELT`. In the fake runtime, `mkChar` heap-allocates a `SEXPREC` node of type `CHARSXP` whose `data` field holds a `std::malloc`-allocated copy of the input string, and throws `RError` on allocation failure (Invariant 1).

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart.c` | 316–359 | Output-list construction epilogue of `rpart()`; `STRSXP` name vector `rname` is allocated at line 328 and populated with seven `SET_STRING_ELT(rname, i, mkChar("..."))` calls at lines 331–344 |

All seven CSV rows reside in the same function body. The 30-line window (lines 316–359) exposes the complete usage pattern:

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    // line 327
SEXP rname = allocVector(STRSXP, nout);              // line 328
setAttrib(rlist, R_NamesSymbol, rname);              // line 329
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));           // line 331
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));         // line 333
SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));          // line 335
SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));          // line 337
SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));           // line 339
SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));           // line 341
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));      // line 344
}
UNPROTECT(1 + nout);
return rlist;
```

**Argument and return types observed.**

The real `Rinternals.h` declaration at line 564:

```c
SEXP Rf_mkChar(const char *);
#define mkChar Rf_mkChar
```

- Input: `const char *` — a null-terminated string literal in all seven call sites (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`, `"csplit"`).
- Return value: `SEXP` — a heap-allocated `CHARSXP` node whose `data` field holds a copy of the input string.
- The returned `SEXP` is immediately passed as the third argument to `SET_STRING_ELT(rname, i, ...)` and written into slot `i` of the `STRSXP` `rname`.

**Co-occurring R API items in context window.**

| Item | Line(s) | Role |
|---|---|---|
| `allocVector(STRSXP, nout)` | 328 | Allocates the `STRSXP` target `rname`; its `data` field is a `SEXP[nout]` array of `CHARSXP` slots. Documented in `STRSXP.md` and `allocVector.md`. |
| `allocVector(VECSXP, nout)` | 327 | Allocates the output list `rlist`. Documented in `VECSXP.md` and `allocVector.md`. |
| `SET_STRING_ELT(rname, i, v)` | 331, 333, 335, 337, 339, 341, 344 | Writes the `CHARSXP` returned by `mkChar` into slot `i` of `rname`. Documented in `SET_STRING_ELT.md`. |
| `SET_VECTOR_ELT(rlist, i, child)` | 330, 332, 334, 336, 338, 340, 343 | Writes child SEXPs into the `VECSXP` output list `rlist`. Documented in `SET_VECTOR_ELT.md`. |
| `setAttrib(rlist, R_NamesSymbol, rname)` | 329 | Attaches `rname` as the names attribute of `rlist`. A no-op in the fake runtime. Documented in `R_NamesSymbol.md`. |
| `PROTECT` / `UNPROTECT` | 327, 347 | No-ops in the fake runtime. `rname` is not `PROTECT`ed at line 328 (the real code relies on the `setAttrib` call to protect it via `rlist`). Documented in `PROTECT.md` and `UNPROTECT.md`. |

**Distinct implementation patterns.**

There is exactly one structural pattern across all seven CSV rows:

| Pattern | Rows | Description |
|---|---|---|
| P1: Construct `CHARSXP` from a string literal to write into a `STRSXP` slot | `rpart.c:331`, `333`, `335`, `337`, `339`, `341`, `344` | `mkChar("literal")` called as the third argument to `SET_STRING_ELT(rname, i, mkChar("..."))`. Input is always a compile-time string literal; the result is never stored in a variable before being passed to `SET_STRING_ELT`. |

All seven rows share the same fake strategy. There is no second pattern (e.g., `mkChar` called with a runtime string variable, or the `CHARSXP` result stored before use). `mkCharCE`, `mkCharLen`, and `mkCharLenCE` are not used in any rpart source file; their fake stubs are required only for header completeness.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`mkChar` allocates a new `SEXPREC` node of type `CHARSXP` and a separate `char[]` buffer to hold the string contents. Both allocations use `std::malloc` (not the arena). The resulting node is heap-managed and must outlive the `ArenaFrame` frame that governs the enclosing `.Call` invocation, because the `CHARSXP` is embedded into the `rname` `STRSXP`, which is itself part of the function's return value.

**Chosen mechanism.**

The fake `mkChar` (named `Rf_mkChar` as the canonical implementation, with `#define mkChar Rf_mkChar` as the alias) performs the following steps:

1. Calls `std::strlen(str)` to measure the string length.
2. `std::malloc(sizeof(SEXPREC))` to allocate the `SEXPREC` node. Throws `RError` on failure (Invariant 1).
3. Sets `s->type = CHARSXP`, `s->length = len`, `s->nrow = len`, `s->ncol = 1`.
4. `std::malloc(len + 1)` to allocate the null-terminated string buffer. Throws `RError` on failure; frees the node before throwing to avoid a partial leak.
5. `std::strcpy(s->data, str)` to copy the string.
6. Returns the `SEXP`.

This is consistent with the `mkChar` stub already present in `SEXP.md` (Pattern P2, the allocation section). The present guide provides the authoritative standalone documentation for `mkChar` and establishes the complete rationale.

**Arena vs. heap allocation.** `CHARSXP` nodes produced by `mkChar` are **heap-allocated** via `std::malloc`, not arena-allocated. The reason is that they are written into `rname->data[]` slots (via `SET_STRING_ELT`) and must survive the `ArenaFrame` destruction at the `.Call` boundary. The `ArenaFrame` only governs scratch allocations made by `R_alloc`/`ALLOC` during tree construction; those are completely separate from the SEXP heap.

**`ArenaFrame` interaction.** The `ArenaFrame` RAII guard must be declared at the entry of every `.Call` entry-point wrapper (e.g., `rpart_wrapper`). It has no direct interaction with `mkChar` itself. However, all `mkChar` calls in `rpart.c` occur in the output-construction epilogue of `rpart()` (lines 327–348), which runs after all arena-managed tree-building is complete. If a `mkChar` call throws `RError`, the exception propagates up through `rpart()` and out through the `.Call` wrapper's `try/catch`, which calls `ArenaFrame`'s destructor in the process — freeing all arena-managed scratch memory correctly. The partially-filled `CHARSXP` nodes and `rname` node are not freed in the error path; this is an accepted trade-off (the process state for that `.Call` invocation is treated as unrecoverable).

**`#define` aliases from the original header that must be preserved.**

The real `Rinternals.h` defines:

```c
#define mkChar       Rf_mkChar
#define mkCharCE     Rf_mkCharCE
#define mkCharLen    Rf_mkCharLen
#define mkCharLenCE  Rf_mkCharLenCE
#define mkString     Rf_mkString
```

All five aliases must be present in `fake_Rinternals.hpp` so that original source files that include `Rinternals.h` and call any of these names compile without modification. `mkChar` is the only one used in rpart's source files, but the others must be stubbed for header completeness because any translation unit that includes the real `Rinternals.h` unconditionally sees all these declarations.

**`free_sexp` interaction.** `CHARSXP` nodes allocated by `mkChar` are freed as part of the `free_sexp(rname)` call chain. The `STRSXP.md` guide amends `free_sexp` to recurse into `STRSXP` children, so `free_sexp(rname)` calls `free_sexp(charsxp)` for each slot, which calls `std::free(charsxp->data)` (the string buffer) and then `std::free(charsxp)` (the `SEXPREC` node). No memory is leaked with the amended `free_sexp`.

---

### 4. Fake Implementation Examples

#### Pattern P1: Construct `CHARSXP` from a String Literal to Write into a `STRSXP` Slot

- **Locations:** `rpart.c:331`, `rpart.c:333`, `rpart.c:335`, `rpart.c:337`, `rpart.c:339`, `rpart.c:341`, `rpart.c:344`

- **Original R API Usage:**

```c
/* rpart.c:327-349 — output-list construction in rpart() */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);

SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));       /* mkChar at line 331 */

SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));     /* mkChar at line 333 */

SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));      /* mkChar at line 335 */

SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));      /* mkChar at line 337 */

SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));       /* mkChar at line 339 */

SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));       /* mkChar at line 341 */

if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));  /* mkChar at line 344 */
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — mkChar and its alias family)
//
// This block must appear AFTER:
//   - struct SEXPREC and typedef SEXPREC *SEXP        (from SEXP.md)
//   - #define CHARSXP 9  (SEXPTYPE constant block)    (from SEXP.md / INTSXP.md)
//   - struct RError : public std::runtime_error        (from SEXP.md)
//   - #include <cstdlib>  (std::malloc, std::free)
//   - #include <cstring>  (std::strlen, std::strcpy)

// -----------------------------------------------------------------------
// Rf_mkChar — heap-allocates a CHARSXP from a null-terminated C string.
//
// Real declaration in Rinternals.h line 564:
//   SEXP Rf_mkChar(const char *);
// Real alias in Rinternals.h line 1020:
//   #define mkChar Rf_mkChar
//
// Allocation strategy:
//   - SEXPREC node:  std::malloc(sizeof(SEXPREC))  — heap, NOT arena
//   - string buffer: std::malloc(len + 1)          — heap, NOT arena
//
// Both allocations must outlive the ArenaFrame because the CHARSXP is
// stored in rname->data[] (a STRSXP slot) and rname is part of the
// function's return value.
//
// Throws RError on std::malloc failure (Invariant 1).
// The node is freed by free_sexp(rname) via the STRSXP-recursive branch
// added in STRSXP.md.
// -----------------------------------------------------------------------
inline SEXP Rf_mkChar(const char *str) {
    std::size_t len = std::strlen(str);

    // Allocate the SEXPREC node.
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s)
        throw RError("mkChar: out of memory (SEXPREC)");

    // Fill the node fields.
    s->type   = CHARSXP;
    s->length = static_cast<int>(len);
    s->nrow   = static_cast<int>(len);
    s->ncol   = 1;

    // Allocate and copy the string buffer.
    s->data = std::malloc(len + 1);
    if (!s->data) {
        std::free(s);  // avoid partial leak before throw
        throw RError("mkChar: out of memory (string buffer)");
    }
    std::strcpy(static_cast<char *>(s->data), str);

    return s;
}

// Public-facing alias preserved from Rinternals.h line 1020.
// Every rpart source file uses mkChar(...), not Rf_mkChar(...) directly.
#define mkChar Rf_mkChar


// -----------------------------------------------------------------------
// Rf_mkCharLen — mkChar variant that takes an explicit length (no NUL scan).
//
// Real declaration in Rinternals.h line 565:
//   SEXP Rf_mkCharLen(const char *, int);
// Real alias in Rinternals.h line 1022:
//   #define mkCharLen Rf_mkCharLen
//
// Not used in any rpart C source file, but the alias is declared
// unconditionally in Rinternals.h so the stub must be present.
// -----------------------------------------------------------------------
inline SEXP Rf_mkCharLen(const char *str, int len) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s)
        throw RError("mkCharLen: out of memory (SEXPREC)");
    s->type   = CHARSXP;
    s->length = len;
    s->nrow   = len;
    s->ncol   = 1;
    s->data   = std::malloc(static_cast<std::size_t>(len) + 1);
    if (!s->data) {
        std::free(s);
        throw RError("mkCharLen: out of memory (string buffer)");
    }
    std::memcpy(s->data, str, static_cast<std::size_t>(len));
    static_cast<char *>(s->data)[len] = '\0';
    return s;
}
#define mkCharLen Rf_mkCharLen


// -----------------------------------------------------------------------
// cetype_t — character encoding type enum.
//
// Declared in Rinternals.h lines 616-625.  Required so that Rf_mkCharCE
// and Rf_mkCharLenCE compile.  Not used by any rpart C source file.
// In the fake runtime, encoding is ignored; all strings are treated as
// plain bytes.
// -----------------------------------------------------------------------
#ifndef FAKE_CETYPE_T_DEFINED
#define FAKE_CETYPE_T_DEFINED
typedef enum {
    CE_NATIVE = 0,
    CE_UTF8   = 1,
    CE_LATIN1 = 2,
    CE_BYTES  = 3,
    CE_SYMBOL = 5,
    CE_ANY    = 99
} cetype_t;
#endif


// -----------------------------------------------------------------------
// Rf_mkCharCE / Rf_mkCharLenCE — encoding-aware mkChar variants.
//
// Real declarations in Rinternals.h lines 631-632.
// Real aliases in Rinternals.h lines 1021, 1023.
//
// Not used in any rpart C source file.  The fake ignores the encoding
// argument and delegates to Rf_mkChar / Rf_mkCharLen.
// -----------------------------------------------------------------------
inline SEXP Rf_mkCharCE(const char *str, cetype_t /*enc*/) {
    return Rf_mkChar(str);
}
inline SEXP Rf_mkCharLenCE(const char *str, int len, cetype_t /*enc*/) {
    return Rf_mkCharLen(str, len);
}
#define mkCharCE    Rf_mkCharCE
#define mkCharLenCE Rf_mkCharLenCE


// -----------------------------------------------------------------------
// Rf_mkString — allocates a length-1 STRSXP whose sole element is the
// CHARSXP produced by Rf_mkChar(str).
//
// Real declaration in Rinternals.h line 1128.
// Real alias in Rinternals.h line 1025.
//
// Not used in any rpart C source file, but the declaration is always
// visible from Rinternals.h so the stub must be present.
// -----------------------------------------------------------------------
inline SEXP Rf_mkString(const char *str) {
    // Allocate a STRSXP of length 1.
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s)
        throw RError("mkString: out of memory (SEXPREC)");
    s->type   = STRSXP;
    s->length = 1;
    s->nrow   = 1;
    s->ncol   = 1;
    s->data   = std::malloc(sizeof(SEXP));
    if (!s->data) {
        std::free(s);
        throw RError("mkString: out of memory (data)");
    }
    // Store the sole CHARSXP child in the slot array.
    static_cast<SEXP *>(s->data)[0] = Rf_mkChar(str);
    return s;
}
#define mkString Rf_mkString


// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — showing mkChar in context.
//
// All seven mkChar calls occur in rpart()'s output-construction epilogue
// (lines 327-344).  The ArenaFrame guard manages R_alloc/ALLOC scratch
// allocations made during tree construction earlier in rpart(); it has no
// direct interaction with mkChar.  The CHARSXP nodes and rname/rlist are
// heap-allocated and must outlive the ArenaFrame.
//
// If any mkChar call throws RError (std::malloc failure), the exception
// propagates through SET_STRING_ELT's call site, up through rpart(), and
// is caught at the .Call boundary.  Partially-allocated CHARSXP nodes are
// not freed in the error path — this is acceptable; the error path is
// treated as unrecoverable for that invocation.
//
//   extern "C" SEXP rpart_wrapper(
//           SEXP ncat2, SEXP method2, SEXP opt2,
//           SEXP parms2, SEXP xvals2, SEXP xgrp2,
//           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;   // frees R_alloc/ALLOC scratch at function exit
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  All memory allocated by `Rf_mkChar` is **heap-allocated** via `std::malloc`, not arena-allocated.

  Per call to `mkChar("literal")`:
  - Two `std::malloc` calls: one for the `SEXPREC` node (`sizeof(SEXPREC)` bytes) and one for the null-terminated string buffer (`len + 1` bytes).
  - Both allocations must outlive the `ArenaFrame` because the `CHARSXP` is stored in `rname->data[]` and `rname` is (notionally) attached to the returned `rlist`.

  The `ArenaFrame` in the `.Call` wrapper for `rpart()` governs only `R_alloc`/`ALLOC` scratch arrays used during the tree-building phase (e.g., `rp.ydata`, `rp.xdata`, `savesort`). These scratch allocations are completely independent of the `CHARSXP` nodes created in the output-construction epilogue.

  Memory lifecycle for the seven `CHARSXP` nodes created by `mkChar`:

  1. `mkChar("which")` at line 331 — `std::malloc` for node + buffer. Written into `rname->data[0]` by `SET_STRING_ELT`.
  2. ... (pattern repeats for slots 1-5, and conditionally for slot 6).
  3. `rpart()` returns `rlist`. The `CHARSXP` nodes are now reachable through `rname->data[]`, and `rname` is reachable (by the Python caller holding the pointer) independently of `rlist`.
  4. Python calls `free_sexp(rname)`: the amended `free_sexp` from `STRSXP.md` recurses into `STRSXP` children, calling `free_sexp(charsxp)` for each slot. `free_sexp(charsxp)` calls `std::free(charsxp->data)` (the string buffer), then `std::free(charsxp)` (the `SEXPREC` node). No leak.
  5. Python calls `free_sexp(rlist)`: frees `which3`, `cptable3`, etc., and then `rlist` itself.

  Failure behavior: if either `std::malloc` inside `Rf_mkChar` returns `nullptr`, `RError` is thrown. The second `std::malloc` failure path frees the already-allocated `SEXPREC` node before throwing. Any `CHARSXP` nodes that were successfully written into `rname->data[]` before the failure are not freed — this constitutes a memory leak in the error path. Because the `.Call` boundary catches the `RError` and reports it as a Python exception, and the process state for that invocation is treated as unrecoverable, this leak is acceptable.

- **Explanation:**

  The fake `Rf_mkChar` is an `inline` function that allocates a minimal `SEXPREC` with `type = CHARSXP` and `data` pointing to a heap-allocated copy of the input string. The `#define mkChar Rf_mkChar` alias from `Rinternals.h` line 1020 is preserved verbatim in `fake_Rinternals.hpp`, so every occurrence of `mkChar("...")` in `rpart.c` expands to a call to the inline function without any source modification.

  The fake `SEXPREC` layout established in `SEXP.md` specifies that for a `CHARSXP`, the `data` field holds a `char *` to the null-terminated string. This is consistent with the `CHAR` / `R_CHAR` accessor defined in `CHAR.md`:

  ```cpp
  inline const char *R_CHAR(SEXP s) { return static_cast<const char *>(s->data); }
  #define CHAR(x) R_CHAR(x)
  ```

  A `CHARSXP` produced by `Rf_mkChar` can therefore be passed to `CHAR(...)` and will yield back the original string. This is the composition used in `rpart_callback.c:24` (`CHAR(PRINTNAME(sym))`), where `PRINTNAME` returns a `CHARSXP` child of a `SYMSXP` — the `install()` stub (Category E) also uses `Rf_mkChar` internally to construct those `CHARSXP` children.

  The real `Rinternals.h` also provides `CHAR(x)` as `#define CHAR(x) R_CHAR(x)` (line 203). Both `CHAR` and `R_CHAR` must be defined before any code that applies them to a `CHARSXP` produced by `mkChar`. Since all these definitions live in the same `fake_Rinternals.hpp`, include order within the file determines their relative position; the `SEXP.md` guide places them in the correct dependency order.

  The `mkCharCE`, `mkCharLen`, `mkCharLenCE`, and `mkString` stubs are required for header completeness even though no rpart source file uses them. Any translation unit that `#include`s `Rinternals.h` will see their declarations; the linker must resolve them. The fake stubs delegate to `Rf_mkChar` or `Rf_mkCharLen` and ignore the encoding argument, which is sufficient since the fake runtime has no encoding infrastructure.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct layout (`type`, `length`, `nrow`, `ncol`, `data` fields) and the `SEXP` typedef. `Rf_mkChar` writes to all five fields and must be consistent with the layout used by `SET_STRING_ELT`, `STRING_ELT`, `R_CHAR`, and `free_sexp`. Also provides `RError` (the C++ exception type thrown on allocation failure, per Invariant 1) and the original `free_sexp` (amended per `STRSXP.md` to free `STRSXP` children). |
| `INTSXP.md` | Establishes `#define CHARSXP 9` within the `SEXPTYPE` constant block. `Rf_mkChar` sets `s->type = CHARSXP`; this constant must be defined before `fake_Rinternals.hpp` is compiled. |
| `STRSXP.md` | Establishes `#define STRSXP 16` (required by `Rf_mkString`) and documents the amendment to `free_sexp` that recurses into `STRSXP` children — without which the `CHARSXP` nodes produced by `mkChar` and stored in `rname->data[]` would be leaked when Python calls `free_sexp(rname)`. |
| `SET_STRING_ELT.md` | Documents the `SET_STRING_ELT(rname, i, mkChar("..."))` call pattern that is the sole consumer of `mkChar`'s return value in rpart. Confirms that `SET_STRING_ELT` writes the `CHARSXP` pointer into the `SEXP[]` slot array of the `STRSXP`, which is the mechanism that transfers ownership of the heap-allocated `CHARSXP` to `rname`. |
| `CHAR.md` | Documents `R_CHAR` / `CHAR`, which reads the `const char *` from a `CHARSXP` node's `data` field. Consistency requirement: `Rf_mkChar` stores the string in `s->data` as a `char *`; `R_CHAR` reads `s->data` as `const char *`. The cast is `static_cast<const char *>(s->data)`. Both must use the same `void *data` field convention established in `SEXP.md`. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` boundary wrapper for the `ArenaFrame` RAII guard. `mkChar` itself has no arena dependency, but the enclosing `rpart()` function uses `R_alloc`/`ALLOC` scratch memory and therefore requires `ArenaFrame _frame;` at the call boundary. |
