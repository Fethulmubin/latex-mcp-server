import os
import uuid
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Load local .env file if present
load_dotenv()

from mcp.server.mcpserver import MCPServer
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import boto3
from botocore.config import Config
import uvicorn

PORT = int(os.environ.get("PORT", 8000))

# Cloudflare R2 Configuration
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "latex-pdf").strip()
R2_PUBLIC_DOMAIN = os.environ.get("R2_PUBLIC_DOMAIN", "").strip().rstrip("/")

def get_s3_client():
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4")
    )

def upload_pdf_to_r2(pdf_bytes: bytes, filename: str) -> str:
    """Uploads PDF to Cloudflare R2 and returns direct HTTPS download URL."""
    client = get_s3_client()
    if not client or not R2_PUBLIC_DOMAIN:
        missing = []
        if not R2_ACCOUNT_ID: missing.append("R2_ACCOUNT_ID")
        if not R2_ACCESS_KEY_ID: missing.append("R2_ACCESS_KEY_ID")
        if not R2_SECRET_ACCESS_KEY: missing.append("R2_SECRET_ACCESS_KEY")
        if not R2_PUBLIC_DOMAIN: missing.append("R2_PUBLIC_DOMAIN")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    object_key = f"{uuid.uuid4().hex[:10]}_{filename}.pdf"
    
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=object_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
        ContentDisposition=f'inline; filename="{filename}.pdf"'
    )
    return f"{R2_PUBLIC_DOMAIN}/{object_key}"

# Initialize MCP Server
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
    Compiles LaTeX markup into a PDF, uploads to Cloudflare R2, 
    and returns a direct HTTPS download link.
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

            pdf_bytes = pdf_path.read_bytes()

            # Upload to Cloudflare R2
            try:
                download_url = upload_pdf_to_r2(pdf_bytes, filename)
            except Exception as upload_err:
                return f"STORAGE_ERROR: Failed to upload PDF to R2: {str(upload_err)}"

            return (
                f"SUCCESS: PDF compiled successfully ({len(pdf_bytes)} bytes).\n"
                f"DOWNLOAD_URL: {download_url}\n"
                f"INSTRUCTION FOR AI: Present this link as a clean, clickable Markdown link: "
                f"[Download {filename}.pdf]({download_url}) in your response."
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

# Extract base MCP application
mcp_app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app

class MCPCloudHostMiddleware:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")

            # OAuth discovery probes
            if path.startswith("/.well-known/oauth-protected-resource"):
                response = JSONResponse({}, status_code=200)
                await response(scope, receive, send)
                return

            # Normalize path
            if path in ["/mcp", "/mcp/"]:
                scope["path"] = "/mcp"

            # Rewrite Host header to satisfy MCP SDK internal check
            new_headers = []
            for name, value in scope.get("headers", []):
                if name.lower() == b"host":
                    new_headers.append((b"host", b"localhost:8000"))
                else:
                    new_headers.append((name, value))
            scope["headers"] = new_headers

        await self.inner_app(scope, receive, send)

app = CORSMiddleware(
    MCPCloudHostMiddleware(mcp_app),
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    client_status = "Configured" if get_s3_client() else "NOT Configured"
    print(f"--> R2 Storage Client Status: {client_status}")
    print(f"--> R2 Public Domain: {R2_PUBLIC_DOMAIN or 'MISSING'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")