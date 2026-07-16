from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from threading import Event, Thread

import pytest

from reporting.models import (
    RenderedSection,
    ReportPayload,
    ReportSection,
    ReportType,
)
from reporting.pdf_renderer import ReportPdfRenderError, ReportPdfRenderer


def _payload(
    content: str, *, report_type: ReportType = ReportType.STOCK
) -> ReportPayload:
    return ReportPayload(
        report_type=report_type,
        title="AAPL 中英双语 Source Report",
        tickers=("AAPL", "MSFT"),
        source_ids=("analysis-1",),
        sections=(
            RenderedSection(
                kind=ReportSection.DECISION,
                title="Investment Decision 投资决策",
                content=content,
            ),
        ),
        generated_at=datetime(2026, 7, 16, 8, 30, tzinfo=timezone.utc),
    )


def _representative_markdown() -> str:
    return (
        "# 一级标题\n\n"
        "## 二级标题\n\n"
        "正文包含 **粗体**、*斜体*、~~删除线~~、`inline_code` 和常用符号 ¥ % ± →。\n\n"
        "- 第一项\n  - 嵌套项\n- 第二项\n\n"
        "1. 有序第一项\n2. 有序第二项\n\n"
        "> 风险引用：保持仓位纪律。\n\n---\n\n"
        "| Ticker | Signal | 说明 |\n"
        "| --- | --- | --- |\n"
        "| AAPL | BUY | 很长的中英文单元格会自然换行 without leaking Markdown separators |\n"
        "| MSFT | HOLD | 等待确认 |\n\n"
        "```python\nprice = 315.32\nprint(price)\n```\n\n"
        "[Official source](https://example.com/research)\n"
    )


def _run_text_command(*command: str) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_preflight_reports_missing_fixed_assets(tmp_path: Path) -> None:
    renderer = ReportPdfRenderer(asset_root=tmp_path)

    with pytest.raises(ReportPdfRenderError, match="Missing PDF report asset"):
        renderer.preflight()


def test_render_requires_successful_preflight(tmp_path: Path) -> None:
    renderer = ReportPdfRenderer()

    with pytest.raises(ReportPdfRenderError, match="preflight has not completed"):
        renderer.render(_payload("正文"), tmp_path / "report.pdf")


def test_resource_fetcher_rejects_non_render_assets() -> None:
    renderer = ReportPdfRenderer()
    license_url = Path("reporting/assets/fonts/LICENSE.txt").resolve().as_uri()

    with pytest.raises(
        ReportPdfRenderError,
        match="outside allowed render assets",
    ):
        renderer._resource_fetcher(license_url)


