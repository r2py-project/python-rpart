# Fake Header Implementation Guide: `SET_VECTOR_ELT`

---

### 1. Overview of `SET_VECTOR_ELT` in R API

`SET_VECTOR_ELT` is a mutator function in R's C API declared in `Rinternals.h` (line 298) as:

```c
SEXP SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v);
```

Its role is to write a child `SEXP` value `v` into slot `i` of a generic vector (list) object `x` of type `VECSXP`. It is the write counterpart of `VECTOR_ELT(x, i)`. Internally, a `VECSXP` stores its elements as a flat `SEXP[length]` array — each slot holds a pointer to a child `SEXPREC` of any type — so `SET_VECTOR_ELT` is equivalent to assigning into that pointer array at index `i`. The function returns `v` (the value that was written), matching the real R implementation. It is classified as **Category B — Accessor/Mutator Inline Function**: it mutates an element of the SEXP data array and requires no allocation, no arena interaction, and no interpreter dependency.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart.c` | 315–349 | Output-list construction epilogue of `rpart()`; a `VECSXP` list `rlist` is allocated and populated with seven child SEXPs via `SET_VECTOR_ELT` before being returned as the `.Call` result |

All seven CSV rows are in the same function (`rpart.c`, lines 330–343). Reading 15 lines above the first occurrence (line 315) through line 349 exposes the complete usage pattern:

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    // line 327
SEXP rname = allocVector(STRSXP, nout);              // line 328
setAttrib(rlist, R_NamesSymbol, rname);              // line 329
SET_VECTOR_ELT(rlist, 0, which3);                   // line 330 — CSV row 1
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);                 // line 332 — CSV row 2
SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);                  // line 334 — CSV row 3
SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);                  // line 336 — CSV row 4
SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);                   // line 338 — CSV row 5
SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);                   // line 340 — CSV row 6
SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);              // line 343 — CSV row 7
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

The seven child SEXPs written into `rlist` were all heap-allocated earlier in `rpart()` via `allocVector` / `allocMatrix` and subsequently PROTECTed:

| Slot | Variable | Source | Type |
|---|---|---|---|
| 0 | `which3` | `allocVector(INTSXP, n)` at line 194 | `INTSXP` — 1-D integer vector |
| 1 | `cptable3` | `allocMatrix(REALSXP, ?, rp.num_unique_cp)` at line 241 | `REALSXP` — 2-D real matrix |
| 2 | `dsplit3` | `allocMatrix(REALSXP, splitcount, 3)` at line 269 | `REALSXP` — 2-D real matrix |
| 3 | `isplit3` | `allocMatrix(INTSXP, splitcount, 3)` at line 285 | `INTSXP` — 2-D integer matrix |
| 4 | `dnode3` | `allocMatrix(REALSXP, nodecount, ?)` at line 261 | `REALSXP` — 2-D real matrix |
| 5 | `inode3` | `allocMatrix(INTSXP, nodecount, 6)` at line 278 | `INTSXP` — 2-D integer matrix |
| 6 | `csplit3` | `allocMatrix(INTSXP, catcount, maxcat)` at line 293, or `R_NilValue` if `catcount == 0` | `INTSXP` (conditional) or `NILSXP` |

**Argument and return types.**

The real `Rinternals.h` signature at line 298 is:

```c
SEXP SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v);
```

- `x` — a `VECSXP` SEXP, the target generic vector (`rlist`).
- `i` — a `R_xlen_t` slot index. In the fake build `R_xlen_t` is `typedef int R_xlen_t` (rpart is 32-bit safe), as established in `SEXP.md`. All rpart call sites pass a compile-time integer literal (`0` through `6`).
- `v` — a `SEXP` of any type (the child object to store); may be `R_NilValue`.
- Return value — `SEXP`: the real R implementation returns `v`. The fake matches this behaviour.

**Co-occurring R API items in context window.**

| Item | Lines | Role |
|---|---|---|
| `allocVector(VECSXP, nout)` | 327 | Allocates the target `VECSXP` container `rlist`; documented in `SEXP.md`, `VECSXP.md` |
| `PROTECT` / `UNPROTECT` | 327, 347 | No-ops in the fake runtime; documented in `PROTECT.md` |
| `SET_STRING_ELT(rname, i, mkChar(...))` | 331, 333, 335, 337, 339, 341, 344 | Parallel population of the companion `STRSXP` names vector; documented in `SET_STRING_ELT.md` |
| `setAttrib(rlist, R_NamesSymbol, rname)` | 329 | Attaches `rname` as the names attribute (no-op in fake); documented in `R_NamesSymbol.md` |
| `VECTOR_ELT(x, i)` | (not in rpart C source, but companion accessor) | Symmetric read accessor for `VECSXP` slots; defined alongside `SET_VECTOR_ELT` in `fake_Rinternals.hpp` |
| `R_NilValue` | 64 | Assigned as the default value of `csplit3`; passed to `SET_VECTOR_ELT(rlist, 6, csplit3)` when `catcount == 0`; documented in `R_NilValue.md`, `SEXP.md` |
| `allocMatrix` / `allocVector` for child SEXPs | 194, 241, 261, 269, 278, 285, 293 | Produce the `SEXP` arguments `v` passed to `SET_VECTOR_ELT`; all heap-allocated; documented in `SEXP.md`, `VECSXP.md` |

**Distinct implementation patterns.**

There is exactly one structural pattern across all seven CSV rows:

**Pattern: Write a pre-allocated child SEXP into a slot of a `VECSXP` output list.**

Every call has the form `SET_VECTOR_ELT(rlist, <integer-literal>, <sexp-variable>)`. The target is always `rlist` (the `VECSXP` allocated at line 327), the index is a compile-time constant from `0` to `6`, and the value is always a previously heap-allocated `SEXP` local variable (or `R_NilValue` for the conditional slot 6). All seven rows share the same fake strategy.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor/Mutator Inline Function.**

`SET_VECTOR_ELT` is a mutator that writes one element into the internal data array of a `VECSXP` object. It requires no memory allocation, no arena interaction, and no interpreter dependency. The fake is a single C++ `inline SEXP` function that casts `x->data` to `SEXP *` and assigns `v` at index `i`, then returns `v`.

**Chosen mechanism.**

The fake `SEXPREC` layout established in `SEXP.md` specifies that for `VECSXP` (and `STRSXP`, `EXPRSXP`) objects, `data` holds a `SEXP[length]` array — a flat array of child `SEXP` pointers allocated by `allocVector`. `SET_VECTOR_ELT(x, i, v)` is therefore:

```cpp
inline SEXP SET_VECTOR_ELT(SEXP x, int i, SEXP v) {
    static_cast<SEXP *>(x->data)[i] = v;
    return v;
}
```

This is structurally parallel to the `SET_STRING_ELT` implementation already in `fake_Rinternals.hpp` (documented in `SET_STRING_ELT.md`), which uses the identical cast for `STRSXP`. The key differences between the two are:

- `SET_VECTOR_ELT` returns `SEXP` (the written value `v`); `SET_STRING_ELT` returns `void`.
- Semantically, `SET_VECTOR_ELT`'s target must be a `VECSXP` and `v` may be a `SEXP` of any type; `SET_STRING_ELT`'s target must be a `STRSXP` and `v` must be a `CHARSXP`. Neither constraint is enforced at compile time in the real R API or in the fake.

The companion reader `VECTOR_ELT(x, i)` is the symmetric read accessor and must be defined alongside `SET_VECTOR_ELT`. Both are already present in `fake_Rinternals.hpp` per `SEXP.md` (Pattern P2, `VECSXP / STRSXP element accessors` block). This guide establishes the full rationale and verifies correctness against all seven call sites.

**Return value behaviour.**

The real R `SET_VECTOR_ELT` returns `v`. In `rpart.c`, none of the seven call sites use the return value (the result is discarded). However, the return type must be `SEXP` rather than `void` to match the declared signature in `Rinternals.h` line 298 (`SEXP SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v)`). Any external client code that calls `SET_VECTOR_ELT` and assigns its return value must compile correctly under the fake.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` line 298 declares `SET_VECTOR_ELT` directly by name — there is no `#define` alias. The original source code calls it by its exact name. The inline function in the fake uses the same name, so no `#define` alias is required. The companion `VECTOR_ELT` at line 296 is declared in parenthesised form `SEXP (VECTOR_ELT)(SEXP x, R_xlen_t i)` — the parentheses are a C convention to prevent potential macro expansion of the name; since no macro with that name exists, the inline definition under the plain name `VECTOR_ELT` is correct.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `SET_VECTOR_ELT` itself. The function performs no allocation and no error checking. If `x` is null or `i` is out of bounds, the result is undefined behaviour — consistent with the real R API under `USE_RINTERNALS`. Allocation errors from the `allocVector` / `allocMatrix` calls that produced the child SEXPs propagate before `SET_VECTOR_ELT` is reached and are caught at the `.Call` boundary.
- Invariant 2 (arena memory): not triggered. `SET_VECTOR_ELT` performs no allocation whatsoever. The target `VECSXP` (`rlist`) and all child SEXPs written into it are heap-allocated via `std::malloc`; none touches the arena.
- Invariant 3 (R Interpreter Items): not applicable. `SET_VECTOR_ELT` is a pure in-memory pointer array write with no interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern: Write Pre-Allocated Child SEXP into a `VECSXP` Slot

