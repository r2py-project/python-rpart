# Fake Header Implementation Guide: `R_NamesSymbol`

> **R Interpreter Item** — `R_NamesSymbol` is a predefined interned symbol maintained by the R interpreter's global symbol table. A complete fake that faithfully replicates R's symbol-interning semantics is impossible without a running R interpreter. However, because the sole usage of `R_NamesSymbol` in the rpart source is as an opaque key argument to `setAttrib`, and because `setAttrib` is itself a no-op in the fake runtime, `R_NamesSymbol` can be reduced to a stable static SEXP sentinel with no runtime interpreter dependency. This guide documents that reduction and explains the boundary conditions under which it is valid.

---

### 1. Overview of `R_NamesSymbol` in R API

`R_NamesSymbol` is a pre-interned `SEXP` of type `SYMSXP` (symbol type tag `1`) that represents the string `"names"` in R's internal symbol table. It is declared in `Rinternals.h` at line 448 as:

```c
LibExtern SEXP  R_NamesSymbol;    /* "names" */
```

`LibExtern` expands to `extern` in C translation units that link against `libR.so`; the definition lives in the R shared library and is filled in at process startup when R initialises its interpreter and pre-interns a fixed set of well-known symbol names. `R_NamesSymbol` is used as the canonical attribute key in calls to `setAttrib(x, R_NamesSymbol, val)` and `getAttrib(x, R_NamesSymbol)` to set or retrieve the `names` attribute of any R vector or list. Its specific SEXP pointer value is only meaningful within a live R session; it is looked up as an identity-compared key by the R attribute system.

In the fake runtime there is no interpreter, no symbol table, and no attribute system. The role of `R_NamesSymbol` reduces entirely to: a non-null, type-stable `SEXP` value that can be passed as the second argument to `setAttrib` — which is itself a no-op in the fake. No runtime behaviour depends on which specific pointer value `R_NamesSymbol` holds, as long as it is a valid (non-null, non-dangling) `SEXP`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart.c` | 314–349 | Output-list construction block at the end of `rpart()` |

The single CSV row is at `rpart.c:329`. The surrounding 15-line window (lines 314–349) exposes the complete usage pattern:

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    // line 327
SEXP rname = allocVector(STRSXP, nout);              // line 328
setAttrib(rlist, R_NamesSymbol, rname);              // line 329  <-- CSV row
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

**Argument and return types at line 329.**

The call is:

```c
setAttrib(rlist, R_NamesSymbol, rname);
```

which expands (via `#define setAttrib Rf_setAttrib` in `Rinternals.h`) to:

```c
SEXP Rf_setAttrib(SEXP x, SEXP name, SEXP val);
```

- `x` (`rlist`) — a `VECSXP` SEXP allocated at line 327.
- `name` (`R_NamesSymbol`) — the pre-interned `SYMSXP` SEXP for `"names"`, of type `SEXP`.
- `val` (`rname`) — a `STRSXP` SEXP allocated at line 328.
- Return value — `SEXP` (real R returns the modified `x`; the return value is unused here).

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `allocVector(VECSXP, nout)` | 327 | Allocates the `VECSXP` output list; documented in `VECSXP.md` |
| `allocVector(STRSXP, nout)` | 328 | Allocates the `STRSXP` name vector; documented in `STRSXP.md` |
| `setAttrib` | 329 | Attaches `rname` as the `names` attribute of `rlist`; documented in `SEXP.md` as a no-op |
| `SET_VECTOR_ELT` | 330–344 | Writes child SEXPs into `rlist`; documented in `SEXP.md` |
| `SET_STRING_ELT` / `mkChar` | 331–344 | Writes `CHARSXP` nodes into `rname`; documented in `SEXP.md` and `STRSXP.md` |
| `PROTECT` / `UNPROTECT` | 327, 347 | No-ops in the fake runtime; documented in `SEXP.md` |

**Distinct implementation patterns.**

There is exactly one occurrence of `R_NamesSymbol` across all rpart source files (`rpart.c:329`). It belongs to a single pattern:

**Pattern: Predefined symbol used as an opaque attribute key in `setAttrib`.**

