--[[
  cleanup.lua — Pandoc Lua filter
  =================================
  Removes LaTeX commands and environments from the AST that have no
  meaningful web equivalent and would otherwise appear as literal text
  (e.g. "\minitoc") or cause spurious content in the generated Markdown.

  WHY IS THIS NEEDED?
  A thesis LaTeX source contains many PDF-specific commands: per-chapter
  mini table of contents (\minitoc), custom header/footer rules (\fancyhf),
  page numbering (\pagenumbering), and layout spacing (\setlength).
  Pandoc cannot convert these to Markdown and emits them as RawBlock or
  RawInline nodes. Without this filter, those raw LaTeX strings appear
  verbatim as artefacts in the rendered web page.

  This filter runs in Pass 2 (per-chapter conversion) BEFORE resolve_refs.lua
  so that subsequent filters and the post-processor only see clean,
  semantic content.
]]

-- Commands whose RawBlock/RawInline nodes are dropped completely.
local DROP_COMMANDS = {
  -- Per-chapter mini table of contents (minitoc package).
  -- These manage a small ToC at the start of each PDF chapter. MkDocs
  -- generates its own section navigation, so these produce nothing useful
  -- on the web and would render as literal "\minitoc" text.
  minitoc = true,
  dominitoc = true,
  adjustmtc = true,

  -- PDF page-break utility: inserts a blank page for double-sided printing.
  -- On the web there are no physical pages; the command is meaningless.
  blankpage = true,

  -- URJC thesis template authoring macros: \tutor{}, \alumno{}, \cotutor{}
  -- populate cover-page fields in the PDF. The website cover is generated
  -- from metadata.json instead, so these are redundant and would appear as
  -- raw LaTeX command fragments in the converted Markdown.
  tutor = true,
  alumno = true,
  cotutor = true,

  -- \nb{} is a "nota bene" review annotation used in some thesis templates.
  -- It has no standard Markdown equivalent and must be removed.
  nb = true,

  -- PDF header/footer and page-style commands (fancyhdr package).
  -- The website has its own header/footer defined in overrides/main.html.
  -- Keeping these would produce raw LaTeX strings in the output.
  pagestyle = true,
  fancyhf = true,
  fancyhead = true,
  fancyfoot = true,
  pagenumbering = true,
  thispagestyle = true,

  -- Layout/spacing commands. These modify PDF dimensions and counters that
  -- have no meaning in HTML. Pandoc passes them through as RawBlock/RawInline
  -- nodes, producing unwanted LaTeX snippets in the Markdown output.
  setcounter = true,
  spacing = true,
  setlength = true,
  renewcommand = true,

  -- Deferred content wrapper. \afterpage{} schedules its argument for the
  -- next PDF page break. Pandoc emits the argument as a stray RawBlock that
  -- would appear at the wrong position in the Markdown output.
  afterpage = true,

  -- PDF hyperref invisible anchor. \phantomsection is a workaround for the
  -- LaTeX PDF bookmark system. Pandoc converts it to an empty RawBlock that
  -- produces a blank-line artefact in Markdown if not removed.
  phantomsection = true,

  -- Navigation structure commands. MkDocs generates its own ToC, list of
  -- figures, and list of tables from the page content. Including the
  -- LaTeX-generated versions would duplicate navigation and render
  -- out-of-context lists on the web page.
  tableofcontents = true,
  listoftables = true,
  listoffigures = true,
  lstlistoflistings = true,
}

-- RawBlock: suppress block-level occurrences of the commands above.
-- Pandoc emits a RawBlock when it encounters a LaTeX command it cannot
-- convert to a Markdown block element (e.g. \minitoc at the start of a
-- chapter), passing the raw text through unchanged. We intercept and drop it.
function RawBlock(el)
  if el.format == "latex" or el.format == "tex" then
    for cmd, _ in pairs(DROP_COMMANDS) do
      if el.text:match("^\\" .. cmd) or el.text:match("\\" .. cmd .. "[%s{]") then
        return {}
      end
    end
  end
end

-- RawInline: suppress inline-level occurrences of the same commands.
-- Some commands appear inline within a paragraph (e.g. \phantomsection
-- inside a \section argument). Pandoc emits these as RawInline nodes.
function RawInline(el)
  if el.format == "latex" or el.format == "tex" then
    for cmd, _ in pairs(DROP_COMMANDS) do
      if el.text:match("^\\" .. cmd) then
        return pandoc.Str("")
      end
    end
  end
end

-- Div: catch environments Pandoc wraps in a <div> rather than emitting as
-- a RawBlock. For example, the minitoc package sometimes generates a Div
-- node with class "minitoc" when Pandoc can parse its structure. Likewise,
-- \todo{} notes from the todonotes package appear as coloured Div blocks
-- that would render as floating boxes with no visible boundary in HTML.
function Div(el)
  local cls = el.classes
  for _, c in ipairs(cls) do
    if c == "minitoc" or c == "todonotes" then
      return {}
    end
    -- multicols: Pandoc adds a leading Para containing the column-count
    -- argument (e.g. "2" from \begin{multicols}{2}). Strip that paragraph
    -- and unwrap the div so the list renders without a spurious number.
    if c == "multicols" then
      local blocks = el.content
      if #blocks > 0 and blocks[1].t == "Para" then
        local inlines = blocks[1].content
        -- Pandoc wraps the column-count in a Span (e.g. Span [Str "2"]),
        -- but it can also appear as a bare Str depending on the LaTeX source.
        local col_str = nil
        if #inlines == 1 then
          if inlines[1].t == "Str" then
            col_str = inlines[1].text
          elseif inlines[1].t == "Span" then
            local span_content = inlines[1].content
            if #span_content == 1 and span_content[1].t == "Str" then
              col_str = span_content[1].text
            end
          end
        end
        if col_str and col_str:match("^%d+$") then
          table.remove(blocks, 1)
        end
      end
      return blocks
    end
  end
end
