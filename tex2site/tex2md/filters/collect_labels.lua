--[[
  collect_labels.lua — Filtro Pandoc (Lua), PASADA 1
  =======================================================
  Se ejecuta sobre el documento COMPLETO (tfg.tex con todos los \input resueltos).
  Recorre el AST y construye un mapa:
      label  →  { file, anchor, type, number }

  Tipos reconocidos:
    - figure     (entornos figure / \label dentro de figure)
    - table      (entornos table  / \label dentro de table)
    - listing    (entornos lstlisting / \label dentro de lstlisting)
    - equation   (\label dentro de equation/align/…)
    - section    (\chapter, \section, \subsection, \subsubsection con \label)
    - appendix   (capítulos en modo \appendix)

  El mapa se serializa como JSON en el fichero indicado por la variable
  de entorno LABELS_JSON (por defecto: web/docs/.labels.json).

  El fichero de destino por capítulo se infiere a partir de la variable de
  entorno CURRENT_FILE pasada por convert.sh para cada capítulo.
  En la pasada de recolección global, convert.sh debe pasar la lista de
  ficheros de salida en CHAPTER_MAP con formato:
      "indice_capitulo:nombre_fichero_sin_.md"
  separados por comas.
  Ejemplo: CHAPTER_MAP="0:index,1:introduccion,2:metodologia,..."
]]

local json_output = os.getenv("LABELS_JSON") or "web/docs/.labels.json"
local chapter_map_env = os.getenv("CHAPTER_MAP") or ""

-- Construir tabla chapter_index → filename
local chapter_map = {}
for entry in chapter_map_env:gmatch("[^,]+") do
  local idx, name = entry:match("^(%d+):(.+)$")
  if idx and name then
    chapter_map[tonumber(idx)] = name
  end
end

-- Counters for each numbered element type.
-- LaTeX numbers figures, tables, equations, and sections relative to their
-- enclosing chapter (e.g. Fig. 3.2 = chapter 3, second figure). We reset
-- per-chapter counters each time we encounter an H1 header so that the
-- computed numbers match those in the compiled PDF.
local counters = {
  figure   = 0,
  table    = 0,
  listing  = 0,
  equation = 0,
  chapter  = 0,
  section  = 0,
  subsection = 0,
  subsubsection = 0,
}

-- Result map: label → {file, anchor, type, number, display}
local labels = {}

-- Index of the current chapter in chapter_map (0 = document preamble)
local current_chapter = 0
local current_chapter_title = ""
-- Whether we have entered appendix mode (\appendix switches chapter
-- numbering from Arabic numerals to letters A, B, C, …)
local in_appendix = false
local appendix_letter_offset = 0  -- 0=A, 1=B, …

-- Obtiene el nombre del fichero para el capítulo actual
local function current_file()
  return (chapter_map[current_chapter] or "index") .. ".md"
end

-- Convierte número de apéndice a letra (1→A, 2→B, …)
local function appendix_letter(n)
  return string.char(64 + n)
end

-- Registra una etiqueta
local function register(label, ltype, number, display_prefix)
  if label and label ~= "" then
    local anchor = label:gsub(":", "-"):gsub("%s", "-"):lower()
    local display = display_prefix .. tostring(number)
    labels[label] = {
      file    = current_file(),
      anchor  = anchor,
      type    = ltype,
      number  = number,
      display = display,
    }
  end
end

-- Extrae el primer \label{...} de un texto raw LaTeX
local function extract_label(text)
  return text:match("\\label%{([^}]+)%}")
end

-- ---- Visitantes del AST -----------------------------------------------

