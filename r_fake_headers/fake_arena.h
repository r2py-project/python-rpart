// =============================================================
// fake_arena.h — Arena allocator for the fake R runtime
//
// Replaces R's vmalloc / R_alloc memory pool.
//
// PUBLIC INTERFACE
// ----------------
//   ArenaFrame           — RAII guard; declare as first local in .Call wrappers
//   arena_alloc(bytes)   — allocate bytes from the current frame
//   arena_calloc(n,size) — zero-initialized allocation (n*size bytes)
//
// USAGE
// -----
// Declare one ArenaFrame at the entry of each .Call-registered wrapper:
//
//   extern "C" SEXP rpart_entry(...) {
//       ArenaFrame _frame;   // <-- owns every R_alloc/ALLOC call below
//       try {
//           return rpart(...);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       } catch (const std::bad_alloc &) {
//           set_python_error("R_alloc: out of memory");
//           return R_NilValue;
//       }
//   }   // _frame destructs here — all arena blocks freed
//
// The five rpart .Call entry points requiring ArenaFrame:
//   rpart, xpred, pred_rpart, rpartexp2, init_rpcallback
//
// Sub-functions (gini.c, anova.c, poisson.c, partition.c, etc.) share the
// caller's frame; they must NOT declare their own ArenaFrame.
//
// DESIGN
// ------
// Each call to arena_alloc(n) performs one std::malloc of (HEADER + n) bytes.
// The first HEADER bytes store a void* chain link (previous block in the
// frame's free list).  The remaining n bytes are returned to the caller,
// aligned to std::max_align_t (16 bytes on x86-64 Linux).
//
// ArenaFrame maintains a singly-linked list of all blocks it allocated.
// Its destructor walks the list and calls std::free on every block.
//
// Multiple ArenaFrames can be nested (e.g., if a sub-function creates its own
// scope).  Each frame only frees its own blocks.  g_current_arena_frame is a
// thread-local pointer to the innermost active frame, maintained by ctor/dtor.
//
// THREAD SAFETY
// -------------
// g_current_arena_frame is thread_local.  Each thread has an independent
// arena stack.  No locking is required.  rpart's .Call entry points are
// single-threaded in the Python ctypes model.
// =============================================================
#pragma once

#ifndef FAKE_ARENA_H
#define FAKE_ARENA_H

#include <cstddef>    // std::size_t, alignof, std::max_align_t
#include <cstdlib>    // std::malloc, std::free
#include <cstring>    // std::memset
#include <new>        // std::bad_alloc
#include <stdexcept>  // std::runtime_error

// ---------------------------------------------------------------------------
// FAKE_ARENA_HDRSIZE — bytes of overhead prepended to every arena block.
//
// Stores one void* chain pointer while preserving std::max_align_t alignment
// for the data that follows.
//
// On x86-64 Linux (GCC/Clang):
//   sizeof(void*)              = 8
//   alignof(std::max_align_t)  = 16
//   FAKE_ARENA_HDRSIZE         = (8 + 15) & ~15 = 16
//
// The data area therefore starts at offset 16, satisfying alignment for
// double, long double, __m128, and any other standard type.
// ---------------------------------------------------------------------------
static constexpr std::size_t FAKE_ARENA_HDRSIZE =
    (sizeof(void *) + alignof(std::max_align_t) - 1u)
    & ~(alignof(std::max_align_t) - 1u);

// ---------------------------------------------------------------------------
// ArenaFrame — forward declaration needed by arena_alloc.
// ---------------------------------------------------------------------------
struct ArenaFrame;

// ---------------------------------------------------------------------------
// g_current_arena_frame — thread-local pointer to the innermost active frame.
//
// nullptr means no ArenaFrame is currently active on this thread.
// arena_alloc throws if this is nullptr.
// ---------------------------------------------------------------------------
inline thread_local ArenaFrame *g_current_arena_frame = nullptr;

// ---------------------------------------------------------------------------
// ArenaFrame — RAII arena frame.
//
// Declare as the first local variable in every .Call boundary wrapper that
// directly or transitively calls R_alloc / ALLOC.
// ---------------------------------------------------------------------------
struct ArenaFrame {
    void       *head_;   // head of this frame's block free-list (nullptr = empty)
    ArenaFrame *prev_;   // previously active frame (nullptr = outermost)

    ArenaFrame() noexcept
        : head_(nullptr)
        , prev_(g_current_arena_frame)
    {
        g_current_arena_frame = this;
    }

    ~ArenaFrame() {
        void *block = head_;
        while (block) {
            // The first FAKE_ARENA_HDRSIZE bytes of each block store a void*
            // to the previous block in the list.
            void *prev = *static_cast<void **>(block);
            std::free(block);
            block = prev;
        }
        g_current_arena_frame = prev_;
    }

    // Non-copyable, non-movable — must live on the C++ call stack.
    ArenaFrame(const ArenaFrame &)            = delete;
    ArenaFrame &operator=(const ArenaFrame &) = delete;
    ArenaFrame(ArenaFrame &&)                 = delete;
    ArenaFrame &operator=(ArenaFrame &&)      = delete;
};

// ---------------------------------------------------------------------------
// arena_alloc — allocate `bytes` bytes from the current ArenaFrame.
//
// Returns a pointer aligned to std::max_align_t.
// Throws std::bad_alloc if std::malloc returns nullptr.
// Throws std::runtime_error if no ArenaFrame is active (programming error:
//   the .Call wrapper forgot to declare ArenaFrame _frame;).
//
// The caller must not std::free the returned pointer; it is freed in bulk
// by the enclosing ArenaFrame destructor.
// ---------------------------------------------------------------------------
inline void *arena_alloc(std::size_t bytes) {
    ArenaFrame *frame = g_current_arena_frame;
    if (!frame)
        throw std::runtime_error(
            "arena_alloc: no active ArenaFrame — "
            "declare 'ArenaFrame _frame;' as the first statement "
            "of the .Call boundary wrapper before calling R_alloc/ALLOC");

    std::size_t total = FAKE_ARENA_HDRSIZE + bytes;
    void *block = std::malloc(total);
    if (!block) throw std::bad_alloc();

    // Write the previous head into the block's header area.
    *static_cast<void **>(block) = frame->head_;
    frame->head_ = block;

    // Return the data area (past the header), aligned to max_align_t.
    return static_cast<char *>(block) + FAKE_ARENA_HDRSIZE;
}

// ---------------------------------------------------------------------------
// arena_calloc — zero-initialized allocation of n*size bytes.
//
// Equivalent to std::calloc but arena-managed.  Not a true two-argument
// calloc (no overflow check on n*size); rpart's usage (moderate counts of
// moderate-sized types) is safe.
// ---------------------------------------------------------------------------
inline void *arena_calloc(std::size_t n, std::size_t size) {
    std::size_t bytes = n * size;
    void *ptr = arena_alloc(bytes);
    std::memset(ptr, 0, bytes);
    return ptr;
}

#endif // FAKE_ARENA_H
