"""
Widget Embed API - Serves the embeddable widget JavaScript bundle.

This endpoint serves the pre-built widget-embed.js file that can be loaded
on any external website (WordPress, etc.) via a simple script tag:

    <script src="http://your-backend-url/widget-embed.js"></script>

The widget bundle is built separately using `npm run build:widget` in the
frontend directory, which outputs to frontend/dist-widget/widget-embed.js.

Caching: The widget JS is cached with appropriate headers for performance.
CORS: Served with permissive CORS headers since it needs to load from any origin.
"""

import hashlib
import os
import time
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Widget"])

# Resolve widget bundle path
# In Docker: /app/frontend/dist-widget/widget-embed.js
# Local dev: ../frontend/dist-widget/widget-embed.js
WIDGET_PATHS = [
    # Docker path
    Path("/app/frontend/dist-widget/widget-embed.js"),
    # Local development path (relative to backend/src/)
    Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist-widget" / "widget-embed.js",
]

# Resolve assessment bundle path
ASSESSMENT_PATHS = [
    Path("/app/frontend/dist-assessment/assessment.js"),
    Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist-assessment" / "assessment.js",
]

# Resolve logo path
LOGO_PATHS = [
    Path("/app/backend/static/images/logo.png"),
    Path(__file__).resolve().parent.parent.parent / "static" / "images" / "logo.png",
]


def _get_external_base_url(request: Request) -> str:
    """
    Derive the externally-visible base URL from the incoming request.

    Respects X-Forwarded-Proto and X-Forwarded-Host headers set by reverse
    proxies (ngrok, nginx, AWS ALB, Cloudflare, etc.).  Falls back to
    request.base_url when no forwarding headers are present (local dev).

    This prevents mixed-content issues where the backend sees http://
    internally but the browser loaded the page over https://.
    """
    # Protocol: trust X-Forwarded-Proto first, then request scheme
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    # Host: trust X-Forwarded-Host, then Host header, then request netloc
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


# ---------------------------------------------------------------------------
# Widget Content Hash Cache — auto-versioning without manual bumps
# ---------------------------------------------------------------------------
# Computed once at startup (or on first request) from the file contents.
# When the file changes after a rebuild, the hash changes automatically.
# Used as an ETag and X-Widget-Version header value.
# ---------------------------------------------------------------------------
_widget_content_hash: str | None = None
_widget_file_mtime: float = 0.0


def _compute_widget_hash(bundle_path: Path) -> str:
    """Compute SHA-256 content hash of the widget bundle for ETag."""
    global _widget_content_hash, _widget_file_mtime
    current_mtime = bundle_path.stat().st_mtime
    if _widget_content_hash is None or current_mtime != _widget_file_mtime:
        content = bundle_path.read_bytes()
        _widget_content_hash = hashlib.sha256(content).hexdigest()[:16]
        _widget_file_mtime = current_mtime
        logger.info(
            "Widget bundle hash computed: %s (%.1f KB)",
            _widget_content_hash, len(content) / 1024,
        )
    return _widget_content_hash


def _find_widget_bundle() -> Path | None:
    """Find the widget bundle file from known paths."""
    for p in WIDGET_PATHS:
        if p.exists():
            return p
    return None


def _find_assessment_bundle() -> Path | None:
    """Find the assessment bundle file from known paths."""
    for p in ASSESSMENT_PATHS:
        if p.exists():
            return p
    return None


# In-memory cache for the assessment bundle content (avoids re-reading on every request)
_assessment_bundle_cache: dict[str, tuple[str, float]] = {}


def _read_assessment_bundle() -> str | None:
    """
    Read the assessment JS bundle content into memory.
    
    Caches the content and re-reads if the file has been modified.
    Returns None if the bundle file is not found.
    """
    bundle_path = _find_assessment_bundle()
    if bundle_path is None:
        return None

    path_str = str(bundle_path)
    mtime = bundle_path.stat().st_mtime

    # Return cached content if file hasn't changed
    if path_str in _assessment_bundle_cache:
        cached_content, cached_mtime = _assessment_bundle_cache[path_str]
        if cached_mtime == mtime:
            return cached_content

    # Read and cache
    content = bundle_path.read_text(encoding="utf-8")
    _assessment_bundle_cache[path_str] = (content, mtime)
    logger.info("Assessment bundle loaded: %s (%.1f KB)", path_str, len(content) / 1024)
    return content


