"""Test WeChat QR code generation logic (mock, no network)."""

import base64
import io

import qrcode as qr_lib
from PIL import Image
from pyzbar.pyzbar import decode as decode_qr


def _make_qr_png(content: str) -> bytes:
    """Generate a valid QR PNG image encoding the given content."""
    qr = qr_lib.QRCode(border=2)
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_qrcode_png_roundtrip():
    """Generate QR PNG → decode it back → verify content matches."""
    url = "https://ilinkai.weixin.qq.com/bot/qr?token=abc123"
    png_bytes = _make_qr_png(url)

    # Decode with pyzbar (same as our CLI does)
    img = Image.open(io.BytesIO(png_bytes))
    results = decode_qr(img)
    assert len(results) == 1
    assert results[0].data.decode() == url


def test_terminal_qr_from_decoded_url():
    """Decode QR image → extract URL → render ASCII QR in terminal."""
    original_url = "https://ilinkai.weixin.qq.com/bot/qr?token=ef50696904"
    png_bytes = _make_qr_png(original_url)

    # Step 1: decode PNG to get URL (simulates _display_qr_in_terminal)
    img = Image.open(io.BytesIO(png_bytes))
    results = decode_qr(img)
    qr_url = results[0].data.decode()
    assert qr_url == original_url

    # Step 2: re-encode as ASCII QR for terminal display
    qr = qr_lib.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    ascii_art = buf.getvalue()

    assert len(ascii_art) > 100
    assert "\n" in ascii_art


def test_mock_ilink_api_response():
    """Simulate real iLink API response: {qrcode, qrcode_img_content, ret}."""
    # The API returns a base64-encoded PNG that contains the real scannable URL
    scannable_url = "https://ilinkai.weixin.qq.com/bot/qr?t=ef50696904e963d1"
    png_bytes = _make_qr_png(scannable_url)

    api_response = {
        "qrcode": "ef50696904e963d1367d27ab78bd9436",  # token for polling only
        "qrcode_img_content": base64.b64encode(png_bytes).decode(),
        "ret": 0,
    }

    # Extract fields
    qrcode_token = api_response["qrcode"]
    qrcode_img_b64 = api_response["qrcode_img_content"]

    # Decode the PNG image
    img_data = base64.b64decode(qrcode_img_b64)
    assert img_data[:4] == b"\x89PNG"

    # Extract the real URL from the QR image
    img = Image.open(io.BytesIO(img_data))
    results = decode_qr(img)
    assert len(results) == 1
    decoded_url = results[0].data.decode()
    assert decoded_url == scannable_url
    # The real URL is NOT the same as the polling token
    assert decoded_url != qrcode_token

    # Render the correct URL as terminal QR
    qr = qr_lib.QRCode(border=1)
    qr.add_data(decoded_url)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    assert len(buf.getvalue()) > 100


def test_base64_decode_and_save(tmp_path):
    """Verify we can save the decoded PNG to disk."""
    png_bytes = _make_qr_png("https://example.com/qr")
    b64 = base64.b64encode(png_bytes).decode()

    img_data = base64.b64decode(b64)
    qr_path = tmp_path / "qrcode.png"
    qr_path.write_bytes(img_data)

    assert qr_path.exists()
    assert qr_path.stat().st_size > 0

    # Verify it's a valid PNG we can re-decode
    results = decode_qr(Image.open(qr_path))
    assert results[0].data.decode() == "https://example.com/qr"
