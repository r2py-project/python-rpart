# Fake Header Implementation Guide: `SET_STRING_ELT`

---

### 1. Overview of `SET_STRING_ELT` in R API

`SET_STRING_ELT` is a mutator function in R's C API declared in `Rinternals.h` as:

```c
void SET_STRING_ELT(SEXP x, R_xlen_t i, SEXP v);
```

It writes a `CHARSXP` scalar-string node `v` into slot `i` of the `STRSXP` string-vector `x`. The function is the write counterpart of `STRING_ELT(x, i)`. Internally, a `STRSXP` stores its elements as an array of `SEXP` child pointers (each a `CHARSXP`), so `SET_STRING_ELT` is equivalent to assigning into that array at index `i`. `SET_STRING_ELT` is classified as a **Category B — Accessor/Mutator Inline Function**: it mutates an element of the SEXP data array and requires no allocation, no arena interaction, and no interpreter dependency.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart.c` | 315–349 | Output-list construction epilogue of `rpart()`; the `STRSXP rname` name vector is allocated and populated with `SET_STRING_ELT` / `mkChar` calls |

All seven CSV rows are in the same function (`rpart.c`, lines 331–344). Reading 15 lines above the first occurrence (line 316) through 15 lines below the last (line 344 + 15 = 359) exposes the full usage pattern:

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    // line 327
SEXP rname = allocVector(STRSXP, nout);              // line 328
setAttrib(rlist, R_NamesSymbol, rname);              // line 329
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));           // line 331 — CSV row 1
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));         // line 333 — CSV row 2
SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));          // line 335 — CSV row 3
SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));          // line 337 — CSV row 4
SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));           // line 339 — CSV row 5
SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));           // line 341 — CSV row 6
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));      // line 344 — CSV row 7
}
UNPROTECT(1 + nout);
return rlist;
```

**Argument and return types.**

The real `Rinternals.h` signature at line 297 is:

```c
void SET_STRING_ELT(SEXP x, R_xlen_t i, SEXP v);
```

- `x` — a `STRSXP` SEXP, the target string vector (`rname`).
- `i` — a `R_xlen_t` (platform-dependent; `ptrdiff_t` on 64-bit, `int` on 32-bit) slot index. All rpart call sites pass a compile-time integer literal (`0` through `6`).
- `v` — a `CHARSXP` SEXP produced by `mkChar(const char *)`.
- Return value — `void`.

In the fake build `R_xlen_t` is `typedef int R_xlen_t` (rpart is 32-bit safe), consistent with the definition in `SEXP.md`.

**Co-occurring R API items.**

| Item | Lines | Role |
|---|---|---|
| `allocVector(STRSXP, nout)` | 328 | Allocates the `STRSXP` target vector `rname`; documented in `STRSXP.md` |
| `mkChar(const char *)` | 331, 333, 335, 337, 339, 341, 344 | Creates the `CHARSXP` value written by `SET_STRING_ELT`; documented in `SEXP.md` |
| `setAttrib(rlist, R_NamesSymbol, rname)` | 329 | Attaches `rname` as the names attribute (no-op in fake); documented in `R_NamesSymbol.md` |
| `SET_VECTOR_ELT(rlist, i, child)` | 330–343 | Writes child SEXPs into the `VECSXP` output list; documented in `SEXP.md` |
| `PROTECT` / `UNPROTECT` | 327, 347 | No-ops in the fake runtime; documented in `SEXP.md` |
| `STRSXP` | 328 | Type tag passed to `allocVector`; documented in `STRSXP.md` |
| `R_NamesSymbol` | 329 | Pre-interned symbol sentinel (no-op key); documented in `R_NamesSymbol.md` |

**Distinct implementation patterns.**

There is exactly one structural pattern across all seven CSV rows:

**Pattern: Write a `CHARSXP` produced by `mkChar` into a slot of a `STRSXP` name vector.**

Every call has the form `SET_STRING_ELT(rname, <integer-literal>, mkChar(<string-literal>))`. The target is always `rname` (the `STRSXP` allocated at line 328), the index is a compile-time constant from `0` to `6`, and the value is always a freshly created `CHARSXP` from `mkChar`. There is no second pattern (e.g., reading back via `STRING_ELT`, or writing a pre-existing `CHARSXP` variable). All seven rows share the same fake strategy.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor/Mutator Inline Function.**

`SET_STRING_ELT` is a mutator that writes one element into the internal data array of a `STRSXP` object. It requires no memory allocation, no arena interaction, and no interpreter. The fake is a single C++ `inline void` function that casts `x->data` to `SEXP *` and assigns `v` at index `i`.