def test_render_preserves_markdown_semantics_without_marker_leakage(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stock.pdf"
    renderer = ReportPdfRenderer()
    renderer.preflight()

    renderer.render(_payload(_representative_markdown()), output)

    assert output.read_bytes().startswith(b"%PDF-")
    pages = _run_text_command("mutool", "show", str(output), "pages")
    assert "page 1" in pages
    extracted = _run_text_command("pdftotext", "-layout", str(output), "-")
    for expected in (
        "AAPL 中英双语 Source Report",
        "一级标题",
        "嵌套项",
        "风险引用",
        "Ticker",
        "AAPL",
        "很长的中英文单元格会自然换行",
        "price = 315.32",
    ):
        assert expected in extracted
    for leaked_marker in ("| --- |", "**粗体**", "```python", "\n---\n"):
        assert leaked_marker not in extracted


def test_render_sets_metadata_outline_tags_and_embeds_fixed_cjk_fonts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "metadata.pdf"
    renderer = ReportPdfRenderer()
    renderer.preflight()

    renderer.render(_payload(_representative_markdown()), output)

    info = _run_text_command("pdfinfo", str(output))
    assert "Title:           AAPL 中英双语 Source Report" in info
    assert "Author:          IntelliFin Assistant" in info
    assert "Creator:         IntelliFin Assistant" in info
    assert "Tagged:          yes" in info
    assert "Pages:" in info
    outline = _run_text_command("mutool", "show", str(output), "outline")
    assert "Investment Decision 投资决策" in outline
    assert "一级标题" in outline
    fonts = _run_text_command("pdffonts", str(output))
    assert "Noto-Sans-CJK-SC " in fonts
    assert "Noto-Sans-CJK-SC-Bold" in fonts
    assert all(" yes " in line for line in fonts.splitlines()[2:] if line.strip())


def test_multipage_report_repeats_header_footer_and_page_count(tmp_path: Path) -> None:
    repeated = "\n\n".join(
        f"### 风险检查 {index}\n中英文分页压力内容 {index} keeps the body searchable."
        for index in range(1, 81)
    )
    output = tmp_path / "multipage.pdf"
    renderer = ReportPdfRenderer()
    renderer.preflight()

    renderer.render(_payload(f"{_representative_markdown()}\n\n{repeated}"), output)

    info = _run_text_command("pdfinfo", str(output))
    match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
    assert match is not None
    page_count = int(match.group(1))
    assert page_count >= 3
    extracted = _run_text_command("pdftotext", "-layout", str(output), "-")
    assert extracted.count("IntelliFin Assistant") == page_count
    assert extracted.count("Generated 2026-07-16T08:30:00Z") == page_count
    for page_number in range(1, page_count + 1):
        assert f"Page {page_number} / {page_count}" in extracted


def test_sector_ticker_prefix_preserves_following_markdown_heading(
    tmp_path: Path,
) -> None:
    output = tmp_path / "sector-prefix.pdf"
    renderer = ReportPdfRenderer()
    renderer.preflight()

    renderer.render(
        _payload(
            "AAPL: # Executive Summary 执行摘要\n\n"
            "first paragraph\n"
            "MSFT: # Second Summary 第二份摘要\n\n正文",
            report_type=ReportType.SECTOR,
        ),
        output,
    )

    extracted = _run_text_command("pdftotext", "-layout", str(output), "-")
    assert "AAPL: # Executive Summary" not in extracted
    assert "first paragraph MSFT:" not in extracted
    outline = _run_text_command("mutool", "show", str(output), "outline")
    assert "Executive Summary 执行摘要" in outline
    assert "Second Summary 第二份摘要" in outline


def test_untrusted_content_cannot_fetch_resources_or_create_unsafe_objects(
    tmp_path: Path,
) -> None:
    requested = Event()

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requested.set()
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *_args) -> None:  # noqa: A002, ANN002
            del format
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    secret = tmp_path / "local-secret.txt"
    secret.write_text("LOCAL_FILE_MUST_NOT_BE_READ", encoding="utf-8")
    address = server.server_address
    host, port = str(address[0]), int(address[1])
    content = (
        "[safe https](https://example.com/allowed)\n"
        "[safe http](http://example.com/allowed)\n"
        "[unsafe javascript](javascript:alert(1))\n"
        f"[unsafe file]({secret.as_uri()})\n"
        f"![remote alt](http://{host}:{port}/remote.png)\n"
        f"![local alt]({secret.as_uri()})\n"
        "<script>alert('must not execute')</script>\n"
        f'<img src="http://{host}:{port}/raw.png" alt="raw html image">\n'
    )
    output = tmp_path / "untrusted.pdf"
    renderer = ReportPdfRenderer()
    renderer.preflight()

    try:
        renderer.render(_payload(content), output)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert not requested.is_set()
    extracted = _run_text_command("pdftotext", str(output), "-")
    assert "remote alt" in extracted
    assert "local alt" in extracted
    assert "unsafe javascript" in extracted
    assert "LOCAL_FILE_MUST_NOT_BE_READ" not in extracted
    urls = _run_text_command("pdfinfo", "-url", str(output))
    assert "https://example.com/allowed" in urls
    assert "http://example.com/allowed" in urls
    assert "javascript:" not in urls
    assert "file:" not in urls
    images = _run_text_command("pdfimages", "-list", str(output))
    assert not images.splitlines()[2:]
    info = _run_text_command("pdfinfo", str(output))
    assert "JavaScript:      no" in info
