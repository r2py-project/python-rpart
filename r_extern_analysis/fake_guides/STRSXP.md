# Fake Header Implementation Guide: `STRSXP`

---

### 1. Overview of `STRSXP` in R API

`STRSXP` is an integer constant with value `16` that serves as the `SEXPTYPE` tag for string vector objects in R's C API. It is defined in `Rinternals.h` as `#define STRSXP 16` (or `STRSXP = 16` in the `enum_SEXPTYPE` branch). A `STRSXP` object is a `SEXPREC` node whose `data` field holds an array of `SEXP` child pointers, where each child is a `CHARSXP` (type tag `9`) — a scalar-string node whose own `data` field is a `char *` to a null-terminated C string. `STRSXP` is used exclusively as the first argument to `allocVector(STRSXP, n)` to allocate a length-`n` character vector; elements are written through `SET_STRING_ELT(vec, i, mkChar("..."))` and read back through `STRING_ELT(vec, i)`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines | Context |
|---|---|---|
| `rpart.c` | 325–348 | Output-list construction block: `STRSXP` name vector allocated, populated with `SET_STRING_ELT` / `mkChar`, attached to a `VECSXP` list via `setAttrib` |

The single CSV row is at `rpart.c:328`. Reading 15 lines above and below exposes the full usage pattern:

```c
/* rpart.c:325-348 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));   // line 327
SEXP rname = allocVector(STRSXP, nout);             // line 328  ← CSV row
setAttrib(rlist, R_NamesSymbol, rname);             // line 329
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));          // line 331
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
    SET_STRING_ELT(rname, 6, mkChar("csplit"));     // line 344
}
UNPROTECT(1 + nout);
return rlist;
```

**Argument and return types observed.**

`STRSXP` is passed as the first argument to `allocVector`, declared in `Rinternals.h` as:

```c
SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length);
```

`STRSXP` is of type `SEXPTYPE` (defined as `typedef unsigned int SEXPTYPE`). The return value is a `SEXP` (`SEXPREC *`), assigned to the local variable `rname`. The allocated SEXP is then used as the target of `SET_STRING_ELT(rname, i, mkChar("..."))` calls, which write `CHARSXP` child pointers into slots `0` through `nout-1`.

**Co-occurring R API items in context window.**

- `allocVector(VECSXP, nout)` — allocates the parent generic list on the line immediately before `rname`. This is documented in `SEXP.md` (Pattern P2). The `rname` STRSXP is attached to it via `setAttrib`.
- `setAttrib(rlist, R_NamesSymbol, rname)` — attaches `rname` as the `names` attribute of `rlist`. In the fake runtime this is a no-op; the Python caller reads SEXP elements by positional index, not by name lookup. Documented in `SEXP.md`.
- `SET_STRING_ELT(rname, i, mkChar("..."))` — writes a CHARSXP child pointer at slot `i`. These two functions are the only runtime operations performed on `rname` after allocation. `mkChar` is documented in `SEXP.md` (Pattern P2) as part of `fake_Rinternals.hpp`.
- `PROTECT` / `UNPROTECT` — `rname` itself is **not** wrapped in `PROTECT` (only `rlist` is, at line 327). `UNPROTECT(1 + nout)` at line 347 unwinds `rlist` plus the `nout` previously PROTECTed SEXP children (`which3`, `cptable3`, etc.). In the fake runtime all PROTECT/UNPROTECT calls are no-ops.
- `mkChar(const char *)` — creates a `CHARSXP` from a string literal. Already faked in `fake_Rinternals.hpp` per `SEXP.md`.
- `R_NamesSymbol` — a sentinel `SYMSXP` SEXP used as the attribute key. Already faked as a static `SEXPREC` in `fake_Rinternals.hpp` per `SEXP.md`.

**Distinct usage patterns.**

Only one structural pattern appears across all occurrences in the codebase:

1. **1-D string vector allocation used as a names attribute** (`allocVector(STRSXP, nout)`): allocate a STRSXP of `nout` slots, populate each slot with a `CHARSXP` via `SET_STRING_ELT`/`mkChar`, then attach to a `VECSXP` via `setAttrib`. This is the only STRSXP pattern in all rpart source files.

