# Fake Header Implementation Guide: `PRINTNAME`

---

### 1. Overview of `PRINTNAME` in R API

`PRINTNAME` is an accessor function declared in `Rinternals.h` with the signature `SEXP (PRINTNAME)(SEXP x)`. It accepts a single `SEXP` argument of type `SYMSXP` (a symbol node, `SEXPTYPE = 1`) and returns the print-name of that symbol as a `SEXP` of type `CHARSXP` (`SEXPTYPE = 9`) — the internal scalar-string node that carries the symbol's name as a null-terminated C string. `PRINTNAME` is not an R Interpreter Item; it is a pure structural accessor that reads a field from an already-constructed `SEXPREC` node and requires no live R interpreter to implement. It is universally composed with `CHAR(...)` (i.e., `CHAR(PRINTNAME(sym))`) to convert a symbol to a printable C string.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart_callback.c` | 18–27 | The `compat_getVar` shim (active when `R_VERSION < R_Version(4, 5, 0)`): calls `findVar` / `findVarInFrame`, checks for `R_UnboundValue`, then calls `error(...)` with `CHAR(PRINTNAME(sym))` to format the variable name into the error message |

The full context window (lines 9–39 of `rpart_callback.c`):

```c
/*
 * callback routines for "user" splitting functions in rpart
 */

#include <stddef.h>
#include <R.h>
#include <Rinternals.h>
#include <Rversion.h>

#ifdef ENABLE_NLS
#include <libintl.h>
#define _(String) dgettext ("rpart", String)
#else
#define _(String) (String)
#endif

/* compatibility shim for R < 4.5.0 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));  /* line 24 */
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

static int ysave;               /* number of columns of y  */
static int rsave;               /* the length of the returned "mean" from the
                                 * user's eval routine */
static SEXP expr1;              /* the evaluation expression for splits */
static SEXP expr2;              /* the evaluation expression for values */
static SEXP rho;
```

**Argument and return types observed.**

The expression `CHAR(PRINTNAME(sym))` is a two-step composition:

1. `PRINTNAME(sym)` — takes `sym` of type `SEXP` (a `SYMSXP`) and returns a `SEXP` of type `CHARSXP`. The `CHARSXP` node carries the symbol's print-name string in its internal data buffer.

2. `CHAR(...)` — takes the `CHARSXP` result (type `SEXP`) and returns `const char *`. This is the raw C string pointer passed as the `%s` argument to `error(...)`.

The full call chain for line 24:

| Expression | Input type | Return type |
|---|---|---|
| `sym` | `SEXP` (SYMSXP) | — |
| `PRINTNAME(sym)` | `SEXP` (SYMSXP) | `SEXP` (CHARSXP) |
| `CHAR(PRINTNAME(sym))` | `SEXP` (CHARSXP) | `const char *` |
| `error("...", CHAR(PRINTNAME(sym)))` | format string + `const char *` | `void` (throws `RError`) |

**Co-occurring R API items in context window.**

- `CHAR(...)` — immediately applied to the `CHARSXP` returned by `PRINTNAME`. The composition `CHAR(PRINTNAME(sym))` is the standard R C API idiom for extracting a symbol name as a C string. `CHAR` is defined in `CHAR.md`.
- `error(fmt, ...)` — the `#define error Rf_error` alias. In the fake runtime this throws `RError` (Invariant 1). It is the sole consumer of the `const char *` returned by `CHAR(PRINTNAME(sym))`.
- `findVar(sym, rho)` / `findVarInFrame(rho, sym)` — Category E items (R Interpreter Items) that provide the `val` checked against `R_UnboundValue`. The `CHAR(PRINTNAME(sym))` expression at line 24 is only reached when `val == R_UnboundValue`.
- `R_UnboundValue` — the sentinel `SEXP` for "variable not found". The `CHAR(PRINTNAME(sym))` expression is inside the `if (val == R_UnboundValue)` guard. Defined in `R_UnboundValue.md`.
- `Rboolean inherits` — controls which of `findVar` or `findVarInFrame` is called. Defined in `Rboolean.md`.

