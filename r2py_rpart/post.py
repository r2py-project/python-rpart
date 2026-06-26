from __future__ import annotations

from typing import Any




def post(tree: dict[str, Any], **kwargs: Any) -> None:
    post_rpart(tree, **kwargs)
