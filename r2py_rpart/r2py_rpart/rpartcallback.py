from __future__ import annotations

from typing import Any, Callable

import numpy as np

from . import ffi, _lib, _check_error, _cptr, _ERR_BUF_SIZE


def rpartcallback(mlist: dict[str, Callable[..., Any]], nobs: int, init: dict[str, Any]) -> dict[str, Any]:
    if len(mlist) < 3:
        raise ValueError("User written methods must have 3 functions")
    if not callable(mlist.get("init")):
        raise ValueError("User written method does not contain an 'init' function")
    if not callable(mlist.get("split")):
        raise ValueError("User written method does not contain a 'split' function")
    if not callable(mlist.get("eval")):
        raise ValueError("User written method does not contain an 'eval' function")

    user_eval = mlist["eval"]
    user_split = mlist["split"]

    numresp = init["numresp"]
    numy = init["numy"]
    parms = init["parms"]

    # rho dict holds shared mutable state; C code will write into the
    # numpy array buffers stored here before each callback invocation.
    rho: dict[str, Any] = {}
    rho["nback"] = np.zeros(1, dtype=np.int32)
    rho["wback"] = np.zeros(nobs, dtype=np.float64)
    rho["xback"] = np.zeros(nobs, dtype=np.float64)
    rho["yback"] = np.zeros(nobs * numy, dtype=np.float64)
    rho["user_eval"] = user_eval
    rho["user_split"] = user_split
    rho["numy"] = int(numy)
    rho["numresp"] = int(numresp)
    rho["parms"] = parms

    # eval2 replaces expr2: node evaluation callback.
    # Called by rpart_callback1 with eval(expr2, rho).
    # Returns a REALSXP of length (1 + numresp): [deviance, *label].
    if numy == 1:
        def eval2() -> np.ndarray:
            nback = int(rho["nback"][0])
            temp = user_eval(rho["yback"][:nback], rho["wback"][:nback], parms)
            if len(temp["label"]) != numresp:
                raise ValueError("User 'eval' function returned invalid label")
            if np.asarray(temp["deviance"]).size != 1:
                raise ValueError("User 'eval' function returned invalid deviance")
            return np.concatenate([np.asarray(temp["deviance"]).ravel(),
                                   np.asarray(temp["label"]).ravel()]).astype(np.float64)
    else:
        def eval2() -> np.ndarray:
            nback = int(rho["nback"][0])
            tempy = rho["yback"][:nback * numy].reshape((nback, numy), order="F")
            temp = user_eval(tempy, rho["wback"][:nback], parms)
            if len(temp["label"]) != numresp:
                raise ValueError("User 'eval' function returned invalid label")
            if np.asarray(temp["deviance"]).size != 1:
                raise ValueError("User 'eval' function returned invalid deviance")
            return np.concatenate([np.asarray(temp["deviance"]).ravel(),
                                   np.asarray(temp["label"]).ravel()]).astype(np.float64)

    # eval1 replaces expr1: split-goodness callback.
    # Called by rpart_callback2 with eval(expr1, rho).
    # nback < 0 signals a categorical variable; true count is -nback.
    # Returns a REALSXP of concatenated [goodness, direction].
    if numy == 1:
        def eval1() -> np.ndarray:
            nback = int(rho["nback"][0])
            if nback < 0:
                n2 = -nback
                temp = user_split(rho["yback"][:n2], rho["wback"][:n2],
                                  rho["xback"][:n2], parms, False)
                ncat = len(np.unique(rho["xback"][:n2]))
                if len(temp["goodness"]) != ncat - 1 or len(temp["direction"]) != ncat:
                    raise ValueError("Invalid return from categorical 'split' function")
            else:
                temp = user_split(rho["yback"][:nback], rho["wback"][:nback],
                                  rho["xback"][:nback], parms, True)
                if len(temp["goodness"]) != nback - 1:
                    raise ValueError("User 'split' function returned invalid goodness")
                if len(temp["direction"]) != nback - 1:
                    raise ValueError("User 'split' function returned invalid direction")
            return np.concatenate([np.asarray(temp["goodness"]).ravel(),
                                   np.asarray(temp["direction"]).ravel()]).astype(np.float64)
    else:
        def eval1() -> np.ndarray:
            nback = int(rho["nback"][0])
            if nback < 0:
                n2 = -nback
                tempy = rho["yback"][:n2 * numy].reshape((n2, numy), order="F")
                temp = user_split(tempy, rho["wback"][:n2],
                                  rho["xback"][:n2], parms, False)
                ncat = len(np.unique(rho["xback"][:n2]))
                if len(temp["goodness"]) != ncat - 1 or len(temp["direction"]) != ncat:
                    raise ValueError("Invalid return from categorical 'split' function")
            else:
                tempy = rho["yback"][:nback * numy].reshape((nback, numy), order="F")
                temp = user_split(tempy, rho["wback"][:nback],
                                  rho["xback"][:nback], parms, True)
                if len(temp["goodness"]) != nback - 1:
                    raise ValueError("User 'split' function returned invalid goodness")
                if len(temp["direction"]) != nback - 1:
                    raise ValueError("User 'split' function returned invalid direction")
            return np.concatenate([np.asarray(temp["goodness"]).ravel(),
                                   np.asarray(temp["direction"]).ravel()]).astype(np.float64)

    # --- C-level callback setup (mirrors .Call(C_init_rpcallback, ...)) ---
    #
    # The C callback mechanism (rpart_callback1/rpart_callback2) calls
    # eval(expr, rho) at two sites.  We register a single Python dispatch
    # function that selects eval1 or eval2 based on the opaque expr pointer,
    # and wrap the result as a fake REALSXP for the C layer to read via REAL().

    # Step 1: retrieve R_UnboundValue sentinel needed by findVarInFrame.
    _R_UNBOUND = _lib.get_R_UnboundValue()

    # Step 2: register install() stub — maps symbol name -> stable opaque pointer.
    _symbol_handles: dict[str, int] = {}
    _symbol_nodes: dict[str, Any] = {}

    def _py_install(name_bytes: Any) -> Any:
        name = ffi.string(name_bytes).decode()
        if name not in _symbol_handles:
            node = ffi.new("char[1]")
            _symbol_handles[name] = int(ffi.cast("uintptr_t", node))
            _symbol_nodes[name] = node
        return ffi.cast("void *", _symbol_handles[name])

    _install_cb = ffi.callback("void *(char *)", _py_install)
    _lib.register_install_fn(ffi.cast("void *", _install_cb))

    # Step 3: build fake REALSXP/INTSXP wrappers for the four back-arrays
    # using the C helper functions (make_real_sexp / make_int_sexp).
    # The data buffers are owned by the numpy arrays in rho and NOT copied.
    _buf_y = ffi.from_buffer(rho["yback"])
    _buf_w = ffi.from_buffer(rho["wback"])
    _buf_x = ffi.from_buffer(rho["xback"])
    _buf_n = ffi.from_buffer(rho["nback"])

    sexp_y = _lib.make_real_sexp(_buf_y, rho["yback"].size)
    _err = ffi.string(_lib.get_make_sexp_error())
    if _err:
        raise RuntimeError(f"make_real_sexp(yback): {_err.decode()}")

    sexp_w = _lib.make_real_sexp(_buf_w, rho["wback"].size)
    _err = ffi.string(_lib.get_make_sexp_error())
    if _err:
        raise RuntimeError(f"make_real_sexp(wback): {_err.decode()}")

    sexp_x = _lib.make_real_sexp(_buf_x, rho["xback"].size)
    _err = ffi.string(_lib.get_make_sexp_error())
    if _err:
        raise RuntimeError(f"make_real_sexp(xback): {_err.decode()}")

    sexp_n = _lib.make_int_sexp(_buf_n, rho["nback"].size)
    _err = ffi.string(_lib.get_make_sexp_error())
    if _err:
        raise RuntimeError(f"make_int_sexp(nback): {_err.decode()}")

    # Step 4: create an opaque rho handle (stable unique identity pointer).
    _rho_sexp = _lib.make_env_sexp()
    _err = ffi.string(_lib.get_make_sexp_error())
    if _err:
        raise RuntimeError(f"make_env_sexp: {_err.decode()}")
    _rho_ptr = int(ffi.cast("uintptr_t", _rho_sexp))

    # Step 5: populate the frame registry and register findVarInFrame stub.
    # Call _py_install for each back variable name to populate _symbol_handles.
    for _name in (b"yback", b"wback", b"xback", b"nback"):
        _py_install(_name)

    _frame_registry: dict[int, dict[int, Any]] = {
        _rho_ptr: {
            _symbol_handles["yback"]: sexp_y,
            _symbol_handles["wback"]: sexp_w,
            _symbol_handles["xback"]: sexp_x,
            _symbol_handles["nback"]: sexp_n,
        }
    }

    def _py_findVarInFrame(rho_p: Any, sym_p: Any) -> Any:
        rho_int = int(ffi.cast("uintptr_t", rho_p))
        sym_int = int(ffi.cast("uintptr_t", sym_p))
        frame = _frame_registry.get(rho_int, {})
        val = frame.get(sym_int)
        if val is None:
            return _R_UNBOUND
        return val

    _findVarInFrame_cb = ffi.callback("void *(void *, void *)", _py_findVarInFrame)
    _lib.register_findVarInFrame_fn(ffi.cast("void *", _findVarInFrame_cb))

    # Step 6: register findVar() stub (inherits=TRUE path; dead code for rpart).
    def _py_findVar(sym_p: Any, rho_p: Any) -> Any:
        return _R_UNBOUND

    _findVar_cb = ffi.callback("void *(void *, void *)", _py_findVar)
    _lib.register_findVar_fn(ffi.cast("void *", _findVar_cb))

    # Step 7: create opaque expr1/expr2 pointer handles.
    _expr1_node = ffi.new("char[1]")
    _expr2_node = ffi.new("char[1]")
    _expr1_ptr  = int(ffi.cast("uintptr_t", _expr1_node))
    _expr2_ptr  = int(ffi.cast("uintptr_t", _expr2_node))

    # Step 8: register eval() stub — dispatches on expr pointer to eval1/eval2.
    # eval(expr2, rho) -> rpart_callback1 (node evaluation)
    # eval(expr1, rho) -> rpart_callback2 (split goodness)
    # Return value must be a fake REALSXP whose REAL() pointer C can read.
    _eval_result_keeper: list[Any] = []  # prevent GC until C has copied data

    def _py_eval(expr_p: Any, rho_p: Any) -> Any:
        try:
            expr_int = int(ffi.cast("uintptr_t", expr_p))
            if expr_int == _expr2_ptr:
                result_arr = eval2()
            elif expr_int == _expr1_ptr:
                result_arr = eval1()
            else:
                return ffi.cast("void *", 0)
            result_arr = np.ascontiguousarray(result_arr, dtype=np.float64)
            buf = ffi.from_buffer(result_arr)
            sexp_result = _lib.make_real_sexp(buf, result_arr.size)
            _eval_result_keeper.append((result_arr, buf, sexp_result))
            return sexp_result
        except Exception:
            return ffi.cast("void *", 0)

    _eval_cb = ffi.callback("void *(void *, void *)", _py_eval)
    _lib.register_eval_fn(ffi.cast("void *", _eval_cb))

    # Step 9: call init_rpcallback_c to initialise C-level statics
    # (rho, ysave, rsave, expr1, expr2, ydata, wdata, xdata, ndata).
    err_buf = np.zeros(_ERR_BUF_SIZE, dtype=np.uint8)
    _lib.init_rpcallback_c(
        _rho_sexp,
        int(numy),
        int(numresp),
        ffi.cast("void *", _expr1_ptr),
        ffi.cast("void *", _expr2_ptr),
        _cptr(err_buf),
        _ERR_BUF_SIZE,
    )
    _check_error(err_buf)

    # Store cffi callbacks and SEXP nodes in rho so they remain alive for
    # the duration of the callback session (cffi callbacks are freed when GC'd).
    rho["_cffi_keep_alive"] = [
        _install_cb, _findVarInFrame_cb, _findVar_cb, _eval_cb,
        _rho_sexp, _expr1_node, _expr2_node,
        sexp_y, sexp_w, sexp_x, sexp_n,
        _buf_y, _buf_w, _buf_x, _buf_n,
        _eval_result_keeper,
        _symbol_nodes,
    ]

    return {"eval1": eval1, "eval2": eval2, "rho": rho}