The pattern is: pass `R_NamesSymbol` as the second argument to `setAttrib(x, R_NamesSymbol, val)`. The value of `R_NamesSymbol` is never dereferenced, never accessed through any accessor (`INTEGER`, `REAL`, `CHAR`, etc.), and never compared against another SEXP. It is used solely as an opaque identity key. Because `setAttrib` is already a no-op in the fake runtime (per `SEXP.md`), the only requirement imposed on `R_NamesSymbol` is that it be a valid `SEXP` value (a non-null pointer to a well-formed `SEXPREC`) so that the call `setAttrib(rlist, R_NamesSymbol, rname)` compiles and does not cause undefined behaviour at the call site.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant (static global sentinel SEXP).**

Although `R_NamesSymbol` is an R Interpreter Item in the strict sense (its real definition requires a live interpreter), its observable contract in the rpart source reduces to a Category A fake: a stable, non-null, correctly-typed global SEXP pointer. No interpreter, no symbol table, no attribute lookup, and no string comparison are exercised at the call site.

**Why a complete fake is technically impossible but practically unnecessary.**

A fully faithful fake of `R_NamesSymbol` would require:

1. A running R symbol table (a hash table mapping interned C strings to unique `SYMSXP` nodes).
2. `R_NamesSymbol` being the unique canonical result of `install("names")` — the interning function that returns the same pointer for every call with the same string.
3. `setAttrib` and `getAttrib` performing identity comparison on `name` against the interned symbols in an attribute list.

None of these are reachable in the fake runtime:
- `setAttrib` is a no-op (documented in `SEXP.md`); it does not perform any identity comparison.
- `getAttrib` returns `R_NilValue` unconditionally; no attribute is ever stored or retrieved.
- No rpart code calls `getAttrib(x, R_NamesSymbol)` to retrieve the names — the names vector `rname` is also a live `SEXP` that the C code populates directly; attribute retrieval is only needed from R-level code.

Therefore the complete fake is a static `SEXPREC` of type `SYMSXP` with all numeric fields set to zero and `data` set to `nullptr`. The pointer is stable across translation units (implemented as a function-static with `inline` linkage, following the same pattern used for `R_NilValue` and `R_UnboundValue` in `SEXP.md`).

**Chosen fake mechanism.**

```cpp
inline SEXP make_names_symbol() {
    static SEXPREC sym = { SYMSXP, 0, 0, 0, nullptr };
    return &sym;
}
static SEXP R_NamesSymbol = make_names_symbol();
```

