project('r2py_rpart', 'c', 'cpp',
  default_options: [
    'c_std=none',      # suppressed — we pass -std=c++14 explicitly via c_args
    'cpp_std=c++14',
  ]
)

py_mod = import('python')
py = py_mod.find_installation(pure: false)

inc_fake = include_directories('r_fake_headers')
inc_src  = include_directories('src')

# rpart C source files.  All .c files must be compiled as C++ because fake_R.h
# uses C++ features (throw, std::bad_alloc, inline variables, extern "C" inline).
#
# Meson compiles .c files with the C compiler.  We pass:
#   -x c++               — tell gcc to treat the input as C++ source
#   -std=c++14           — C++14 avoids <cmath> C++17 builtins (__iscanonical etc.)
#                          that are undefined on GCC 11's glibc; inline variables in
#                          fake headers are accepted as a GCC extension in C++14 mode
#   -fkeep-inline-functions — force GCC to emit out-of-line copies of extern "C"
#                             inline registration functions so Python can call them
#                             via cffi/ctypes (register_eval_fn, register_install_fn, …)
rpart_src = files(
  'src/anova.c',
  'src/anovapred.c',
  'src/branch.c',
  'src/bsplit.c',
  'src/choose_surg.c',
  'src/fix_cp.c',
  'src/free_tree.c',
  'src/gini.c',
  'src/graycode.c',
  'src/init.c',
  'src/insert_split.c',
  'src/make_cp_list.c',
  'src/make_cp_table.c',
  'src/mysort.c',
  'src/nodesplit.c',
  'src/partition.c',
  'src/poisson.c',
  'src/pred_rpart.c',
  'src/print_tree.c',
  'src/rpart.c',
  'src/rpart_callback.c',
  'src/rpartexp2.c',
  'src/rpartexp.c',
  'src/rpcountup.c',
  'src/rpmatrix.c',
  'src/rundown2.c',
  'src/rundown.c',
  'src/surrogate.c',
  'src/usersplit.c',
  'src/xpred.c',
  'src/xval.c',
  # Pure-C-ABI entry-point wrappers (extern "C" noexcept, callable from cffi)
  'c_entry_points/rpart_c.c',
  'c_entry_points/pred_rpart_c.c',
  'c_entry_points/xpred_c.c',
  'c_entry_points/rpartexp2_c.c',
  'c_entry_points/init_rpcallback_c.c',
)

# Build a plain shared library.  cffi's dlopen() in __init__.py loads it by
# absolute path, so no soname or RPATH configuration is required.
# name_prefix: '' avoids the 'lib' prefix → _rpart_core.so instead of lib_rpart_core.so.
# Apple clang (macOS) ships libc++, not libstdc++.  GCC and MinGW (Linux,
# Windows) ship libstdc++.  Pick the right runtime based on the target OS.
if host_machine.system() == 'darwin'
  cxx_stdlib_link = ['-lc++']
else
  cxx_stdlib_link = ['-lstdc++']
endif

shared_library(
  '_rpart_core',
  rpart_src,
  include_directories: [inc_fake, inc_src],
  c_args: [
    '-x', 'c++',
    '-std=c++14',
    '-fkeep-inline-functions',
    '-fPIC',
  ],
  name_prefix: '',
  # All .c files are compiled as C++ (via -x c++) by the C compiler.
  # The C compiler's linker does not automatically pull in the C++ runtime,
  # so we link it explicitly to resolve C++ ABI symbols (__cxa_throw, etc.).
  link_args: cxx_stdlib_link + ['-lm'],
  install: true,
  install_dir: py.get_install_dir() / 'r2py_rpart',
)

py.install_sources(
  'r2py_rpart/__init__.py',
  'r2py_rpart/formatg.py',
  'r2py_rpart/importance.py',
  'r2py_rpart/labels_rpart.py',
  'r2py_rpart/meanvar_rpart.py',
  'r2py_rpart/model_frame_rpart.py',
  'r2py_rpart/na_rpart.py',
  'r2py_rpart/path_rpart.py',
  'r2py_rpart/plot_rpart.py',
  'r2py_rpart/plotcp.py',
  'r2py_rpart/post.py',
  'r2py_rpart/post_rpart.py',
  'r2py_rpart/pred_rpart.py',
  'r2py_rpart/predict_rpart.py',
  'r2py_rpart/print_rpart.py',
  'r2py_rpart/printcp.py',
  'r2py_rpart/prune.py',
  'r2py_rpart/prune_rpart.py',
  'r2py_rpart/residuals_rpart.py',
  'r2py_rpart/roc_rpart.py',
  'r2py_rpart/rpart.py',
  'r2py_rpart/rpart_anova.py',
  'r2py_rpart/rpart_branch.py',
  'r2py_rpart/rpart_class.py',
  'r2py_rpart/rpart_control.py',
  'r2py_rpart/rpart_exp.py',
  'r2py_rpart/rpart_matrix.py',
  'r2py_rpart/rpart_poisson.py',
  'r2py_rpart/rpartcallback.py',
  'r2py_rpart/rpartco.py',
  'r2py_rpart/rsq_rpart.py',
  'r2py_rpart/snip_rpart.py',
  'r2py_rpart/snip_rpart_mouse.py',
  'r2py_rpart/summary_rpart.py',
  'r2py_rpart/text_rpart.py',
  'r2py_rpart/xpred_rpart.py',
  'r2py_rpart/zzz.py',
  subdir: 'r2py_rpart',
)