**Chosen mechanism.**

The fake `SEXPREC` layout established in `SEXP.md` specifies that for `STRSXP` (and `VECSXP`, `EXPRSXP`) objects, `data` holds a `SEXP[length]` array — an array of child `SEXP` pointers. `SET_STRING_ELT(x, i, v)` is therefore:

```cpp
inline void SET_STRING_ELT(SEXP x, int i, SEXP v) {
    static_cast<SEXP *>(x->data)[i] = v;
}
```

This is consistent with the `SET_VECTOR_ELT` implementation already in `fake_Rinternals.hpp` (documented in `SEXP.md`), which uses the identical cast for `VECSXP`. The only difference between the two is the parameter name and the semantic assertion that `x` must be a `STRSXP` and `v` must be a `CHARSXP`; neither assertion is enforced at compile time in the real R API or in the fake.

The companion reader `STRING_ELT(x, i)` is the symmetric read accessor and must be defined alongside `SET_STRING_ELT`:

```cpp
inline SEXP STRING_ELT(SEXP x, int i) {
    return static_cast<SEXP *>(x->data)[i];
}
```

Both are already present in `fake_Rinternals.hpp` per `SEXP.md` (the `VECSXP / STRSXP element accessors` block). This guide establishes the full rationale and verifies correctness against the call sites.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` at line 295 comments out the function-form declaration of `STRING_ELT` (replacing it with a macro-less declaration at line 1162), and at line 297 declares `SET_STRING_ELT` directly without a `#define` alias. No `#define` alias for `SET_STRING_ELT` or `STRING_ELT` exists in `Rinternals.h`. The original source code calls them by their exact names; the fake inline functions use those same names, so no `#define` alias is needed.

The `mkChar` alias (`#define mkChar Rf_mkChar`) is required at every call site of `SET_STRING_ELT` in `rpart.c` because the third argument is always `mkChar(...)`. That alias is already present in `fake_Rinternals.hpp` per `SEXP.md`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `SET_STRING_ELT` itself. If `x` is null or `i` is out of bounds, the write produces undefined behaviour (same as the real R API under `USE_RINTERNALS`). No error is thrown by `SET_STRING_ELT`; allocation errors in the `mkChar` third argument propagate before `SET_STRING_ELT` is reached.
- Invariant 2 (arena memory): not triggered. `SET_STRING_ELT` performs no allocation. The target `STRSXP` (`rname`) and the written `CHARSXP` nodes (from `mkChar`) are both heap-allocated via `std::malloc`; neither touches the arena.
- Invariant 3 (R Interpreter Items): not applicable. `SET_STRING_ELT` is a pure in-memory array write with no interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern: Write `CHARSXP` from `mkChar` into a `STRSXP` Name Vector Slot

- **Locations:** `rpart.c:331`, `rpart.c:333`, `rpart.c:335`, `rpart.c:337`, `rpart.c:339`, `rpart.c:341`, `rpart.c:344`

- **Original R API Usage:**

