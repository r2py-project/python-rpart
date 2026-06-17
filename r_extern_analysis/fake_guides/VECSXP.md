# Fake Header Implementation Guide: `VECSXP`

---

### 1. Overview of `VECSXP` in R API

`VECSXP` is an integer constant with value `19` that serves as the `SEXPTYPE` tag for generic vector (list) objects in R's C API. It is defined in `Rinternals.h` as `#define VECSXP 19` (non-`enum_SEXPTYPE` branch) or `VECSXP = 19` (enum branch). A `VECSXP` object is a `SEXPREC` node whose `data` field holds a flat `SEXP[length]` array — each element is a pointer to a child `SEXPREC` of any type (`INTSXP`, `REALSXP`, `STRSXP`, `NILSXP`, etc.). It is the C-level representation of an R `list()`. Elements are written through `SET_VECTOR_ELT(vec, i, child_sexp)` and read back through `VECTOR_ELT(vec, i)`. In rpart, `VECSXP` is used to construct the named output list returned from the top-level `.Call` function `rpart()`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines | Context |
|---|---|---|
| `rpart.c` | 312–349 | Output-list construction block: `VECSXP` list allocated, populated with `SET_VECTOR_ELT`, returned as the `.Call` result |

The single CSV row is at `rpart.c:327`. Reading 15 lines above and below exposes the complete pattern:

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    // line 327  <- CSV row
SEXP rname = allocVector(STRSXP, nout);              // line 328
setAttrib(rlist, R_NamesSymbol, rname);              // line 329
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

**Argument and return types observed.**

`VECSXP` is passed as the first argument to `allocVector`, declared in `Rinternals.h` as:

```c
SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length);
```

`VECSXP` is of type `SEXPTYPE` (defined as `typedef unsigned int SEXPTYPE` in the non-enum branch). The return value is a `SEXP` (`SEXPREC *`), immediately wrapped in `PROTECT` and assigned to the local variable `rlist`. After allocation, `rlist` is populated by repeated `SET_VECTOR_ELT(rlist, i, child_sexp)` calls and then returned as the `.Call` return value.

The child SEXPs written into `rlist` are:

| Slot | Variable | Type |
|---|---|---|
| 0 | `which3` | `INTSXP` (1-D integer vector, length `n`) |
| 1 | `cptable3` | `REALSXP` (2-D real matrix) |
| 2 | `dsplit3` | `REALSXP` (2-D real matrix) |
| 3 | `isplit3` | `INTSXP` (2-D integer matrix) |
| 4 | `dnode3` | `REALSXP` (2-D real matrix) |
| 5 | `inode3` | `INTSXP` (2-D integer matrix) |
| 6 | `csplit3` | `INTSXP` (2-D integer matrix, conditional) or `R_NilValue` |

All child SEXPs were heap-allocated earlier in the same function body via `allocVector` / `allocMatrix`; they are alive at the time `SET_VECTOR_ELT` is called.

**Co-occurring R API items in context window.**

- `PROTECT` / `UNPROTECT` — `rlist` is wrapped in `PROTECT` at line 327; `UNPROTECT(1 + nout)` at line 347 unwinds `rlist` (1) plus the `nout` previously PROTECTed child SEXPs. In the fake runtime both are no-ops.
- `allocVector(STRSXP, nout)` at line 328 — allocates the parallel names vector `rname`. Documented in `STRSXP.md`.
- `setAttrib(rlist, R_NamesSymbol, rname)` at line 329 — attaches the names vector as an attribute. In the fake runtime this is a no-op; Python reads elements by positional index.
- `SET_VECTOR_ELT(rlist, i, child)` — writes child SEXP pointers into `rlist->data[i]`. Documented in `SEXP.md` (Pattern P2, `VECSXP / STRSXP element accessors`).
- `SET_STRING_ELT(rname, i, mkChar("..."))` — populates the `rname` STRSXP in parallel. Documented in `STRSXP.md`.
- `R_NilValue` — assigned as the default value of `csplit3` at `rpart.c:64` before the conditional allocation; passed to `SET_VECTOR_ELT(rlist, 6, csplit3)` when `catcount == 0`. Documented in `SEXP.md`.

**Distinct usage patterns.**

Only one structural pattern appears across all rpart source files:

