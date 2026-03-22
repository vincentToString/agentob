from pydantic import BaseModel
from typing import Dict, Any
from enum import Enum

class OwlLevel(str, Enum):
    OWL_QUICK = "owl_quick"
    OWL_DEEP = "owl_deep"
    OWL_STANDARD = "owl_standard"

class PullRequestData(BaseModel):
    action: str
    pr_number: int
    pr_title: str
    pr_body: str | None
    pr_url: str
    pr_diff_url: str
    pr_author: str
    repo_name: str
    repo_url: str
    created_at: str
    diff_id: str
    owl_level: OwlLevel