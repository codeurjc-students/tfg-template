// MathJax configuration.
// This script must be loaded BEFORE the MathJax CDN script.
//
// pymdownx.arithmatex (generic: true) converts $...$ in Markdown text to
// \(...\) inside <span class="arithmatex"> elements, so the default MathJax 3
// inline delimiter \(...\) handles most math. However, math that appears
// inside raw HTML blocks (e.g. <th>$p_i$</th>) is not processed by arithmatex
// and stays as literal $...$. Enabling $ as an additional inline delimiter
// makes MathJax render those cases as well.
//
// MathJax's default skipHtmlTags list already excludes <pre> and <code>, so
// enabling $ globally does not affect code blocks.
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"], ["$", "$"]],
    displayMath: [["\\[", "\\]"], ["$$", "$$"]],
    processEscapes: true,
    processEnvironments: true,
  },
};
