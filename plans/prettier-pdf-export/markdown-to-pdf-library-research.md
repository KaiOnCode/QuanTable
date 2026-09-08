# Markdown 到精美 PDF 的方案调研

## 当前约束

- PDF 由 FastAPI 后端异步生成并持久化，前端只负责提交 stock / sector 作业和下载成品。
- 源内容主要是中文 Markdown、GFM 表格、列表和分节文本，当前不依赖 JavaScript 图表。
- 生产依赖已有 `fpdf2`；Playwright 目前只在 Python `dev` dependency
  group，但本机的 Playwright 1.58.0 + Chromium 已验证可生成 PDF。
- 目标应保留现有 `ReportService -> renderer -> persisted artifact` 边界，不应退化成只存在于浏览器本地的一次性导出。

## 结论排序

| 排名 | 方案 | 适配度 | 结论 |
| --- | --- | --- | --- |
| 1 | `markdown-it-py` + WeasyPrint | 高 | 最适合当前以文本、表格为主的 Python 服务端报告 |
| 2 | `markdown-it-py` + Playwright | 高 | CSS 还原最强，适合未来动态图表 |
| 3 | Markdown parser + `fpdf2.write_html()` | 中 | 改动和部署成本最低，但版式能力有明显上限 |
| 4 | `@react-pdf/renderer` | 低至中 | 适合从 React 组件重新设计 PDF，不适合直接消费现有 Markdown |

## 1. 推荐：markdown-it-py + WeasyPrint

处理链路：Markdown -> `markdown-it-py` HTML -> 固定 Jinja/HTML 模板与
print CSS -> WeasyPrint PDF。

优点：

- 与现有 Python/FastAPI 后端、后台作业和文件持久化边界天然一致。
- WeasyPrint 是面向 HTML/CSS 打印的分页引擎，支持 `@page`、页边距盒、
  页码、running header/footer、孤行控制、分页规则、书签和 SVG，适合长篇
  金融报告。
- Markdown-it-py 遵循 CommonMark，可启用 table 规则和插件；可以关闭 raw HTML，保留表格、列表、标题、代码与链接的语义。
- 可固定内嵌 Source Han / Noto CJK 字体，避免当前按宿主机扫描字体导致输出漂移。

缺点：

- WeasyPrint 需要 Pango 等系统组件，容器和 CI 必须显式安装并固定版本。
- 不执行 JavaScript；Plotly 等动态图表需要先导出 SVG/PNG。
- 官方说明大版本升级可能改变渲染结果，需要保留黄金样例视觉回归。
- 必须限制 URL fetcher、禁用不受信任 HTML，并限制外部资源访问。

官方资料：

- [WeasyPrint 概览与 BSD 许可](https://doc.courtbouillon.org/weasyprint/stable/)
- [WeasyPrint CSS/PDF 能力](https://doc.courtbouillon.org/weasyprint/stable/api_reference.html#supported-features)
- [WeasyPrint Web 应用与安全注意事项](https://doc.courtbouillon.org/weasyprint/stable/common_use_cases.html)
- [markdown-it-py CommonMark、插件与安全能力](https://markdown-it-py.readthedocs.io/en/latest/)
- [markdown-it-py table/plugin 示例与 MIT 许可](https://github.com/executablebooks/markdown-it-py)

## 2. 高保真备选：markdown-it-py + Playwright/Chromium

处理链路与方案 1 相同，但最终由 Chromium 的 `page.pdf()` 打印 HTML。

优点：

- 完整浏览器 CSS 能力，最容易实现现代网页式视觉、复杂 grid/flex、背景、字体和前端图表。
- `page.pdf()` 支持 print CSS、A4、边距、背景、header/footer template、outline 和 tagged PDF。
- 本项目已经有 Playwright dev 依赖，本机 1.58.0 + 对应 Chromium 已实际验证能生成 `%PDF-` 成品。

缺点：

- 当前不是生产依赖；部署时需安装与 Playwright 版本匹配的 Chromium 和系统依赖。
- 浏览器二进制占用数百 MB，常驻/冷启动、内存、并发和线程生命周期管理成本高于 WeasyPrint。
- header/footer template 有脚本不执行、页面样式不可见等限制。
- 若直接加载前端路由，会把 PDF 作业耦合到 Next.js 服务可用性；更稳妥的是后端生成自包含 HTML，再交给 Chromium。

官方资料：

- [Playwright `page.pdf()` API](https://playwright.dev/python/docs/api/class-page#page-pdf)
- [Playwright 浏览器安装和版本匹配](https://playwright.dev/python/docs/browsers)

## 3. 最小改动备选：Markdown parser + fpdf2.write_html()

优点：

- `fpdf2` 已是生产依赖，保留当前 CJK 字体预检和 PDF 文件生成方式，部署变化最小。
- 官方给出了 Mistune / Python-Markdown 转 HTML 后调用 `write_html()` 的路径。
- 标题、列表、链接、代码、图片和基础表格可得到正确语义，不再泄漏 Markdown 管道符和分隔线。

缺点：

- 官方明确说明它只支持基础 HTML，不支持完整 HTML5 和 CSS；tag style 也只覆盖一部分属性。
- 可修复“raw Markdown”问题，但难以稳定做到现代品牌化页面、复杂表格、精细分页和高级页眉页脚。
- 若业务目标是“明显精美”，它更适合作为短期止血方案，不宜作为最终架构。

官方资料：

- [fpdf2 HTML 支持和限制](https://py-pdf.github.io/fpdf2/HTML.html)
- [fpdf2 与 Markdown 组合](https://py-pdf.github.io/fpdf2/CombineWithMarkdown.html)

## 4. 不优先：@react-pdf/renderer

优点：React 声明式 API、自动分页、固定页眉页脚、孤行/寡行控制，适合从组件模型精确设计 PDF。

不优先原因：它不直接渲染现有 Markdown，需要再引入 Markdown AST 并把
标题、表格、列表逐一映射到 PDF primitives；还会把当前 Python 服务端报告
作业拆出一条 Node/React 渲染链，表格与样式需重复实现。

官方资料：

- [React-pdf 分页、fixed 元素和动态页码](https://react-pdf.org/advanced)

## 推荐落地边界

采用方案 1，并保持 API、作业状态、仓库持久化与下载 URL 不变，只替换 renderer：

1. Markdown 解析时关闭 raw HTML，启用 CommonMark + table；对链接、图片协议和外部资源做 allowlist。
2. 用一份自包含 HTML 模板建立封面、摘要卡、章节、表格、风险提示、页码和页眉页脚。
3. 固定打包 Source Han / Noto CJK 字体，不再从宿主机“找到哪个用哪个”。
4. WeasyPrint 使用受限 URL fetcher；图表统一先转 SVG/PNG。
5. 保留现有 PDF 结构/下载测试，并增加 Markdown 表格不泄漏、标题层级、页数/书签、CJK 字体以及样例页 PNG 视觉回归。

如果下一阶段明确要把 Plotly/Recharts 的交互图表原样带进报告，则把最终
渲染器切换为方案 2；Markdown 解析、HTML 模板、安全边界和绝大多数
print CSS 都可以复用。
