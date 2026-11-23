import logging
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class OcrProvider(ABC):
    @abstractmethod
    def ocr(self, image_path: str) -> str: ...


class NullOcrProvider(OcrProvider):
    def ocr(self, image_path: str) -> str:
        return ""


class EasyOcrProvider(OcrProvider):
    def __init__(self, languages: list[str]):
        import easyocr
        logger.info("EasyOCR 초기화 (languages=%s)", languages)
        self._reader = easyocr.Reader(languages, gpu=True)

    def ocr(self, image_path: str) -> str:
        results = self._reader.readtext(image_path, detail=0, paragraph=True)
        return "\n".join(str(r) for r in results)


_provider: OcrProvider | None = None


def get_ocr_provider() -> OcrProvider:
    """환경변수 OCR_PROVIDER 기반 lazy singleton 반환.

    OCR_PROVIDER=easyocr  → EasyOcrProvider (PyTorch 재사용, 추가 프레임워크 없음)
    OCR_PROVIDER=none     → NullOcrProvider (기본값, 스캔 페이지 텍스트 비어있음)

    향후 provider를 추가할 때는 이 함수에 분기만 추가한다.
    """
    global _provider
    if _provider is None:
        name = os.getenv("OCR_PROVIDER", "none").lower()
        if name == "easyocr":
            langs = [l.strip() for l in os.getenv("OCR_LANGUAGES", "ko,en").split(",")]
            _provider = EasyOcrProvider(languages=langs)
            logger.info("OCR provider: EasyOCR (languages=%s)", langs)
        else:
            _provider = NullOcrProvider()
            logger.debug("OCR provider: NullOcrProvider (OCR_PROVIDER=%s)", name)
    return _provider