- **Locations:** `rpart.c:330`, `rpart.c:332`, `rpart.c:334`, `rpart.c:336`, `rpart.c:338`, `rpart.c:340`, `rpart.c:343`

- **Original R API Usage:**

```c
/* rpart.c:325-349 — output list construction in rpart() */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);

SET_VECTOR_ELT(rlist, 0, which3);    /* store INTSXP child into slot 0 */
SET_STRING_ELT(rname, 0, mkChar("which"));

SET_VECTOR_ELT(rlist, 1, cptable3);  /* store REALSXP matrix child into slot 1 */
SET_STRING_ELT(rname, 1, mkChar("cptable"));

SET_VECTOR_ELT(rlist, 2, dsplit3);   /* store REALSXP matrix child into slot 2 */
SET_STRING_ELT(rname, 2, mkChar("dsplit"));

SET_VECTOR_ELT(rlist, 3, isplit3);   /* store INTSXP matrix child into slot 3 */
SET_STRING_ELT(rname, 3, mkChar("isplit"));

SET_VECTOR_ELT(rlist, 4, dnode3);    /* store REALSXP matrix child into slot 4 */
SET_STRING_ELT(rname, 4, mkChar("dnode"));

SET_VECTOR_ELT(rlist, 5, inode3);    /* store INTSXP matrix child into slot 5 */
SET_STRING_ELT(rname, 5, mkChar("inode"));

if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);  /* conditional: INTSXP matrix or R_NilValue */
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// The following definitions implement SET_VECTOR_ELT and its companion
// VECTOR_ELT.  They belong in fake_Rinternals.hpp after the SEXPREC/SEXP
// typedef block, the SEXPTYPE constants, and the allocVector definition
// (all established in SEXP.md).

// -----------------------------------------------------------------------
// VECTOR_ELT — read accessor for VECSXP elements.
//
// Real declaration in Rinternals.h line 296:
//   SEXP (VECTOR_ELT)(SEXP x, R_xlen_t i);
//
// The parenthesised form prevents macro substitution; no #define alias
// for VECTOR_ELT exists in Rinternals.h.
//
// Fake: cast x->data to SEXP * and return the element at index i.
// x must be a VECSXP; x->data is a SEXP[x->length] array of child SEXP
// pointers allocated by allocVector(VECSXP, n) and zero-initialised
// (each slot starts as nullptr).
// -----------------------------------------------------------------------
inline SEXP VECTOR_ELT(SEXP x, int i) {
    return static_cast<SEXP *>(x->data)[i];
}

// -----------------------------------------------------------------------
// SET_VECTOR_ELT — write mutator for VECSXP elements.
//
// Real declaration in Rinternals.h line 298:
//   SEXP SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v);
//
// No #define alias exists in Rinternals.h for SET_VECTOR_ELT; the
// original source calls it by its exact name.
//
// Fake: cast x->data to SEXP * and assign v at index i, then return v.
//
// v may be any SEXP type (INTSXP, REALSXP, NILSXP, etc.) — consistent
// with the seven call sites in rpart.c which store a mix of INTSXP,
// REALSXP, and (conditionally) NILSXP children.
//
// No allocation is performed; no arena is touched.  Ownership of v does
// not transfer in any special sense: the child SEXP pointer is copied
// into the slot.  When free_sexp(rlist) is called by Python, the
// free_sexp function (from SEXP.md, amended in VECSXP.md and STRSXP.md)
// recurses into the VECSXP data array and frees each non-null child SEXP.
// -----------------------------------------------------------------------
inline SEXP SET_VECTOR_ELT(SEXP x, int i, SEXP v) {
    static_cast<SEXP *>(x->data)[i] = v;
    return v;
}

// -----------------------------------------------------------------------
// free_sexp — canonical form (from SEXP.md, amended by VECSXP.md and
// STRSXP.md).  Shown here for reference; must NOT be redefined if
// SEXP.md is already included.
//
// The VECSXP branch recurses into children stored by SET_VECTOR_ELT:
//
//   inline void free_sexp(SEXP s) {
//       if (!s) return;
//       if (s->type == VECSXP || s->type == EXPRSXP || s->type == STRSXP) {
//           SEXP *elems = static_cast<SEXP *>(s->data);
//           for (int i = 0; i < s->length; i++)
//               free_sexp(elems[i]);
//       }
//       std::free(s->data);
//       std::free(s);
//   }
//
// When Python calls free_sexp(rlist):
//   1. Each slot rlist->data[0..nout-1] is freed via recursive free_sexp.
//      Slot 6 may be nullptr (from zero-initialisation) if catcount == 0
//      and SET_VECTOR_ELT(rlist, 6, ...) was never called; free_sexp(nullptr)
//      returns immediately, so no null-pointer dereference occurs.
//   2. The SEXP[] data array (rlist->data) is freed.
//   3. The SEXPREC node for rlist itself is freed.
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — showing SET_VECTOR_ELT in context.
//
// SET_VECTOR_ELT is called in the output-construction epilogue of rpart(),
// after all tree-building (which uses R_alloc / ALLOC arena memory) is
// complete.  The ArenaFrame governs only the scratch allocations from the
// tree-building body; the VECSXP rlist and all its child SEXPs are heap-
// allocated and must outlive the ArenaFrame because they are the return
// value.
//
// If any mkChar call in the companion SET_STRING_ELT calls throws RError
// (out of memory), the exception propagates through rpart() and is caught
// at the .Call boundary.  Any SEXP child pointers already written into
// rlist->data are not freed in the error path — this is acceptable; the
// process state for that call is treated as unrecoverable, consistent with
// the analysis in SEXP.md and STRSXP.md.
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

  `SET_VECTOR_ELT` performs no allocation whatsoever. It is a single pointer-array write followed by a return of the written pointer. No heap memory, no arena memory, and no static memory is touched by `SET_VECTOR_ELT` itself.

  The memory objects involved at the call sites in `rpart.c` are:

  1. `rlist` (VECSXP) — heap-allocated via `allocVector(VECSXP, nout)` at line 327. Its `data` field is a `SEXP[nout]` array, also heap-allocated by `allocVector`, zero-initialised (all slots start as `nullptr`). `SET_VECTOR_ELT` writes child SEXP pointers into this array.

  2. Child SEXPs (`which3`, `cptable3`, `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) — each is individually heap-allocated earlier in `rpart()` by `allocVector` or `allocMatrix`. By the time `SET_VECTOR_ELT` is called at lines 330–343, all allocations have already succeeded (or `RError` was thrown earlier). `SET_VECTOR_ELT` copies their pointer values into `rlist->data[i]`; no new memory is allocated.

  3. `R_NilValue` (when `catcount == 0`) — `csplit3` is initialised to `R_NilValue` at `rpart.c:64` and `SET_VECTOR_ELT(rlist, 6, ...)` is only called when `catcount > 0`. When `catcount == 0`, slot 6 of `rlist->data` remains `nullptr` (from zero-initialisation by `allocVector`). `free_sexp` handles `nullptr` slots gracefully with an early-return guard.

  4. Arena (`ArenaFrame`) — completely separate; governs `R_alloc`/`ALLOC` scratch arrays (`ddnode`, `ddsplit`, `iinode`, `iisplit`, `ccsplit`, etc.) used during tree construction earlier in `rpart()`. `SET_VECTOR_ELT` is called after all tree construction is complete; by that point the arena holds live scratch data that is still in use. The arena is freed only when `ArenaFrame` destructs at `.Call` boundary exit, which is after `rpart()` returns `rlist`.

  Memory lifecycle for the output structure:

  1. `allocVector(VECSXP, nout)` — `std::malloc` for the `SEXPREC` node; `std::malloc` for the `SEXP[nout]` slot array (zero-initialised).
  2. `SET_VECTOR_ELT(rlist, i, child_sexp)` — copies the child pointer into `rlist->data[i]`. O(1), no allocation.
  3. Python receives `rlist` as the return value of the `rpart_wrapper` `extern "C"` function.
  4. Python extracts each element by calling `VECTOR_ELT(rlist, i)` and reading the element's data buffer via `INTEGER()` or `REAL()`.
  5. Python calls `free_sexp(rlist)` to recursively free all child SEXPs then `rlist` itself. Python also calls `free_sexp(rname)` independently (since `setAttrib` is a no-op in the fake, `rname` is not owned by `rlist`).

