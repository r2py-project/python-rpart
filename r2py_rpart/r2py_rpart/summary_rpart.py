from __future__ import annotations

from typing import Any

import sys
import contextlib
import numpy as np
import pandas as pd

_MISSING = object()


def summary_rpart(object: dict[str, Any], cp: float = 0, digits: int | None = None, file: str | object = _MISSING, **kwargs) -> dict[str, Any]:
    if not isinstance(object, dict) or 'frame' not in object:
        raise ValueError('Not a legitimate "rpart" object')
    x = object
    if digits is None:
        digits = 7
    def _do_summary():
        if x.get('call') is not None:
            print('Call:')
            print(repr(x.get('call')))
        omit = x.get('na.action')
        ff = x['frame']
        n = ff['n'].values
        if omit is not None and len(omit) > 0:
            _n_omit = len(omit)
            _noun = 'observation' if _n_omit == 1 else 'observations'
            _naprint_str = f'{_n_omit} {_noun} deleted due to missingness'
            print(f'  n={n[0]} ({_naprint_str})\n')
        else:
            print(f'  n={n[0]}\n')
        print(pd.DataFrame(x['cptable']).to_string())
        temp_vi = x.get('variable.importance')
        if temp_vi is not None:
            temp_vi_rounded = np.round(100 * temp_vi / temp_vi.sum()).astype(int)
            if hasattr(temp_vi_rounded, 'values'):
                _arr = temp_vi_rounded.values
                _idx = temp_vi_rounded.index
            else:
                _arr = temp_vi_rounded
                _idx = np.arange(len(_arr))
            if np.any(_arr > 0):
                print('\nVariable importance')
                _mask = _arr > 0
                for _name, _val in zip(np.asarray(_idx)[_mask], _arr[_mask]):
                    print(f'{_name}: {_val}')
        ff = x['frame']
        ylevel = object.get('ylevels')
        id = ff.index.astype(int).values
        parent_id = np.where(id == 1, 1, id // 2)
        _id_to_pos = {v: i for i, v in enumerate(id)}
        parent_cp = np.array([ff['complexity'].values[_id_to_pos[pid]] for pid in parent_id])
        _rows_candidates = np.where(parent_cp > cp)[0]
        if len(_rows_candidates) > 0:
            rows = _rows_candidates[np.argsort(id[_rows_candidates])]
        else:
            rows = np.array([0], dtype=int)
        is_leaf = ff['var'].values == '<leaf>'
        index = np.cumsum(np.concatenate([[1], ff['ncompete'].values + ff['nsurrogate'].values + (~is_leaf).astype(int)])) - 1
        if not np.all(is_leaf):
            sname = list(x['splits'].index) if hasattr(x['splits'], 'index') else [str(i) for i in range(x['splits'].shape[0])]
            splits_arr = np.asarray(x['splits'])
            temp_col = splits_arr[:, 1].astype(float)
            cuts = [''] * splits_arr.shape[0]
            for i in range(len(cuts)):
                _tc = temp_col[i]
                if _tc == -1:
                    _val = splits_arr[i, 3]
                    _val_fmt = f'{_val:.{digits}g}'
                    cuts[i] = f'< {_val_fmt}'
                elif _tc == 1:
                    _val = splits_arr[i, 3]
                    _val_fmt = f'{_val:.{digits}g}'
                    cuts[i] = f'< {_val_fmt}'
                else:
                    _ncat = int(_tc)
                    _csplit_idx = int(splits_arr[i, 3]) - 1
                    _csplit_vals = x['csplit'][_csplit_idx, :_ncat]
                    _lut = ['L', '-', 'R']
                    _letters = ''.join(_lut[int(v) - 1] for v in _csplit_vals)
                    cuts[i] = f'splits as {_letters}'
            cuts = np.array(cuts, dtype=object)
            _continuous_mask = temp_col < 2
            if np.any(_continuous_mask):
                _widths = np.array([len(s) for s in cuts[_continuous_mask]])
                _max_w = int(_widths.max()) if len(_widths) > 0 else 0
                _formatted = np.array([s.ljust(_max_w) for s in cuts[_continuous_mask]])
                cuts_copy = cuts.copy()
                cuts_copy[_continuous_mask] = _formatted
                cuts = cuts_copy
            cuts = np.array([
                s + (',') if temp_col[_ci] >= 2 else
                s + (' to the right,') if temp_col[_ci] == 1 else
                s + (' to the left, ')
                for _ci, s in enumerate(cuts)
            ], dtype=object)
        else:
            sname = []
            cuts = np.array([], dtype=object)
            temp_col = np.array([], dtype=float)
        if 'yval2' in ff.columns:
            _tmp = ff['yval2'].values[rows]
        else:
            _tmp = ff['yval'].values[rows]
        tprint = x['functions']['summary'](_tmp, ff['dev'].values[rows], ff['wt'].values[rows], ylevel, digits)
        for ii in range(len(rows)):
            i = rows[ii]
            nn = ff['n'].values[i]
            print(f'\nNode number {id[i]}: {nn} observations', end='')
            if ff['complexity'].values[i] < cp or is_leaf[i]:
                print()
            else:
                _cp_fmt = f"{ff['complexity'].values[i]:.{digits}g}"
                print(f',    complexity param={_cp_fmt}')
            _tp = tprint[ii] if hasattr(tprint, '__getitem__') else str(tprint)
            print(f'{_tp}')
            if ff['complexity'].values[i] > cp and not is_leaf[i]:
                sons = np.array([2 * id[i], 2 * id[i] + 1], dtype=int)
                sons_n = np.array([ff['n'].values[_id_to_pos[s]] if s in _id_to_pos else np.nan for s in sons])
                print(f'  left son={sons[0]} ({int(sons_n[0])} obs) right son={sons[1]} ({int(sons_n[1])} obs)', end='')
                j_miss = nn - (sons_n[0] + sons_n[1])
                if j_miss > 1:
                    print(f', {int(j_miss)} observations remain')
                elif j_miss == 1:
                    print(', 1 observation remains')
                else:
                    print()
                print('  Primary splits:')
                _ncompete_i = ff['ncompete'].values[i]
                j = np.arange(index[i], index[i] + 1 + _ncompete_i, dtype=int)
                _cuts_j = cuts[j]
                _widths_j = np.array([len(s) for s in _cuts_j])
                if np.all(_widths_j < 25):
                    _max_w_j = int(_widths_j.max()) if len(_widths_j) > 0 else 0
                    _temp_j = np.array([s.ljust(_max_w_j) for s in _cuts_j])
                else:
                    _temp_j = _cuts_j
                _snames_j = [sname[jj] for jj in j]
                _max_name_w = max((len(s) for s in _snames_j), default=0)
                _improve_arr = splits_arr[j, 2]
                _missing_arr = nn - splits_arr[j, 0]
                for _k in range(len(j)):
                    _sn = _snames_j[_k].ljust(_max_name_w)
                    _ct = _temp_j[_k]
                    _imp_fmt = f'{_improve_arr[_k]:.{digits}g}'
                    _miss_int = int(_missing_arr[_k])
                    print(f'      {_sn} {_ct} improve={_imp_fmt}, ({_miss_int} missing)')
                _nsurrogate_i = ff['nsurrogate'].values[i]
                if _nsurrogate_i > 0:
                    print('  Surrogate splits:')
                    j2 = np.arange(1 + index[i] + _ncompete_i, 1 + index[i] + _ncompete_i + _nsurrogate_i, dtype=int)
                    _agree = splits_arr[j2, 2]
                    _cuts_j2 = cuts[j2]
                    _widths_j2 = np.array([len(s) for s in _cuts_j2])
                    if np.all(_widths_j2 < 25):
                        _max_w_j2 = int(_widths_j2.max()) if len(_widths_j2) > 0 else 0
                        _temp_j2 = np.array([s.ljust(_max_w_j2) for s in _cuts_j2])
                    else:
                        _temp_j2 = _cuts_j2
                    _snames_j2 = [sname[jj] for jj in j2]
                    _max_name_w2 = max((len(s) for s in _snames_j2), default=0)
                    _adj = splits_arr[j2, 4]
                    _split_count = splits_arr[j2, 0]
                    for _k in range(len(j2)):
                        _sn2 = _snames_j2[_k].ljust(_max_name_w2)
                        _ct2 = _temp_j2[_k]
                        _agree_fmt = f'{round(float(_agree[_k]), 3)}'
                        _adj_fmt = f'{round(float(_adj[_k]), 3)}'
                        _sc_int = int(_split_count[_k])
                        print(f'      {_sn2} {_ct2} agree={_agree_fmt}, adj={_adj_fmt}, ({_sc_int} split)')
        print()
    if file is not _MISSING:
        with open(file, 'w') as _fh, contextlib.redirect_stdout(_fh):
            _do_summary()
    else:
        _do_summary()
    return x