This is already present in `SEXP.md` (lines 506–510 of that guide's code listing, within the `setAttrib / R_NamesSymbol` section). The `R_NamesSymbol.md` guide establishes the rationale and correctness argument that was summarised there.

**`setAttrib` no-op and its interaction with `R_NamesSymbol`.**

The call `setAttrib(rlist, R_NamesSymbol, rname)` passes `R_NamesSymbol` as the `name` argument. Because `setAttrib` is defined as:

```cpp
inline void setAttrib(SEXP /*x*/, SEXP /*name*/, SEXP /*val*/) {}
```

the pointer value of `R_NamesSymbol` is received, stored in a discarded parameter, and immediately abandoned. No pointer dereference occurs. The fake `SEXPREC` for `R_NamesSymbol` never has any of its fields read. The only requirement satisfied is: the expression `setAttrib(rlist, R_NamesSymbol, rname)` must parse as a valid C++ call expression where all three arguments are `SEXP` (i.e., `SEXPREC *`). The static sentinel satisfies this requirement exactly.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` defines `#define setAttrib Rf_setAttrib` (line 1048) and `#define getAttrib Rf_getAttrib` (line 945). Both aliases must be present in `fake_Rinternals.hpp` so that the original source files compile unchanged:

```cpp
#define setAttrib   Rf_setAttrib
#define getAttrib   Rf_getAttrib
```

with `Rf_setAttrib` and `Rf_getAttrib` either defined as the inline no-op functions directly or as further aliases pointing to them.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `R_NamesSymbol` is a constant sentinel; no error or warning is thrown.
- Invariant 2 (arena memory): not triggered. The `SEXPREC` for `R_NamesSymbol` is a function-static (BSS-segment) object, not heap- or arena-allocated.
- Invariant 3 (R Interpreter Item): partially applicable. `R_NamesSymbol` technically requires an interpreter for faithful replication. However, because its only rpart usage is as an opaque no-op argument to `setAttrib`, the function-pointer bridge required by Invariant 3 is unnecessary — the static sentinel fully satisfies the observable contract. No Python callback registration is needed.

---

### 4. Fake Implementation Examples

#### Pattern: Predefined Symbol Used as Opaque Key in `setAttrib`

- **Locations:** `rpart.c:329`

- **Original R API Usage:**

```c
/* rpart.c:327-329 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// The following definitions implement the R_NamesSymbol + setAttrib/getAttrib
// pattern used at rpart.c:329.  They belong in fake_Rinternals.hpp after the
// SEXPREC / SEXP typedef block and the SEXPTYPE constants (both from SEXP.md).

// -----------------------------------------------------------------------
// R_NamesSymbol
//
// Real declaration in Rinternals.h line 448:
//   LibExtern SEXP  R_NamesSymbol;    /* "names" */
//
// LibExtern expands to `extern` when linking against libR.so.
// In the fake build there is no libR.so, so the variable must be defined
// (not merely declared) in the fake header.
//
// The fake provides a function-static SEXPREC of type SYMSXP.  The pointer
// is stable: make_names_symbol() returns the address of the same static
// object on every call, so all translation units that include this header
// see the same address.  (static keyword on the module-level variable gives
// it internal linkage per translation unit; the function-static inside
// make_names_symbol() ensures the SEXPREC itself is allocated only once
// process-wide via the first-call-wins guarantee for function statics.)
//
// Fields:
//   type   = SYMSXP (1) — consistent with a symbol node.
//   length = 0          — symbols are not vectors; length is irrelevant.
//   nrow   = 0          — not a matrix.
//   ncol   = 0          — not a matrix.
//   data   = nullptr    — the symbol name string is not stored; it is not
//                         accessed anywhere in the rpart source.
// -----------------------------------------------------------------------
inline SEXP make_names_symbol() {
    static SEXPREC sym = { SYMSXP, 0, 0, 0, nullptr };
    return &sym;
}
static SEXP R_NamesSymbol = make_names_symbol();

// -----------------------------------------------------------------------
// setAttrib / Rf_setAttrib
//
// Real declaration in Rinternals.h line 582:
//   SEXP Rf_setAttrib(SEXP, SEXP, SEXP);
// Real alias in Rinternals.h line 1048:
//   #define setAttrib  Rf_setAttrib
//
// In the fake runtime, R objects have no attribute lists.  Python reads
// the output list (rlist) by positional slot index, not by name lookup,
// so the names attribute is not needed at the C level.  setAttrib is a
// no-op: it accepts the three SEXP arguments (preventing compile errors)
// and does nothing.
// -----------------------------------------------------------------------
inline void Rf_setAttrib(SEXP /*x*/, SEXP /*name*/, SEXP /*val*/) {}
#define setAttrib  Rf_setAttrib

// -----------------------------------------------------------------------
// getAttrib / Rf_getAttrib
//
// Real declaration in Rinternals.h line 540:
//   SEXP Rf_getAttrib(SEXP, SEXP);
// Real alias in Rinternals.h line 945:
//   #define getAttrib  Rf_getAttrib
//
// Returns R_NilValue unconditionally — no attributes are stored in the
// fake runtime.  This is consistent with the STRSXP.md note that rname
// is write-only from the C side and is never retrieved via getAttrib.
// -----------------------------------------------------------------------
inline SEXP Rf_getAttrib(SEXP /*x*/, SEXP /*name*/) { return R_NilValue; }
#define getAttrib  Rf_getAttrib

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — R_NamesSymbol in context.
//
// The setAttrib call at rpart.c:329 is in the output-construction epilogue
// of rpart(), which also contains allocVector(VECSXP,...), allocVector(STRSXP,
// ...), SET_VECTOR_ELT, SET_STRING_ELT, mkChar, and UNPROTECT.  All of these
// are heap-allocating or no-op operations; none use the arena.
//
// The ArenaFrame at the .Call boundary governs only the R_alloc/ALLOC scratch
// memory allocated during tree construction earlier in rpart().  It does not
// affect the VECSXP rlist or the STRSXP rname, which are heap-allocated and
// must outlive the ArenaFrame.
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

  `R_NamesSymbol` itself is a function-static `SEXPREC` — it is allocated in the BSS segment at process startup and lives for the entire process lifetime. It is not heap-allocated, not arena-allocated, and not freed. The `make_names_symbol()` function uses a function-local `static` to guarantee a single `SEXPREC` object even across multiple calls and multiple translation units (each translation unit's module-level `static SEXP R_NamesSymbol = make_names_symbol()` stores the same pointer returned by the function).

  There is no memory management concern for `R_NamesSymbol` itself. The memory management concerns at `rpart.c:329` belong to `rlist` (a `VECSXP` heap-allocated at line 327) and `rname` (a `STRSXP` heap-allocated at line 328), both of which are documented in `VECSXP.md` and `STRSXP.md` respectively.

- **Explanation:**

  The fake header adds two definitions to `fake_Rinternals.hpp`:

  1. `make_names_symbol()` + `static SEXP R_NamesSymbol` — replaces the `LibExtern SEXP R_NamesSymbol;` declaration from the real `Rinternals.h` with a definition. The `LibExtern` expansion to `extern` would cause a link-time undefined-symbol error when building without `libR.so`; the fake definition eliminates that error by providing a BSS-segment `SEXPREC` as the variable's value.

  2. `Rf_setAttrib` / `#define setAttrib Rf_setAttrib` and `Rf_getAttrib` / `#define getAttrib Rf_getAttrib` — these are already present in `SEXP.md` but are documented here as the structural reason why the `R_NamesSymbol` sentinel's exact pointer value is irrelevant. The `#define` aliases must be present so that the original `rpart.c` source, which writes `setAttrib(rlist, R_NamesSymbol, rname)` directly, compiles without modification.

  The original `rpart.c` line 329 compiles unchanged because:
  - `setAttrib` resolves to `Rf_setAttrib` via the `#define` alias.
  - `rlist` is a `SEXP` — compatible with the first parameter.
  - `R_NamesSymbol` is a `SEXP` (a `SEXPREC *` returned by `make_names_symbol()`) — compatible with the second parameter.
  - `rname` is a `SEXP` — compatible with the third parameter.
  - The call compiles as a void function call with three pointer arguments, all of which are discarded inside the no-op body.

  No interpreter callback, no `ctypes` registration, and no function pointer bridge is required for this item.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The `SEXPREC` struct layout (`type`, `length`, `nrow`, `ncol`, `data` fields) is required so that `static SEXPREC sym = { SYMSXP, 0, 0, 0, nullptr };` is a valid aggregate initialiser. The `SEXP` typedef (`typedef SEXPREC *SEXP`) is required so that `static SEXP R_NamesSymbol` has the correct type. The `R_NilValue` sentinel (defined as `make_nil_value()` in `SEXP.md`) is required because `Rf_getAttrib` returns `R_NilValue`; `R_NilValue` must be defined before `Rf_getAttrib` is defined. The `SYMSXP` constant (`#define SYMSXP 1`) from the SEXPTYPE block is required for the initialiser `{ SYMSXP, 0, 0, 0, nullptr }`. All of these are provided by `SEXP.md` within `fake_Rinternals.hpp`. |
| `STRSXP.md` | Documents the `STRSXP` allocation (`allocVector(STRSXP, nout)`) at `rpart.c:328` — the line immediately before the `setAttrib` call that consumes `R_NamesSymbol`. That guide also documents the `free_sexp` amendment (adding `STRSXP` recursion) required to free the `CHARSXP` children of `rname` without a memory leak. `R_NamesSymbol` itself has no dependency on `STRSXP`, but `STRSXP.md` must be consulted to understand the full lifecycle of the `rname` argument passed alongside `R_NamesSymbol`. |
| `VECSXP.md` | Documents the `VECSXP` allocation (`allocVector(VECSXP, nout)`) at `rpart.c:327`, which is the `rlist` object that `setAttrib(rlist, R_NamesSymbol, rname)` modifies (as a no-op). `VECSXP.md` explains why Python reads `rlist` by positional slot index and does not need `getAttrib(rlist, R_NamesSymbol)` at the C level. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` boundary shown above for the `ArenaFrame` RAII guard. `R_NamesSymbol` itself has no arena dependency, but the enclosing `rpart()` function uses `R_alloc`/`ALLOC` scratch memory, and the wrapper must declare `ArenaFrame _frame;` before calling `rpart()`. |
