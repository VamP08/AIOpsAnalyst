"""Strip issue-template boilerplate before anyone reads the text.

GitHub issue bodies open with a submission checklist and section headings that
are identical across every report in a repo. Left in, they fill the first few
hundred characters the model is given and the labeler sees, making unrelated
issues look alike. Headings, checkboxes and HTML comments go; prose and code
stay. If a body is nothing but boilerplate, it is returned unchanged rather
than emptied — no text is worse than boring text.
"""
import re

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[[ xX]\]")
_HEADING = re.compile(r"^\s*#{1,6}\s")


def strip_boilerplate(text: str | None) -> str:
    if not text:
        return ""
    kept = [line for line in _COMMENT.sub("", text).splitlines()
            if not _CHECKBOX.match(line) and not _HEADING.match(line)]
    cleaned = "\n".join(kept).strip()
    return cleaned or text.strip()
