import os
import subprocess
import tempfile
import base64
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount
import uvicorn

PORT = int(os.environ.get("PORT", 8000))

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
    """Compiles LaTeX markup into a PDF and returns a Base64 data URI."""
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

            pdf_bytes = pdf_path.read_bytes()
            b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
            return (
                f"SUCCESS: PDF created ({len(pdf_bytes)} bytes).\n"
                f"DATA_URI: data:application/pdf;base64,{b64_pdf}"
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

# 2. Get the streamable HTTP Starlette sub-app and its lifespan
mcp_app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app

# Handle OAuth probe so Gemini knows no auth is required
async def oauth_discovery(request):
    return JSONResponse({}, status_code=200)

async def root_probe(request):
    if request.method == "HEAD":
        return Response(status_code=200)
    # Forward any GET or other probes
    return JSONResponse({"status": "ok", "server": "latex-to-pdf", "protocol": "mcp"})

# 3. Use the MCP app's lifespan so the anyio TaskGroup initializes properly!
main_app = Starlette(
    lifespan=mcp_app.router.lifespan_context,
    routes=[
        Route("/.well-known/oauth-protected-resource", oauth_discovery, methods=["GET", "OPTIONS"]),
        Route("/.well-known/oauth-protected-resource/mcp", oauth_discovery, methods=["GET", "OPTIONS"]),
        # Mount the MCP handler directly on BOTH /mcp and root / for POST JSON-RPC requests
        Mount("/mcp", mcp_app),
        Mount("/", mcp_app)
    ]
)

main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(main_app, host="0.0.0.0", port=PORT)