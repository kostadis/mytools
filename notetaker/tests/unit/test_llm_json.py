from notetaker.utils.llm_json import strip_code_fence


def test_bare_json_is_unchanged():
    raw = '{"title": "Overview", "bullets": []}'
    assert strip_code_fence(raw) == raw


def test_strips_json_tagged_fence():
    raw = '```json\n{"title": "Overview", "bullets": []}\n```'
    assert strip_code_fence(raw) == '{"title": "Overview", "bullets": []}'


def test_strips_untagged_fence():
    raw = '```\n{"title": "Overview"}\n```'
    assert strip_code_fence(raw) == '{"title": "Overview"}'


def test_tolerates_surrounding_whitespace():
    raw = '\n\n  ```json\n{"a": 1}\n```  \n'
    assert strip_code_fence(raw) == '{"a": 1}'


def test_preserves_multiline_json_body():
    raw = '```json\n{\n  "title": "T",\n  "bullets": ["a", "b"]\n}\n```'
    expected = '{\n  "title": "T",\n  "bullets": ["a", "b"]\n}'
    assert strip_code_fence(raw) == expected


def test_unfenced_text_with_internal_backticks_is_unchanged():
    raw = 'no fence here, but `inline code` exists'
    assert strip_code_fence(raw) == raw
