# Fake Header Implementation Guide: `setAttrib`

---

### 1. Overview of `setAttrib` in R API

`setAttrib` is a macro alias defined in `Rinternals.h` (line 1048) as `#define setAttrib Rf_setAttrib`, where `Rf_setAttrib` is declared at line 582 as:

```c
SEXP Rf_setAttrib(SEXP x, SEXP name, SEXP val);
```

Its role in R's C API is to attach a named attribute to an R object. Internally, R maintains a pairlist of `(name, value)` attribute slots on every `SEXPREC` node; `setAttrib` traverses or extends that pairlist, then writes `val` under the key `name` (which must be a `SYMSXP` symbol or a `CHARSXP` string). The most common usage is attaching the `names` attribute to a list or vector: `setAttrib(x, R_NamesSymbol, val)`. The return value is the modified `x` (the first argument), though callers most often discard it. `setAttrib` is **not** an R Interpreter Item; it is a regular C function that operates on in-memory SEXP nodes and can be fully faked without a running R interpreter.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart.c` | 314–349 | Output-list construction epilogue of `rpart()`; single `setAttrib` call at line 329 |

The CSV contains one row. The surrounding 15-line window (lines 314–349) exposes the complete context:

```c
/* rpart.c:314-349 */
    k = rp.which[i];
    do {
        for (j = 0; j < nodecount; j++)
        if (iinode[0][j] == k) {
            rp.which[i] = j + 1;
            break;
        }
        k /= 2;
    } while (j >= nodecount);
    }

    /* Create the output list */
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

which expands via the `#define` alias to `Rf_setAttrib(rlist, R_NamesSymbol, rname)`.

- `x` (`rlist`) — type `SEXP`, a `VECSXP` generic list allocated at line 327 by `allocVector(VECSXP, nout)`.
- `name` (`R_NamesSymbol`) — type `SEXP`, a `SYMSXP` symbol sentinel representing the string `"names"`. Documented fully in `R_NamesSymbol.md`.
- `val` (`rname`) — type `SEXP`, a `STRSXP` string vector allocated at line 328 by `allocVector(STRSXP, nout)`.
- Return value — `SEXP` (the real R returns the modified `x`); the return value is discarded at the call site (the result of `setAttrib(...)` is not assigned to anything).

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `allocVector(VECSXP, nout)` | 327 | Allocates `rlist`; `setAttrib`'s first argument — documented in `allocVector.md` and `VECSXP.md` |
| `PROTECT` | 327 | No-op guard around `rlist` allocation — documented in `PROTECT.md` |
| `allocVector(STRSXP, nout)` | 328 | Allocates `rname`; `setAttrib`'s third argument — documented in `allocVector.md` and `STRSXP.md` |
| `R_NamesSymbol` | 329 | `setAttrib`'s second argument, the `names` attribute key — documented in `R_NamesSymbol.md` |
| `SET_VECTOR_ELT` | 330–344 | Writes child SEXPs into `rlist` by slot index — documented in `SET_VECTOR_ELT.md` |
| `SET_STRING_ELT` / `mkChar` | 331–344 | Writes `CHARSXP` nodes into `rname` — documented in `SET_STRING_ELT.md` and `mkChar.md` |
| `UNPROTECT` | 347 | No-op — documented in `UNPROTECT.md` |

**Distinct implementation patterns.**

There is exactly one occurrence of `setAttrib` in the rpart source (`rpart.c:329`), belonging to a single pattern:

**Pattern: Set the `names` attribute of a `VECSXP` output list using `R_NamesSymbol` as the key.**

The return value is discarded. The `name` argument is always `R_NamesSymbol` (a `SYMSXP` sentinel). The `val` argument is a `STRSXP` whose slots are populated immediately after the `setAttrib` call via `SET_STRING_ELT`. The attribute is set before the slots are filled (the `rname` SEXP is allocated but empty at the time of the `setAttrib` call; it is populated in the lines that follow). This ordering is immaterial in the fake runtime because `setAttrib` is a no-op and no snapshot of `rname` is taken.

