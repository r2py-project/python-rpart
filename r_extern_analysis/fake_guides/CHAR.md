# Fake Header Implementation Guide: `CHAR`

---

### 1. Overview of `CHAR` in R API

`CHAR` is a macro defined in `Rinternals.h` as `#define CHAR(x) R_CHAR(x)`, where `R_CHAR` is declared as `const char *(R_CHAR)(SEXP x)`. It accepts a single `SEXP` argument of type `CHARSXP` (the internal scalar-string node, `SEXPTYPE = 9`) and returns a `const char *` pointer to the null-terminated C string stored inside that node. `CHAR` is the canonical way to extract a raw C string from a symbol name or string element in R's C API; it is typically applied to the result of `PRINTNAME(sym)` (which returns the name `CHARSXP` of a symbol) or to the result of `STRING_ELT(vec, i)` (which returns the `CHARSXP` at position `i` of a string vector). `CHAR` is not an R Interpreter Item; it is a pure accessor that reads from an already-constructed `SEXPREC` node and requires no live R interpreter to implement.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart_callback.c` | 18–27 | The `compat_getVar` shim (active when `R_VERSION < R_Version(4, 5, 0)`): calls `findVar` / `findVarInFrame`, checks for `R_UnboundValue`, then calls `error(...)` with `CHAR(PRINTNAME(sym))` to format the variable name into the error message |

The full context window (lines 18–27):

```c
/* rpart_callback.c:18-27 */
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
```

**Argument and return types observed.**

The expression `CHAR(PRINTNAME(sym))` is a two-step composition:

1. `PRINTNAME(sym)` — takes `sym` of type `SEXP` (a `SYMSXP`) and returns a `SEXP` of type `CHARSXP`. In `Rinternals.h` this is declared as `SEXP (PRINTNAME)(SEXP x)`. The `CHARSXP` node carries the symbol's name string in its internal data buffer.

2. `CHAR(...)` — takes the `CHARSXP` result (type `SEXP`) and returns `const char *`. This is the raw C string pointer that is passed as the `%s` argument to `error(...)`.

The full call chain for line 24:

| Expression | Input type | Return type |
|---|---|---|
| `sym` | `SEXP` (SYMSXP) | — |
| `PRINTNAME(sym)` | `SEXP` (SYMSXP) | `SEXP` (CHARSXP) |
| `CHAR(PRINTNAME(sym))` | `SEXP` (CHARSXP) | `const char *` |
| `error("...", CHAR(PRINTNAME(sym)))` | format string + `const char *` | `void` (throws `RError`) |

**Co-occurring R API items in context window.**

- `PRINTNAME(sym)` — extracts the name `CHARSXP` from a `SYMSXP`. Must be defined before `CHAR` is applied to its result.
- `error(fmt, ...)` — the `#define error Rf_error` alias from `R_ext/Error.h`. In the fake runtime this throws `RError` (Invariant 1). It is the sole consumer of the `const char *` returned by `CHAR(PRINTNAME(sym))`.
- `findVar(sym, rho)` / `findVarInFrame(rho, sym)` — Category E items (R Interpreter Items) that provide the `val` checked against `R_UnboundValue`. The `CHAR(PRINTNAME(sym))` expression at line 24 is only reached when `val == R_UnboundValue`.
- `R_UnboundValue` — the sentinel `SEXP` for "variable not found". The `CHAR(PRINTNAME(sym))` expression is inside the `if (val == R_UnboundValue)` guard.
- `Rboolean inherits` — controls which of `findVar` or `findVarInFrame` is called; not directly involved with `CHAR`.

**Distinct implementation patterns.**

There is exactly one distinct usage pattern in the CSV:

| Pattern | CSV row | Description |
|---|---|---|
| P1: Extract `const char *` from a symbol's name CHARSXP for use in an error message | `rpart_callback.c:24` | `CHAR(PRINTNAME(sym))` where `sym` is a `SYMSXP`; the result is passed as a `%s` argument to `error()` |

No other usage pattern appears in the CSV. The composition `CHAR(PRINTNAME(...))` is the standard R C API idiom for converting a symbol to a printable C string.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`CHAR` is a macro alias for `R_CHAR`, which is an accessor function. Its purpose is to cast the internal data pointer of a `CHARSXP` node to `const char *`. In the fake runtime, the `SEXPREC` struct (defined in `SEXP.md`) stores strings in its `void *data` field as a `char *` to a null-terminated buffer. `R_CHAR` simply casts that field; no allocation, no interpreter, and no arena interaction is involved.

