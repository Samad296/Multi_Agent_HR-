from typing import Literal, TypedDict


class HRState(TypedDict, total=False):
    # input
    question: str

    # set by the router
    intent: Literal["policy", "leave", "other"]

    # set by the policy node
    retrieved: list[dict]      # doc, section, score of each chunk used
    citations: list[str]       # "document - section"

    # set by the leave node (next step)
    pending_action: dict | None   # proposed write waiting for the user's yes/no
    needs_confirmation: bool

    # output, set by whichever node answers
    answer: str