```c
/* rpart.c:327-344 — output list construction in rpart() */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);

SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));    /* write "which" CHARSXP into slot 0 */

SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable")); /* write "cptable" CHARSXP into slot 1 */

SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));  /* write "dsplit" CHARSXP into slot 2 */

SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));  /* write "isplit" CHARSXP into slot 3 */

SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));   /* write "dnode" CHARSXP into slot 4 */

SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));   /* write "inode" CHARSXP into slot 5 */

if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit")); /* conditional: slot 6 only when catcount > 0 */
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// The following definitions implement SET_STRING_ELT and its companion
// STRING_ELT.  They belong in fake_Rinternals.hpp after the SEXPREC/SEXP
// typedef block, the SEXPTYPE constants, and the mkChar definition
// (all established in SEXP.md).

// -----------------------------------------------------------------------
// STRING_ELT — read accessor for STRSXP elements.
//
// Real declaration in Rinternals.h line 1162:
//   SEXP (STRING_ELT)(SEXP x, R_xlen_t i);
//
// The parenthesised form in the real header exists to block macro
// substitution in old-style implementations; no macro alias for
// STRING_ELT exists.
//
// Fake: cast x->data to SEXP * and return element at index i.
// x must be a STRSXP; x->data is a SEXP[x->length] array of CHARSXP
// pointers allocated by allocVector(STRSXP, n) and zero-initialised.
// -----------------------------------------------------------------------
inline SEXP STRING_ELT(SEXP x, int i) {
    return static_cast<SEXP *>(x->data)[i];
}

// -----------------------------------------------------------------------
// SET_STRING_ELT — write mutator for STRSXP elements.
//
// Real declaration in Rinternals.h line 297:
//   void SET_STRING_ELT(SEXP x, R_xlen_t i, SEXP v);
//
// No #define alias exists in Rinternals.h for SET_STRING_ELT; the
// original source calls it by its exact name.
//
// Fake: cast x->data to SEXP * and assign v at index i.
// v must be a CHARSXP produced by mkChar; its pointer is stored in the
// slot array.  No allocation is performed; no arena is touched.
// Ownership of v (the CHARSXP heap node) passes to the STRSXP: when
// free_sexp(rname) is called by Python, the amended free_sexp (from
// STRSXP.md) recurses into STRSXP children and frees each CHARSXP.
// -----------------------------------------------------------------------
inline void SET_STRING_ELT(SEXP x, int i, SEXP v) {
    static_cast<SEXP *>(x->data)[i] = v;
}

// -----------------------------------------------------------------------
// mkChar / Rf_mkChar — creates a heap-allocated CHARSXP.
//
// Already defined in fake_Rinternals.hpp per SEXP.md.
// Shown here for completeness, since every SET_STRING_ELT call site
// uses mkChar as the third argument.
//
// Real declaration in Rinternals.h line 564:
//   SEXP Rf_mkChar(const char *);
// Real alias in Rinternals.h line 1020:
//   #define mkChar  Rf_mkChar
//
// Fake (from SEXP.md):
//   inline SEXP mkChar(const char *str) {
//       std::size_t len = std::strlen(str);
//       SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
//       if (!s) throw RError("mkChar: out of memory (SEXPREC)");
//       s->type   = CHARSXP;
//       s->length = static_cast<int>(len);
//       s->nrow   = static_cast<int>(len);
//       s->ncol   = 1;
//       s->data   = std::malloc(len + 1);
//       if (!s->data) { std::free(s); throw RError("mkChar: out of memory (data)"); }
//       std::strcpy(static_cast<char *>(s->data), str);
//       return s;
//   }
//   inline SEXP Rf_mkChar(const char *str) { return mkChar(str); }
//   #define mkChar  Rf_mkChar
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — showing SET_STRING_ELT in context.
//
// SET_STRING_ELT is called in the output-construction epilogue of rpart(),
// after all tree-building (which uses R_alloc / ALLOC arena memory) is
// complete.  The ArenaFrame governs only the scratch allocations made
// during tree construction; the STRSXP rname and its CHARSXP children are
// heap-allocated and must outlive the ArenaFrame because they are part of
// the return structure.
//
// If mkChar throws RError (out of memory), the exception propagates
// through SET_STRING_ELT's caller and is caught at the .Call boundary.
// Any CHARSXP nodes already written into rname and the rname node itself
// are not freed in the error path — this is acceptable; the process state
// for that call is treated as unrecoverable, consistent with the STRSXP.md
// analysis.
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
//           set_python_error(e.what());   // store message for Python to read
//           return R_NilValue;            // signal failure to caller
//       }
//   }
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  `SET_STRING_ELT` performs no allocation whatsoever. It is a single pointer-array write. No heap memory, no arena memory, and no static memory is touched by `SET_STRING_ELT` itself.

  The memory objects involved at the call sites in `rpart.c` are:

  1. `rname` (STRSXP) — heap-allocated via `allocVector(STRSXP, nout)` at line 328. Its `data` field is a `SEXP[nout]` array, also heap-allocated, zero-initialised by `allocVector`. `SET_STRING_ELT` writes into this array.
  2. `mkChar("which")` etc. — each call to `mkChar` heap-allocates a `SEXPREC` node and a `char[]` buffer via `std::malloc`. The resulting `CHARSXP` pointer is passed as the third argument and immediately written into `rname->data[i]` by `SET_STRING_ELT`. After the write, the only reference to the `CHARSXP` is the slot in `rname->data`.
  3. `rlist` (VECSXP) — heap-allocated, not affected by `SET_STRING_ELT`.
  4. Arena (`ArenaFrame`) — completely separate; governs `R_alloc`/`ALLOC` scratch arrays used during tree construction earlier in `rpart()`. None of the objects written by `SET_STRING_ELT` are arena-managed.

  Lifecycle after the call returns:

  - Python reads `rlist` (the return value) by positional slot index. `rname` is attached via `setAttrib` which is a no-op, so Python holds a separate reference to `rname` obtained before the call (or not at all, since `rname` is only needed for name lookups which the Python caller performs by position).
  - `free_sexp(rname)` (using the amended version from `STRSXP.md` that recurses into `STRSXP` children) frees each `CHARSXP` node written by `mkChar`, then frees the `SEXP[]` data array, then frees the `SEXPREC` node for `rname` itself. No memory leak.
  - `free_sexp(rlist)` recursively frees the `VECSXP` children (`which3`, `cptable3`, etc.) and then `rlist` itself.

- **Explanation:**

  The fake `SET_STRING_ELT` is a one-line inline function:

  ```cpp
  inline void SET_STRING_ELT(SEXP x, int i, SEXP v) {
      static_cast<SEXP *>(x->data)[i] = v;
  }
  ```

  This works because:

  1. `allocVector(STRSXP, nout)` (documented in `STRSXP.md`) allocates `nout * sizeof(SEXP)` bytes for `rname->data` — an array of `SEXP` slots, zero-initialised (`nullptr` in each slot). `SET_STRING_ELT` writes `v` (a `CHARSXP` pointer) into one of those slots.

  2. The cast `static_cast<SEXP *>(x->data)` is valid because `data` is `void *` pointing to the `SEXP[]` array created by `allocVector`, and casting `void *` to `SEXP *` in C++ is explicit and legal.

  3. The index `i` is an `int` literal (0–6) at all rpart call sites. The real API uses `R_xlen_t` (which maps to `int` in the 32-bit-safe fake); the implicit conversion from the integer literal to `int` is exact.

  4. No `#define` alias for `SET_STRING_ELT` is needed: the real `Rinternals.h` declares it with its exact name (not through a `#define`). The inline function in the fake uses the same name, so `rpart.c` compiles unchanged.

  5. The companion `STRING_ELT` is the symmetric read accessor. It is not used in the rpart C source files, but must be defined to satisfy completeness of the `fake_Rinternals.hpp` header (any client that includes `Rinternals.h` and calls `STRING_ELT` must compile against the fake).

  The overall sequence at `rpart.c:327-344` compiles without modification under `fake_Rinternals.hpp` because every symbol used — `PROTECT`, `allocVector`, `VECSXP`, `STRSXP`, `setAttrib`, `R_NamesSymbol`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, `UNPROTECT` — is defined in the fake header under its exact original name.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The complete `fake_Rinternals.hpp` from `SEXP.md` is the primary prerequisite. It provides: the `SEXPREC` struct layout (`type`, `length`, `nrow`, `ncol`, `data` fields) required so that `static_cast<SEXP *>(x->data)[i] = v` is a valid expression; the `SEXP` typedef (`typedef SEXPREC *SEXP`); the `R_xlen_t` typedef (`typedef int R_xlen_t`) required to match the real function signature; `mkChar` / `Rf_mkChar` definitions used as the third argument at every call site; `SET_VECTOR_ELT` and `VECTOR_ELT` definitions (adjacent calls in the same code block); `PROTECT`/`UNPROTECT` no-ops; `R_NilValue` sentinel; and the `free_sexp` utility (amended per `STRSXP.md` to recurse into `STRSXP` children, which is required to free the `CHARSXP` nodes written by `SET_STRING_ELT`). |
