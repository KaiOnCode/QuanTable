# 精美 PDF Report 导出实施计划

## 文档状态

- 状态：已实施并于 2026-07-17 完成恢复验收
- 规划日期：2026-07-16
- 规划基线：`dev`，`5d6dd06`
- 已选方案 A：`markdown-it-py` + WeasyPrint
- 未来备选方案 B：`markdown-it-py` + Playwright/Chromium
- 参考旧 PDF：`plans/prettier-pdf-export/AAPL-source-report.pdf`
- 方案调研：
  `plans/prettier-pdf-export/markdown-to-pdf-library-research.md`

下一会话必须先重新确认分支和工作区。若基线已变化，应阅读差异并调整
实施步骤，不得 reset、覆盖或丢弃用户已有修改。

## 1. 目标与完成定义

把 Reports 页面导出的 stock 和 sector PDF，从当前的纯文本式输出升级为
语义正确、排版稳定、适合阅读和归档的报告，同时保留现有业务链路：

```text
Reports 页面
  -> stock / sector report API
  -> ReportService
  -> ReportPdfRenderer
  -> 持久化 PDF artifact
  -> 历史记录与下载 API
```

完成后必须同时满足：

1. Markdown 标题、粗体、列表、表格、分隔线、引用和代码不再以 raw text
   泄漏到 PDF。
2. 中英文和常用金融符号可稳定渲染，不依赖宿主机碰巧安装的字体。
3. stock 和 sector 两条导出链路都复用同一个新 renderer。
4. API schema、作业状态、历史列表、artifact 持久化和下载 URL 不变。
5. 不受信任的报告内容不能读取本地文件、访问网络或执行 raw HTML。
6. 自动化测试、真实 PDF 结构检查和逐页视觉检查全部通过。
7. 运行时依赖及 Linux 系统组件有明确安装和诊断文档。

“生成了一个以 `%PDF-` 开头的文件”不等于完成。版式、Markdown 语义、
安全性和两类 report 的端到端行为都属于完成条件。

## 2. 当前实现基线

当前活动前端共有两条 PDF 创建入口：

- `POST /api/reports/stock`
- `POST /api/reports/sector`

它们都在 `server/routes/reports.py` 中构造同一个
`ReportPdfRenderer`，最终由 `ReportService._run()` 写入临时文件、校验、
原子替换并记录完成状态。

当前问题位于 `utils/pdf_generator.py`：

- `_normalize_text()` 只删除少量 Markdown 标记；
- `_add_section()` 把整个 section 交给 `FPDF.multi_cell()`；
- 表格管道符、表头分隔线和部分列表结构会原样进入 PDF；
- 活动 renderer 运行时扫描宿主机字体，输出不可复现；
- 版式能力局限于标题和连续文本块。

同一文件中的 `generate_pdf_report()` 是归档 Streamlit 路径仍可能使用的
旧接口。本需求不删除它，也不移除它所需的 `fpdf2`。

## 3. 已批准的架构决策

### 3.1 方案 A 的处理链

```text
ReportPayload
  -> 受限 Markdown parser
  -> 安全 HTML fragments
  -> 固定 HTML 模板 + print CSS + bundled CJK font
  -> WeasyPrint
  -> ReportService 管理的临时 PDF
```

实施应保持 `PdfRenderer` protocol 不变：

```python
def preflight(self) -> None: ...
def render(self, payload: ReportPayload, output_path: Path) -> None: ...
```

`ReportService` 继续拥有作业状态、错误归一化、临时文件、fsync、PDF
校验和 artifact 原子替换。renderer 只负责把 `ReportPayload` 渲染到指定
路径。

### 3.2 依赖决策

在 `pyproject.toml` 的生产依赖中直接声明：

```toml
"jinja2>=3.1,<4",
"markdown-it-py[plugins]>=4.2,<5",
"weasyprint>=69,<70",
```

随后用 `uv lock` 或 `uv sync` 更新 `uv.lock`。不要依赖 Jinja2 当前的
传递依赖状态。

