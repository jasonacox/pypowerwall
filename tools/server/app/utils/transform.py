"""Transform utilities for serving and injecting content into static files."""
import os
from pathlib import Path
from bs4 import BeautifulSoup


def get_static(web_root: str, fpath: str):
    """Get static file content and type."""
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


def inject_js(htmlsrc, *args):
    """Inject JavaScript files into HTML content."""
    soup = BeautifulSoup(htmlsrc, "html.parser")
    
    for fpath in args:
        script = soup.new_tag("script")
        script["type"] = "text/javascript"
        script["src"] = fpath
        soup.body.append(script)
    
    return str(soup)