1. **1-D generic list allocation used as the `.Call` return value** (`allocVector(VECSXP, nout)`): allocate a VECSXP of `nout` slots, populate each slot with a pre-allocated SEXP child via `SET_VECTOR_ELT`, attach a parallel `STRSXP` names vector via `setAttrib` (no-op in fake), and return the VECSXP as the function result.

There is no second pattern (e.g., reading elements from an input VECSXP parameter, or allocating a VECSXP of VECSXP children). The `rlist` object is write-only from the C side; it is constructed and immediately returned.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`VECSXP` is a named integer constant used solely as a type tag passed to `allocVector`. Its fake implementation is a single `#define` macro consistent with the non-`enum_SEXPTYPE` branch of `Rinternals.h`. No runtime logic lives inside `VECSXP` itself; all behavior belongs to `allocVector` (which allocates the `SEXP[length]` data buffer), `SET_VECTOR_ELT` and `VECTOR_ELT` (which read and write child pointer slots), and `free_sexp` (which recursively frees child nodes at teardown time).

**Chosen mechanism.** Following the pattern established in `INTSXP.md`, `REALSXP.md`, and `STRSXP.md`, the fake header defines `SEXPTYPE` as `typedef unsigned int SEXPTYPE` and provides each type tag as a `#define` macro. `VECSXP` is defined as `#define VECSXP 19`. This constant is already present in the complete `SEXPTYPE` block documented in `SEXP.md` (the authoritative source for `fake_Rinternals.hpp`). No separate block or file is required; `#define VECSXP 19` is one line within the block already established.

**How `VECSXP` interacts with the fake `SEXPREC` layout.** The `SEXP.md` guide specifies (Pattern P2, `VECSXP / STRSXP element accessors`) that for `VECSXP` objects, `SEXPREC.data` holds a `SEXP[length]` array. This is already implemented in `fake_Rinternals.hpp`:

- `sexptype_element_size(VECSXP)` returns `sizeof(SEXP)` (already in the `sexptype_element_size` switch in `SEXP.md`).
- `allocVector(VECSXP, n)` allocates `n * sizeof(SEXP)` bytes for `data` and zero-initializes it (all child pointer slots start as `nullptr`).
- `SET_VECTOR_ELT(rlist, i, v)` writes `v` into `((SEXP *)rlist->data)[i]`.
- `VECTOR_ELT(rlist, i)` reads `((SEXP *)rlist->data)[i]`.

Both `SET_VECTOR_ELT` and `VECTOR_ELT` are already defined in `fake_Rinternals.hpp` per `SEXP.md`.

**`free_sexp` interaction.** The `free_sexp` utility in `fake_Rinternals.hpp` (from `SEXP.md`, amended by `STRSXP.md`) already recurses into `VECSXP` children:

```cpp
if (s->type == VECSXP || s->type == EXPRSXP || s->type == STRSXP) {
    SEXP *elems = static_cast<SEXP *>(s->data);
    for (int i = 0; i < s->length; i++)
        free_sexp(elems[i]);
}
```

When `free_sexp(rlist)` is called by the Python caller after data extraction, it recursively frees each child SEXP (`which3`, `cptable3`, etc.) before freeing the `SEXP[nout]` data array and the `SEXPREC` node itself. Note that `rname` (the STRSXP names vector) is **not** stored inside `rlist->data` in the fake runtime (because `setAttrib` is a no-op), so `rname` must be freed separately via `free_sexp(rname)`. The amended `free_sexp` from `STRSXP.md` handles `rname`'s `CHARSXP` children correctly.

**`#define` aliases that must be preserved.** The real `Rinternals.h` declares:

```c
SEXP (VECTOR_ELT)(SEXP x, R_xlen_t i);
SEXP SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v);
```

No `#define` macros wrap `VECSXP` itself. The type tag is used directly as an integer constant argument to `allocVector`. All function-level aliases needed by rpart (`SET_VECTOR_ELT`, `VECTOR_ELT`) are already defined as inline functions in `fake_Rinternals.hpp` per `SEXP.md`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not directly triggered by `VECSXP` the constant. `allocVector` (called with `VECSXP`) throws `RError` on `std::malloc` failure; that behavior is already present in `fake_Rinternals.hpp`.
- Invariant 2 (arena memory): not triggered. `VECSXP` vectors and all their child SEXPs are heap-allocated via `std::malloc`, not arena-allocated. The `rlist` VECSXP is the `.Call` return value and must outlive the `ArenaFrame` that governs `R_alloc`/`ALLOC` scratch memory in the same function body.
- Invariant 3 (R Interpreter Items): not triggered. `VECSXP` is a compile-time integer constant with no runtime interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern: Allocate Generic List as `.Call` Return Value