保留：

- `fpdf2`：旧 `generate_pdf_report()` 仍需要它；
- dev group 中现有 Playwright：它不是本次生产渲染器。

不得在方案 A 中安装 Chromium，也不得把 Playwright 移入生产依赖。

### 3.3 模块边界

建议新增：

```text
reporting/
  pdf_renderer.py
  templates/
    source_report.html
  assets/
    source_report.css
    fonts/
      NotoSansCJKsc-Regular.otf
      NotoSansCJKsc-Bold.otf
      LICENSE.txt
test/reporting/
  test_pdf_renderer.py
docs/
  pdf-report-runtime.md
```

`reporting/pdf_renderer.py` 应拥有：

- Markdown parser 的安全配置；
- URL scheme 过滤；
- 受限 WeasyPrint resource fetcher；
- 模板加载；
- `ReportPdfRenderer.preflight()`；
- `ReportPdfRenderer.render()`。

如果该文件超过项目可读性边界，再把纯 Markdown 转换逻辑拆为
`reporting/markdown_renderer.py`。不要在一开始为单个实现创建多层抽象。

应修改：

- `server/routes/reports.py`：从新模块导入活动 renderer；
- `test/reporting/test_service.py`：更新真实 renderer 的 import；
- `pyproject.toml` 和 `uv.lock`：加入生产依赖；
- `utils/pdf_generator.py`：移除已迁移的活动 `ReportPdfRenderer`，保留旧
  `generate_pdf_report()` 及其依赖 helpers；
- `docs/pdf-report-runtime.md`：记录运行时系统依赖和诊断方式；
- `PROGRESS.md`：仅在实现和全部验证完成后如实更新。

预计不应修改：

- `frontend/app/reports/page.tsx`；
- `frontend/lib/api/reports.ts`；
- `reporting/service.py` 的业务语义；
- `reporting/repository.py`；
- 数据库 schema；
- 任何 `quick_ask/` 或 `archive/` 文件。

若实施中确认必须改变这些边界，应暂停并说明证据，取得用户批准后再扩大
范围。

## 4. 安全与可信内容边界

报告正文来自持久化分析结果，仍应按不受信任输入处理。

### 4.1 Markdown parser

用 `MarkdownIt("commonmark", ...)` 建立独立 parser，并明确配置：

- `html=False`：raw HTML 必须作为文本处理；
- `linkify=False`：不自动把任意文本转换为链接；
- 启用 `table` 和 `strikethrough`；
- 保留标题、段落、强调、列表、引用、代码和水平分隔线；
- 禁止图片 token 发起资源加载，图片语法只保留安全的 alt text；
- 链接只允许 `https` 和 `http`，其他 scheme 退化为普通文本。

不得通过开启 raw HTML 后再“尽量清洗”的方式实现。

### 4.2 模板

Jinja environment 必须开启 autoescape。标题、ticker、时间、section
标题等 metadata 全部正常转义。

只有由受限 Markdown parser 生成的 HTML fragment 可以被标记为可信 HTML。
不得对任意 payload 字符串使用 `|safe`。

### 4.3 WeasyPrint resource fetcher

自定义 URL fetcher 的默认策略为拒绝：

- 拒绝 `http` 和 `https` 资源请求；
- 拒绝模板中任意外部图片；
- 拒绝 `file://` 指向 asset root 以外的路径；
- 只允许解析后位于 `reporting/assets/` 下的 CSS 和 font 文件；
- 路径判断使用 `resolve()` 后的真实路径，避免 `..` 和 symlink 绕过；
- 当前没有明确需求时，不开放 `data:` URL。

测试必须证明恶意 Markdown 中的本地文件和外部 URL 不会被读取或请求。

### 4.4 字体

从 Noto CJK 官方发行源引入固定的 Simplified Chinese Regular 和 Bold
字体以及 SIL Open Font License：

- 不复制用户 home 或系统字体目录中的文件；
- 在运行时不下载远程字体；
- 在运行时不扫描“可用的第一个中文字体”；
- 在 runtime 文档中记录字体来源、版本、许可和 SHA-256；
- preflight 校验两个字体文件、模板、CSS 和关键 CJK glyph 可用。

