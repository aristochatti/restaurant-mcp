import runpy

from resto_mcp.carousel import build_carousel_html

data = runpy.run_path("tests/test_carousel.py")
html = build_carousel_html("Rome", data["SAMPLE"])

with open("/tmp/carousel-preview.html", "w", encoding="utf-8") as file:
    file.write(html)

print("Preview created at /tmp/carousel-preview.html")