**Chosen mechanism.**

The real `Rinternals.h` declares:

```c
#define CHAR(x)  R_CHAR(x)
const char *(R_CHAR)(SEXP x);
```

The parentheses around `R_CHAR` in the declaration follow the R convention of providing a function prototype alongside a possible macro definition — the parenthesized name suppresses macro substitution in the declaration itself. In the fake, `R_CHAR` is implemented as a C++ `inline` function:

```cpp
inline const char *R_CHAR(SEXP s) { return static_cast<const char *>(s->data); }
#define CHAR(x) R_CHAR(x)
```

This directly reads `s->data`, which in the fake `SEXPREC` struct (from `SEXP.md`) holds a `char *` to the null-terminated string when `s->type == CHARSXP`. The cast to `const char *` matches the declared return type of `R_CHAR` in the real API.

**How `PRINTNAME` interacts with `CHAR` in the fake.**

The `SEXP.md` guide already defines `PRINTNAME` as:

```cpp
inline SEXP PRINTNAME(SEXP s) {
    if (s->type == SYMSXP && s->data)
        return static_cast<SEXP>(s->data);
    return s;
}
```

For a correctly constructed fake symbol `SYMSXP`, `s->data` points to a child `CHARSXP` node whose `data` field in turn holds the string. So `CHAR(PRINTNAME(sym))` evaluates as:

1. `PRINTNAME(sym)` returns `static_cast<SEXP>(sym->data)` — the child `CHARSXP`.
2. `R_CHAR(charsxp)` returns `static_cast<const char *>(charsxp->data)` — the raw C string.

For the specific case of `compat_getVar`, the `sym` argument is a `SYMSXP` passed in from the `install()` or `findVar` fake. The `install()` stub (Category E) is responsible for constructing a `SYMSXP` whose `data` field points to a `CHARSXP` node carrying the symbol name. `CHAR(PRINTNAME(sym))` then retrieves that name as a C string.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` defines:

```c
#define CHAR(x)  R_CHAR(x)
```

This alias must be preserved in the fake header so that every occurrence of `CHAR(...)` in the original rpart source files expands correctly to the `R_CHAR` inline function without any source modification.

Additionally, the real header provides:

```c
#define translateChar       Rf_translateChar
#define translateCharUTF8   Rf_translateCharUTF8
```

These aliases expand to functions that accept a `CHARSXP` and return a re-encoded `const char *`. They are declared in `Rinternals.h` at lines 588–589 and aliased at lines 1058–1059. Although rpart does not use `translateChar` directly, the aliases must be present so that any transitively included header compiles. The fake implementations delegate to `R_CHAR` (since the fake runtime has no encoding infrastructure):

```cpp
inline const char *Rf_translateChar(SEXP s)      { return R_CHAR(s); }
inline const char *Rf_translateCharUTF8(SEXP s)  { return R_CHAR(s); }
#define translateChar       Rf_translateChar
#define translateCharUTF8   Rf_translateCharUTF8
```

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `CHAR` itself. The `error(...)` call that consumes `CHAR(PRINTNAME(sym))` is governed by Invariant 1 and is documented in the `error` / `Rf_error` fake guide. `CHAR` only produces the `const char *` argument; it does not call `error`.
- Invariant 2 (arena memory): not triggered. `CHAR` / `R_CHAR` is a pure read accessor. It does not allocate any memory; it returns a pointer into an existing buffer.
- Invariant 3 (R Interpreter Items): not triggered by `CHAR` itself. The surrounding context in `compat_getVar` uses `findVar` / `findVarInFrame` and `install` (all Category E), but `CHAR` is a Category B accessor that operates on whatever `SEXP` it receives — it does not require the interpreter.

---

### 4. Fake Implementation Examples

#### Pattern P1: Extract `const char *` from a Symbol's Name CHARSXP for Use in an Error Message

- **Locations:** `rpart_callback.c:24`

- **Original R API Usage:**

```c
/* rpart_callback.c:18-27 */
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — CHAR / R_CHAR accessor)
//
// This block must appear AFTER:
//   - struct SEXPREC and typedef SEXPREC *SEXP    (from SEXP.md)
//   - #define CHARSXP 9                           (from SEXP.md / INTSXP.md)
//   - inline SEXP PRINTNAME(SEXP s) { ... }       (from SEXP.md)
//   - struct RError and Rf_error()                (from SEXP.md / error guide)

