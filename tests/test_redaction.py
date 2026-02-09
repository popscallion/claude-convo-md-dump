from redaction import Redactor


def test_redact_standard_masks_paths_email_url_and_tokens():
    r = Redactor(strict=False)
    text = (
        "home=/Users/alice/work "
        "mail=alice@example.com "
        "url=https://api.example.com/x "
        "tok=sk-abcdefghijk"
    )
    out = r.redact_string(text)
    assert "/Users/USER" in out
    assert "EMAIL-" in out
    assert "HOST-" in out
    assert "TOKEN-" in out


def test_redact_strict_masks_key_value_and_hex():
    r = Redactor(strict=True)
    text = "api_key=secretvalue abcdef0123456789abcdef0123456789"
    out = r.redact_string(text)
    assert "TOKEN-" in out
    assert "secretvalue" not in out


def test_redact_max_len_truncates():
    r = Redactor(max_len=20)
    out = r.redact_string("x" * 80)
    assert "[TRUNCATED len=80]" in out


def test_redact_recursive_structures():
    r = Redactor()
    obj = {"a": ["alice@example.com", {"k": "/Users/alice"}]}
    out = r.redact(obj)
    assert "EMAIL-" in out["a"][0]
    assert "/Users/USER" in out["a"][1]["k"]