如果官方字体二进制大小违反仓库已有政策，应暂停并让用户决定使用 Git
LFS、发布镜像内资产或接受其他具备再分发许可的固定字体。不得悄悄回退到
宿主机扫描。

## 5. PDF 视觉与排版规格

### 5.1 页面

- A4 portrait；
- 明确的上下左右打印边距；
- 首页为报告标题区，不要求单独占满一页；
- 页眉显示产品名和 report type；
- 页脚显示生成时间及 `current page / total pages`；
- 页眉页脚不能覆盖正文。

### 5.2 信息层级

首页标题区至少包含：

- report title；
- stock 或 sector 类型；
- ticker 列表；
- UTC 生成时间；
- 一句中性的“source report”说明。

正文按 `ReportPayload.sections` 的既有顺序渲染。每个 section 有统一的
编号或视觉标识，但不得重写正文内容或虚构摘要。

### 5.3 Markdown 元素

必须为以下元素定义 print CSS：

- `h1` 至 `h6`；
- 段落、粗体、斜体和删除线；
- 有序、无序及嵌套列表；
- blockquote；
- horizontal rule；
- inline code 和 fenced code block；
- link；
- GFM table。

表格至少满足：

- 表头与正文有明显视觉层级；
- 跨页时重复表头；
- 单行尽量不被拆开；
- 长 ticker、URL 和中英文内容能换行；
- 不出现页面右侧截断；
- 斑马纹和边框在黑白打印时仍可辨认。

分页至少满足：

- 标题不孤立在页尾；
- section 标题与首段尽量保持在同页；
- blockquote、代码块和较短表格尽量不跨页；
- 长表格允许自然分页，不能为了 `break-inside: avoid` 造成内容丢失；
- 设置合理的 orphan 和 widow 控制。

### 5.4 PDF 能力

- 设置 title、author 和 creator metadata；
- 标题生成 PDF outline/bookmarks；
- 若当前 WeasyPrint API 支持，启用 tagged PDF；
- 正文文本应可搜索和复制；
- 字体必须嵌入 PDF；
- 不把页面整体栅格化成图片。

当前范围不包含图表生成、品牌 logo、封面插图或前端组件复用。

## 6. 实施顺序

严格按以下阶段推进。每一阶段只有在对应证据通过后才进入下一阶段。

### 阶段 0：会话启动与基线保护

1. 阅读 `CLAUDE.md`、`PROGRESS.md`、`docs/development-plan.md` 和本计划。
2. 运行：

   ```bash
   git branch --show-current
   git status --short --branch
   git rev-parse HEAD
   ```

3. 确认当前活动调用点：

   ```bash
   rg -n "ReportPdfRenderer|generate_pdf_report" \
     --glob '!archive/**' --glob '!plans/**'
   ```

4. 把 `plans/prettier-pdf-export/AAPL-source-report.pdf` 作为旧版问题样例，
   不覆盖它，也不把它当作新 PDF 的 binary golden file。
5. 记录工作区已有修改。不要清理、reset 或覆盖无关内容。

阶段出口：调用链、工作区所有权和实施范围与本计划一致。

### 阶段 1：先建立失败测试

新增 `test/reporting/test_pdf_renderer.py`，先用具有代表性的固定
`ReportPayload` 写 RED tests。fixture 至少包含：

- 中文和英文；
- 多级标题；
- 粗体、斜体和删除线；
- 有序、无序及嵌套列表；
- blockquote 和 horizontal rule；
- inline code 和 fenced code；
- 至少一个多列表格和长单元格；
- 安全及不安全链接；
- raw `<script>` 和带本地文件 URL 的 image。

测试应验证行为，不比较整份 PDF bytes。至少先写出以下失败用例：

1. `preflight()` 在固定 assets 完整时通过，缺文件时给出稳定的
   renderer 错误。
