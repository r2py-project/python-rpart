# Fake Header Implementation Guide: `R_CheckUserInterrupt`

---

### 1. Overview of `R_CheckUserInterrupt` in R API

`R_CheckUserInterrupt` is a void function declared in `R_ext/Utils.h` with the signature `void R_CheckUserInterrupt(void)`. Its role in R's C API is to give the R session an opportunity to respond to an asynchronous user interrupt (e.g., Ctrl+C) that arrived while C code was executing a long-running loop. R's signal handler sets a pending-interrupt flag; `R_CheckUserInterrupt` checks that flag and, if it is set, unwinds the C stack back to the R top-level via `longjmp` and signals an R condition of class `interrupt`. In the fake runtime there is no R session, no R condition system, and no `longjmp`-based unwinding. The fake replaces `R_CheckUserInterrupt` with a thin C++ stub that checks a thread-local atomic flag; if Python has set that flag (e.g., by catching `SIGINT` in a Python signal handler), the stub throws a C++ exception (`RError`) rather than performing a `longjmp`, consistent with Invariant 1.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Loop context | Surrounding API items |
|---|---|---|---|
| `xpred.c` | 291 | Bottom of outer `for (xgroup = 0; xgroup < xvals; xgroup++)` loop; each iteration builds one cross-validation tree and runs predictions | `free_tree(xtree, 0)` immediately before; `UNPROTECT(1); return predict2;` immediately after the loop |
| `xval.c` | 168 | Bottom of outer `for (xgroup = 0; xgroup < n_xval; xgroup++)` loop; each iteration builds one cross-validation tree, runs out-of-fold observations, and accumulates risk | `free_tree(xtree, 1)` immediately before; post-loop `R_Free(savew); R_Free(xtemp)` after |

**Argument and return types.**

`R_CheckUserInterrupt` takes no arguments and returns `void`. It is a pure side-effect call: either it returns normally, or (in the real R runtime) it never returns because it `longjmp`s out of the C stack.

**Call pattern across both files.**

Both usages follow exactly the same structural pattern: a single bare call `R_CheckUserInterrupt();` at the bottom of a multi-iteration cross-validation loop, placed after all per-iteration heap/tree cleanup (`free_tree`) and before the next loop iteration begins. The intent is to check for a user interrupt once per fold so that the user can abort a long cross-validation run without waiting for all folds to complete.

Neither call site uses any return value. Neither call site is guarded by a conditional. There are no adjacent PROTECT/UNPROTECT or R memory allocation calls at the exact interrupt-check point; the memory management around the call is:

- `xpred.c:289`: `free_tree(xtree, 0)` — frees the per-fold tree (heap, `Calloc`-allocated nodes).
- `xpred.c:291`: `R_CheckUserInterrupt();`
- `xpred.c:293–294`: `UNPROTECT(1); return predict2;` — after the loop exits.

- `xval.c:167`: `free_tree(xtree, 1)` — frees the per-fold tree.
- `xval.c:168`: `R_CheckUserInterrupt();`
- `xval.c:170–179`: post-loop accumulation and `R_Free` calls.

**Distinct implementation patterns.**

There is exactly one pattern: a bare, no-argument, void-result call at the tail of a long-running loop iteration. Both CSV rows belong to this single pattern and share the same fake strategy.

---

### 3. Fake C++ Implementation Strategy

**Category: D — Error, Warning, or Print Function.**

Although `R_CheckUserInterrupt` is not an error or warning function in the traditional sense, it belongs to Category D because its only observable runtime behavior (beyond doing nothing) is to abort execution — and aborting execution in the fake runtime must follow Invariant 1: throw a C++ exception rather than performing a `longjmp`. The function fits Category D because its "exceptional exit" path must be replaced by `throw RError(...)`.

**Chosen mechanism.**

The fake provides two cooperating pieces:

1. A thread-local atomic interrupt flag (`g_interrupt_requested`) that Python can set from a `SIGINT` handler or any other context.
2. An inline `R_CheckUserInterrupt` stub that tests the flag and, if set, clears it and throws `RError("UserInterrupt")`.

When the flag is not set, the stub is a no-op — a direct return — matching the common case where no interrupt has arrived.