// -----------------------------------------------------------------------
// R_CHAR — extracts the const char* from a CHARSXP node.
//
// In the fake SEXPREC (from SEXP.md), a CHARSXP node stores its string
// in the void* data field as a char* to a null-terminated buffer.
// R_CHAR simply casts that field to const char*.
//
// Precondition: s must be a non-null SEXP with s->type == CHARSXP and
//               s->data pointing to a valid null-terminated string.
//               This is guaranteed for any CHARSXP produced by mkChar()
//               or by the install() stub (Category E).
// -----------------------------------------------------------------------
inline const char *R_CHAR(SEXP s) {
    return static_cast<const char *>(s->data);
}

// CHAR is the public-facing macro alias that the rpart source uses.
// Preserved verbatim from the real Rinternals.h (line 203).
#define CHAR(x) R_CHAR(x)

// -----------------------------------------------------------------------
// translateChar / translateCharUTF8 — re-encoding helpers.
// The real implementations consult R's encoding infrastructure.
// In the fake runtime there is no encoding infrastructure; the raw
// buffer from R_CHAR is returned unchanged (all strings are assumed
// to be plain ASCII or the system locale encoding).
// These aliases are required so that any header that calls translateChar
// on a CHARSXP compiles without modification.
// -----------------------------------------------------------------------
inline const char *Rf_translateChar(SEXP s)     { return R_CHAR(s); }
inline const char *Rf_translateCharUTF8(SEXP s) { return R_CHAR(s); }
#define translateChar       Rf_translateChar
#define translateCharUTF8   Rf_translateCharUTF8

// -----------------------------------------------------------------------
// Full composition: CHAR(PRINTNAME(sym))
//
// PRINTNAME is defined in SEXP.md as:
//
//   inline SEXP PRINTNAME(SEXP s) {
//       if (s->type == SYMSXP && s->data)
//           return static_cast<SEXP>(s->data);
//       return s;
//   }
//
// For a SYMSXP node constructed by the install() stub, s->data is a
// pointer to a child CHARSXP node.  PRINTNAME extracts that child, and
// R_CHAR then reads its char* data field.
//
// Example (showing the two-step expansion for line 24):
//
//   sym                           // SYMSXP, sym->data == &charsxp_node
//   PRINTNAME(sym)                // returns &charsxp_node  (CHARSXP)
//   CHAR(PRINTNAME(sym))          // R_CHAR(&charsxp_node)
//                                 //   == (const char*)charsxp_node.data
//                                 //   == "yback"  (or whatever symbol name)
//
// This const char* is then passed to Rf_error() / error() which formats
// it into the error message and throws RError (Invariant 1).
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// .Call boundary and error-handling context for compat_getVar
//
// compat_getVar itself is a static helper, not a .Call entry point.
// It is called by the R_getVar macro, which is in turn called from
// init_rpcallback() (a .Call entry point).
//
// The ArenaFrame guard and the try/catch for RError live in the
// init_rpcallback wrapper (documented in SEXP.md), not in compat_getVar.
// When error() at line 24 throws RError, it propagates up through
// compat_getVar -> R_getVar macro -> init_rpcallback ->
// init_rpcallback_wrapper -> caught by the try/catch.
//
// Representative wrapper (from SEXP.md Pattern P2):
//
//   extern "C" SEXP init_rpcallback_wrapper(
//           SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x) {
//       ArenaFrame _frame;
//       try {
//           return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// If sym is a properly constructed SYMSXP with a valid CHARSXP child,
// CHAR(PRINTNAME(sym)) is safe to call before the throw.  If sym->data
// is null (malformed symbol), PRINTNAME returns sym itself, and
// R_CHAR(sym) would read sym->data == nullptr — undefined behavior.
// The install() stub must therefore always set sym->data to a valid
// CHARSXP to prevent this.
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:** Not applicable. `CHAR` / `R_CHAR` performs no allocation. It reads the `void *data` field of an existing `SEXPREC` node and casts it to `const char *`. The string buffer was allocated (via `std::malloc`) when the `CHARSXP` node was constructed by `mkChar()` or by the `install()` stub. That buffer's lifetime is governed by the SEXP heap (freed by `free_sexp()` after the `.Call` boundary). The `const char *` returned by `R_CHAR` is a non-owning pointer into that buffer; the caller must not free it.

