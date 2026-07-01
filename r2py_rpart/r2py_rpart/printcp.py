from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd



def printcp(x: dict, digits: int = 2) -> np.ndarray | pd.DataFrame:
    if not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart'):
        raise TypeError('x must be an "rpart" object')
    _METHOD_HEADER = {
        'anova':   '\nRegression tree:\n',
        'class':   '\nClassification tree:\n',
        'poisson': '\nRates regression tree:\n',
        'exp':     '\nSurvival regression tree:\n',
    }
    print(_METHOD_HEADER[x['method']], end='')
    cl = x.get('call')
    if cl is not None:
        print(repr(cl))
        print()
    frame = x['frame']
    leaves = frame['var'] == '<leaf>'
    used = frame['var'][~leaves].unique()
    if used is not None and len(used) > 0:
        print('Variables actually used in tree construction:')
        print(sorted(str(v) for v in used))
        print()
    dev0 = frame['dev'].iloc[0]
    n0 = frame['n'].iloc[0]
    print(
        f'Root node error: {format(dev0, f".{digits}g")}/{n0} = '
        f'{format(dev0 / n0, f".{digits}g")}',
    )
    print()
    n = x['frame']['n']
    omit = x.get('na.action')
    # `na.action` is a dict {'indices', 'names', 'class'} (see na_rpart.py);
    # the observation count is len(omit['indices']), not len(omit) (which
    # would wrongly always be 3, the fixed number of dict keys).
    n_omit = len(omit['indices']) if omit is not None else 0
    if omit is not None and n_omit > 0:
        noun = 'observation' if n_omit == 1 else 'observations'
        naprint_str = f'{n_omit} {noun} deleted due to missingness'
        print(f'n={n.iloc[0]} ({naprint_str})', end='\n\n')
    else:
        print(f'n={n.iloc[0]}', end='\n\n')
    cptable = x['cptable']
    if isinstance(cptable, pd.DataFrame):
        print(cptable.to_string(float_format=lambda v: format(v, f'.{digits}g')))
    else:
        col_names = ['CP', 'nsplit', 'rel error', 'xerror', 'xstd']
        row_names = [str(i + 1) for i in range(cptable.shape[0])]
        cptable_df = pd.DataFrame(cptable, index=row_names, columns=col_names[:cptable.shape[1]])
        print(cptable_df.to_string(float_format=lambda v: format(v, f'.{digits}g')))
    return x['cptable']