| `STRSXP.md` | Establishes `#define STRSXP 16` within the SEXPTYPE constant block and documents the `allocVector(STRSXP, n)` allocation that creates the target `rname` object written by `SET_STRING_ELT`. Crucially, `STRSXP.md` provides the amended `free_sexp` that recurses into `STRSXP` children — without this amendment, the `CHARSXP` nodes written by `SET_STRING_ELT(rname, i, mkChar(...))` are leaked when Python calls `free_sexp(rname)`. `STRSXP.md` also documents why `rname` is not `PROTECT`ed in the original source and why that is safe in the fake runtime. |
| `R_NamesSymbol.md` | Documents `R_NamesSymbol` and the no-op `setAttrib` / `Rf_setAttrib` functions used at `rpart.c:329`, the line immediately before the first `SET_STRING_ELT` call. These must be defined before `SET_STRING_ELT` is reached so that the output-construction block compiles as a unit. |
| `mkChar.md` | Documents `mkChar` / `Rf_mkChar` in detail (if the guide is generated as a standalone item). If `mkChar.md` does not exist as a separate guide, the definition is provided by `SEXP.md`. The `#define mkChar Rf_mkChar` alias from `Rinternals.h` line 1020 must be present in `fake_Rinternals.hpp` so that every `SET_STRING_ELT(rname, i, mkChar("..."))` call site compiles unchanged. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` boundary wrapper (shown above) for the `ArenaFrame` RAII guard. `SET_STRING_ELT` itself has no arena dependency, but the enclosing `rpart()` function uses `R_alloc`/`ALLOC` scratch memory and therefore requires `ArenaFrame _frame;` at the call boundary. |