- **Locations:** `rpart.c:327`

- **Original R API Usage:**

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
SET_VECTOR_ELT(rlist, 0, which3);        /* INTSXP child */
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);      /* REALSXP child */
SET_STRING_ELT(rname, 1, mkChar("cptable"));
/* ... pattern repeats for slots 2-5 ... */
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);   /* INTSXP child, conditional */
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// The following definitions are required to support the VECSXP usage
// pattern in rpart.c.  They either already appear in fake_Rinternals.hpp
// (per SEXP.md and STRSXP.md) or are confirmed present here.
// Annotations indicate which prior guide introduced each piece.

// -----------------------------------------------------------------------
// SEXPTYPE constant — already defined in the SEXPTYPE block from SEXP.md.
// Reproduced here for reference; do NOT redefine if SEXP.md is included.
// -----------------------------------------------------------------------
// #define VECSXP   19    /* generic vectors (lists) — element type is SEXP* */
// (Present in the full SEXPTYPE block in fake_Rinternals.hpp.)

// -----------------------------------------------------------------------
// sexptype_element_size — already defined in SEXP.md.
// For VECSXP the element size is sizeof(SEXP) = sizeof(SEXPREC *).
// allocVector(VECSXP, n) therefore allocates n * sizeof(SEXP) bytes for
// data and zero-initializes the slot array (all child pointers == nullptr).
// -----------------------------------------------------------------------
// inline std::size_t sexptype_element_size(SEXPTYPE type) {
//     ...
//     case STRSXP:  case VECSXP:  case EXPRSXP:  return sizeof(SEXP);
//     ...
// }

// -----------------------------------------------------------------------
// allocVector — already defined in SEXP.md.
// allocVector(VECSXP, nout) produces a SEXP with:
//   s->type   = VECSXP (19)
//   s->length = nout
//   s->nrow   = nout
//   s->ncol   = 1
//   s->data   = SEXP[nout], zero-initialized (each slot == nullptr)
// -----------------------------------------------------------------------
// inline SEXP allocVector(SEXPTYPE type, int length) { ... }

// -----------------------------------------------------------------------
// SET_VECTOR_ELT / VECTOR_ELT — already defined in SEXP.md.
// Confirmed interface:
//   SEXP SET_VECTOR_ELT(SEXP s, int i, SEXP v)
//     writes v into ((SEXP*)s->data)[i] and returns v.
//   SEXP VECTOR_ELT(SEXP s, int i)
//     reads ((SEXP*)s->data)[i].
// -----------------------------------------------------------------------
// inline SEXP VECTOR_ELT(SEXP s, int i) {
//     return static_cast<SEXP *>(s->data)[i];
// }
// inline SEXP SET_VECTOR_ELT(SEXP s, int i, SEXP v) {
//     static_cast<SEXP *>(s->data)[i] = v;
//     return v;
// }