Crucially, no rpart code ever calls `getAttrib(rlist, R_NamesSymbol)` to retrieve the names back at the C level. The `names` attribute is consumed by R-level code after the `.Call` returns — but that path is irrelevant when calling directly from Python, because Python reads the result SEXP by positional slot index via `VECTOR_ELT`, not by name lookup.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function (closely related, but actually: no-op mutator).**

`setAttrib` does not allocate memory (in the fake runtime). It is most accurately a **no-op mutator** — a function that in the real R runtime modifies an in-memory attribute pairlist, but in the fake runtime can be safely discarded because:

1. The fake `SEXPREC` struct (from `SEXP.md`) has no `attrs` field. Adding an attribute map would require amending `SEXPREC`.
2. No rpart code retrieves attributes from the fake SEXPs at the C level. The only consumer of the `names` attribute is R-level code post-return, which is bypassed when calling from Python.
3. Python reads the output list (`rlist`) by positional index via `VECTOR_ELT(rlist, i)` — the names stored in `rname` are not needed.

The fake is therefore classified as **Category C** (a function that in the real runtime manages object state but whose side effect is skipped), implemented as a no-op `inline void` function.

**Chosen fake mechanism.**

`Rf_setAttrib` is defined as an inline void function that accepts three `SEXP` parameters and does nothing:

```cpp
inline void Rf_setAttrib(SEXP /*x*/, SEXP /*name*/, SEXP /*val*/) {}
#define setAttrib  Rf_setAttrib
```

The companion `Rf_getAttrib` returns `R_NilValue` unconditionally (no attributes are stored):

```cpp
inline SEXP Rf_getAttrib(SEXP /*x*/, SEXP /*name*/) { return R_NilValue; }
#define getAttrib  Rf_getAttrib
```

**Why no `SEXPREC::attrs` field is needed.**

The design in `SEXP.md` deliberately omits an `attrs` field from `SEXPREC`. Adding one (e.g., `std::unordered_map<std::string, SEXP> attrs`) would:

- Require C++ headers (`<unordered_map>`, `<string>`) in a struct that is also included from C-linkage contexts.
- Require the `SEXPREC` constructor to initialize the map, making `SEXPREC` a non-trivially-constructible type and breaking C-style aggregate initialization (`static SEXPREC nil = { NILSXP, 0, 0, 0, nullptr };`).
- Add overhead that is never observable from within the rpart source.

Since no rpart code calls `getAttrib` on a fake-runtime SEXP, the omission is correct and safe.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` defines:

```c
#define setAttrib   Rf_setAttrib   // line 1048
#define getAttrib   Rf_getAttrib   // line 945
```

Both aliases must appear in `fake_Rinternals.hpp` so that the original `rpart.c` line 329 (`setAttrib(rlist, R_NamesSymbol, rname);`) compiles unchanged.

**Relationship to previously generated guides.**

- `SEXP.md` already contains an inline stub for `setAttrib` and `getAttrib` within its Pattern P2 code listing (lines 503–504 of that guide). The present guide provides the authoritative standalone documentation. The stubs in `SEXP.md` and those here are identical; no conflict exists.
- `R_NamesSymbol.md` documents the second argument (`name`) passed to `setAttrib` in the sole rpart usage. That guide establishes that `R_NamesSymbol` is a static `SYMSXP` sentinel and that its pointer value is never dereferenced inside the no-op `setAttrib`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `setAttrib` is a no-op; it never calls `Rf_error` or `Rf_warning`.
- Invariant 2 (arena memory): not triggered. The no-op `setAttrib` allocates nothing. The arena governs only `R_alloc`/`ALLOC` scratch memory; the SEXP arguments to `setAttrib` are heap-allocated (not arena-allocated) and their lifetimes are unaffected.
- Invariant 3 (R Interpreter Items): not applicable. `setAttrib` is not an R Interpreter Item; it operates on plain in-memory SEXP nodes and requires no running interpreter.

---

### 4. Fake Implementation Examples

#### Pattern: Set `names` Attribute of `VECSXP` Output List Using `R_NamesSymbol`

- **Locations:** `rpart.c:329`

- **Original R API Usage:**

```c
/* rpart.c:327-345 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);        /* line 329 — CSV row */
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));
/* ... four more pairs ... */
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
// The following definitions implement the setAttrib / getAttrib pattern
// used at rpart.c:329.  They must appear after the SEXPREC / SEXP typedef
// block, the SEXPTYPE constants, and the R_NilValue definition — all of
// which are provided earlier in fake_Rinternals.hpp (see SEXP.md).

