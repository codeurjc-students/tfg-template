--[[
  resolve_refs.lua — Pandoc Lua filter, PASS 2 (reference resolution)
  ====================================================================

  Runs once PER CHAPTER (not over the full document) during Pass 2.
  Reads .labels.json produced by collect_labels.lua and replaces every
  \ref{label} / \autoref{label} / \cref{label} in the chapter AST with
  a correct Markdown hyperlink:

    \ref{fig:diagrama}  →  [fig. 3.1](descripcion-informatica.md#fig-diagrama)

  WHY READ FROM A FILE INSTEAD OF PASSING DATA IN-PROCESS?
  Pandoc invokes each Lua filter in a fresh Lua state per-file. There is no
  shared memory between the full-document pass and the per-chapter passes.
  The JSON file on disk is the only supported mechanism to transfer data
  from Pass 1 to Pass 2.

  Required environment variables (set by tex2md.py):
    LABELS_JSON      — path to the .labels.json file
    CURRENT_DOC_FILE — filename of the .md being generated (e.g. "introduccion.md")
                       Used to build same-page anchor-only links.
]]

local json_path = os.getenv("LABELS_JSON") or "web/docs/.labels.json"
local current_doc = os.getenv("CURRENT_DOC_FILE") or ""

-- ---- Carga del mapa de etiquetas --------------------------------------

local labels = {}

local function load_labels()
  local f = io.open(json_path, "r")
  if not f then
    io.stderr:write("resolve_refs.lua: no se encontró " .. json_path ..
      " — ejecuta primero la pasada collect_labels.\n")
    return
  end
  local content = f:read("*all")
  f:close()

  -- Parser JSON mínimo para nuestro formato conocido
  -- Formato: { "label": {"file":"...","anchor":"...","type":"...","number":"...","display":"..."}, ... }
  for label, blob in content:gmatch('"([^"]+)"%s*:%s*(%b{})') do
    local file    = blob:match('"file"%s*:%s*"([^"]*)"')
    local anchor  = blob:match('"anchor"%s*:%s*"([^"]*)"')
    local display = blob:match('"display"%s*:%s*"([^"]*)"')
    if file and anchor and display then
      labels[label] = { file = file, anchor = anchor, display = display }
    end
  end
  io.stderr:write("resolve_refs.lua: " .. #vim_tbl_keys_compat(labels) ..
    " etiquetas cargadas desde " .. json_path .. "\n")
end

-- Compat: contar claves de tabla (Lua 5.1 no tiene table.pack con n)
function vim_tbl_keys_compat(t)
  local keys = {}
  for k in pairs(t) do keys[#keys+1] = k end
  return keys
end

-- Cargar etiquetas al arrancar el módulo (antes de que se invoquen los handlers)
load_labels()

-- ---- Construcción de links -------------------------------------------

-- Dado un label, genera el link relativo desde current_doc
local function make_link(label)
  local info = labels[label]
  if not info then
    -- The label was not found in .labels.json. This can happen when the
    -- label is misspelled in the LaTeX source, or when it is defined in a
    -- file that was excluded from Pass 1. We use a visually prominent
    -- placeholder rather than silently dropping the reference so the
    -- student can find and fix it. extra.css styles .ref-unresolved as
    -- red italic text.
    return pandoc.Span(
      { pandoc.Str("(referencia no resuelta: " .. label .. ")") },
      pandoc.Attr("", {"ref-unresolved"}, {})
    )
  end

  -- Use a bare anchor (#section-id) when the target is in the same file.
  -- A full filename reference (introduccion.md#section-id) for a same-page
  -- link would cause a full page reload in some browsers instead of smooth
  -- in-page scrolling to the anchor.
  local href
  if info.file == current_doc then
    href = "#" .. info.anchor
  else
    href = info.file .. "#" .. info.anchor
  end

  return pandoc.Link(
    { pandoc.Str(info.display) },
    href,
    info.display
  )
end

-- ---- Sustitución en el AST -------------------------------------------

-- Link() handles the primary case: Pandoc 3.x converts \ref{label} to a
-- Link AST node with attributes reference-type="ref" and reference="label".
-- This is the expected path for well-formed LaTeX cross-references when
-- Pandoc can fully parse the surrounding environment.
function Link(el)
  local ref_type = el.attr.attributes["reference-type"]
  if ref_type == "ref" or ref_type == "autoref" or ref_type == "cref"
      or ref_type == "Cref" or ref_type == "eqref" then
    local label = el.attr.attributes["reference"]
    if label then
      return make_link(label)
    end
  end
end

-- RawInline() is the fallback for \ref{} commands that Pandoc emits as raw
-- LaTeX inline fragments instead of converting to Link nodes. This occurs
-- when the \ref is inside a custom macro, a \mbox{}, or another construct
-- that Pandoc passes through partially without expanding.
local function is_ref(el)
  if (el.format == "latex" or el.format == "tex") then
    return el.text:match("^\\[aA]?[cC]?ref%{([^}]+)%}$")
  end
end

function RawInline(el)
  local label = is_ref(el)
  if label then
    return make_link(label)
  end
end

-- Str() handles the rare case where \ref{} ends up as plain text in the AST.
-- This happens when the ref is embedded inside a string that Pandoc already
-- tokenised into a Str node before pattern-matching the \ref (e.g. "see
-- \ref{fig:x} above" packed into a single Str). We split the string at each
-- \ref occurrence, substitute the link, and return an array of inlines so
-- Pandoc can reassemble the paragraph.
function Str(el)
  local text = el.text
  if text:find("\\ref{") or text:find("\\autoref{") or text:find("\\cref{") then
    local parts = {}
    local pos = 1
    while pos <= #text do
      -- Buscar el siguiente \...ref{
      local s, e, label = text:find("\\[aA]?[cC]?ref%{([^}]+)%}", pos)
      if s then
        if s > pos then
          parts[#parts+1] = pandoc.Str(text:sub(pos, s-1))
        end
        parts[#parts+1] = make_link(label)
        pos = e + 1
      else
        parts[#parts+1] = pandoc.Str(text:sub(pos))
        break
      end
    end
    if #parts == 1 then return parts[1] end
    return parts  -- pandoc acepta array de Inline como reemplazo
  end
end


