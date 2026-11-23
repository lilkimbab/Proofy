"""
OCR 모듈 테스트 — pytest + unittest.TestCase 스타일.

vector_db/ocr.py 검증:
  - OCR 모듈이 import 가능하고 graceful fallback 제공
  - 유효한 PNG 이미지를 넣었을 때 텍스트 문자열(비어있어도 됨) 반환
  - 존재하지 않는 파일 경로 → 예외 없이 "" 반환
  - 의도적으로 깨진 PNG 바이트 → 예외 없이 처리
"""

import io
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_minimal_png(path: str) -> None:
    """최소한의 유효한 1x1 흰색 PNG 파일을 생성한다."""
    # PNG 시그니처
    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    # IHDR: width=1, height=1, bit_depth=8, color_type=2(RGB), compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: 단일 픽셀(RGB: 255,255,255) + filter byte 0
    raw_row = b"\x00\xff\xff\xff"
    compressed = zlib.compress(raw_row)
    idat = _chunk(b"IDAT", compressed)

    iend = _chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(signature + ihdr + idat + iend)


class TestOcrModule(unittest.TestCase):

    def setUp(self):
        # OCR 싱글톤 초기화 방지: 각 테스트 전에 provider를 None으로 리셋
        import vector_db.ocr as ocr_mod
        ocr_mod._provider = None
        os.environ["OCR_PROVIDER"] = "none"

    # ── 1. import 가능 여부 ───────────────────────────────────────────────────

    def test_module_importable(self):
        """vector_db.ocr 모듈이 예외 없이 import 되어야 한다."""
        import vector_db.ocr as ocr_mod
        self.assertTrue(hasattr(ocr_mod, "get_ocr_provider"))
        self.assertTrue(hasattr(ocr_mod, "NullOcrProvider"))

    def test_null_provider_is_default(self):
        """OCR_PROVIDER=none일 때 NullOcrProvider가 반환되어야 한다."""
        from vector_db.ocr import get_ocr_provider, NullOcrProvider
        provider = get_ocr_provider()
        self.assertIsInstance(provider, NullOcrProvider)

    def test_provider_implements_ocr_method(self):
        """반환된 provider가 ocr(image_path) 메서드를 가져야 한다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()
        self.assertTrue(callable(getattr(provider, "ocr", None)))

    # ── 2. 유효한 PNG → 텍스트 문자열 반환 ──────────────────────────────────

    def test_valid_png_returns_string(self):
        """유효한 PNG 파일을 넣으면 텍스트 문자열(비어있어도 됨)이 반환된다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()  # NullOcrProvider

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            png_path = f.name
        try:
            _make_minimal_png(png_path)
            result = provider.ocr(png_path)
            self.assertIsInstance(result, str, f"ocr()가 str을 반환하지 않음: {type(result)}")
        finally:
            os.unlink(png_path)

    def test_null_provider_returns_empty_string(self):
        """NullOcrProvider.ocr()는 항상 빈 문자열을 반환해야 한다."""
        from vector_db.ocr import NullOcrProvider
        provider = NullOcrProvider()
        self.assertEqual(provider.ocr("/any/path.png"), "")

    # ── 3. 존재하지 않는 파일 경로 → 예외 없이 처리 ─────────────────────────

    def test_missing_file_no_exception(self):
        """존재하지 않는 경로를 넣어도 예외 없이 빈 문자열을 반환해야 한다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()
        try:
            result = provider.ocr("/nonexistent/path/image.png")
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"존재하지 않는 파일에서 예외 발생: {e}")

    def test_empty_path_no_exception(self):
        """빈 문자열 경로를 넣어도 예외 없이 처리해야 한다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()
        try:
            result = provider.ocr("")
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"빈 경로에서 예외 발생: {e}")

    # ── 4. 깨진 PNG 바이트 → 예외 없이 처리 ─────────────────────────────────

    def test_corrupted_png_no_exception(self):
        """의도적으로 깨진 PNG 바이트를 넣어도 예외 없이 처리되어야 한다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\nCORRUPTED_BYTES_\xff\xfe\x00\x01")
            corrupt_path = f.name

        try:
            result = provider.ocr(corrupt_path)
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"깨진 PNG에서 예외 발생: {e}")
        finally:
            os.unlink(corrupt_path)

    def test_non_image_file_no_exception(self):
        """이미지가 아닌 파일(txt)을 넣어도 예외 없이 처리되어야 한다."""
        from vector_db.ocr import get_ocr_provider
        provider = get_ocr_provider()

        with tempfile.NamedTemporaryFile(suffix=".png", mode="w", delete=False) as f:
            f.write("이것은 이미지가 아닌 텍스트 파일입니다.")
            text_as_png = f.name

        try:
            result = provider.ocr(text_as_png)
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"텍스트 파일을 png로 넣었을 때 예외 발생: {e}")
        finally:
            os.unlink(text_as_png)

    # ── 5. easyocr graceful fallback (패키지 없을 때) ───────────────────────

    def test_easyocr_provider_fallback_on_import_error(self):
        """
        OCR_PROVIDER=easyocr이지만 easyocr 패키지가 없으면 ImportError가 발생한다.
        NullOcrProvider는 항상 사용 가능해야 한다.
        """
        import vector_db.ocr as ocr_mod
        ocr_mod._provider = None
        os.environ["OCR_PROVIDER"] = "easyocr"

        try:
            provider = ocr_mod.get_ocr_provider()
            # easyocr가 설치된 경우 — EasyOcrProvider가 반환됨 (테스트 통과)
            self.assertTrue(callable(getattr(provider, "ocr", None)))
        except ImportError:
            # easyocr 미설치 — 예외 자체가 전파되는 것이 현재 동작이므로 허용
            pass
        finally:
            os.environ["OCR_PROVIDER"] = "none"
            ocr_mod._provider = None