2. `render()` 在没有成功 preflight 时拒绝工作。
3. 输出有 PDF signature、非空 page object，并写入指定路径。
4. `pdftotext` 可提取中文正文、标题、列表和 table cell 内容。
5. 提取文本不再包含 table separator、raw `**`、fence 或用于排版的
   horizontal-rule 标记。
6. `pdfinfo` 可见正确 title 和页数。
7. `pdffonts` 显示 CJK Regular/Bold 字体已嵌入。
8. `pdfinfo -url` 只包含允许的 `http` 或 `https` link annotation。
9. 恶意 image URL 不触发网络或本地文件访问。
10. raw HTML 不执行，也不生成脚本或图片对象。

保留并扩展现有 `test/reporting/test_service.py` 中的真实 Unicode renderer
测试，确保新 renderer 仍经过 `ReportService` 的临时文件和状态机。

先运行测试，保存失败原因。测试因新模块或新依赖尚不存在而失败是有效的
RED；测试本身无法收集或断言目标行为不是有效 RED。

阶段出口：失败测试准确描述新 renderer 的合同和安全边界。

### 阶段 2：依赖、资产与 preflight

1. 用以下命令加入三个生产依赖并更新 lockfile：

   ```bash
   uv add \
     'jinja2>=3.1,<4' \
     'markdown-it-py[plugins]>=4.2,<5' \
     'weasyprint>=69,<70'
   ```

2. 从官方发行源加入两份固定字体和许可证。
3. 新增 HTML template 和 print CSS 的最小骨架。
4. 实现幂等且线程安全的 `preflight()`：
   - 导入 WeasyPrint 并确认 native runtime 可用；
   - 校验 template、CSS、字体和许可文件存在；
   - 校验关键 CJK glyph；
   - 用内存中的最小 HTML 执行一次真实 PDF smoke render；
   - 成功后缓存 ready 状态；失败时保留原始 exception chain。
5. 不在 preflight 中扫描系统字体或下载资产。

建议立即运行：

```bash
uv sync
uv run python -m weasyprint --info
uv run pytest test/reporting/test_pdf_renderer.py -q
```

阶段出口：preflight 相关测试通过，其他渲染测试仍可保持 RED。

### 阶段 3：安全 Markdown 到 HTML

1. 实现受限 parser 配置。
2. 为 image 和 link token 实现明确规则。
3. 用 Jinja autoescape 组装 metadata 和 section。
4. 只有 parser 产物进入可信 HTML 插槽。
5. 实现并单测受限 resource fetcher。

先让 parser 和安全测试转绿，再接入 WeasyPrint。不要通过放宽 URL fetcher
或开启 raw HTML 来绕过失败。

阶段出口：Markdown HTML 结构正确，所有恶意内容测试通过。

### 阶段 4：完成 WeasyPrint renderer 与版式

1. 实现 `ReportPdfRenderer.render()`。
2. 完成第 5 节定义的 HTML 和 print CSS。
3. 使用 CSS paged media 实现页眉、页脚、页码和分页。
4. 设置 metadata、outline/bookmarks 和可用的 tagged PDF 选项。
5. 确保输出 parent directory 存在，但不接管临时文件生命周期。
6. renderer 异常原样抛给 `ReportService`，不要自行写 job 状态。

调整样式时使用代表性长 fixture。不要用隐藏 overflow、极小字体或裁剪
内容的方式消除版面问题。

阶段出口：focused renderer tests 全绿，并生成可供视觉检查的候选 PDF。

### 阶段 5：接回 stock 和 sector 共用链路

1. 把活动 `ReportPdfRenderer` 从 `utils/pdf_generator.py` 迁至
   `reporting/pdf_renderer.py`。
2. 更新 routes 和测试 import。
3. 保留旧 `generate_pdf_report()` 及其 helpers 和 `fpdf2`。
4. 不改变 `ReportService` protocol 和业务状态机。
5. 运行 stock 与 sector 的 API 测试。

必须证明：