@router.get("/widget-embed.js", response_class=FileResponse)
async def serve_widget_bundle(request: Request):
    """
    Serve the embeddable widget JavaScript bundle.
    
    This endpoint serves the compiled widget-embed.js file with appropriate
    CORS and caching headers. The file is built using `npm run build:widget`.
    
    Returns:
        FileResponse: The widget JavaScript bundle
    """
    bundle_path = _find_widget_bundle()
    
    if bundle_path is None:
        logger.error(
            "Widget bundle not found. Run 'cd frontend && npm run build:widget' to build it. "
            f"Searched paths: {[str(p) for p in WIDGET_PATHS]}"
        )
        return JSONResponse(
            status_code=404,
            content={
                "error": "widget_not_built",
                "message": "Widget bundle not found. Run 'npm run build:widget' in the frontend directory.",
            },
        )
    
    # Compute content hash for automatic versioning (changes on every rebuild)
    content_hash = _compute_widget_hash(bundle_path)

    return FileResponse(
        path=str(bundle_path),
        media_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            # AGGRESSIVE NO-CACHE: Force browsers, CDNs, WP Rocket, and
            # proxies (ngrok, CloudFront) to NEVER serve a cached copy.
            # - no-cache: revalidate on every request
            # - no-store: do not store in any cache at all
            # - must-revalidate: stale copies must not be used
            # - Pragma/Expires: legacy HTTP/1.0 compatibility
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            # AUTO-VERSIONING: Content-hash ETag changes automatically on
            # every rebuild — no manual version bumping needed.
            "ETag": f'"{content_hash}"',
            "X-Widget-Version": content_hash,
            "X-Content-Type-Options": "nosniff",
            "ngrok-skip-browser-warning": "true",
        },
    )


