"""URL redaction for credential safety (Article VI.1).

`redact_url(url)` strips credential-bearing query parameters and any URL
userinfo, returning a string safe to write to a log file or print on
stderr. The hash of the original URL (e.g. for cache keying) is computed
elsewhere — this helper is only about display/logging.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query parameter names whose values are treated as credentials. Match is
# case-insensitive. Conservative on purpose — better to redact a benign
# parameter than to leak a token. Add new names here when the upstream
# platform introduces them.
_CREDENTIAL_PARAM_NAMES = {
    "pwd",
    "password",
    "tk",
    "token",
    "access_token",
    "auth",
    "authorization",
    "signature",
    "sig",
}


def redact_url(url: str) -> str:
    """Return a copy of *url* with credential-bearing components blanked.

    - Userinfo (`user:pass@host`) becomes `***@host`.
    - Any query parameter whose name is in the credential denylist
      (case-insensitive) has its value replaced with `***`.
    - Scheme, host, port, path, and fragment are preserved verbatim.
    - Non-credential query parameters round-trip unchanged.
    - A URL with no credentials round-trips unchanged.
    """
    if not url:
        return url

    parts = urlsplit(url)

    netloc = parts.netloc
    if "@" in netloc:
        _, _, host_port = netloc.rpartition("@")
        netloc = f"***@{host_port}"

    if parts.query:
        redacted_pairs = [
            (key, "***" if key.lower() in _CREDENTIAL_PARAM_NAMES else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        new_query = urlencode(redacted_pairs)
    else:
        new_query = parts.query

    return urlunsplit((parts.scheme, netloc, parts.path, new_query, parts.fragment))