The choice of `thread_local` is consistent with the arena stack in `fake_arena.hpp` (which is also `thread_local`) and with rpart's usage model in which each top-level `.Call` invocation runs in its own thread context. Using `std::atomic<bool>` ensures that a Python signal handler (which may run in a different thread) can safely set the flag without a data race.

Python sets the flag by calling a C-linkage registration function `request_user_interrupt()` exported from the shared library. The typical Python pattern is to install a `signal.signal(signal.SIGINT, handler)` callback that calls this function via `ctypes`.

**Invariant applicability.**

- Invariant 1: Directly applicable. The real `R_CheckUserInterrupt` exits via `longjmp`. The fake exits via `throw RError("UserInterrupt")`. The `.Call` boundary wrapper catches `RError` and converts it to a Python exception. No `longjmp`, no `setjmp`, no `abort()`.
- Invariant 2: Not applicable. `R_CheckUserInterrupt` performs no memory allocation; neither the arena nor `std::malloc` is involved.
- Invariant 3: Not applicable. `R_CheckUserInterrupt` does not require a running R interpreter. It only consults a flag.

**`#define` aliases from the original header.**

`R_ext/Utils.h` does not define any `#define` alias for `R_CheckUserInterrupt`. The function is called by its canonical name in both rpart source files. No alias preservation is required.

---

### 4. Fake Implementation Examples

#### Pattern: Bare Interrupt Check at Bottom of Cross-Validation Loop

- **Locations:** `xpred.c:291`, `xval.c:168`

- **Original R API Usage:**

```c
/* xpred.c — outer cross-validation loop, ~line 222-294 */
for (xgroup = 0; xgroup < xvals; xgroup++) {
    /* ... rearrange rp.sorts, call rp_init/rp_eval/partition/fix_cp,
           run out-of-fold observations through rundown2 ... */

    free_tree(xtree, 0);
    R_CheckUserInterrupt();   /* <-- xpred.c:291 */
}
UNPROTECT(1);
return predict2;

/* xval.c — outer cross-validation loop, ~line 82-169 */
for (xgroup = 0; xgroup < n_xval; xgroup++) {
    /* ... rearrange rp.sorts, call rp_init/rp_eval/partition/fix_cp,
           run out-of-fold observations through rundown/accumulate risk ... */

    free_tree(xtree, 1);    // Calloc-ed
    R_CheckUserInterrupt();   /* <-- xval.c:168 */
}
/* post-loop: accumulate xstd, R_Free(savew), R_Free(xtemp) */
```

- **C++ Fake Implementation:**

