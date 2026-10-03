"""Portable raster-only PDF fixture: page text is inside an image, not PDF text."""
import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader


def scan_pdf(pages=1):
    image = Image.new('RGB', (600, 800), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    for number, line in enumerate(['SMETRA SCAN TEST', 'PAINT WALLS 12 m2', 'TOTAL 1234.50 RUB']):
        draw.text((40, 80 + number * 90), line, fill='black', font=font)
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(600, 800))
    for _ in range(pages):
        canvas.drawImage(ImageReader(image), 0, 0, width=600, height=800)
        canvas.showPage()
    canvas.save()
    image.close()
    return output.getvalue()
