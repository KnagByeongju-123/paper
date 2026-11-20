-- 참고문헌 정렬: 국내(한글) 문헌을 먼저, 해외 문헌을 뒤에 둔다. (각 묶음 안의 순서는 인용 양식 그대로)
-- build.py 가 --citeproc 다음에 이 필터를 적용한다. thesis.yaml → format.bib_order: korean-first
local function is_korean(blk)
  local s = pandoc.utils.stringify(blk):gsub("^[%s%p]+", "")
  local ok, cp = pcall(utf8.codepoint, s, 1)
  return ok and cp and ((cp >= 0xAC00 and cp <= 0xD7A3) or (cp >= 0x3130 and cp <= 0x318F) or (cp >= 0x1100 and cp <= 0x11FF))
end

function Div(el)
  if el.identifier ~= "refs" then return nil end
  local ko, other = {}, {}
  for _, b in ipairs(el.content) do
    if is_korean(b) then table.insert(ko, b) else table.insert(other, b) end
  end
  local out = {}
  for _, b in ipairs(ko) do table.insert(out, b) end
  for _, b in ipairs(other) do table.insert(out, b) end
  el.content = out
  return el
end
