"""Embed HTML generators for docs-open module."""

from __future__ import annotations

import html
import json
from urllib.parse import urlencode

# ── Document type mapping ──

DOC_TYPE_MAP = {
    "xlsx": {"category": "spreadsheet", "editor": "excel-engine", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "xls": {"category": "spreadsheet", "editor": "excel-engine", "mime": "application/vnd.ms-excel"},
    "csv": {"category": "spreadsheet", "editor": "excel-engine", "mime": "text/csv"},
    "txt": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "md": {"category": "text", "editor": "text-editor", "mime": "text/markdown"},
    "json": {"category": "text", "editor": "text-editor", "mime": "application/json"},
    "yaml": {"category": "text", "editor": "text-editor", "mime": "text/yaml"},
    "yml": {"category": "text", "editor": "text-editor", "mime": "text/yaml"},
    "xml": {"category": "text", "editor": "text-editor", "mime": "application/xml"},
    "ini": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "cfg": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "log": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "pdf": {"category": "document", "editor": "pdf-viewer", "mime": "application/pdf"},
    "docx": {"category": "document", "editor": "doc-viewer", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "doc": {"category": "document", "editor": "doc-viewer", "mime": "application/msword"},
    "pptx": {"category": "presentation", "editor": "ppt-viewer", "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "ppt": {"category": "presentation", "editor": "ppt-viewer", "mime": "application/vnd.ms-powerpoint"},
    "png": {"category": "image", "editor": "image-viewer", "mime": "image/png"},
    "jpg": {"category": "image", "editor": "image-viewer", "mime": "image/jpeg"},
    "jpeg": {"category": "image", "editor": "image-viewer", "mime": "image/jpeg"},
    "gif": {"category": "image", "editor": "image-viewer", "mime": "image/gif"},
    "svg": {"category": "image", "editor": "image-viewer", "mime": "image/svg+xml"},
    "bmp": {"category": "image", "editor": "image-viewer", "mime": "image/bmp"},
    "webp": {"category": "image", "editor": "image-viewer", "mime": "image/webp"},
}

EMBED_URL_TEMPLATE = "/api/docs/embed/{file_id}?token={access_token}&client_id={client_id}&open_id={open_id}"


def _get_doc_type(extension: str) -> dict:
    ext = (extension or "").lower().lstrip(".")
    info = DOC_TYPE_MAP.get(ext, {"category": "unknown", "editor": None, "mime": "application/octet-stream"})
    return {**info, "extension": ext}


def _html(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _json_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _token_headers(cid: str, oid: str, token: str) -> dict[str, str]:
    return {"X-Client-Id": cid, "X-Open-Id": oid, "X-Access-Token": token}


def _content_url(base: str, file_id: int) -> str:
    return f"{base}/api/docs/{file_id}/content"


def _file_url(base: str, file_id: int, token: str, cid: str, oid: str) -> str:
    query = urlencode({"token": token, "client_id": cid, "open_id": oid})
    return f"{base}/api/docs/{file_id}/file?{query}"


# ── Embed HTML generator ──

def _generate_embed_html(
    file_id: int,
    file_name: str,
    extension: str,
    doc_info: dict,
    base_url: str,
    token: str,
    client_id: str,
    open_id: str,
    is_editable: bool,
) -> str:
    category = doc_info.get("category", "unknown")

    api_base = base_url.rstrip("/")

    if category == "spreadsheet" and extension in ("xlsx", "xls"):
        return _spreadsheet_embed_html(file_id, file_name, api_base, token, client_id, open_id, is_editable)
    elif extension == "csv":
        return _csv_embed_html(file_id, file_name, api_base, token, client_id, open_id, is_editable)
    elif category == "text":
        return _text_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id, is_editable)
    elif extension == "pdf":
        return _pdf_embed_html(file_id, file_name, api_base, token, client_id, open_id)
    elif category == "document":
        return _doc_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    elif category == "presentation":
        return _presentation_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    elif category == "image":
        return _image_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    else:
        return _fallback_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)


def _spreadsheet_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    name_html = _html(name)
    content_url_js = _json_script(_content_url(base, file_id))
    headers_js = _json_script(_token_headers(cid, oid, token))
    return rf"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - 文档</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed;flex-shrink:0}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
.table-wrap{{overflow:auto;border:1px solid #e4e7ed;border-radius:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #e4e7ed;padding:4px 8px;text-align:left;white-space:nowrap;min-width:60px}}
th{{background:#f5f7fa;font-weight:500;color:#606266;position:sticky;top:0;z-index:1}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399;font-size:14px}}
.error{{display:flex;align-items:center;justify-content:center;height:100%;color:#f56c6c;font-size:14px;padding:20px;text-align:center}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">{"可编辑" if editable else "只读"}</span></div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  const esc=(v)=>String(v).replace(/[&<>"']/g,(ch)=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]))
  try{{
    const r=await fetch({content_url_js},{{
      headers:{headers_js}
    }})
    if(!r.ok)throw new Error('HTTP '+r.status)
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const data=body.data||{{}}
    let cells=data.content||data.cells||{{}}
    if(data.content?.sheet_set){{
      const ss=data.content.sheet_set
      const first=Object.keys(ss)[0]
      if(first)cells=ss[first].cells||{{}}
    }}
    if(data.sheet_set){{
      const ss=data.sheet_set
      const first=Object.keys(ss)[0]
      if(first)cells=ss[first].cells||{{}}
    }}
    const addrs=Object.keys(cells).sort((a,b)=>{{
      const ca=a.match(/^([A-Z]+)(\d+)$/),cb=b.match(/^([A-Z]+)(\d+)$/)
      if(!ca||!cb)return a.localeCompare(b)
      const colA=ca[1].length*26+ca[1].charCodeAt(0)-64,colB=cb[1].length*26+cb[1].charCodeAt(0)-64
      return parseInt(ca[2])-parseInt(cb[2])||colA-colB
    }})
    if(addrs.length===0){{app.innerHTML='<div class="loading">空表格</div>';return}}
    const rows={{}},cols=new Set
    for(const addr of addrs){{
      const m=addr.match(/^([A-Z]+)(\d+)$/)
      if(!m)continue
      const col=m[1],row=parseInt(m[2])
      if(!rows[row])rows[row]={{}};
      (rows[row])[col]=cells[addr]?.value??''
      cols.add(col)
    }}
    const sortedCols=[...cols].sort((a,b)=>a.length-b.length||a.localeCompare(b));
    const sortedRows=Object.keys(rows).sort((a,b)=>parseInt(a)-parseInt(b))
    let html='<div class="table-wrap"><table><thead><tr><th></th>'+sortedCols.map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'
    for(const r of sortedRows){{
      html+='<tr><th>'+r+'</th>'
      for(const c of sortedCols){{
        const val=(rows[r]?.[c]||'')
        html+='<td>'+esc(val)+'</td>'
      }}
      html+='</tr>'
    }}
    html+='</tbody></table></div>'
    app.innerHTML=html
  }}catch(e){{
    app.innerHTML='<div class="error">加载失败: '+esc(e.message)+'</div>'
  }}
}})()
</script>
</body></html>"""


def _csv_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    name_html = _html(name)
    content_url_js = _json_script(_content_url(base, file_id))
    headers_js = _json_script(_token_headers(cid, oid, token))
    editable_js = _json_script(bool(editable))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - CSV</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
textarea{{width:100%;height:100%;border:1px solid #e4e7ed;border-radius:4px;padding:12px;font-family:monospace;font-size:13px;resize:none;outline:none}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">{"可编辑" if editable else "只读"}</span></div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  const esc=(v)=>String(v).replace(/[&<>"']/g,(ch)=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]))
  try{{
    const r=await fetch({content_url_js},{{
      headers:{headers_js}
    }})
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const text=body.data?.content||''
    if({editable_js} && 'content' in (body.data||{{}})){{
      app.innerHTML='<textarea id="editor">'+esc(text)+'</textarea><div style="margin-top:8px;text-align:right"><button onclick="saveCsv()" style="padding:6px 16px;background:#2395bc;color:#fff;border:none;border-radius:4px;cursor:pointer">保存</button></div>'
      window.saveCsv=async function(){{
        const val=document.getElementById('editor').value
        const r=await fetch({content_url_js},{{
          method:'POST',headers:{{'Content-Type':'application/json',...{headers_js}}},
          body:JSON.stringify({{content:val}})
        }})
        const b=await r.json()
        alert(b.success?'✅ 保存成功':'❌ '+b.error)
      }}
    }}else{{
      app.innerHTML='<textarea readonly>'+esc(text)+'</textarea>'
    }}
  }}catch(e){{
    app.innerHTML='<div class="loading">加载失败: '+esc(e.message)+'</div>'
  }}
}})()
</script>
</body></html>"""


def _text_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    name_html = _html(name)
    ext_html = _html(ext.upper())
    content_url_js = _json_script(_content_url(base, file_id))
    headers_js = _json_script(_token_headers(cid, oid, token))
    editable_js = _json_script(bool(editable))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - 文本</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed;flex-shrink:0}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.toolbar .save-btn{{padding:6px 16px;background:#2395bc;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px;display:none}}
.toolbar .save-btn:hover{{background:#31A1C6}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
textarea{{width:100%;height:100%;border:1px solid #e4e7ed;border-radius:4px;padding:12px;font-family:monospace;font-size:13px;line-height:1.6;resize:none;outline:none}}
textarea:focus{{border-color:#2395bc}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2>
<span class="badge">{ext_html} {"可编辑" if editable else "只读"}</span>
<button class="save-btn" id="saveBtn" onclick="saveText()" style="display:none">保存</button>
</div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  const esc=(v)=>String(v).replace(/[&<>"']/g,(ch)=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]))
  try{{
    const r=await fetch({content_url_js},{{
      headers:{headers_js}
    }})
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const text=body.data?.content||''
    const canEdit={editable_js}
    if(canEdit){{
      app.innerHTML='<textarea id="editor">'+esc(text)+'</textarea>'
      document.getElementById('saveBtn').style.display='inline-block'
    }}else{{
      app.innerHTML='<textarea readonly>'+esc(text)+'</textarea>'
    }}
  }}catch(e){{
    app.innerHTML='<div class="loading">加载失败: '+esc(e.message)+'</div>'
  }}
}})()
window.saveText=async function(){{
  const val=document.getElementById('editor').value
  const r=await fetch({content_url_js},{{
    method:'POST',headers:{{'Content-Type':'application/json',...{headers_js}}},
    body:JSON.stringify({{content:val}})
  }})
  const b=await r.json()
  if(b.success){{document.getElementById('saveBtn').textContent='✅ 已保存';setTimeout(()=>document.getElementById('saveBtn').textContent='保存',2000)}}else{{alert('❌ '+b.error)}}
}}
</script>
</body></html>"""


def _pdf_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = _html(_file_url(base, file_id, token, cid, oid))
    name_html = _html(name)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - PDF</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">PDF</span></div>
<div class="content">
<iframe src="{file_url}" title="{name_html}"></iframe>
</div>
</body></html>"""


def _doc_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = _html(_file_url(base, file_id, token, cid, oid))
    name_html = _html(name)
    ext_html = _html(ext.upper())
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - 文档</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">{ext_html}</span></div>
<div class="content">
<iframe src="{file_url}" title="{name_html}"></iframe>
</div>
</body></html>"""


def _presentation_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = _html(_file_url(base, file_id, token, cid, oid))
    name_html = _html(name)
    ext_html = _html(ext.upper())
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - 演示</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">{ext_html}</span></div>
<div class="content">
<iframe src="{file_url}" title="{name_html}"></iframe>
</div>
</body></html>"""


def _image_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    img_url = _html(_file_url(base, file_id, token, cid, oid))
    name_html = _html(name)
    ext_html = _html(ext.upper())
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html} - 图片</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px;overflow:auto}}
img{{max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
</style></head>
<body>
<div class="toolbar"><h2>{name_html}</h2><span class="badge">{ext_html}</span></div>
<div class="content">
<img src="{img_url}" alt="{name_html}" />
</div>
</body></html>"""


def _fallback_embed_html(file_id: int, name: str, ext: str, base: str = "", token: str = "", cid: str = "", oid: str = "") -> str:
    raw_file_url = _file_url(base, file_id, token, cid, oid) if base and token else f"/api/docs/{file_id}/file"
    file_url = _html(raw_file_url)
    name_html = _html(name)
    ext_html = _html(ext)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name_html}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#fff;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.content{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#909399;gap:12px}}
.icon{{font-size:48px}}
</style></head>
<body>
<div class="content">
<div class="icon">📄</div>
<h3>{name_html}</h3>
<p>格式 .{ext_html} 暂不支持在线预览</p>
<p style="font-size:13px"><a href="{file_url}" style="color:#2395bc">下载文件</a></p>
</div>
</body></html>"""