**Distinct implementation patterns.**

There is exactly one distinct usage pattern in the CSV:

| Pattern | CSV row | Description |
|---|---|---|
| P1: Extract print-name `CHARSXP` from a `SYMSXP` for use in an error message | `rpart_callback.c:24` | `CHAR(PRINTNAME(sym))` where `sym` is a `SYMSXP`; the result is passed as a `%s` argument to `error()` |

No other usage pattern appears in the CSV. The composition `CHAR(PRINTNAME(...))` is the universal R C API idiom for converting a symbol SEXP to a printable C string.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`PRINTNAME` is a structural accessor that extracts the print-name child node from a symbol `SEXPREC`. In the real R runtime, a `SYMSXP` node contains a dedicated `CHARSXP` slot for the print name (accessible via the `PRINTNAME` macro, which reads a specific field in the node's header word). In the fake runtime, the `SEXPREC` struct (defined in `SEXP.md`) uses a single `void *data` field. For a `SYMSXP` node, this `data` field is assigned to hold a pointer to the child `CHARSXP` node that carries the symbol's name string. `PRINTNAME(sym)` then returns `static_cast<SEXP>(sym->data)`.

**Chosen mechanism.**

The real `Rinternals.h` declares `PRINTNAME` in a form similar to:

```c
SEXP (PRINTNAME)(SEXP x);
```

The parentheses around `PRINTNAME` follow the R convention of providing a function prototype alongside a possible macro definition — the parenthesized form suppresses macro substitution in the declaration so that the prototype is always visible to the compiler. In the fake build, `PRINTNAME` is implemented as a C++ `inline` function:

```cpp
inline SEXP PRINTNAME(SEXP s) {
    if (s->type == SYMSXP && s->data)
        return static_cast<SEXP>(s->data);
    return s;
}
```

This directly reads `s->data` and casts it from `void *` to `SEXP`. For a correctly constructed fake `SYMSXP` (produced by the `install()` Category E stub), `s->data` always points to a heap-allocated `CHARSXP` child node whose own `data` field holds the null-terminated symbol name string. The fallback `return s;` handles malformed or non-symbol nodes gracefully by returning the input unchanged, which avoids a null dereference in `R_CHAR`.

**How `PRINTNAME` interacts with `CHAR` in the fake.**

`CHAR(PRINTNAME(sym))` expands as follows:

1. `PRINTNAME(sym)` — returns `static_cast<SEXP>(sym->data)`, the child `CHARSXP` node.
2. `CHAR(charsxp)` — expands to `R_CHAR(charsxp)` which returns `static_cast<const char *>(charsxp->data)`.

The result is the raw C string pointer for the symbol name. This is consistent with both the `SEXP.md` and `CHAR.md` guides, which already document this two-step composition. The `SEXP.md` guide includes a preliminary `PRINTNAME` stub at the end of Pattern P2; this guide is the authoritative definition.

**How a fake `SYMSXP` must be constructed.**

For `PRINTNAME` to return a meaningful result, any `SYMSXP` passed to it must be constructed with `data` pointing to a valid `CHARSXP` child. The `install()` stub (Category E, separate guide) is the canonical constructor for symbol SEXPs in the rpart fake build. It must:

1. Allocate a `CHARSXP` node via `mkChar(name_string)`.
2. Allocate a `SEXPREC` with `type = SYMSXP` and `data = charsxp_node`.
3. Return the `SYMSXP` pointer.

This is a runtime contract between `install()` and `PRINTNAME()`. The `PRINTNAME` implementation documented here does not enforce this contract — it trusts that any `SYMSXP` it receives has a valid `CHARSXP` in its `data` field.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` may define `PRINTNAME` as both a macro and a function prototype (following the same pattern as `CHAR`/`R_CHAR`). In the fake, `PRINTNAME` is defined only as an `inline` function — no `#define` alias is required because the original rpart source at line 24 calls `PRINTNAME(sym)` as a function call, which resolves directly to the inline function. No alias is strictly needed; however, if the real header used `#define PRINTNAME(x) ...`, that macro is superseded by the inline function definition, and the `#pragma once` / include guard in the fake header prevents double-definition.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `PRINTNAME` itself. The `error(...)` call that consumes `CHAR(PRINTNAME(sym))` is governed by Invariant 1 and is documented in the `error` / `Rf_error` fake guide. `PRINTNAME` only produces the intermediate `SEXP` (CHARSXP) argument; it does not call `error`.
- Invariant 2 (arena memory): not triggered. `PRINTNAME` is a pure read accessor. It performs no allocation; it returns a pointer into an existing `SEXPREC` node's `data` field. The `CHARSXP` node it returns was heap-allocated at symbol construction time (by `mkChar` inside `install()`).
- Invariant 3 (R Interpreter Items): not triggered by `PRINTNAME` itself. The surrounding context in `compat_getVar` uses `findVar` / `findVarInFrame` and `install` (all Category E), but `PRINTNAME` is a Category B accessor that operates on whatever `SEXP` it receives — it does not require the interpreter. The `compat_getVar` function as a whole is a Category E dependency site, but `PRINTNAME` within it is pure Category B.

---

### 4. Fake Implementation Examples

#### Pattern P1: Extract Print-Name CHARSXP from a SYMSXP for Use in an Error Message

- **Locations:** `rpart_callback.c:24`

- **Original R API Usage:**

```c
/* rpart_callback.c:18-27 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — PRINTNAME accessor)
//
// This block must appear AFTER:
//   - struct SEXPREC and typedef SEXPREC *SEXP        (from SEXP.md)
//   - #define SYMSXP 1  and  #define CHARSXP 9       (from SEXP.md / INTSXP.md)
//   - inline const char *R_CHAR(SEXP s) { ... }       (from CHAR.md)
//   - #define CHAR(x) R_CHAR(x)                       (from CHAR.md)
//   - struct RError and Rf_error() / #define error    (from SEXP.md / error guide)

// -----------------------------------------------------------------------
// PRINTNAME — extracts the print-name CHARSXP from a SYMSXP node.
//
// In R's internal representation, a SYMSXP node carries a dedicated
// print-name slot (a CHARSXP) as part of its header.  In the fake
// SEXPREC (from SEXP.md), which has a single void* data field, a SYMSXP
// stores a pointer to its child CHARSXP in that data field.
//
// Contract with install(): any SYMSXP passed to PRINTNAME must have been
// constructed with data pointing to a valid CHARSXP node created by
// mkChar().  The install() stub (Category E guide) is responsible for
// satisfying this contract.
//
// If s->type != SYMSXP or s->data is null (malformed node), the function
// returns s unchanged.  This prevents a null dereference when R_CHAR is
// subsequently applied, because R_CHAR(s) would then cast s->data —
// which is null for a SYMSXP — but the fallback returns the symbol itself,
// whose type is SYMSXP (not CHARSXP).  The resulting const char* from
// R_CHAR would be null.  To make this completely safe, the install() stub
// must never produce a SYMSXP with data == nullptr.
// -----------------------------------------------------------------------
inline SEXP PRINTNAME(SEXP s) {
    if (s && s->type == SYMSXP && s->data)
        return static_cast<SEXP>(s->data);
    return s;
}

// -----------------------------------------------------------------------
// Canonical usage: CHAR(PRINTNAME(sym))
//
// PRINTNAME(sym) returns the child CHARSXP node.
// CHAR(charsxp)  expands to R_CHAR(charsxp), which returns
//                static_cast<const char*>(charsxp->data).
//
// Full expansion of rpart_callback.c:24:
//
//   error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
//
// Step 1 — PRINTNAME(sym):
//   sym->type == SYMSXP  and  sym->data == &charsxp_node
//   returns &charsxp_node   (a SEXP of type CHARSXP)
//
// Step 2 — CHAR(charsxp_node):
//   CHAR expands to R_CHAR(charsxp_node)
//   R_CHAR returns static_cast<const char*>(charsxp_node->data)
//   which is e.g. "yback"
//
// Step 3 — error("variable '%s' not found", "yback"):
//   expands to Rf_error("variable '%s' not found", "yback")
//   which formats the message via vsnprintf, then throws
//   RError("variable 'yback' not found")   (Invariant 1)
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// How a correctly formed SYMSXP is constructed (for reference):
//
// The install() stub (Category E, separate guide) must create nodes like:
//
//   inline SEXP fake_install(const char *name) {
//       SEXP charnode = mkChar(name);         // CHARSXP, heap-allocated
//       SEXPREC *sym  = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
//       if (!sym) throw RError("install: out of memory");
//       sym->type   = SYMSXP;
//       sym->length = 0;
//       sym->nrow   = 0;
//       sym->ncol   = 0;
//       sym->data   = charnode;   // <-- PRINTNAME reads this field
//       return sym;
//   }
//
// PRINTNAME(sym) then returns charnode, and CHAR(charnode) returns the
// null-terminated string stored in charnode->data.
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// .Call boundary and error-handling context for compat_getVar
//
// compat_getVar is a static helper, not a .Call entry point.
// It is called via the R_getVar macro from init_rpcallback() (a .Call
// entry point).  The ArenaFrame guard and the RError try/catch live in
// the init_rpcallback wrapper, not in compat_getVar itself.
//
// When error() at line 24 throws RError, the exception propagates up:
//   CHAR(PRINTNAME(sym))    -- pure accessor, no throw
//   error(fmt, ...)          -- throws RError("variable 'X' not found")
//   compat_getVar()          -- does not catch, propagates
//   R_getVar macro           -- inlined, propagates
//   init_rpcallback()        -- does not catch, propagates
//   init_rpcallback_wrapper  -- catches RError (see SEXP.md Pattern P2):
//
//   extern "C" SEXP init_rpcallback_wrapper(
//           SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x) {
//       ArenaFrame _frame;   // frees R_alloc scratch allocations on exit
//       try {
//           return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
//       } catch (const RError &e) {
//           set_python_error(e.what());  // store message for Python to read
//           return R_NilValue;           // signal failure to caller
//       }
//   }
//
// The entire CHAR(PRINTNAME(sym)) expression executes safely before the
// throw, provided that sym is a properly constructed SYMSXP.
// -----------------------------------------------------------------------
```

- **Explanation:**

  The fake header defines `PRINTNAME` as a C++ `inline` function. The function checks `s->type == SYMSXP && s->data` before casting and returning the `data` field as a `SEXP`. This type check is a defensive measure absent from the real R implementation (which trusts that callers pass a `SYMSXP`) but important in the fake runtime where a malformed node could cause a null pointer dereference.

  The original source at `rpart_callback.c:24` uses `CHAR(PRINTNAME(sym))` without any change. `PRINTNAME` resolves to the inline function defined here, and `CHAR` expands to `R_CHAR` (defined in `CHAR.md`). The composition is type-consistent: `PRINTNAME` takes `SEXP` and returns `SEXP`; `R_CHAR` takes `SEXP` and returns `const char *`; `error` takes `const char *` as its variadic argument for `%s`. No source modification is required.

  The entire `compat_getVar` function is guarded by `#if R_VERSION < R_Version(4, 5, 0)`. In the fake build, the `R_VERSION` and `R_Version` macros (from `R_VERSION.md`) must evaluate such that this condition is true, causing `compat_getVar` and the `#define R_getVar` shim to be compiled. When the condition is false, `PRINTNAME` is still required because `Rinternals.h` declares it unconditionally and it may be used by other headers included transitively.

  The `_("variable '%s' not found")` macro at line 24 expands to the string literal itself (since `ENABLE_NLS` is not defined in the fake build, line 15 defines `#define _(String) (String)`). The `error(...)` call then expands to `Rf_error(...)`, which formats the message via `vsnprintf` and throws `RError` (Invariant 1). `PRINTNAME` and `CHAR` execute to completion before `Rf_error` is called; they are not interrupted by the exception.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct with fields `type` (SEXPTYPE), `length`, `nrow`, `ncol`, and `data` (void*). `PRINTNAME` reads `s->type` to confirm the node is a `SYMSXP` and casts `s->data` to `SEXP` to return the child `CHARSXP`. Also provides `RError`, `Rf_error`, and `R_NilValue`. `SEXP.md` includes a preliminary `PRINTNAME` stub; this guide is the authoritative and complete definition that supersedes it. |
| `INTSXP.md` | Provides `#define SYMSXP 1` and `#define CHARSXP 9` within the `SEXPTYPE` constant block. Both constants are used inside the `PRINTNAME` implementation: `SYMSXP` in the type guard, and `CHARSXP` is the type of the returned node (used by `CHAR.md` to validate the result). |
| `CHAR.md` | Provides `R_CHAR(SEXP s)` and `#define CHAR(x) R_CHAR(x)`. `PRINTNAME` is always composed with `CHAR` in rpart source code; `CHAR` must be defined in the same fake header file for the composition `CHAR(PRINTNAME(sym))` to compile. `CHAR.md` must be ordered after `SEXP.md` and `INTSXP.md` but before any usage site. |
| `R_UnboundValue.md` | Provides the `R_UnboundValue` sentinel `SEXP`. The `CHAR(PRINTNAME(sym))` expression at line 24 is inside the guard `if (val == R_UnboundValue)`. `R_UnboundValue` must be defined before `compat_getVar` is compiled. |
| `R_VERSION.md` | Provides the `R_VERSION` macro and `R_Version(major, minor, patch)` macro so that `#if R_VERSION < R_Version(4, 5, 0)` evaluates to true in the fake build, causing `compat_getVar` (which contains the `PRINTNAME` usage) to be compiled. Without this, the `CHAR(PRINTNAME(sym))` line is compiled out, though `PRINTNAME` itself remains required for completeness. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean`. Required because `compat_getVar` takes a `Rboolean inherits` parameter. `PRINTNAME` does not reference `Rboolean` directly, but both must be visible in the same translation unit. |
| `error` / `Rf_error` fake guide (Category D) | Provides `Rf_error(const char *fmt, ...)` which throws `RError`, and the `#define error Rf_error` alias. The `error(...)` call at line 24 is the consumer of `CHAR(PRINTNAME(sym))`; without it the translation unit does not compile. The `RError` struct is established in `SEXP.md` and will be fully documented in the `error` guide. |
| `install` fake guide (Category E — not yet generated) | The `install("yback")` etc. calls in `rpart_callback.c:59–68` (invoked via the `R_getVar` macro) construct `SYMSXP` nodes. For `CHAR(PRINTNAME(sym))` to return a meaningful string at runtime, the `install()` stub must produce a `SYMSXP` whose `data` field points to a valid `CHARSXP` child node created by `mkChar()`. The correctness of `PRINTNAME` at runtime is contingent on `install()` constructing well-formed symbol nodes. |
| `findVar` / `findVarInFrame` fake guide (Category E — not yet generated) | Required by the `val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym)` expression at line 22 of `compat_getVar`. These Category E stubs must be defined before `compat_getVar` is compiled. `PRINTNAME` itself does not depend on them, but they must coexist in the same translation unit that compiles `rpart_callback.c`. |
