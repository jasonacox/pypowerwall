"""Transform utilities for serving and injecting content into static files.

This module provides utilities for:
- Serving static files with proper MIME type detection
- Injecting JavaScript into HTML content
"""
import os
from pathlib import Path
from typing import Optional, Tuple

from bs4 import BeautifulSoup


def get_static(web_root: str, fpath: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Get static file content and MIME type.
    
    Args:
        web_root: Root directory for static files
        fpath: Request path (e.g., "/index.html" or "/")
        
    Returns:
        Tuple of (file_content, mime_type) or (None, None) if not found
        
    Example:
        content, mime = get_static("/var/www", "/index.html")
        if content:
            return Response(content, media_type=mime)
    """
    if fpath.split("?")[0] == "/":
        fpath = "index.html"
    if fpath.startswith("/"):
        fpath = fpath[1:]
    
    freq = os.path.join(web_root, fpath)
    
    if os.path.exists(freq):
        # Determine content type
        if freq.lower().endswith(".js"):
            ftype = "application/javascript"
        elif freq.lower().endswith(".css"):
            ftype = "text/css"
        elif freq.lower().endswith(".png"):
            ftype = "image/png"
        elif freq.lower().endswith(".html"):
            ftype = "text/html"
        elif freq.lower().endswith(".otf"):
            ftype = "font/opentype"
        elif freq.lower().endswith(".woff"):
            ftype = "font/woff"
        elif freq.lower().endswith(".woff2"):
            ftype = "font/woff2"
        elif freq.lower().endswith(".ttf"):
            ftype = "font/ttf"
        elif freq.lower().endswith(".svg"):
            ftype = "image/svg+xml"
        elif freq.lower().endswith(".eot"):
            ftype = "application/vnd.ms-fontobject"
        elif freq.lower().endswith(".json"):
            ftype = "application/json"
        elif freq.lower().endswith(".xml"):
            ftype = "application/xml"
        else:
            ftype = "text/plain"
        
        with open(freq, "rb") as f:
            return f.read(), ftype
    
    return None, None


def inject_js(htmlsrc: str, *args: str) -> str:
    """Inject JavaScript files into HTML content.
    
    Appends <script> tags to the HTML body for each provided JavaScript path.
    
    Args:
        htmlsrc: HTML source content as string
        *args: JavaScript file paths to inject (e.g., "/static/viz-static/clear.js")
        
    Returns:
        Modified HTML with script tags appended to body
        
    Example:
        html = inject_js(html_content, "/static/app.js", "/static/utils.js")
    """
    soup = BeautifulSoup(htmlsrc, "html.parser")
    
    for fpath in args:
        script = soup.new_tag("script")
        script["type"] = "text/javascript"
        script["src"] = fpath
        soup.body.append(script)
    
    return str(soup)
