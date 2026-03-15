"""
comobot - A lightweight AI agent framework
"""

import os as _os

# Force LiteLLM to use its bundled local model cost map instead of fetching
# from raw.githubusercontent.com (which is unreachable in mainland China
# without a proxy).  Must be set before ``import litellm`` anywhere.
_os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

__version__ = "0.2.0"
__logo__ = "🤖"
