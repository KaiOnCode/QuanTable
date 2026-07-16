from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from importlib import import_module
import mimetypes
from pathlib import Path
import re
from threading import Lock
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from fontTools.ttLib import TTFont, TTLibError
from jinja2 import (
    Environment,
    FileSystemLoader,
    Template,
    TemplateError,
    select_autoescape,
)
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from reporting.models import ReportPayload

if TYPE_CHECKING:
    from weasyprint.text.fonts import FontConfiguration
    from weasyprint.urls import URLFetcherResponse

_REPORTING_ROOT = Path(__file__).resolve().parent
_REQUIRED_CJK_CODEPOINTS = frozenset({0x4E2D, 0x6587, 0x91D1, 0x878D})
_ALLOWED_LINK_SCHEMES = frozenset({"http", "https"})
_TICKER_HEADING_PREFIX = re.compile(r"(?m)^([A-Z0-9.^-]{1,16}):[ \t]+(?=#{1,6}[ \t])")


@dataclass(frozen=True, slots=True)
class _HtmlSection:
    kind: str
    title: str
    html: Markup


class ReportPdfRenderError(RuntimeError):
    pass


class _SafeRenderer(RendererHTML):
    def link_open(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        del options
        href_value = tokens[idx].attrGet("href")
        href = href_value if isinstance(href_value, str) else ""
        allowed = urlsplit(href).scheme.lower() in _ALLOWED_LINK_SCHEMES
        _link_stack(env).append(allowed)
        if not allowed:
            return ""
        title_value = tokens[idx].attrGet("title")
        title = title_value if isinstance(title_value, str) else ""
        title_attribute = f' title="{escape(title, quote=True)}"' if title else ""
        return f'<a href="{escape(href, quote=True)}"{title_attribute}>'

    def link_close(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        del tokens, idx, options
        return "</a>" if _link_stack(env).pop() else ""

    def image(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        del options, env
        return escape(tokens[idx].content)


class _SafeMarkdownIt(MarkdownIt):
    def validateLink(self, url: str) -> bool:
        del url
        return True


class ReportPdfRenderer:
    def __init__(self, asset_root: str | Path | None = None) -> None:
        self._asset_root = (
            Path(asset_root).resolve()
            if asset_root is not None
            else (_REPORTING_ROOT / "assets").resolve()
        )
        self._template_path = _REPORTING_ROOT / "templates" / "source_report.html"
        self._css_path = self._asset_root / "source_report.css"
        self._regular_font_path = (
            self._asset_root / "fonts" / "NotoSansCJKsc-Regular.otf"
        )
        self._bold_font_path = self._asset_root / "fonts" / "NotoSansCJKsc-Bold.otf"
        self._license_path = self._asset_root / "fonts" / "LICENSE.txt"
        self._markdown = self._create_markdown_parser()
        self._template: Template | None = None
        self._ready = False
        self._preflight_lock = Lock()

    def preflight(self) -> None:
        with self._preflight_lock:
            if self._ready:
                return
            required = (
                self._template_path,
                self._css_path,
                self._regular_font_path,
                self._bold_font_path,
                self._license_path,
            )
            for path in required:
                if not path.is_file():
                    raise ReportPdfRenderError(f"Missing PDF report asset: {path.name}")
            self._validate_font(self._regular_font_path)
            self._validate_font(self._bold_font_path)
            try:
                environment = Environment(
                    loader=FileSystemLoader(self._template_path.parent),
                    autoescape=select_autoescape(("html",)),
                )
                environment.filters["zfill"] = lambda value, width: str(value).zfill(
                    width
                )
                self._template = environment.get_template(self._template_path.name)
            except (OSError, TemplateError) as error:
                raise ReportPdfRenderError("PDF report template is invalid") from error
            self._smoke_render()
            self._ready = True

    def render(self, payload: ReportPayload, output_path: Path) -> None:
        if not self._ready or self._template is None:
            raise ReportPdfRenderError("PDF renderer preflight has not completed")
        sections = tuple(
            _HtmlSection(
                kind=section.kind.value,
                title=section.title,
                html=self._render_markdown(section.content),
            )
            for section in payload.sections
        )
        generated_at = payload.generated_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        rendered_html = self._template.render(
            title=payload.title,
            report_type=payload.report_type.value.title(),
            tickers=payload.tickers,
            generated_at=generated_at,
            sections=sections,
        )
        weasyprint = import_module("weasyprint")
        html = weasyprint.HTML(
            string=rendered_html,
            base_url=self._asset_root.as_uri(),
            url_fetcher=self._resource_fetcher,
        )
        css = weasyprint.CSS(
            filename=self._css_path,
            url_fetcher=self._resource_fetcher,
            font_config=(font_config := self._font_configuration()),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html.write_pdf(
            target=output_path,
            stylesheets=(css,),
            pdf_tags=True,
            font_config=font_config,
            uncompressed_pdf=True,
        )

    @staticmethod
    def _create_markdown_parser() -> MarkdownIt:
        return _SafeMarkdownIt(
            "commonmark",
            {"html": False, "linkify": False, "typographer": False},
            renderer_cls=_SafeRenderer,
        ).enable(("table", "strikethrough"))

    def _render_markdown(self, content: str) -> Markup:
        normalized = _TICKER_HEADING_PREFIX.sub(r"\n\n\1:\n\n", content)
        return Markup(self._markdown.render(normalized, {}))

    def _resource_fetcher(self, url: str) -> URLFetcherResponse:
        parsed = urlsplit(url)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ReportPdfRenderError("Blocked external PDF report resource")
        candidate = Path(unquote(parsed.path)).resolve()
        allowed_assets = (
            self._css_path.resolve(),
            self._regular_font_path.resolve(),
            self._bold_font_path.resolve(),
        )
        if (
            not candidate.is_relative_to(self._asset_root)
            or candidate not in allowed_assets
            or not candidate.is_file()
        ):
            raise ReportPdfRenderError(
                "Blocked PDF report resource outside allowed render assets"
            )
        mime_type = (
            mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        )
        urls = import_module("weasyprint.urls")
        return urls.URLFetcherResponse(
            candidate.as_uri(),
            body=candidate.read_bytes(),
            headers={"Content-Type": mime_type},
        )

    @staticmethod
    def _validate_font(path: Path) -> None:
        try:
            with TTFont(path, lazy=True) as font:
                cmap = font.getBestCmap()
                if cmap is None or not _REQUIRED_CJK_CODEPOINTS.issubset(cmap):
                    raise ReportPdfRenderError(
                        f"PDF report font lacks required CJK glyphs: {path.name}"
                    )
        except (OSError, TTLibError) as error:
            raise ReportPdfRenderError(
                f"PDF report font is invalid: {path.name}"
            ) from error

    def _smoke_render(self) -> None:
        try:
            weasyprint = import_module("weasyprint")
            html = weasyprint.HTML(
                string='<html lang="zh-CN"><body>中文金融 smoke</body></html>',
                base_url=self._asset_root.as_uri(),
                url_fetcher=self._resource_fetcher,
            )
            css = weasyprint.CSS(
                filename=self._css_path,
                url_fetcher=self._resource_fetcher,
                font_config=(font_config := self._font_configuration()),
            )
            rendered = html.write_pdf(
                stylesheets=(css,),
                pdf_tags=True,
                font_config=font_config,
            )
        except (ImportError, OSError, TypeError, ValueError) as error:
            raise ReportPdfRenderError(
                "WeasyPrint PDF runtime is unavailable"
            ) from error
        if not isinstance(rendered, bytes) or not rendered.startswith(b"%PDF-"):
            raise ReportPdfRenderError("WeasyPrint PDF smoke render failed")

    @staticmethod
    def _font_configuration() -> FontConfiguration:
        fonts = import_module("weasyprint.text.fonts")
        return fonts.FontConfiguration()


def _link_stack(environment: EnvType) -> list[bool]:
    raw_stack = environment.get("safe_link_stack", [])
    stack = [value for value in raw_stack if isinstance(value, bool)]
    environment["safe_link_stack"] = stack
    return stack
