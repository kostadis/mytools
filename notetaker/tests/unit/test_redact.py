from notetaker.utils.redact import redact_url


def test_zoom_share_recording_pwd_is_redacted():
    url = "https://zoom.us/rec/play/abc123?pwd=SECRETSECRET"
    out = redact_url(url)
    assert "SECRETSECRET" not in out
    assert "pwd=%2A%2A%2A" in out or "pwd=***" in out
    assert out.startswith("https://zoom.us/rec/play/abc123?")


def test_multiple_credential_params_all_redacted():
    url = "https://zoom.us/rec/play/abc?pwd=SECRETSECRET&access_token=TOKENTOKEN"
    out = redact_url(url)
    assert "SECRETSECRET" not in out
    assert "TOKENTOKEN" not in out


def test_userinfo_is_redacted():
    url = "https://alice:hunter2@example.com/path?x=1"
    out = redact_url(url)
    assert "alice" not in out
    assert "hunter2" not in out
    assert "***@example.com" in out
    # Non-credential query param preserved.
    assert "x=1" in out


def test_no_credentials_round_trips_unchanged():
    url = "https://zoom.us/rec/play/abc123?clip_id=42"
    assert redact_url(url) == url


def test_non_credential_params_are_not_touched():
    url = "https://example.com/search?q=password&page=1"
    # `q` is a search query, not a credential param.
    out = redact_url(url)
    assert "q=password" in out
    assert "page=1" in out


def test_credential_keys_match_case_insensitively():
    url = "https://example.com/x?Authorization=BEARERTOKEN&PWD=FOO"
    out = redact_url(url)
    assert "BEARERTOKEN" not in out
    assert "FOO" not in out


def test_empty_string_passes_through():
    assert redact_url("") == ""


def test_path_and_fragment_preserved():
    url = "https://zoom.us/rec/play/abc?pwd=SECRET#t=120"
    out = redact_url(url)
    assert "/rec/play/abc" in out
    assert "#t=120" in out
    assert "SECRET" not in out