// -----------------------------------------------------------------------
// Rf_setAttrib / setAttrib
//
// Real declaration in Rinternals.h line 582:
//   SEXP Rf_setAttrib(SEXP, SEXP, SEXP);
// Real alias in Rinternals.h line 1048:
//   #define setAttrib  Rf_setAttrib
//
// In the fake runtime, SEXPREC has no attribute pairlist.  The call
//   setAttrib(rlist, R_NamesSymbol, rname);
// is a compile-time-required statement: it must parse and compile without
// error.  Its runtime side-effect (recording rname under the "names" key
// on rlist) is not needed because:
//   1. No rpart C code calls getAttrib to retrieve attributes.
//   2. Python reads rlist by positional slot index via VECTOR_ELT, not
//      by name lookup.
//
// Therefore Rf_setAttrib is a no-op that accepts its three SEXP arguments
// (preventing compile errors) and discards them.
//
// Note: the real Rf_setAttrib returns SEXP (the modified x).  The rpart
// call site discards the return value, so a void return type is sufficient
// here.  However, to exactly match the declared signature and avoid
// -Wreturn-type warnings if any other code path uses the return value,
// the fake returns x unchanged.
// -----------------------------------------------------------------------
inline SEXP Rf_setAttrib(SEXP x, SEXP /*name*/, SEXP /*val*/) {
    return x;
}
#define setAttrib  Rf_setAttrib

// -----------------------------------------------------------------------
// Rf_getAttrib / getAttrib
//
// Real declaration in Rinternals.h line 540:
//   SEXP Rf_getAttrib(SEXP, SEXP);
// Real alias in Rinternals.h line 945:
//   #define getAttrib  Rf_getAttrib
//
// Returns R_NilValue unconditionally — no attributes are stored in the
// fake runtime.  Consistent with the observation that rpart never calls
// getAttrib on a fake-runtime SEXP from within the C source files.
// -----------------------------------------------------------------------
inline SEXP Rf_getAttrib(SEXP /*x*/, SEXP /*name*/) {
    return R_NilValue;
}
#define getAttrib  Rf_getAttrib

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — context of the setAttrib call.
//
// The setAttrib call at rpart.c:329 is in the output-construction epilogue
// of rpart().  The enclosing function also uses R_alloc/ALLOC scratch memory
// (governed by the ArenaFrame) and heap-allocated SEXP nodes (rlist, rname,
// and all child SEXPs accumulated since the function entry).  The ArenaFrame
// frees only the scratch memory; the SEXP heap nodes outlive the frame so
// that the returned rlist remains valid after the .Call boundary.
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
//
// The setAttrib no-op at line 329 does not throw and does not allocate,
// so it does not affect the ArenaFrame lifecycle or the try/catch boundary.
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  `setAttrib` in the fake runtime allocates nothing and frees nothing. It is a pure no-op with respect to both arena memory and heap memory.

  The three SEXP arguments passed to `setAttrib` at `rpart.c:329` have the following memory origins:

  - `rlist` — heap-allocated by `allocVector(VECSXP, nout)` at line 327. Its `SEXPREC` node and its `SEXP[nout]` data buffer were obtained via `std::malloc`. It is returned from `rpart()` and freed by the Python caller after data extraction via `free_sexp()`.
  - `rname` — heap-allocated by `allocVector(STRSXP, nout)` at line 328. Its `SEXPREC` node and `SEXP[nout]` data buffer were obtained via `std::malloc`. Because `rname` is stored as an element of `rlist`'s child array (via `SET_VECTOR_ELT` — though that is not done here; `rname` is populated separately via `SET_STRING_ELT`), it must be freed recursively when `rlist` is freed.

    Note: `rname` is never inserted into `rlist` via `SET_VECTOR_ELT`. It is a parallel data structure populated alongside `rlist`. In the real R runtime, `setAttrib(rlist, R_NamesSymbol, rname)` logically attaches `rname` to `rlist`'s attribute list, making `rname` part of `rlist`'s reachable object graph. In the fake runtime, no such attachment occurs. The Python caller is therefore responsible for freeing both `rlist` and `rname` separately. If `rname` is needed on the Python side, it must be extracted and passed back alongside `rlist` or freed explicitly after `rlist` is processed. If `rname` is not needed (Python reads `rlist` by index), it should be freed directly via `free_sexp(rname)` before the wrapper returns, to avoid a memory leak.

  - `R_NamesSymbol` — a function-static `SEXPREC` in the BSS segment; neither heap-allocated nor arena-allocated; never freed.

