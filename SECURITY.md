# Security Policy

## Supported versions

Only the latest release receives security fixes. psd-tools requires Python 3.11 or later.

## Reporting a vulnerability

Report privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. This is the only reporting channel. Do not open a public
issue or pull request for a suspected vulnerability.

Include the psd-tools version, a minimal reproduction, and the impact. Attach a small
forged or minimized PSD, never a file with private or copyrighted content; see
[Files in reports and pull requests](docs/contributing.rst) for what to attach.

psd-tools is maintained by volunteers and has no fixed response time. A valid report gets a
GitHub Security Advisory, a fix with a regression test, and a release; reporters are credited
unless they ask otherwise.

## Scope

Reportable:

- Memory or CPU exhaustion from a crafted file that gets past the limits in
  [Handling untrusted files](docs/untrusted.rst).
- Reading or writing files outside the intended directory, for example through smart objects.
- Unintended code execution, filesystem access, or network access.
- An exception other than `ValueError` or `OSError` from a call that reads a document, such as
  `PSDImage.open()`, `composite()` or `numpy()`, on malformed input. See
  [Error handling](docs/untrusted.rst).

Not a vulnerability by itself:

- A deliberate `ValueError` or `OSError` rejecting a malformed or over-limit file.
- Any other exception from a property of a document that already opened. It is an ordinary
  bug; report it as a public issue.
- Resource use that [Handling untrusted files](docs/untrusted.rst) says is not bounded.
- Behavior that requires the caller to disable a limit or pass `trust_full_path=True`.
- Mutating low-level structures under the high-level API, which is out of contract.
- Vulnerabilities in dependencies such as Pillow or numpy; report those upstream.

For untrusted files, follow the recommendations in
[Handling untrusted files](docs/untrusted.rst), including process isolation and an OS memory limit.

## Dependencies

Dependabot security updates and secret scanning are enabled.