@router.get("/widget-test", response_class=HTMLResponse)
async def widget_test_page(request: Request):
    """
    Serve a test page for the embeddable widget.
    
    This page simulates an external website loading the widget via a script tag.
    Useful for testing before deploying to a real WordPress site.
    
    Returns:
        HTMLResponse: Test HTML page with the widget embedded
    """
    # Determine the base URL for the widget script
    base_url = str(request.base_url).rstrip("/")
    cache_bust = int(time.time())
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NeuroReach AI Widget - Test Page</title>
    <style>
        /* Simulating a typical WordPress site */
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
            color: #333;
            line-height: 1.8;
        }}
        h1 {{ color: #1a1a2e; font-size: 2.2em; margin-bottom: 0.5em; }}
        h2 {{ color: #16213e; font-size: 1.5em; margin-top: 1.5em; }}
        p {{ margin: 1em 0; }}
        .hero {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 60px 40px;
            border-radius: 12px;
            margin-bottom: 40px;
            text-align: center;
        }}
        .hero h1 {{ color: white; font-size: 2.5em; }}
        .hero p {{ font-size: 1.2em; opacity: 0.9; }}
        .card {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}
        .badge {{
            display: inline-block;
            background: #e3f2fd;
            color: #1565c0;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            margin-right: 8px;
        }}
        footer {{
            text-align: center;
            margin-top: 60px;
            padding: 20px;
            color: #888;
            font-size: 0.9em;
        }}
        code {{
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        pre {{
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>🧠 TMS Therapy Center</h1>
        <p>Advanced Transcranial Magnetic Stimulation for Depression, Anxiety &amp; More</p>
        <p><span class="badge" style="background:rgba(255,255,255,0.2);color:white;">FDA-Cleared</span>
           <span class="badge" style="background:rgba(255,255,255,0.2);color:white;">Insurance Accepted</span>
           <span class="badge" style="background:rgba(255,255,255,0.2);color:white;">HIPAA Compliant</span></p>
    </div>

    <div class="card">
        <h2>What is TMS Therapy?</h2>
        <p>Transcranial Magnetic Stimulation (TMS) is a non-invasive procedure that uses magnetic fields to stimulate nerve cells in the brain to improve symptoms of depression, anxiety, OCD, and PTSD.</p>
        <p>TMS therapy is FDA-cleared and covered by most major insurance plans. Treatment typically involves daily sessions over 4-6 weeks, with each session lasting about 20-40 minutes.</p>
    </div>

    <div class="card">
        <h2>Is TMS Right for You?</h2>
        <p>Click the <strong>"Free Assessment"</strong> button in the bottom-right corner to take our quick 2-minute assessment. Our care coordinators will review your information and reach out within 24 hours to schedule a consultation.</p>
        <p><span class="badge">✓ Free Assessment</span>
           <span class="badge">✓ HIPAA Protected</span>
           <span class="badge">✓ 2 Minutes</span></p>
    </div>

    <div class="card">
        <h2>Widget Embed Code</h2>
        <p>To embed this widget on your WordPress site, add this script tag:</p>
        <pre>&lt;script src="{base_url}/widget-embed.js"&gt;&lt;/script&gt;</pre>
        <p>That's it! The widget will automatically appear as a floating button.</p>
    </div>

    <footer>
        <p>This is a test page for the NeuroReach AI embeddable widget.</p>
        <p>Widget is served from: <code>{base_url}/widget-embed.js</code></p>
    </footer>

    <!-- NeuroReach AI Widget - Single script tag embedding -->
    <script src="{base_url}/widget-embed.js?v={cache_bust}"></script>
</body>
</html>"""
    
    return HTMLResponse(
        content=html,
        headers={
            "ngrok-skip-browser-warning": "true",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/assessment-bundle.js", response_class=FileResponse)
async def serve_assessment_bundle(request: Request):
    """
    Serve the assessment page JavaScript bundle.
    
    Built using `npm run build:assessment` in the frontend directory.
    Output: frontend/dist-assessment/assessment.js
    """
    bundle_path = _find_assessment_bundle()
    
    if bundle_path is None:
        logger.error(
            "Assessment bundle not found. Run 'cd frontend && npm run build:assessment' to build it. "
            f"Searched paths: {[str(p) for p in ASSESSMENT_PATHS]}"
        )
        return JSONResponse(
            status_code=404,
            content={
                "error": "assessment_not_built",
                "message": "Assessment bundle not found. Run 'npm run build:assessment' in the frontend directory.",
            },
        )
    
    return FileResponse(
        path=str(bundle_path),
        media_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            # no-cache: browser revalidates every request — picks up
            # rebuilt bundles immediately after deploy.
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "ngrok-skip-browser-warning": "true",
        },
    )


@router.get("/assessment")
async def assessment_page(request: Request):
    """
    Serve the full-page assessment form as a single self-contained HTML response.
    
    The entire React assessment bundle is INLINED into the HTML to eliminate a
    second network request. This is critical for ngrok/tunnel environments where
    each request can be intercepted by an interstitial page.
    
    Result: ONE request = HTML + CSS + JS. ~280KB raw, ~73KB gzipped.
    GZip compression is handled by the GZipMiddleware in main.py.
    
    Returns:
        Response: Self-contained HTML page with inlined JS assessment bundle
    """
    base_url = _get_external_base_url(request)
    
    # Read the assessment JS bundle (cached in memory after first read)
    bundle_js = _read_assessment_bundle()
    
    if bundle_js is None:
        logger.error(
            "Assessment bundle not found for inline serving. "
            "Run 'cd frontend && npm run build:assessment' to build it."
        )
        return HTMLResponse(
            content="<html><body><h1>Assessment Not Available</h1>"
                    "<p>The assessment form is being updated. Please try again shortly.</p></body></html>",
            status_code=503,
            headers={"ngrok-skip-browser-warning": "true"},
        )
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Free TMS Assessment — TMS Institute of Arizona</title>
    <meta name="description" content="Take a free 2-minute assessment to see if TMS therapy is right for you. HIPAA compliant and secure.">
    <meta name="robots" content="noindex, nofollow">
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            min-height: 100vh;
            background: #F8F9FA;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
            color: #1f2937;
        }}
        *, *::before, *::after {{ box-sizing: border-box; }}
        #assessment-root {{ min-height: 100vh; }}
    </style>
</head>
<body>
    <div id="assessment-root" data-api-url="{base_url}"></div>
    <script>{bundle_js}</script>
</body>
</html>"""
    
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "ngrok-skip-browser-warning": "true",
            "Access-Control-Allow-Origin": "*",
            # no-cache: browser must revalidate on every request — critical so
            # that a rebuild/deploy is picked up immediately instead of serving
            # stale HTML+JS for up to max-age seconds.
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