function Header(el)
  local level = el.level
  if level == 1 then
    -- Skip empty headers (e.g. \chapter*{} in licencia.tex)
    local title_text = pandoc.utils.stringify(el.content)
    if title_text == "" then return end

    -- Detect appendix mode. \appendix in LaTeX switches chapter numbering
    -- from Arabic numerals to letters (A, B, C, …). Pandoc marks the first
    -- appendix chapter with class "appendix" on its header element. Once
    -- seen, all subsequent H1 headers are treated as appendix chapters.
    local is_appendix = false
    for _, c in ipairs(el.classes) do
      if c == "appendix" then is_appendix = true end
    end
    if is_appendix then in_appendix = true end

    if in_appendix then
      appendix_letter_offset = appendix_letter_offset + 1
      current_chapter = current_chapter + 1
      counters.chapter = appendix_letter_offset
    else
      counters.chapter = counters.chapter + 1
      current_chapter = current_chapter + 1
    end
    -- Reset per-chapter element counters. LaTeX numbers figures, tables,
    -- equations, and sections relative to the chapter (e.g. Fig. 3.2 = chapter
    -- 3, second figure). Resetting here replicates that behaviour so the
    -- display string stored in .labels.json matches the compiled PDF.
    counters.section = 0
    counters.subsection = 0
    counters.subsubsection = 0
    counters.figure = 0
    counters.table = 0
    counters.listing = 0
    counters.equation = 0

    local label = el.identifier
    if label and label ~= "" then
      local title = pandoc.utils.stringify(el.content)
      local display = in_appendix
        and ("Anexo " .. appendix_letter(appendix_letter_offset) .. ": " .. title)
        or  title
      current_chapter_title = title
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = in_appendix and "appendix" or "chapter",
        number  = counters.chapter,
        display = display,
      }
    else
      -- Sin label: aún así actualizar el título del capítulo actual
      current_chapter_title = pandoc.utils.stringify(el.content)
    end

  elseif level == 2 then
    counters.section = counters.section + 1
    counters.subsection = 0
    local label = el.identifier
    if label and label ~= "" then
      local num = counters.chapter .. "." .. counters.section
      local sec_title = pandoc.utils.stringify(el.content)
      local display = current_chapter_title ~= ""
        and (current_chapter_title .. " → " .. sec_title)
        or  sec_title
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = "section",
        number  = num,
        display = display,
      }
    end

  elseif level == 3 then
    counters.subsection = counters.subsection + 1
    counters.subsubsection = 0
    local label = el.identifier
    if label and label ~= "" then
      local num = counters.chapter .. "." .. counters.section .. "." .. counters.subsection
      local sec_title = pandoc.utils.stringify(el.content)
      local display = current_chapter_title ~= ""
        and (current_chapter_title .. " → " .. sec_title)
        or  sec_title
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = "subsection",
        number  = num,
        display = display,
      }
    end

  elseif level == 4 then
    counters.subsubsection = counters.subsubsection + 1
    local label = el.identifier
    if label and label ~= "" then
      local num = counters.chapter .. "." .. counters.section .. "."
               .. counters.subsection .. "." .. counters.subsubsection
      local sec_title = pandoc.utils.stringify(el.content)
      local display = current_chapter_title ~= ""
        and (current_chapter_title .. " → " .. sec_title)
        or  sec_title
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = "subsubsection",
        number  = num,
        display = display,
      }
    end
  end
end

-- Figure() handles the native Pandoc 3.x Figure AST node produced by
-- \begin{figure}...\end{figure} environments. Pandoc 3.0 introduced Figure
-- as a first-class element; in earlier versions figures were represented as
-- a Para containing a single Image node (handled by Para() below).
-- Both handlers are kept to support sites built with Pandoc >= 2.x.
function Figure(el)
  local label = el.identifier
  if label and label ~= "" then
    counters.figure = counters.figure + 1
    local num = counters.chapter .. "." .. counters.figure
    local caption = pandoc.utils.stringify(el.caption)
    labels[label] = {
      file    = current_file(),
      anchor  = label,
      type    = "figure",
      number  = num,
      display = caption ~= "" and caption or ("fig. " .. num),
    }
  end
end

-- Para() is the fallback for the older Pandoc (< 3.0) representation of
-- figures: a paragraph containing a single Image node. This also catches
-- cases where Pandoc 3.x cannot detect the figure environment natively and
-- falls back to the Para+Image form. Keeping this handler ensures correct
-- label numbers regardless of the installed Pandoc version.
function Para(el)
  if #el.content == 1 and el.content[1].t == "Image" then
    local img = el.content[1]
    local label = img.identifier
    if not (label and label ~= "") then
      label = img.title and img.title:match("\\label%{([^}]+)%}") or nil
    end
    if label and label ~= "" then
      counters.figure = counters.figure + 1
      local num = counters.chapter .. "." .. counters.figure
      local caption = pandoc.utils.stringify(img.caption)
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = "figure",
        number  = num,
        display = caption ~= "" and caption or ("fig. " .. num),
      }
    end
  end
end

