from aiops.textclean import strip_boilerplate

LANGCHAIN = """### Submission checklist

- [x] This is a bug, not a usage question.
- [x] I added a clear and descriptive title.
- [ ] I used the GitHub search.

<!-- please keep this comment -->

### Description

ContextEditingMiddleware calls count_tokens synchronously inside the event
loop, which blocks every other request for ~400ms per message.

### Error Message

```
RuntimeError: event loop blocked
```
"""


def test_checkboxes_headings_and_html_comments_are_dropped():
    out = strip_boilerplate(LANGCHAIN)
    assert "Submission checklist" not in out
    assert "[x]" not in out and "[ ]" not in out
    assert "please keep this comment" not in out
    assert "### Description" not in out


def test_the_actual_report_and_code_survive():
    out = strip_boilerplate(LANGCHAIN)
    assert "ContextEditingMiddleware calls count_tokens" in out
    assert "RuntimeError: event loop blocked" in out
    assert out.startswith("ContextEditingMiddleware")


def test_text_that_is_all_boilerplate_falls_back_to_the_original():
    only_template = "### Checklist\n- [x] I read the docs\n"
    assert strip_boilerplate(only_template).strip() == only_template.strip()


def test_empty_and_none_are_safe():
    assert strip_boilerplate("") == ""
    assert strip_boilerplate(None) == ""