// -----------------------------------------------------------------------
// free_sexp — amended form required by STRSXP.md.
// The VECSXP branch is already present in the original SEXP.md version;
// STRSXP.md added the STRSXP branch.  The complete correct form is:
// -----------------------------------------------------------------------
inline void free_sexp(SEXP s) {
    if (!s) return;
    // Recurse into container types whose data[] is a SEXP[] child array.
    if (s->type == VECSXP || s->type == EXPRSXP || s->type == STRSXP) {
        SEXP *elems = static_cast<SEXP *>(s->data);
        for (int i = 0; i < s->length; i++)
            free_sexp(elems[i]);
    }
    std::free(s->data);
    std::free(s);
}

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — showing ArenaFrame placement.
//
// rpart() mixes SEXP allocations (heap: which3, cptable3, rlist, rname,
// etc.) with R_alloc/ALLOC scratch allocations (arena: rp.ydata, rp.xdata,
// savesort, etc.) in the same function body.  The ArenaFrame RAII guard
// manages only the arena-allocated scratch memory; it does not affect the
// heap-allocated SEXP objects.
//
// rlist (VECSXP) is the return value of rpart() and must outlive the
// ArenaFrame destruction.  Python receives a SEXP* and is responsible for:
//   1. Extracting data from each child SEXP by positional index:
//        VECTOR_ELT(rlist, 0)  -> which3  (INTSXP, use INTEGER())
//        VECTOR_ELT(rlist, 1)  -> cptable3 (REALSXP, use REAL())
//        VECTOR_ELT(rlist, 2)  -> dsplit3 (REALSXP)
//        VECTOR_ELT(rlist, 3)  -> isplit3 (INTSXP)
//        VECTOR_ELT(rlist, 4)  -> dnode3  (REALSXP)
//        VECTOR_ELT(rlist, 5)  -> inode3  (INTSXP)
//        VECTOR_ELT(rlist, 6)  -> csplit3 (INTSXP) or R_NilValue
//   2. Calling free_sexp(rlist) after extraction to release rlist and all
//      child SEXPs it owns.
//   3. Calling free_sexp(rname) separately (setAttrib is a no-op in the
//      fake, so rname is NOT owned by rlist).
//
// extern "C" SEXP rpart_wrapper(
//         SEXP ncat2, SEXP method2, SEXP opt2,
//         SEXP parms2, SEXP xvals2, SEXP xgrp2,
//         SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
//     ArenaFrame _frame;   // frees R_alloc/ALLOC scratch at function exit
//     try {
//         return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                      ymat2, xmat2, wt2, ny2, cost2);
//     } catch (const RError &e) {
//         set_python_error(e.what());
//         return R_NilValue;
//     }
// }
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  The `rlist` VECSXP node, its `SEXP[nout]` data array, and all child SEXPs written into it (`which3`, `cptable3`, `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) are all **heap-allocated** via `std::malloc`. None of them participate in the arena. The reasons are:

  1. `rlist` is the `.Call` return value. It must survive past the `ArenaFrame` destructor that runs at the `.Call` boundary.
  2. Each child SEXP (`which3`, etc.) was itself heap-allocated earlier in `rpart()` by `allocVector` / `allocMatrix`. Those allocations also do not use the arena.
  3. The `SEXP[nout]` slot array inside `rlist->data` is allocated by `allocVector` via `std::malloc(nout * sizeof(SEXP))` and is freed by `free_sexp(rlist)` after Python extracts the data.

  The arena (`fake_arena.hpp`, via `ArenaFrame _frame` in the wrapper) exclusively governs scratch memory allocated with `R_alloc` / `ALLOC` inside `rpart()`'s tree-building body — arrays such as `rp.ydata`, `rp.xdata`, `savesort`, `rp.sorts`, `ddnode`, `ddsplit`, and similar temporary pointer arrays. These are completely independent of the VECSXP output construction. They are freed automatically when `_frame` destructs on return from `rpart_wrapper`.

  Memory lifecycle for `rlist`:
  1. `allocVector(VECSXP, nout)` — `std::malloc` for the `SEXPREC` node and `std::malloc` for the `SEXP[nout]` slot array. Both succeed or `RError` is thrown.
  2. `SET_VECTOR_ELT(rlist, i, child_sexp)` — stores the pointer value of each child SEXP into `rlist->data[i]`. No allocation; this is a pointer copy.
  3. Python receives `rlist` as the return value of the `rpart_wrapper` `extern "C"` function.
  4. Python extracts each element by calling `VECTOR_ELT(rlist, i)` and then reading the element's data via `INTEGER()` or `REAL()`.
  5. Python calls `free_sexp(rlist)` to recursively free all child SEXPs and then the `rlist` node itself. Python also calls `free_sexp(rname)` independently.

  If `allocVector(VECSXP, nout)` fails (either `std::malloc` call returns `nullptr`), `RError` is thrown. At that point the child SEXPs (`which3`, `cptable3`, etc.) have already been heap-allocated and are not freed — this is acceptable because in an error path the `.Call` wrapper catches the exception, returns `R_NilValue` as the sentinel, and the process-level state for that call is treated as unrecoverable. In production usage the subsequent Python exception causes the call to be aborted and the process continues.

- **Explanation:**

  `VECSXP` itself is purely a compile-time constant `19`. It requires no runtime logic beyond being defined as `#define VECSXP 19` in the `SEXPTYPE` block of `fake_Rinternals.hpp`. That constant is already present in the block established by `SEXP.md`.

  The complete fake implementation for the VECSXP usage pattern in `rpart.c` is provided by the following combination, all already defined in `fake_Rinternals.hpp`:

  1. `#define VECSXP 19` — in the SEXPTYPE constant block.
  2. `sexptype_element_size(VECSXP)` returning `sizeof(SEXP)` — so `allocVector(VECSXP, n)` allocates a `SEXP[n]` child-pointer array.
  3. `allocVector` — heap-allocates `SEXPREC` node and `SEXP[nout]` data buffer; sets `s->type = VECSXP`, `s->length = nout`, `s->nrow = nout`, `s->ncol = 1`; zero-initializes data.
  4. `SET_VECTOR_ELT` and `VECTOR_ELT` — already defined as inline functions for write and read access to child SEXP slots.
  5. `PROTECT` / `UNPROTECT` — no-op identity and no-op void; `PROTECT(allocVector(VECSXP, nout))` evaluates to `allocVector(VECSXP, nout)` unchanged.
  6. `free_sexp` — already recurses into `VECSXP` children (from `SEXP.md`; confirmed correct in `STRSXP.md`'s amended form).
  7. `R_NilValue` — the nil singleton, used as the default value of `csplit3`. When `catcount == 0`, `SET_VECTOR_ELT(rlist, 6, csplit3)` is not called; `rlist->data[6]` remains `nullptr` (from zero-initialization). This is safe because Python checks `nout` before accessing slot 6.

  The original `rpart.c` source compiles without modification because every symbol it uses at lines 327–348 (`VECSXP`, `allocVector`, `PROTECT`, `UNPROTECT`, `SET_VECTOR_ELT`, `setAttrib`, `R_NamesSymbol`) is present in `fake_Rinternals.hpp` under the same name and with the same visible signature.

  Note on `PROTECT(allocVector(VECSXP, nout))` vs bare `allocVector(VECSXP, nout)`: the `PROTECT` macro expands to `Rf_protect(...)`, which is the identity function in the fake. The surrounding `SEXP rlist = PROTECT(allocVector(VECSXP, nout))` is therefore identical to `SEXP rlist = allocVector(VECSXP, nout)` at runtime. The paired `UNPROTECT(1 + nout)` at line 347 is a no-op call to `Rf_unprotect(1 + nout)`. Neither changes any state.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The complete `fake_Rinternals.hpp` established by `SEXP.md` is the primary dependency. It provides: `SEXPREC` struct layout (`type`, `length`, `nrow`, `ncol`, `data` fields); `SEXP` typedef; `sexptype_element_size` (which already includes the `VECSXP` case returning `sizeof(SEXP)`); `allocVector` (used as `allocVector(VECSXP, nout)` at `rpart.c:327`); `SET_VECTOR_ELT` and `VECTOR_ELT` (the read/write accessors for VECSXP elements); `setAttrib` and `R_NamesSymbol` (no-op attribute attachment); `PROTECT`/`UNPROTECT` no-ops; `R_NilValue` (used as the default value of `csplit3`); and the original `free_sexp` (which already recurses into `VECSXP` children). |
| `STRSXP.md` | Provides the amended `free_sexp` that adds `STRSXP` to the recursive-free branch alongside `VECSXP`. Also defines `allocVector(STRSXP, nout)` (the parallel `rname` allocation at `rpart.c:328`), `SET_STRING_ELT` / `STRING_ELT` / `mkChar` / `R_NaString` / `R_BlankString` / `R_BlankScalarString`. All of these appear in the same function body (`rpart.c:325-349`) and must be present in `fake_Rinternals.hpp` for the translation unit to compile. |
| `INTSXP.md` | Establishes `#define INTSXP 13` within the SEXPTYPE constant block that also contains `#define VECSXP 19`. The child SEXPs written into `rlist` slots 0, 3, 4, 5, and (conditionally) 6 are `INTSXP` objects; `INTEGER(child_sexp)` is used elsewhere in `rpart()` to populate them before they are stored in `rlist`. |
| `REALSXP.md` | Establishes `#define REALSXP 14` in the same SEXPTYPE block. The child SEXPs written into `rlist` slots 1, 2, and 4 are `REALSXP` objects; `REAL(child_sexp)` is used elsewhere in `rpart()` to populate them. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` entry-point for the `ArenaFrame` RAII guard. `VECSXP` allocations themselves do not use the arena, but the `rpart()` function body uses `R_alloc`/`ALLOC` extensively for scratch arrays and therefore requires `ArenaFrame` at the call boundary. `fake_arena.hpp` is generated once as a foundational file referenced by all memory-related guides. |
