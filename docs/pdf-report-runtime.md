# PDF Report Runtime

The active stock and sector report exporter uses `markdown-it-py` and
WeasyPrint. It does not use Chromium. The archived `generate_pdf_report()` path
continues to use `fpdf2`.

## Python dependencies

The production dependency ranges are declared in `pyproject.toml` and resolved
in `uv.lock`:

```text
jinja2>=3.1,<4
markdown-it-py[plugins]>=4.2,<5
weasyprint>=69,<70
```

Install the locked environment and print the native runtime versions with:

```bash
uv sync
uv run python -m weasyprint --info
```

WeasyPrint 69 requires Python 3.10 or newer, Pango 1.44 or newer, and the
matching HarfBuzz, Fontconfig, and PangoFT2 runtime libraries. This repository
uses Python 3.12.

## Linux system packages

For Debian 11 or newer when Python wheels are used:

```bash
apt-get update
apt-get install -y --no-install-recommends \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

For Ubuntu 20.04 or newer when Python wheels are used:

```bash
apt-get update
apt-get install -y --no-install-recommends \
  libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0
```

For Alpine 3.17 or newer:

```bash
apk add \
  so:libgobject-2.0.so.0 so:libpango-1.0.so.0 \
  so:libharfbuzz.so.0 so:libharfbuzz-subset.so.0 \
  so:libfontconfig.so.1 so:libpangoft2-1.0.so.0
```

For Fedora 39 or newer, install `pango` before `uv sync`. Compiling Python
dependencies from source also requires the image, FFI, compiler, and Python
development packages listed in the official WeasyPrint installation guide.

No container definition is added by this feature. Apply these packages to the
deployment or CI image that actually runs the FastAPI service.

## Bundled fonts

The renderer uses repository-owned Noto Sans CJK SC files and never scans the
host font directories or downloads fonts at runtime.

Source: `notofonts/noto-cjk`, release tag `NotoSansV2.001`, commit
`cf29231ab8029678af4bbc1a9480e2b296a5b2d3`.

| File | Size | SHA-256 |
| --- | ---: | --- |
| `NotoSansCJKsc-Regular.otf` | 17,281,332 bytes | `ee85a1e4126e287a373625cce025b3235cdebf96f71b78f5ef165893c6f8c99f` |
| `NotoSansCJKsc-Bold.otf` | 17,878,572 bytes | `f132a846a6c0ef1a496e64a8a2d38c7dff6872cb5cfc9cf4efe881bd1f7ed41b` |
| `LICENSE.txt` | 4,301 bytes | `6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2` |

The files are distributed under the SIL Open Font License 1.1 copied into
`reporting/assets/fonts/LICENSE.txt`.

Verify the checked-in assets with:

```bash
sha256sum reporting/assets/fonts/*
fc-scan reporting/assets/fonts/NotoSansCJKsc-Regular.otf
fc-scan reporting/assets/fonts/NotoSansCJKsc-Bold.otf
```

## Preflight and diagnostics

`ReportPdfRenderer.preflight()` is idempotent and performs a real in-memory PDF
render after checking the template, stylesheet, license, both font files, and
required CJK glyphs. Report creation fails before a job is queued when this
gate fails.

Run the focused runtime checks with:

```bash
uv run pytest \
  test/reporting/test_pdf_renderer.py \
  test/reporting/test_service.py \
  test/server/test_reports_api.py \
  -q
```

For an existing artifact, use:

```bash
pdfinfo report.pdf
pdfinfo -url report.pdf
mutool show report.pdf outline
pdffonts report.pdf
pdftotext -layout report.pdf report.txt
```

## Content and resource security

Report Markdown is untrusted input. The parser disables raw HTML and automatic
linkification. Image syntax becomes escaped alt text. Only explicit `http` and
`https` links become PDF link annotations; other schemes become plain text.

The WeasyPrint URL fetcher rejects network resources, data URLs, and local files
outside the resolved `reporting/assets/` root. Only the checked-in stylesheet
and fonts can be loaded. Production should additionally run the service as a
non-root account with operating-system memory and execution-time limits.

## Renderer upgrades

WeasyPrint major versions can change page layout. Before changing the pinned
major range, rerun the complete backend suite, stock and sector PDF structure
checks, and visual inspection of every rendered page.

The Chromium renderer described as plan B is not enabled and is not a fallback.
It requires a separate approved plan when JavaScript-rendered charts are
necessary, a shared Next.js report component is a product requirement, or an
accepted layout cannot be implemented with reasonable WeasyPrint print CSS.
That plan must also approve Chromium as a production dependency, resource
interception, browser lifecycle, and measured worker costs.

## References

- WeasyPrint installation: <https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation>
- WeasyPrint security and URL fetchers: <https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#security>
- Noto CJK release: <https://github.com/notofonts/noto-cjk/tree/NotoSansV2.001>
- Noto font licensing: <https://notofonts.github.io/noto-docs/website/use/>