- **Explanation:**

  The fake `SET_VECTOR_ELT` is a two-line inline function:

  ```cpp
  inline SEXP SET_VECTOR_ELT(SEXP x, int i, SEXP v) {
      static_cast<SEXP *>(x->data)[i] = v;
      return v;
  }
  ```

  This works because:

  1. `allocVector(VECSXP, nout)` (documented in `SEXP.md` and `VECSXP.md`) allocates `nout * sizeof(SEXP)` bytes for `rlist->data` — an array of `SEXP` slots, zero-initialised (`nullptr` in each slot). `SET_VECTOR_ELT` writes `v` (any SEXP pointer) into one of those slots.

  2. The cast `static_cast<SEXP *>(x->data)` is valid because `data` is `void *` pointing to the `SEXP[]` array created by `allocVector`, and casting `void *` to `SEXP *` explicitly is legal C++.

  3. The index `i` is an `int` literal (0–6) at all rpart call sites. The real API uses `R_xlen_t` (which maps to `int` in the 32-bit-safe fake per `SEXP.md`); the implicit conversion from the integer literal to `int` is exact.

  4. Returning `v` matches the real `Rinternals.h` signature (`SEXP SET_VECTOR_ELT(...)`). No rpart call site uses the return value, but the correct return type is required for compilation against any client code that does.

  5. No `#define` alias for `SET_VECTOR_ELT` is needed: the real `Rinternals.h` declares it with its exact name (not through a `#define`). The inline function in the fake uses the same name, so `rpart.c` compiles unchanged.

  6. The conditional slot 6 (`if (catcount > 0) { SET_VECTOR_ELT(rlist, 6, csplit3); }`) compiles without special treatment. When `catcount == 0`, `SET_VECTOR_ELT` is never called for slot 6, and `rlist->data[6]` remains `nullptr` from zero-initialisation. Python checks `nout` (which is 6 when `catcount == 0`) before accessing slot 6, so the `nullptr` slot is never read.

  7. The implementation is consistent with `SET_STRING_ELT` (from `SET_STRING_ELT.md`): both use `static_cast<SEXP *>(x->data)[i] = v`. The only structural difference is the return type — `void` for `SET_STRING_ELT`, `SEXP` for `SET_VECTOR_ELT`.

  The overall sequence at `rpart.c:327–347` compiles without modification under `fake_Rinternals.hpp` because every symbol used — `PROTECT`, `allocVector`, `VECSXP`, `STRSXP`, `setAttrib`, `R_NamesSymbol`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, `UNPROTECT` — is defined in the fake header under its exact original name.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The complete `fake_Rinternals.hpp` from `SEXP.md` is the primary prerequisite. It provides: the `SEXPREC` struct layout (`type`, `length`, `nrow`, `ncol`, `data` fields) required so that `static_cast<SEXP *>(x->data)[i] = v` is a valid expression; the `SEXP` typedef (`typedef SEXPREC *SEXP`); the `R_xlen_t` typedef (`typedef int R_xlen_t`) to match the real function signature; `allocVector` (used to allocate the `VECSXP` target `rlist`); the `VECTOR_ELT` and `SET_VECTOR_ELT` inline definitions themselves (Pattern P2, `VECSXP / STRSXP element accessors`); `PROTECT` / `UNPROTECT` no-ops; `R_NilValue` (the default value of `csplit3`); and the `free_sexp` utility that recurses into `VECSXP` children and frees each child SEXP stored by `SET_VECTOR_ELT`. |
