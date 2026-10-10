import os
import uuid
import subprocess
import tempfile
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, FileResponse, Response

PORT = int(os.environ.get("PORT", 8000))
# Dynamically determine the public URL from Render, or fallback
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://latex-mcp-server.onrender.com").rstrip("/")

# Directory to temporarily hold generated PDFs for download
PDF_CACHE_DIR = Path("/tmp/pdf_cache")
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 1. Initialize MCP Server
mcp = MCPServer("latex-to-pdf")

DEFAULT_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=1in]{geometry}
\usepackage{microtype}
\usepackage{booktabs}
\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\usepackage{hyperref}
\hypersetup{colorlinks=true, linkcolor=blue!70!black, urlcolor=blue!70!black}
"""

@mcp.tool()
def compile_latex(latex_source: str, filename: str = "document") -> str:
    """
    Compiles LaTeX markup into a PDF and returns a direct HTTPS download link.
    """
    code = latex_source.strip()
    if r"\documentclass" not in code:
        code = f"{DEFAULT_PREAMBLE}\n\\begin{{document}}\n{code}\n\\end{{document}}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tex_path = tmp_path / f"{filename}.tex"
        pdf_path = tmp_path / f"{filename}.pdf"

        tex_path.write_text(code, encoding="utf-8")

        try:
            process = subprocess.run(
                ["tectonic", str(tex_path), "--outdir", str(tmp_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            if process.returncode != 0:
                raw_log = (process.stderr or process.stdout).strip()
                return (
                    f"COMPILATION_ERROR:\n{raw_log}\n\n"
                    "INSTRUCTION FOR AI: Examine the compiler error above, fix the LaTeX code, "
                    "and invoke compile_latex again."
                )

            # Generate a unique download ID and store the PDF
            file_id = f"{uuid.uuid4().hex[:12]}_{filename}.pdf"
            dest_file = PDF_CACHE_DIR / file_id
            dest_file.write_bytes(pdf_path.read_bytes())

            # Construct the direct download link
            download_url = f"{PUBLIC_URL}/download/{file_id}"

            return (
                f"SUCCESS: PDF compiled successfully.\n"
                f"DOWNLOAD_URL: {download_url}\n"
                f"INSTRUCTION: Present this link as a clickable markdown link [Download {filename}.pdf]({download_url}) to the user."
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

# 2. Get base MCP application
mcp_app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app

# 3. ASGI Middleware for OAuth probes, host headers, and serving PDF downloads
class MCPAppWithDownloads:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")

            # Serve generated PDFs for one-click browser viewing/download
            if path.startswith("/download/"):
                filename = path.replace("/download/", "").strip()
                file_path = PDF_CACHE_DIR / filename
                if file_path.is_file():
                    response = FileResponse(
                        str(file_path),
                        media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'}
                    )
                    await response(scope, receive, send)
                    return
                else:
                    response = JSONResponse({"error": "File not found or expired"}, status_code=404)
                    await response(scope, receive, send)
                    return

            # OAuth discovery probes
            if path.startswith("/.well-known/oauth-protected-resource"):
                response = JSONResponse({}, status_code=200)
                await response(scope, receive, send)
                return

            # Normalize MCP paths
            if path in ["/mcp", "/mcp/"]:
                scope["path"] = "/mcp"

            # Rewrite Host header for MCP SDK internal check
            new_headers = []
            for name, value in scope.get("headers", []):
                if name.lower() == b"host":
                    new_headers.append((b"host", b"localhost:8000"))
                else:
                    new_headers.append((name, value))
            scope["headers"] = new_headers

        await self.inner_app(scope, receive, send)

# Wrap with CORS
app = CORSMiddleware(
    MCPAppWithDownloads(mcp_app),
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")