// Render pseudocode.js blocks on every page load and SPA navigation.
// Requires KaTeX and pseudocode.js to be loaded before this script.
//
// Algorithm blocks preprocessed from LaTeX \begin{algorithm}...\end{algorithm}
// are emitted as <pre class="pseudocode"> by fix_code_captions() in
// tex2site/tex2md/process_md.py.  pseudocode.js renders them in the browser
// using KaTeX for the embedded math expressions.
document$.subscribe(function () {
  if (typeof pseudocode === "undefined") return;
  document.querySelectorAll("pre.pseudocode").forEach(function (el) {
    if (!el.getAttribute("data-pseudocode-rendered")) {
      try {
        pseudocode.renderElement(el, {
          lineNumber: true,
          noEnd: false,
          indentSize: "1.2em",
          commentDelimiter: "//",
        });
        el.setAttribute("data-pseudocode-rendered", "true");
      } catch (e) {
        console.error("[pseudocode.js] Error rendering element:", e);
      }
    }
  });
});