- stock API 生成、轮询、列表和下载仍成功；
- sector API 生成、轮询、列表和下载仍成功；
- 两者注入的是同一个新 renderer class；
- 失败仍清理临时文件并落为安全的 failed 状态；
- preflight 失败不会留下虚假的 queued job。

阶段出口：两条活动导出链路都通过新 renderer，外部 API 合同未变化。

### 阶段 6：运行时文档

新增 `docs/pdf-report-runtime.md`，至少记录：

- Python 依赖及锁定范围；
- WeasyPrint 在目标 Linux 环境需要的 Pango、HarfBuzz 等系统包；
- CI 和部署环境的安装示例；
- `uv run python -m weasyprint --info` 诊断命令；
- 字体来源、版本、许可和 SHA-256；
- 网络和本地文件 fetch 的拒绝策略；
- 升级 WeasyPrint 大版本前必须重新做 PDF 视觉回归；
- 方案 B 尚未启用及其升级条件。

本仓库当前没有统一容器部署文件，不应为本需求猜测并新增一套未被使用的
Docker 架构。只记录目标运行时要求；若后续确认实际部署入口，再在对应
部署文件落地系统包。

阶段出口：新环境可根据文档安装、诊断并解释 renderer 的安全边界。

## 7. 自动化验证矩阵

### 7.1 必跑测试

```bash
uv run pytest \
  test/reporting/test_pdf_renderer.py \
  test/reporting/test_service.py \
  test/server/test_reports_api.py \
  -q
```

然后运行完整后端测试：

```bash
uv run pytest test -q
```

如果完整测试出现与本改动无关的既有失败，应保存命令、失败用例和错误
输出，不能把 focused tests 通过描述为“全部通过”。

### 7.2 静态检查

```bash
uv run basedpyright
uv run ruff check \
  reporting \
  utils/pdf_generator.py \
  server/routes/reports.py \
  test/reporting \
  test/server/test_reports_api.py
uv run ruff format --check \
  reporting \
  utils/pdf_generator.py \
  server/routes/reports.py \
  test/reporting \
  test/server/test_reports_api.py
git diff --check
```

只有实际修改 frontend 或共享前端 API types 时才运行 frontend build。按本
计划正常实施时，前端不应有改动。

### 7.3 PDF 结构检查

对生成的 stock 和 sector PDF 分别执行：

```bash
pdfinfo <report.pdf>
pdfinfo -url <report.pdf>
mutool show <report.pdf> outline
pdffonts <report.pdf>
pdftotext -layout <report.pdf> <report.txt>
```

逐项确认：

- title、author、creator、页数正确；
- outline destinations 存在；
- 只有允许的 URL；
- CJK 字体为 embedded；
- 中文可搜索、可复制；
- table separator、fence 和 Markdown emphasis marker 未泄漏；
- 没有空白页、截断页或只包含页眉页脚的尾页。

## 8. 真实 PDF 视觉 QA

视觉 QA 是硬门槛，不能只看测试和提取文本。

### 8.1 生成视觉样例

使用同一个长 fixture 分别通过 stock 和 sector 的公共服务/API 生成 PDF。
如果本地已有合格的持久化 source，可从 Reports 页面真实提交；若没有，
使用隔离临时 repository 的 API fixture，不能伪造“页面实测通过”。

旧样例只用于观察缺陷：

```text
plans/prettier-pdf-export/AAPL-source-report.pdf
```

候选新 PDF 放入临时 QA 目录，不覆盖旧样例，默认不提交生成物。

### 8.2 渲染为图片

```bash
mkdir -p /tmp/prettier-pdf-qa/stock
mkdir -p /tmp/prettier-pdf-qa/sector
pdftoppm -png -r 144 <stock.pdf> \
  /tmp/prettier-pdf-qa/stock/page
pdftoppm -png -r 144 <sector.pdf> \
  /tmp/prettier-pdf-qa/sector/page
```

逐页检查，不只抽查首页：

