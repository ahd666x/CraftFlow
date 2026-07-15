from django import template
from django.utils.safestring import mark_safe
import qrcode
from io import BytesIO
import base64

register = template.Library()

@register.simple_tag
def load_barcode(barcode_text):
    """تولید QR Code از متن بارکد"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(barcode_text)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    image_data = base64.b64encode(buffer.read()).decode()
    return mark_safe(f'<img src="data:image/png;base64,{image_data}" alt="QR Code" />')

@register.inclusion_tag('barcode_css.html')
def barcode_css():
    return {}