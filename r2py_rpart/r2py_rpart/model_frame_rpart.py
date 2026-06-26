from __future__ import annotations

from typing import Any

import pandas as pd
from .na_rpart import na_rpart



def model_frame_rpart(formula: dict[str, Any], **kwargs: Any) -> pd.DataFrame | None:
    m: pd.DataFrame | None = formula.get('model')
    if m is not None:
        return m
    oc: dict[str, Any] = formula['call']
    if str(oc.get('func_name', ''))[:7] == 'predict':
        m = oc['newdata']
        if m.attrs.get('terms') is None:
            m = na_rpart(m)
        return m
    oc = formula['call']
    oc['subset'] = list(formula['where'].keys())
    oc['method'] = formula['method']
    return None
