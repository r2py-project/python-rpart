from __future__ import annotations

from typing import Any

from .post_rpart import post_rpart


def post(tree: dict[str, Any], **kwargs: Any) -> None:
    post_rpart(tree, **kwargs)