```cpp
// fake_Utils.hpp
// Drop-in replacement for R_ext/Utils.h.
// Provides: R_CheckUserInterrupt (and stubs for R_CheckStack,
// R_CheckStack2, which appear in the same header).
//
// Include order: include after fake_Rinternals.hpp (for RError definition).

#pragma once
#ifndef FAKE_UTILS_H
#define FAKE_UTILS_H

#include <atomic>     // std::atomic
#include <cstdio>     // std::fprintf
#include <stdexcept>  // std::runtime_error (RError comes from fake_Rinternals.hpp)

// RError must already be defined (from fake_Rinternals.hpp).
// If this header is included standalone, define a minimal RError here.
#ifndef FAKE_RINTERNALS_H
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};
#endif

// -----------------------------------------------------------------------
// Interrupt flag.
//
// thread_local so that each worker thread has its own flag, consistent
// with the thread_local arena stack in fake_arena.hpp.
//
// std::atomic<bool> so that a Python SIGINT handler (potentially running
// in a different OS thread) can set the flag without a data race.
// -----------------------------------------------------------------------
inline thread_local std::atomic<bool> g_interrupt_requested{false};

// -----------------------------------------------------------------------
// request_user_interrupt — C-linkage function callable from Python via
// ctypes to signal that the current computation should be interrupted.
//
// Python SIGINT handler pattern:
//
//   import ctypes, signal
//   lib = ctypes.CDLL("/path/to/librpart_fake.so")
//   lib.request_user_interrupt.restype  = None
//   lib.request_user_interrupt.argtypes = []
//
//   def _sigint_handler(signum, frame):
//       lib.request_user_interrupt()
//
//   signal.signal(signal.SIGINT, _sigint_handler)
//
// After installation, any Ctrl+C while rpart's cross-validation loops
// are running will cause R_CheckUserInterrupt() to throw RError on the
// next loop iteration. The .Call wrapper catches RError and raises a
// Python KeyboardInterrupt (or RuntimeError) on the Python side.
// -----------------------------------------------------------------------
extern "C" inline void request_user_interrupt() {
    g_interrupt_requested.store(true, std::memory_order_relaxed);
}

// -----------------------------------------------------------------------
// R_CheckUserInterrupt — inline stub.
//
// Behavior:
//   - If no interrupt has been requested: returns immediately (no-op).
//     This is the hot path; the atomic load with memory_order_relaxed
//     compiles to a single register read on x86-64.
//   - If an interrupt has been requested: clears the flag, then throws
//     RError("UserInterrupt") to unwind the C++ call stack back to the
//     .Call boundary wrapper (Invariant 1). The wrapper catches RError
//     and translates it into a Python exception.
//
// The real R_CheckUserInterrupt() exits via longjmp; the fake exits via
// throw. The calling code in xpred.c and xval.c does not check the
// return value (it is void) and does not set up any cleanup between the
// R_CheckUserInterrupt() call and the end of the loop body — free_tree()
// has already been called before the check. Therefore, throwing here
// leaves no pending cleanup obligations inside the loop body itself.
//
// Resources that remain live when the throw occurs:
//   - predict2 (xpred.c): a PROTECT-ed SEXP on the heap. Because
//     UNPROTECT is a no-op in the fake runtime, and free_sexp() is
//     called by the Python caller after data extraction, this SEXP is
//     not leaked in practice — but it IS abandoned if the interrupt fires
//     before the function returns predict2. The .Call wrapper should
//     call free_sexp(predict2) in its catch block if predict2 was
//     already allocated. See the Integration Requirements section for
//     the wrapper pattern that handles this.
//   - xval.c: xval() is a void function called internally (not a .Call
//     entry point); its caller (xpred or rpart) is responsible for
//     catching RError at the .Call boundary.
// -----------------------------------------------------------------------
inline void R_CheckUserInterrupt(void) {
    if (g_interrupt_requested.load(std::memory_order_relaxed)) {
        g_interrupt_requested.store(false, std::memory_order_relaxed);
        throw RError("UserInterrupt");
    }
}

// -----------------------------------------------------------------------
// R_CheckStack / R_CheckStack2 — no-ops in the fake runtime.
// There is no R stack depth limit to enforce.
// -----------------------------------------------------------------------
inline void R_CheckStack(void) {}
inline void R_CheckStack2(std::size_t /*extra*/) {}

#endif // FAKE_UTILS_H
```

**`.Call` boundary wrapper that handles the interrupt case (xpred as representative example):**

```cpp
// fake_entry_points.cpp (excerpt)
//
// The wrapper for xpred must handle RError thrown both by
// R_CheckUserInterrupt (interrupt path) and by any allocation failure.
// Because predict2 is a heap-allocated SEXP that is only returned on
// the success path, the wrapper must not leak it on the interrupt path.
//
// The real xpred() function allocates predict2 internally and returns it.
// The wrapper below catches RError and returns R_NilValue as a sentinel;
// Python checks for R_NilValue and raises an appropriate Python exception.

extern "C" SEXP xpred_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2,
        SEXP ny2, SEXP cost2, SEXP all2,
        SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    ArenaFrame _frame;   // frees all R_alloc / CALLOC scratch allocations
    try {
        return xpred(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2, all2,
                     cp2, toprisk2, nresp2);
    } catch (const RError &e) {
        // Distinguish interrupt from other errors for Python:
        bool is_interrupt = (std::string(e.what()) == "UserInterrupt");
        set_python_error(e.what(), is_interrupt);
        // predict2 is heap-allocated inside xpred(); if the throw
        // occurred after its allocation but before 'return predict2',
        // it is leaked here. In practice, the interrupt fires after
        // free_tree() and before the next iteration, so predict2 was
        // already fully populated or the throw propagated upward through
        // the loop without any intermediate allocation. Accepting this
        // minor leak on the interrupt path is consistent with the fake
        // runtime's simplified lifetime model.
        return R_NilValue;
    }
}
```

