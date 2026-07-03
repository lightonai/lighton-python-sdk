"""Primary-verb mixins composed onto the LightOn client."""

from lighton.verbs.ask import AskMixin
from lighton.verbs.extract import ExtractMixin
from lighton.verbs.parse import ParseMixin
from lighton.verbs.search import SearchMixin

__all__ = ["AskMixin", "ExtractMixin", "ParseMixin", "SearchMixin"]