There is no second pattern (e.g., reading back string elements via `STRING_ELT`, or using `STRSXP` as an input parameter). The `rname` object is write-only from the C side; it is constructed and immediately embedded into the return value.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`STRSXP` is a named integer constant used solely as a type tag passed to `allocVector`. Its fake implementation is a single `#define` macro consistent with the non-`enum_SEXPTYPE` branch of `Rinternals.h`.

**Chosen mechanism.** Following the pattern established in `INTSXP.md` and `REALSXP.md`, `STRSXP` is defined as `#define STRSXP 16` within the complete `SEXPTYPE` constant block in `fake_Rinternals.hpp`. This is already present in the `SEXP.md` guide (see the SEXPTYPE block at lines 191–221 of that guide's code listing). `STRSXP` itself requires no runtime implementation logic — it is a pure compile-time integer constant.

**How `STRSXP` interacts with the fake `SEXPREC` layout.** The `SEXP.md` guide specifies that for `STRSXP` (and `VECSXP`, `EXPRSXP`) objects, the `data` field of `SEXPREC` holds a `SEXP[length]` array — a flat array of child `SEXP` pointers, each of which is itself a heap-allocated `SEXPREC`. This is set up by `allocVector` when called with `type == STRSXP`:

- `sexptype_element_size(STRSXP)` returns `sizeof(SEXP)` (already defined in `SEXP.md`).
- `allocVector(STRSXP, n)` allocates `n * sizeof(SEXP)` bytes for `data` and zero-initializes it (so all child pointer slots start as `nullptr`).
- `SET_STRING_ELT(rname, i, v)` writes `v` (a `CHARSXP` pointer returned by `mkChar`) into `((SEXP *)rname->data)[i]`.
- `STRING_ELT(rname, i)` reads `((SEXP *)rname->data)[i]` back.

Both `SET_STRING_ELT` and `STRING_ELT` are already defined in `fake_Rinternals.hpp` per `SEXP.md` (Pattern P2, the `VECSXP / STRSXP element accessors` block).

**`free_sexp` interaction.** The `free_sexp` utility in `fake_Rinternals.hpp` (also from `SEXP.md`) recursively frees children for `VECSXP` and `EXPRSXP` but not for `STRSXP`. This is intentional: `rname` is embedded into `rlist` (a `VECSXP`) via `setAttrib`, but in the fake runtime `setAttrib` is a no-op, so `rname` is **not** tracked inside `rlist->data`. The Python caller is responsible for calling `free_sexp(rname)` separately if it retains a reference to `rname` independent of `rlist`. In practice, because `setAttrib` is a no-op and the Python caller reads names by positional index from `rlist`, `rname` can simply be freed via `free_sexp(rname)` at the same time as `free_sexp(rlist)`. The `mkChar` CHARSXP children stored in `rname->data` are freed by `free_sexp(rname)` because `free_sexp` calls `std::free(s->data)` (which frees the `SEXP[]` array) but does **not** recursively free the `CHARSXP` elements. To avoid leaking the `CHARSXP` nodes, `free_sexp` should be extended to handle `STRSXP` analogously to `VECSXP`. This is noted in the implementation example below.

**`#define` aliases that must be preserved.** `Rinternals.h` defines:

```c
#define mkChar       Rf_mkChar
#define mkCharCE     Rf_mkCharCE
#define mkCharLen    Rf_mkCharLen
#define mkCharLenCE  Rf_mkCharLenCE
#define mkString     Rf_mkString
#define CHAR(x)      R_CHAR(x)
#define NA_STRING    R_NaString
```

All of these must be present in `fake_Rinternals.hpp` so that the original source files compile unchanged. `mkChar` and `CHAR` are already in `fake_Rinternals.hpp` per `SEXP.md`. `NA_STRING`, `R_NaString`, `R_BlankString`, and `R_BlankScalarString` must also be defined; none are used in rpart's C source files, but any include of `Rinternals.h` through `rpart.h` or similar headers will see their `LibExtern SEXP R_NaString;` declaration and require a definition.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `STRSXP` the constant. `allocVector` (called with `STRSXP`) and `mkChar` throw `RError` on `std::malloc` failure; that behavior is already handled in `fake_Rinternals.hpp`.
- Invariant 2 (arena memory): not triggered. `STRSXP` vectors and their `CHARSXP` children are heap-allocated via `std::malloc`, not arena-allocated. They must outlive the `ArenaFrame` because `rname` is (conceptually) the `names` attribute of the returned `rlist`.
- Invariant 3 (R Interpreter Items): not triggered. `STRSXP` is a compile-time constant; it has no runtime interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern: Allocate 1-D String Vector as Names Attribute

- **Locations:** `rpart.c:328` (the sole CSV row; `SET_STRING_ELT` calls at `rpart.c:331`, `333`, `335`, `337`, `339`, `341`, `344` complete the usage pattern)

- **Original R API Usage:**

```c
/* rpart.c:326-348 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);          // allocate string vector
setAttrib(rlist, R_NamesSymbol, rname);           // attach as names attribute

SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));       // write CHARSXP into slot 0

SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));

/* ... pattern repeats for slots 2-5 ... */

if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// The following definitions are required to support the STRSXP usage
// pattern.  They either already appear in fake_Rinternals.hpp (per SEXP.md)
// or must be confirmed present.  Annotations indicate their origin.

// -----------------------------------------------------------------------
// SEXPTYPE constant — already defined in the SEXPTYPE block from SEXP.md.
// Reproduced here for clarity; do NOT redefine if SEXP.md is already included.
// -----------------------------------------------------------------------
// #define STRSXP   16    /* string vectors  — element type is SEXP (CHARSXP*) */
// #define CHARSXP   9    /* scalar string   — element type is char*           */
// (Both are present in the full SEXPTYPE block in fake_Rinternals.hpp.)

// -----------------------------------------------------------------------
// sexptype_element_size — already defined in SEXP.md.
// For STRSXP the element size is sizeof(SEXP) = sizeof(SEXPREC *).
// allocVector(STRSXP, n) therefore allocates n * sizeof(SEXP) bytes for
// data and zero-initializes the slot array.
// -----------------------------------------------------------------------
// inline std::size_t sexptype_element_size(SEXPTYPE type) {
//     ...
//     case STRSXP:  case VECSXP:  case EXPRSXP:  return sizeof(SEXP);
//     ...
// }

// -----------------------------------------------------------------------
// SET_STRING_ELT / STRING_ELT — already defined in SEXP.md.
// Confirmed interface:
//   void SET_STRING_ELT(SEXP s, int i, SEXP v)
//     writes v (a CHARSXP) into ((SEXP*)s->data)[i].
//   SEXP STRING_ELT(SEXP s, int i)
//     reads ((SEXP*)s->data)[i].
// The real Rinternals.h declares SET_STRING_ELT with R_xlen_t index;
// rpart only uses int indices, so the fake uses int for simplicity.
// -----------------------------------------------------------------------
// inline SEXP STRING_ELT(SEXP s, int i) {
//     return static_cast<SEXP *>(s->data)[i];
// }
// inline void SET_STRING_ELT(SEXP s, int i, SEXP v) {
//     static_cast<SEXP *>(s->data)[i] = v;
// }

// -----------------------------------------------------------------------
// mkChar — already defined in SEXP.md.
// Creates a heap-allocated CHARSXP from a C string literal.
// Throws RError on std::malloc failure.
// -----------------------------------------------------------------------
// inline SEXP mkChar(const char *str) { ... }
// #define mkChar Rf_mkChar   // alias — Rinternals.h line 1020

// -----------------------------------------------------------------------
// free_sexp — AMENDMENT REQUIRED relative to SEXP.md.
//
// The SEXP.md version of free_sexp recurses into VECSXP and EXPRSXP
// children but not STRSXP children.  The rname STRSXP stores CHARSXP
// nodes produced by mkChar; without explicit recursion these nodes leak.
//
// Replace the free_sexp body in fake_Rinternals.hpp with the version
// below, which adds STRSXP to the recursive-free branch:
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
// R_NaString / R_BlankString / R_BlankScalarString
//
// Declared as LibExtern SEXP in Rinternals.h lines 469-471.
// Not used in any rpart C source file, but the declarations are visible
// to any translation unit that includes Rinternals.h.  The fake must
// provide definitions so the linker does not fail.
//
// NA_STRING is #defined as R_NaString (Rinternals.h line 468).
// In the fake runtime these are static CHARSXP / STRSXP sentinels.
// -----------------------------------------------------------------------
inline SEXP make_na_string_charsxp() {
    // CHARSXP for NA — used as NA_STRING sentinel
    static char na_data[] = "NA";
    static SEXPREC na_rec = { CHARSXP, 2, 2, 1, static_cast<void *>(na_data) };
    return &na_rec;
}
static SEXP R_NaString = make_na_string_charsxp();
#define NA_STRING R_NaString

inline SEXP make_blank_string_charsxp() {
    static char blank_data[] = "";
    static SEXPREC blank_rec = { CHARSXP, 0, 0, 1, static_cast<void *>(blank_data) };
    return &blank_rec;
}
static SEXP R_BlankString = make_blank_string_charsxp();

// R_BlankScalarString is a length-1 STRSXP wrapping R_BlankString.
// Implemented lazily — if rpart never uses it, the static is never built.
inline SEXP make_blank_scalar_string() {
    static SEXP child     = make_blank_string_charsxp();
    static SEXP slot_arr  = &child;   // SEXP[1] stored inline
    static SEXPREC bss    = { STRSXP, 1, 1, 1, static_cast<void *>(&slot_arr) };
    return &bss;
}
static SEXP R_BlankScalarString = make_blank_scalar_string();

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — showing ArenaFrame placement.
//
// rpart() is the only function that uses allocVector(STRSXP, ...).
// The ArenaFrame manages R_alloc/ALLOC scratch memory inside rpart();
// the STRSXP rname and the VECSXP rlist are heap-allocated and survive
// the ArenaFrame because they are embedded in the returned rlist SEXP.
//
// Python reads the returned rlist by positional index:
//   rlist->data[0] == which3  (INTSXP)
//   rlist->data[1] == cptable3 (REALSXP)
//   ... etc.
// rname is attached via setAttrib which is a no-op in the fake; Python
// does not need it. Both rlist and rname must be freed by Python after
// data extraction via free_sexp(rlist) and free_sexp(rname).
// -----------------------------------------------------------------------
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
```

- **Arena / Memory Notes:**

  The `rname` STRSXP and all `CHARSXP` children created by `mkChar` are **heap-allocated** via `std::malloc`. They are not arena-managed. The reasons are identical to those given in `SEXP.md` for `rlist`: the `rname` object must outlive the `ArenaFrame` destruction at the `.Call` boundary because it is (notionally) part of the return structure.

  The `ArenaFrame` in the `.Call` wrapper for `rpart()` governs only the `R_alloc`/`ALLOC` scratch arrays inside the function body (e.g., `rp.ydata`, `rp.xdata`, `savesort`, etc.). These are allocated during tree construction and are completely independent of the STRSXP allocation at line 328, which occurs during the output-construction epilogue after tree building is complete.

  Memory lifecycle for `rname`:
  1. `allocVector(STRSXP, nout)` — `std::malloc` for `SEXPREC` node + `std::malloc` for `SEXP[nout]` data array. Both succeed or `RError` is thrown.
  2. `SET_STRING_ELT(rname, i, mkChar("..."))` — `mkChar` performs two `std::malloc` calls (node + char buffer) per element, `n` times. Each can throw `RError`. If a throw occurs partway through, partially-filled `CHARSXP` nodes and the `rname` node itself are not freed — this is acceptable in an error path, as the Python `.Call` wrapper will surface the exception and the process state is treated as unrecoverable for that call.
  3. Python caller uses `free_sexp(rname)` after data extraction to free all `CHARSXP` children and the STRSXP node itself. With the amended `free_sexp` above (which now recurses into `STRSXP` children), no memory is leaked.

- **Explanation:**

  `STRSXP` itself is purely a compile-time constant `16`. It requires no runtime logic. The entire fake implementation for the STRSXP usage pattern in `rpart.c` is already provided by the combination of:

  1. `#define STRSXP 16` — the constant itself, in the SEXPTYPE block of `fake_Rinternals.hpp`.
  2. `sexptype_element_size(STRSXP)` returning `sizeof(SEXP)` — so `allocVector(STRSXP, n)` allocates a `SEXP[n]` child-pointer array.
  3. `SET_STRING_ELT` and `STRING_ELT` — already defined as inline functions in `fake_Rinternals.hpp`.
  4. `mkChar` — already defined as an inline function that allocates a `CHARSXP`.
  5. `free_sexp` — amended to recurse into `STRSXP` children, preventing `CHARSXP` leaks.
  6. `R_NaString` / `R_BlankString` / `R_BlankScalarString` — static sentinels, required by the linker even though rpart's C source never calls them.

  The original `rpart.c` source compiles without modification because every symbol it uses (`STRSXP`, `allocVector`, `SET_STRING_ELT`, `mkChar`, `setAttrib`, `R_NamesSymbol`) is present in `fake_Rinternals.hpp` under the same name and with the same visible signature. The `#define mkChar Rf_mkChar` alias from the real `Rinternals.h` must also be present; the fake provides it as:

  ```cpp
  #define mkChar    Rf_mkChar
  #define mkString  Rf_mkString
  ```

  with `Rf_mkChar` and `Rf_mkString` either defined as inline functions or `#define`-aliased back to the fake `mkChar` implementation.

  Note on `rname` not being PROTECTed: the real `rpart.c` does not call `PROTECT(rname)` at line 328, even though `allocVector` triggers a GC in real R. This is valid in real R because `setAttrib(rlist, R_NamesSymbol, rname)` at line 329 immediately registers `rname` as an attribute of the already-protected `rlist`, preventing GC collection. In the fake runtime neither `PROTECT` nor `setAttrib` do anything, so the absence of `PROTECT(rname)` is irrelevant — the SEXP is simply a C pointer that is valid as long as the `std::malloc`-allocated memory is not freed.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The complete `fake_Rinternals.hpp` established by `SEXP.md` is the primary dependency. It provides: `SEXPREC` struct layout (with `type`, `length`, `nrow`, `ncol`, `data` fields); the `SEXP` typedef; `sexptype_element_size` (which already includes the `STRSXP` case returning `sizeof(SEXP)`); `allocVector` (used as `allocVector(STRSXP, nout)` at `rpart.c:328`); `mkChar` / `Rf_mkChar` (used by every `SET_STRING_ELT` call); `SET_STRING_ELT` and `STRING_ELT` (the accessors for `STRSXP` elements); `setAttrib` and `R_NamesSymbol` (no-op attachment); `PROTECT`/`UNPROTECT` no-ops; and the original `free_sexp` (which is amended here to add `STRSXP` recursion). |
| `INTSXP.md` | Establishes `#define INTSXP 13` within the SEXPTYPE constant block that also contains `#define STRSXP 16`. The two constants live in the same block in `fake_Rinternals.hpp`; `INTSXP.md` is the authoritative reference for that block's design rationale. |
| `REALSXP.md` | Establishes `#define REALSXP 14` in the same SEXPTYPE block. Same rationale as `INTSXP.md`. |
| `fake_arena.hpp` | Required by every `.Call`-entry-point wrapper (including the `rpart()` wrapper shown above) for the `ArenaFrame` RAII guard. `STRSXP` allocations themselves do not use the arena, but the `rpart()` function body uses `R_alloc`/`ALLOC` for scratch arrays and therefore requires `ArenaFrame` at the call boundary. `fake_arena.hpp` is generated once as a foundational file (documented in the arena section of each memory-related guide). |