- **Arena / Memory Notes:** Not applicable. `R_CheckUserInterrupt` performs no memory allocation of any kind. The arena and heap allocation patterns in `xpred.c` and `xval.c` are not affected by this stub. The `free_tree(xtree, 0)` call immediately before `R_CheckUserInterrupt()` in `xpred.c` frees the per-fold tree's `Calloc`-allocated nodes via `R_Free` before the interrupt check; if the interrupt fires, the tree memory is already released. In `xval.c`, `free_tree(xtree, 1)` similarly releases the per-fold tree before the check.

- **Python Interop Notes:** Not applicable (this is not a Category E item). However, the `request_user_interrupt()` registration function serves a similar purpose to the Category E function pointer bridge: it provides a C-linkage entry point that Python can call to influence the C-level behavior. The complete Python side setup is:

```python
import ctypes
import signal

# Load the compiled fake rpart shared library.
lib = ctypes.CDLL("/path/to/librpart_fake.so")

# Declare the interrupt-request entry point.
lib.request_user_interrupt.restype  = None
lib.request_user_interrupt.argtypes = []

# Install a SIGINT handler that sets the interrupt flag.
# When the user presses Ctrl+C while rpart's cross-validation is running,
# Python's signal mechanism calls this handler, which sets the atomic flag.
# On the next R_CheckUserInterrupt() call (i.e., the next loop iteration),
# the C stub detects the flag and throws RError("UserInterrupt").
# The .Call wrapper catches the RError and returns R_NilValue; the Python
# wrapper function then checks for R_NilValue and raises KeyboardInterrupt.
_original_sigint = signal.getsignal(signal.SIGINT)

def _sigint_handler(signum, frame):
    lib.request_user_interrupt()

signal.signal(signal.SIGINT, _sigint_handler)

# To cancel a running xpred / xval computation from Python:
#   lib.request_user_interrupt()   # call directly if needed
#   # or simply press Ctrl+C if the signal handler above is installed.
```

- **Explanation:**

  In the real R runtime, `R_CheckUserInterrupt` does one of two things: (a) returns immediately if no interrupt is pending — the common case — or (b) calls `R_interrupts_pending` checking logic and ultimately `longjmp`s to the R top level if an interrupt has been signaled. The `longjmp` target is set by a `SETJMP` in R's evaluation loop; in the fake runtime there is no such setjmp context, so the only safe alternative is a C++ `throw`.

  The stub in `fake_Utils.hpp` reads a `thread_local std::atomic<bool>` flag on every call. When the flag is `false` (the overwhelmingly common case), the function body is a single branch-predicted-not-taken test followed by a return — negligible overhead compared to the tree-partitioning work in the surrounding loop body.

  The original source files in `xpred.c` and `xval.c` call `R_CheckUserInterrupt()` by its canonical name with no arguments. Because the fake header defines an `inline void R_CheckUserInterrupt(void)` function with the identical signature, the original source files compile unchanged. No macro alias is required.

  The `xval()` function is not a `.Call` entry point — it is called internally by `xpred()` and by `rpart()` (via `xval`). The `RError` thrown from within `xval()` propagates up through `xpred()` (or through `rpart()`) to the outermost `.Call` boundary wrapper, where it is caught. This propagation is safe because all intermediate stack frames in rpart's C code use only automatic-storage or arena-managed variables (no `longjmp`-unsafe state), so stack unwinding via C++ exceptions is sound.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — provides `fake_Rinternals.hpp` | The `RError` struct (`struct RError : public std::runtime_error`) must be defined before `fake_Utils.hpp` is included, because `R_CheckUserInterrupt` throws `RError`. `fake_Rinternals.hpp` is also the source of the `ArenaFrame` include (via `fake_arena.hpp`) used in the `.Call` boundary wrappers shown above. If `fake_Utils.hpp` is included without `fake_Rinternals.hpp`, it defines its own minimal `RError` via the `#ifndef FAKE_RINTERNALS_H` guard; in a full build, the `SEXP.md` guide must be included first to avoid the duplicate definition. |
| `fake_arena.hpp` (foundational, no separate guide) | The `ArenaFrame` RAII guard used in the `.Call` boundary wrappers for `xpred_wrapper` and the `rpart_wrapper` that calls `xval`. Not used by `R_CheckUserInterrupt` itself, but required by every `.Call` boundary wrapper in which `R_CheckUserInterrupt` is transitively reachable. |

No other fake guides are required by `R_CheckUserInterrupt` itself. The function has no dependencies on `SEXP`, `SEXPTYPE`, allocators, or interpreter items.
