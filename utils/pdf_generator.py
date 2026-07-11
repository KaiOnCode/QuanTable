import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator

from fpdf import FPDF
from fpdf.fonts import TTFFont

from reporting.models import ReportPayload


def _normalize_text(value: Any, fallback: str = "暂无数据") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    if not text:
        return fallback

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("```", "")
    text = text.replace("**", "").replace("__", "").replace("`", "")

    normalized_lines = []
    for line in text.split("\n"):
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", line.strip())
        cleaned = re.sub(r"^\s*[-*+]\s+", "- ", cleaned)
        normalized_lines.append(cleaned)

    normalized = "\n".join(normalized_lines).strip()
    return normalized or fallback


def _extract_report_info(report: str) -> Dict[str, str]:
    info = {
        "direction": "Unknown",
        "timeframe": "Unknown",
        "confidence": "Unknown",
        "summary": "Unknown",
    }

    clean_report = _normalize_text(report, "")
    lines = clean_report.split("\n")

    field_map = {
        "direction": ("方向", "direction"),
        "timeframe": ("时间范围", "timeframe"),
        "confidence": ("置信度", "confidence"),
        "summary": ("一句话结论", "summary", "结论"),
    }

    for line in lines:
        stripped = line.strip()
        if not stripped or ("：" not in stripped and ":" not in stripped):
            continue

        separator = "：" if "：" in stripped else ":"
        key_text, value = stripped.split(separator, 1)
        key_text = key_text.strip().lower()
        value = value.strip()

        for field, aliases in field_map.items():
            if any(alias.lower() in key_text for alias in aliases) and value:
                info[field] = value
                break

    if info["summary"] == "Unknown":
        for line in lines:
            stripped = line.strip()
            if len(stripped) >= 12 and not any(
                marker in stripped for marker in ("方向", "时间范围", "置信度")
            ):
                info["summary"] = stripped
                break

    return info


def _iter_font_candidates() -> Iterator[Path]:
    common_candidates = [
        Path("/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"),
        Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]

    seen = set()
    for candidate in common_candidates:
        if candidate.exists():
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield resolved

    font_dirs = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
    ]
    font_keywords = (
        "cjk",
        "han",
        "noto",
        "sourcehan",
        "source han",
        "wqy",
        "wenquanyi",
        "yahei",
        "simhei",
        "simsun",
        "pingfang",
        "ukai",
        "uming",
        "gkai",
    )

    for font_dir in font_dirs:
        if not font_dir.exists():
            continue

        for path in font_dir.rglob("*"):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            file_name = path.name.lower()
            if not any(keyword in file_name for keyword in font_keywords):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield resolved


def _register_report_font(pdf: FPDF) -> str:
    for font_path in _iter_font_candidates():
        try:
            font_name = f"report_font_{abs(hash(str(font_path)))}"
            pdf.add_font(font_name, fname=str(font_path))
            return font_name
        except Exception:
            continue

    raise RuntimeError(
        "未找到可用于中文 PDF 的字体，请安装 Noto Sans CJK、WenQuanYi 或 Arphic 中文字体。"
    )


def _format_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return "Unknown"


def _format_news_sources(news_sources: Any) -> str:
    if not isinstance(news_sources, list) or not news_sources:
        return "暂无参考新闻来源"

    formatted_items = []
    for idx, item in enumerate(news_sources, 1):
        if not isinstance(item, dict):
            formatted_items.append(f"{idx}. {_normalize_text(item)}")
            continue

        title = _normalize_text(item.get("title"), "无标题")
        source = _normalize_text(item.get("source"), "Unknown")
        published_at = _normalize_text(item.get("published_at"), "Unknown")
        url = item.get("url")

        parts = [f"{idx}. {title}", f"来源: {source} | 时间: {published_at}"]
        if url:
            parts.append(f"链接: {url}")
        formatted_items.append("\n".join(parts))

    return "\n\n".join(formatted_items)


def _add_section(pdf: FPDF, font_name: str, title: str, body: Any) -> None:
    pdf.set_font(font_name, size=14)
    pdf.set_text_color(24, 24, 27)
    pdf.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(209, 213, 219)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)

    pdf.set_font(font_name, size=11)
    pdf.set_text_color(55, 65, 81)
    pdf.multi_cell(0, 7, _normalize_text(body))
    pdf.ln(4)


