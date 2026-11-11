import random
import string
import qrcode
import io
import base64
from cachetools import TTLCache

# Base62 alphabet
ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

# Simple in-memory cache: short_code -> original_url
# maxsize=1000 entries, ttl=300 seconds (5 min) before re-checking DB
redirect_cache = TTLCache(maxsize=1000, ttl=300)


def generate_short_code(length: int = 6) -> str:
    """Generate a random Base62 short code."""
    return "".join(random.choices(ALPHABET, k=length))


def generate_qr_code_base64(url: str) -> str:
    """Generate a QR code for a URL and return it as a base64 data URI."""
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