- **Explanation:**

  The fake header defines `R_CHAR` as an `inline` function that casts `s->data` to `const char *` and immediately returns it. The `#define CHAR(x) R_CHAR(x)` alias is preserved verbatim from `Rinternals.h` line 203, so every occurrence of `CHAR(...)` in the rpart source compiles to a call to the inline function without any source modification.

  The original source at `rpart_callback.c:24` uses the pattern `CHAR(PRINTNAME(sym))`. `PRINTNAME` is already defined in `fake_Rinternals.hpp` (as documented in `SEXP.md`) and returns the child `CHARSXP` of a `SYMSXP`. `CHAR` then extracts the `const char *` from that `CHARSXP`. The composition compiles unchanged because both `PRINTNAME` and `R_CHAR` accept and return `SEXP` / `const char *` types that are consistent with the fake `SEXPREC` definition.

  The `_("variable '%s' not found")` macro at line 24 expands to either `dgettext("rpart", "variable '%s' not found")` (when `ENABLE_NLS` is defined) or the string literal itself. In the fake build, `ENABLE_NLS` is not defined, so `_` is `#define _(String) (String)` (line 15). The `error(...)` call then expands to `Rf_error(...)`, which throws `RError` containing the formatted message (Invariant 1).

  The entire `compat_getVar` function is guarded by `#if R_VERSION < R_Version(4, 5, 0)`. In the fake build, the `R_VERSION` / `R_Version` macros must be defined such that this condition is true; the `R_VERSION.md` guide establishes this. When the condition is false (R >= 4.5.0 build), `CHAR` and `PRINTNAME` are still required because `Rinternals.h` declares them unconditionally and the `#define CHAR(x) R_CHAR(x)` alias is always present.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data` fields) and the `SEXP` typedef. `R_CHAR` reads `s->data` and casts it to `const char *`; this is only valid if `data` is defined as `void *` in `SEXPREC`. Also provides `PRINTNAME(SEXP s)` (the inline function that extracts the child `CHARSXP` from a `SYMSXP`), `mkChar(const char *)` (which constructs `CHARSXP` nodes with `data` pointing to a heap-allocated string), and `RError` (the C++ exception type thrown by `error()` on the same line that uses `CHAR`). |
| `INTSXP.md` | Provides `#define CHARSXP 9` within the `SEXPTYPE` constant block. The `CHARSXP` tag is used in `PRINTNAME` to verify the type of the returned node, and in `mkChar` to set `s->type`. Both must be visible when `R_CHAR` is defined. |
| `R_UnboundValue.md` | Provides the `R_UnboundValue` sentinel `SEXP`. The `CHAR(PRINTNAME(sym))` expression at line 24 is inside `if (val == R_UnboundValue)`. `R_UnboundValue` must be defined before `compat_getVar` is compiled. |
| `R_VERSION.md` (not yet generated) | Provides the `R_VERSION` macro and `R_Version(major, minor, patch)` macro so that `#if R_VERSION < R_Version(4, 5, 0)` evaluates to true in the fake build, causing `compat_getVar` and the `#define R_getVar` shim to be compiled. Without this, the `CHAR(PRINTNAME(sym))` line is compiled out, but `CHAR` and `R_CHAR` are still required because they are unconditionally declared in `Rinternals.h`. |
| `error` / `Rf_error` fake guide (Category D — the `RError` struct and `Rf_error` function are established in `SEXP.md` and will be fully documented in a separate guide) | The `error(...)` call at line 24 must expand to `Rf_error(...)` which throws `RError`. The `#define error Rf_error` alias (from `R_ext/Error.h`, reproduced in the fake) must be present. `CHAR` itself does not throw, but the complete compilable unit at line 24 requires `Rf_error` and `RError` to be defined. |
| `findVar` / `findVarInFrame` fake guide (Category E — not yet generated) | The `val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym)` expression at line 22 requires Category E stubs for `findVar` and `findVarInFrame`. These stubs must be defined before `compat_getVar` is compiled. `CHAR` itself is not a dependency of those stubs, but the two must coexist in the same translation unit. |
| `install` fake guide (Category E — not yet generated) | The `install("yback")` calls at `rpart_callback.c:59–68` (invoked via the `R_getVar` macro which expands to `compat_getVar`) construct `SYMSXP` nodes. For `CHAR(PRINTNAME(sym))` to return a meaningful string, the `install()` stub must produce a `SYMSXP` whose `data` field points to a valid `CHARSXP` child node. The correctness of `R_CHAR` at runtime depends on `install()` constructing well-formed symbol nodes. |