def generate_pdf_report(
    result: Dict[str, Any], ticker: str, output_path: str | None = None
) -> str:
    if not isinstance(result, dict):
        raise TypeError("result 必须是 dict")

    pm_report = _normalize_text(result.get("PM_report"), "")
    if not pm_report:
        raise ValueError("缺少 PM_report，无法生成 PDF 报告")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    font_name = _register_report_font(pdf)
    pdf.add_page()

    report_info = _extract_report_info(pm_report)
    ticker_value = (ticker or result.get("ticker") or "UNKNOWN").upper()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pdf.set_title(f"{ticker_value} Analysis Report")
    pdf.set_author("IntelliFin Assistant")
    pdf.set_creator("IntelliFin Assistant")

    pdf.set_font(font_name, size=18)
    pdf.set_text_color(17, 24, 39)
    pdf.multi_cell(0, 10, f"IntelliFin Assistant 股票分析报告\n{ticker_value}")
    pdf.ln(2)

    pdf.set_font(font_name, size=11)
    pdf.set_text_color(75, 85, 99)
    summary_lines = [
        f"生成时间: {generated_at}",
        f"交易动作: {result.get('Action', 'Unknown')}",
        f"目标仓位: {_format_percent(result.get('Target_position_pct'))}",
        f"方向: {report_info['direction']}",
        f"时间范围: {report_info['timeframe']}",
        f"置信度: {report_info['confidence']}",
    ]
    pdf.multi_cell(0, 7, "\n".join(summary_lines))
    pdf.ln(3)

    _add_section(pdf, font_name, "一句话结论", report_info["summary"])
    _add_section(pdf, font_name, "最终投资决策", pm_report)
    _add_section(pdf, font_name, "市场分析报告", result.get("market_report"))
    _add_section(pdf, font_name, "新闻分析报告", result.get("news_report"))
    _add_section(pdf, font_name, "基本面分析报告", result.get("fundamental_report"))
    _add_section(pdf, font_name, "风险分析报告", result.get("risk_report"))
    _add_section(
        pdf,
        font_name,
        "参考新闻来源",
        _format_news_sources(result.get("news_sources")),
    )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            prefix=f"{ticker_value.lower()}_", suffix=".pdf"
        )
        os.close(fd)
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    pdf.output(output_path)
    return output_path


class ReportPdfRenderer:
    def __init__(self, font_path: str | Path | None = None) -> None:
        self._configured_font = Path(font_path).resolve() if font_path else None
        self._font_path: Path | None = None

    def preflight(self) -> None:
        candidates = (
            (self._configured_font,)
            if self._configured_font is not None
            else tuple(_iter_font_candidates())
        )
        for candidate in candidates:
            if candidate is None or not candidate.is_file():
                continue
            try:
                pdf = FPDF()
                pdf.add_font("preflight", fname=str(candidate))
                font = pdf.fonts["preflight"]
                if not isinstance(font, TTFFont) or not all(
                    codepoint in font.cmap for codepoint in (0x4E2D, 0x6587)
                ):
                    continue
                self._font_path = candidate
                return
            except Exception:
                continue
        raise RuntimeError(
            "Unicode/CJK PDF font unavailable; install Noto Sans CJK or WenQuanYi"
        )

    def render(self, payload: ReportPayload, output_path: Path) -> None:
        if self._font_path is None:
            raise RuntimeError("PDF renderer preflight has not completed")
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(15, 15, 15)
        pdf.add_font("report", fname=str(self._font_path))
        pdf.add_page()
        pdf.set_title(payload.title)
        pdf.set_author("IntelliFin Assistant")
        pdf.set_font("report", size=18)
        pdf.multi_cell(0, 10, payload.title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("report", size=10)
        pdf.multi_cell(
            0,
            7,
            f"Type: {payload.report_type.value}\nTickers: {', '.join(payload.tickers)}\n"
            f"Generated: {payload.generated_at.isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        for section in payload.sections:
            _add_section(pdf, "report", section.title, section.content)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
