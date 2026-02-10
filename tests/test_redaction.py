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


def test_redact_stable_tokens_reuse_same_mapping():
    r = Redactor()
    out = r.redact_string("bob@example.com and bob@example.com")
    tokens = [part for part in out.split() if part.startswith("EMAIL-")]
    assert len(tokens) == 2
    assert tokens[0] == tokens[1]


def test_redact_url_userinfo_and_ip_and_domain_file_extension():
    r = Redactor(strict=False)
    out = r.redact_string("https://alice@127.0.0.1:8443/x 127.0.0.1 readme.md")
    assert "USERINFO@" in out
    assert "HOST-" in out
    assert "IP-" in out
    assert "readme.md" in out