- 首页层级、留白、标题和 metadata；
- 每个 section 的起始位置；
- 所有表格的表头、换行和跨页边界；
- 列表层级、引用、代码和水平分隔线；
- 页眉页脚、页码和正文无重叠；
- 中文字形、粗体和标点无 tofu、乱码或异常间距；
- 没有横向裁切、内容溢出、孤立标题或大块无意义空白；
- stock 与 sector 风格一致，但 metadata 正确区分类型。

发现问题后只修改 template/CSS 或 renderer，重新执行 focused tests 和逐页
检查。不要只修被截图的单页。

### 8.3 Reports 页面验收

如果本地数据具备真实 stock 和 sector source：

1. 启动 FastAPI 与 frontend。
2. 在 Reports 页面各提交一个 stock 和 sector report。
3. 观察 queued、running、completed 状态。
4. 刷新页面，确认历史记录仍存在。
5. 分别下载 PDF，确认文件名、content type 和内容。
6. 对下载产物执行第 7.3 节和第 8.2 节检查。

若缺少 sector scan 或 stock analysis source，应明确记录“因缺少本地业务
前置数据未执行页面路径”，同时保留 API fixture 和 renderer 证据。不得为了
凑齐页面验收修改用户业务数据。

## 9. 方案 B：未来可选升级路线

方案 B 为 `markdown-it-py` + Playwright/Chromium。它不是本次范围，也
不是方案 A 的自动 fallback。

### 9.1 建议升级条件

只有至少一个产品能力触发条件成立，并且运行成本条件也成立时，才建议从
WeasyPrint 升级到 Chromium。

产品能力触发条件：

1. PDF 必须执行 JavaScript 才能渲染 Plotly、Recharts、MathJax 或同类
   动态内容，且预先生成 SVG/PNG 不能满足已批准的质量要求。
2. 产品明确要求复用同一套 Next.js report component 和 CSS，并达到接近
   浏览器截图的视觉一致性。
3. 已有可复现并被验收测试锁定的版式，WeasyPrint 的 CSS 支持无法实现，
   且尝试合理的 print CSS fallback 后仍失败。
4. 产品需要 Chromium 独有的布局、字体或浏览器渲染能力，而该能力对报告
   价值是必要条件。

运行成本条件：

1. Playwright 被明确加入生产依赖；
2. CI 和生产镜像安装与 Playwright 版本匹配的 Chromium；
3. 已测量并接受浏览器二进制体积、冷启动、内存和并发成本；
4. 已设计 browser/context/page 生命周期及崩溃恢复；
5. 已实现 request interception，默认拒绝网络和非许可本地资源；
6. stock 和 sector 的负载测试证明不会耗尽 worker 或文件描述符。

以下情况本身不构成升级条件：

- 开发机已经装有 Chromium；
- 只对某个颜色、圆角或单一 CSS property 不满意；
- WeasyPrint 可通过简化 print CSS 解决的小型差异；
- 仅仅因为 Playwright 已位于 dev dependency group；
- 希望保留两套 renderer 并自动重试。

### 9.2 未来迁移边界

若方案 B 获批：

- 保留 `ReportService -> PdfRenderer` protocol；
- 复用当前安全 Markdown parser、模板数据模型和资源策略；
- 新增 `ChromiumReportPdfRenderer`，通过明确配置或依赖注入选择；
- 不让后端 renderer 依赖 Next.js 服务在线，除非该耦合被单独批准；
- 不同时运行两套引擎进行静默 fallback；
- 用同一组语义、安全和视觉验收用例比较 A 与 B；
- 将本节的触发证据、成本测量和用户批准写入新的升级计划。

## 10. 严格非目标

本计划不授权：

- 修改 Reports 页面交互或重新设计前端；
- 修改 request/response schema、状态枚举或下载 URL；
- 修改数据库和 artifact 存储模型；
- 重新生成、润色或总结 LLM 正文；
- 添加图表、logo、远程图片或网络字体；
- 修改冻结的 `quick_ask/`；
- 修改 `archive/`；
- 删除旧 `generate_pdf_report()`；
- 删除 `fpdf2`；
- 在生产中加入 Playwright/Chromium；
- 提交、push、创建 PR 或修改 remote。