- **Explanation:**

  The fake header adds two definitions to `fake_Rinternals.hpp`:

  1. `Rf_setAttrib` / `#define setAttrib Rf_setAttrib` — replaces the real `SEXP Rf_setAttrib(SEXP, SEXP, SEXP)` with a no-op that returns its first argument unchanged. The `#define` alias ensures that the original `rpart.c` call `setAttrib(rlist, R_NamesSymbol, rname)` expands to `Rf_setAttrib(rlist, R_NamesSymbol, rname)` without any source-level modification.

  2. `Rf_getAttrib` / `#define getAttrib Rf_getAttrib` — a no-op companion that returns `R_NilValue`. Although `getAttrib` does not appear in the rpart C source files, the `#define getAttrib Rf_getAttrib` alias is present in the real `Rinternals.h` (line 945) and must be replicated in the fake header to prevent compilation errors if any transitively included header references it.

  The original `rpart.c` line 329 compiles unchanged because:
  - `setAttrib` resolves to `Rf_setAttrib` via the `#define` alias.
  - `rlist` is a `SEXP` — compatible with the first parameter type.
  - `R_NamesSymbol` is a `SEXP` (a `SEXPREC *` returned by `make_names_symbol()` from `R_NamesSymbol.md`) — compatible with the second parameter type.
  - `rname` is a `SEXP` — compatible with the third parameter type.
  - The call compiles as a `SEXP`-returning function call whose result is discarded by the statement (the return type is compatible with a discarded-value expression).

  No interpreter callback, no `ctypes` registration, no function pointer bridge, and no arena interaction is required for this item.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | The `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data` fields) and the `typedef SEXPREC *SEXP` are required so that `Rf_setAttrib(SEXP, SEXP, SEXP)` compiles as a valid C++ inline function signature. The `SYMSXP` constant (`#define SYMSXP 1`) is required by `R_NamesSymbol.md` (not by `setAttrib` directly). The `R_NilValue` sentinel is required because `Rf_getAttrib` returns it; `R_NilValue` must be defined before `Rf_getAttrib` appears in the header. All of these are provided by `SEXP.md` within `fake_Rinternals.hpp`. |
| `R_NamesSymbol.md` | Provides the `make_names_symbol()` function and `static SEXP R_NamesSymbol` definition that is passed as the second argument to `setAttrib` at `rpart.c:329`. `R_NamesSymbol.md` must be ordered before `setAttrib`'s definition in `fake_Rinternals.hpp` so that `R_NamesSymbol` is a valid `SEXP` at the point of the call. In practice, both definitions reside in the same `fake_Rinternals.hpp` file; their relative order within that file must place `make_names_symbol()` before `Rf_getAttrib` (which references `R_NilValue`, already defined ahead of both). |
| `allocVector.md` | Documents the `allocVector(VECSXP, nout)` and `allocVector(STRSXP, nout)` calls at lines 327–328 that produce the first and third arguments to `setAttrib`. `setAttrib` itself has no compile-time dependency on `allocVector`, but the runtime context (the allocation of `rlist` and `rname`) is inseparable from the `setAttrib` call in `rpart.c:327-329`. |
| `PROTECT.md` / `UNPROTECT.md` | The `PROTECT` wrap around `rlist` at line 327 and `UNPROTECT(1 + nout)` at line 347 bracket the `setAttrib` call. These are no-ops in the fake runtime (documented in their respective guides) and have no effect on `setAttrib`'s behaviour. |
| `fake_arena.hpp` | Required by the `rpart_wrapper` `.Call` boundary wrapper shown above for the `ArenaFrame` RAII guard. `setAttrib` itself has no arena dependency, but the enclosing `rpart()` function uses `R_alloc`/`ALLOC` scratch memory that the wrapper must manage. |