-- Tablas
function Table(el)
  local label = el.attr and el.attr.identifier
  if label and label ~= "" then
    counters.table = counters.table + 1
    local num = counters.chapter .. "." .. counters.table
    local caption = ""
    if el.caption then
      if el.caption.short then
        caption = pandoc.utils.stringify(el.caption.short)
      end
      if caption == "" and el.caption.long then
        caption = pandoc.utils.stringify(el.caption.long)
      end
    end
    labels[label] = {
      file    = current_file(),
      anchor  = label,
      type    = "table",
      number  = num,
      display = caption ~= "" and caption or ("tabla " .. num),
    }
  end
end

-- Bloques de código (lstlisting → CodeBlock con posible label en atributo id)
function CodeBlock(el)
  local label = el.identifier
  if label and label ~= "" then
    counters.listing = counters.listing + 1
    local num = counters.chapter .. "." .. counters.listing
    labels[label] = {
      file    = current_file(),
      anchor  = label,
      type    = "listing",
      number  = num,
      display = "código " .. num,
    }
  end
end

-- RawBlock() captures \label{} commands that appear inside LaTeX environments
-- Pandoc cannot fully parse and emits as opaque RawBlock nodes. This includes
-- display equations (\begin{equation}, \begin{align}), non-standard figure
-- environments, and any environment Pandoc passes through unchanged. Without
-- this handler, labels inside those environments would be silently dropped
-- and the corresponding \ref{} commands would produce unresolved-reference
-- markers in the output.
function RawBlock(el)
  if el.format == "latex" or el.format == "tex" then
    local label = extract_label(el.text)
    if label then
      -- Determine element type by heuristic inspection of the raw block text
      local ltype = "section"
      local num   = counters.chapter
      local display = "Sección " .. num
      if el.text:match("\\begin%{equation") or el.text:match("\\begin%{align") then
        counters.equation = counters.equation + 1
        ltype   = "equation"
        num     = counters.chapter .. "." .. counters.equation
        display = "ec. " .. num
      elseif el.text:match("\\begin%{figure") then
        counters.figure = counters.figure + 1
        num     = counters.chapter .. "." .. counters.figure
        ltype   = "figure"
        local cap = el.text:match("\\caption%{([^}]*)%}")
        display = cap or ("fig. " .. num)
      elseif el.text:match("\\begin%{table") then
        counters.table = counters.table + 1
        num     = counters.chapter .. "." .. counters.table
        ltype   = "table"
        local cap = el.text:match("\\caption%{([^}]*)%}")
        display = cap or ("tabla " .. num)
      elseif el.text:match("\\begin%{lstlisting") then
        counters.listing = counters.listing + 1
        num     = counters.chapter .. "." .. counters.listing
        ltype   = "listing"
        display = "código " .. num
      end
      labels[label] = {
        file    = current_file(),
        anchor  = label,
        type    = ltype,
        number  = tostring(num),
        display = display,
      }
    end
  end
end

-- ---- Serialización al final del documento ------------------------------

function Pandoc(doc)
  -- Serialise the labels map to JSON manually.
  -- Pandoc's embedded Lua (5.3) does not include a standard JSON library,
  -- and installing one via luarocks is not feasible in a portable build
  -- pipeline. The .labels.json format is well-defined (a flat object with
  -- fixed string fields), so a manual serialiser is safe and has no
  -- external dependencies.
  local lines = {"{"}
  local first = true
  for label, info in pairs(labels) do
    if not first then lines[#lines+1] = "," end
    first = false
    -- Escapar comillas en valores
    local esc = function(s)
      return tostring(s):gsub('"', '\\"')
    end
    lines[#lines+1] = string.format(
      '  "%s": {"file":"%s","anchor":"%s","type":"%s","number":"%s","display":"%s"}',
      esc(label), esc(info.file), esc(info.anchor),
      esc(info.type), esc(info.number), esc(info.display)
    )
  end
  lines[#lines+1] = "}"

  local out_path = json_output
  local f, err = io.open(out_path, "w")
  if not f then
    io.stderr:write("collect_labels.lua: no se pudo escribir " .. out_path .. ": " .. (err or "") .. "\n")
  else
    f:write(table.concat(lines, "\n"))
    f:close()
    local label_count = 0
    for _ in pairs(labels) do label_count = label_count + 1 end
    io.stderr:write("collect_labels.lua: " .. label_count .. " etiquetas escritas en " .. out_path .. "\n")
  end

  -- Return the document unchanged: this filter only collects metadata and
  -- does not transform any AST nodes. Pandoc requires that the top-level
  -- Pandoc() handler return a valid document, even if unmodified.
  return doc
end
