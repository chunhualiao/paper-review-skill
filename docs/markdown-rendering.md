# Markdown Rendering Subset

`scripts/render_review_html.py` intentionally uses a dependency-free Markdown
subset instead of a maintained CommonMark renderer. The review artifacts are
trusted local files, the renderer must run in minimal Codex environments, and the
HTML page adds project-specific audit and follow-up-question sections around the
rendered review.

Supported review Markdown:

- ATX headings with stable generated anchors: `#` through `######`.
- Paragraphs with inline code, bold, emphasis, links, and images.
- Fenced code blocks with optional language labels.
- Display math blocks delimited by lines containing only `$$`.
- Blockquotes beginning with `>`.
- Ordered and unordered lists, including simple indentation-based nesting.
- Pipe tables with separator rows and escaped pipe cells such as `A \| B`.

Unsupported or intentionally limited:

- Full CommonMark compliance.
- Raw HTML passthrough.
- Reference-style links and footnotes.
- Mixed Markdown inside table separator rows.
- Complex list continuation paragraphs.

If review output starts depending on more CommonMark features, prefer adopting a
maintained renderer such as `markdown-it-py` instead of expanding this parser
piecemeal.