| `VECSXP.md` | Establishes `#define VECSXP 19` within the SEXPTYPE constant block and documents the `allocVector(VECSXP, nout)` allocation that creates the `rlist` target object written by `SET_VECTOR_ELT`. Confirms that `sexptype_element_size(VECSXP)` returns `sizeof(SEXP)`, so `allocVector(VECSXP, n)` allocates a `SEXP[n]` slot array. Also provides the amended `free_sexp` form that recurses into both `VECSXP` and `STRSXP` children — required so that the child SEXPs stored by `SET_VECTOR_ELT` are freed when Python calls `free_sexp(rlist)`. |
| `SET_STRING_ELT.md` | Documents the structurally parallel `SET_STRING_ELT` mutator for `STRSXP` objects. The `SET_STRING_ELT(rname, i, mkChar(...))` calls appear at every alternate line in the same `rpart.c:330–344` block as `SET_VECTOR_ELT`. Both must be present in `fake_Rinternals.hpp` for the entire output-construction block to compile as a unit. Confirms the identical `static_cast<SEXP *>(x->data)[i] = v` implementation pattern. |
| `PROTECT.md` | Documents `PROTECT` / `UNPROTECT` as no-op identity / void functions. Required because `rlist` is wrapped in `PROTECT` at `rpart.c:327` — one line before the first `SET_VECTOR_ELT` call — and `UNPROTECT(1 + nout)` appears at line 347 after the last call. Both must compile and execute correctly for the output block to function. |
| `STRSXP.md` | Establishes `#define STRSXP 16` and documents `allocVector(STRSXP, nout)` (the `rname` allocation at `rpart.c:328`). Also provides the amended `free_sexp` that recurses into `STRSXP` children — required so that the `CHARSXP` nodes written into `rname` by the companion `SET_STRING_ELT` calls are freed. `rname` must be freed separately via `free_sexp(rname)` since `setAttrib` is a no-op and `rname` is not owned by `rlist`. |
| `R_NamesSymbol.md` | Documents `R_NamesSymbol` and the no-op `setAttrib` / `Rf_setAttrib` used at `rpart.c:329`, the line immediately before the first `SET_VECTOR_ELT` call. These must be defined in `fake_Rinternals.hpp` before the output-construction block is compiled. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` boundary wrapper (shown above) for the `ArenaFrame` RAII guard. `SET_VECTOR_ELT` itself has no arena dependency, but the enclosing `rpart()` function uses `R_alloc`/`ALLOC` scratch memory throughout its tree-building body and therefore requires `ArenaFrame _frame;` at the `.Call` boundary. `fake_arena.hpp` is generated once as a foundational file referenced by all memory-related guides. |