发布动作需要用户另行授权。

## 11. 简化的 OMO 执行规则

下一会话使用单一主 agent 顺序推进，不启用 team mode、ultrawork 或并行
review。

仅保留必要 skill：

1. 开始修改 Python 时使用 `omo:programming`。
2. 检查旧样例和新 PDF 时使用 `pdf`。
3. 逐页检查候选 PDF 时使用 `omo:visual-qa`。
4. 只有真实 runtime failure 无法从直接错误定位时，才使用
   `omo:debugging`。

默认不启动 sub-agent。以下情况才可以考虑：

- 用户明确要求独立复核或并行工作；
- 一个可独立验证的系统依赖问题，在主 agent 完成本地复现后仍阻塞；
- 工作范围发生重大变化，确实需要独立领域调查，并先向用户说明必要性。

常规代码阅读、测试、CSS 调整和 PDF 逐页 QA 都由主 agent 完成。

## 12. 最终验收清单

全部勾选后才能宣布完成：

- [x] 方案 A 的生产依赖和 lockfile 已更新。
- [x] 固定 CJK 字体、许可证、来源和 checksum 已记录。
- [x] raw HTML、图片、URL 和 file access 安全边界已有测试。
- [x] Markdown 标题、列表、表格、引用、代码和分隔线正确渲染。
- [x] stock 和 sector 共用新 `ReportPdfRenderer`。
- [x] 现有 API、job、history 和 download 合同未变化。
- [x] 旧 `generate_pdf_report()` 与 `fpdf2` 未被误删。
- [x] focused pytest 全绿。
- [x] 完整后端 pytest 已运行并如实记录结果。
- [x] basedpyright、ruff、format check 和 `git diff --check` 通过。
- [x] stock 与 sector PDF 通过 `pdfinfo`、`pdffonts` 和 `pdftotext`。
- [x] stock 与 sector PDF 的所有页面完成视觉检查。
- [x] Reports 页面在具备真实前置数据时完成生成、刷新和下载验收。
- [x] runtime 文档记录系统依赖、安全策略和方案 B 条件。
- [x] `PROGRESS.md` 只记录真实完成和验证证据。
- [x] `git status` 已复核，没有覆盖用户的无关修改。
- [x] 未 commit、push 或创建 PR，除非用户另行授权。

## 13. 下一会话启动提示词

```text
请在 /home/eden/MasterGraduation/COMP7705-Agent-Quant 中，严格按照
plans/prettier-pdf-export/prettier-pdf-export-implementation-plan.md
实施精美 PDF Report 导出。先阅读 CLAUDE.md、PROGRESS.md、
docs/development-plan.md 和计划，核对当前分支、HEAD、工作区及调用链，
从最早未完成阶段开始。采用已批准的方案 A：markdown-it-py +
WeasyPrint；方案 B 仅作为计划中有明确触发条件的未来升级，不要实现。
遵循 TDD，保持 ReportService、API、job/history/download 合同不变，保留
旧 generate_pdf_report() 和 fpdf2。使用单一主 agent，除非计划定义的
必要条件成立且先说明原因，否则不要启动 sub-agent。完成 focused/full
测试、静态检查、stock/sector PDF 结构检查和逐页视觉 QA 后再汇报；不要
commit、push 或创建 PR，除非我另行授权。
```

## 14. 官方资料

- [WeasyPrint stable documentation](https://doc.courtbouillon.org/weasyprint/stable/)
- [WeasyPrint installation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
- [WeasyPrint API and supported features](https://doc.courtbouillon.org/weasyprint/stable/api_reference.html)
- [markdown-it-py documentation](https://markdown-it-py.readthedocs.io/en/latest/)
- [markdown-it-py security notes](https://markdown-it-py.readthedocs.io/en/latest/security.html)
- [Playwright page.pdf API](https://playwright.dev/python/docs/api/class-page#page-pdf)
- [Playwright browser installation](https://playwright.dev/python/docs/browsers)
