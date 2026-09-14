"""Image preprocessing for PDF scan pages.

MVP configuration:
- DPI: 600 (high quality for legal documents)
- Binary Threshold: 140 (Otsu's method variant)
- Target: EasyOCR input

Per docs/pdf_processing_pipeline.md Section 6:
- Deskew / Rotate / Denoise
- Layout Detection preparation
- Table region preparation
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import numpy as np


class PreprocessMode(StrEnum):
    """Preprocessing quality modes."""

    FAST = "fast"  # Lower DPI, faster processing
    BALANCED = "balanced"  # 300 DPI
    QUALITY = "quality"  # 600 DPI (MVP default)


@dataclass
class PreprocessConfig:
    """Configuration for image preprocessing."""

    # DPI settings
    dpi: int = 600  # MVP default for legal documents
    scale_factor: float = 1.0  # Additional scaling

    # Threshold settings
    binary_threshold: int = 140  # MVP default for EasyOCR
    threshold_method: Literal["binary", "otsu", "adaptive"] = "binary"

    # Enhancement
    denoise: bool = True
    denoise_strength: int = 3  # cv2.fastNlMeansDenoising parameter
    sharpen: bool = True
    contrast_enhancement: float = 1.0  # 1.0 = no change

    # Layout prep
    deskew: bool = True
    deskew_threshold: float = 5.0  # degrees

    # Table processing
    enhance_tables: bool = True
    table_border_thickness: int = 2


class ImagePreprocessor:
    """Preprocessor for PDF page images before OCR.

    Optimized for:
    - Vietnamese legal documents
    - EasyOCR input
    - DPI 600 + Binary Threshold 140 (MVP)

    Usage:
        preprocessor = ImagePreprocessor(config=PreprocessConfig())
        processed = preprocessor.preprocess(image_array, page_num=1)
    """

    def __init__(self, config: PreprocessConfig | None = None):
        self.config = config or PreprocessConfig()
        self._import_optional_deps()

    def _import_optional_deps(self) -> None:
        """Import optional dependencies with fallbacks."""
        self._cv2_available = False
        self._skimage_available = False

        try:
            import cv2
            self.cv2 = cv2
            self._cv2_available = True
        except ImportError:
            pass

        try:
            import skimage
            self.skimage = skimage
            self._skimage_available = True
        except ImportError:
            pass

    def preprocess(
        self,
        image: np.ndarray,
        page_num: int = 1,
        mode: PreprocessMode = PreprocessMode.QUALITY,
    ) -> dict:
        """Preprocess a single page image.

        Args:
            image: Input image as numpy array (H, W, C) in BGR or RGB
            page_num: Page number for logging
            mode: Preprocessing quality mode

        Returns:
            Dictionary with:
                - 'image': preprocessed image
                - 'original': original image
                - 'metadata': processing metadata
        """
        config = self._get_config_for_mode(mode)
        self.config = config

        result = {
            "image": image.copy(),
            "original": image.copy(),
            "metadata": {
                "page_num": page_num,
                "mode": mode.value,
                "dpi": config.dpi,
                "threshold": config.binary_threshold,
                "operations": [],
            },
        }

        if not self._cv2_available:
            return result

        img = result["image"]

        # Skip processing for empty or invalid images
        if img is None or img.size == 0 or img.shape[0] == 0 or img.shape[1] == 0:
            return result

        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        result["metadata"]["operations"].append("grayscale")

        # Denoise
        if config.denoise and self._skimage_available:
            gray = self._denoise_image(gray, config.denoise_strength)
            result["metadata"]["operations"].append("denoise")

        # Deskew
        if config.deskew:
            angle, gray = self._deskew_image(gray, config.deskew_threshold)
            if angle != 0:
                result["metadata"]["operations"].append(f"deskew({angle:.1f}°)")

        # Contrast enhancement
        if config.contrast_enhancement != 1.0:
            gray = self._enhance_contrast(gray, config.contrast_enhancement)
            result["metadata"]["operations"].append("contrast")

        # Sharpen
        if config.sharpen:
            gray = self._sharpen_image(gray)
            result["metadata"]["operations"].append("sharpen")

        # Binary threshold (MVP choice)
        binary = self._apply_threshold(gray, config)
        result["metadata"]["operations"].append(f"threshold({config.threshold_method})")

        # Convert back to BGR for EasyOCR (which expects 3-channel)
        if len(img.shape) == 3:
            result["image"] = self.cv2.cvtColor(binary, self.cv2.COLOR_GRAY2BGR)
        else:
            result["image"] = binary

        # Table enhancement
        if config.enhance_tables:
            result["image"] = self._enhance_tables(result["image"], config.table_border_thickness)
            result["metadata"]["operations"].append("table_enhance")

        return result

    def _get_config_for_mode(self, mode: PreprocessMode) -> PreprocessConfig:
        """Get config preset for processing mode."""
        configs = {
            PreprocessMode.FAST: PreprocessConfig(dpi=200, binary_threshold=140),
            PreprocessMode.BALANCED: PreprocessConfig(dpi=300, binary_threshold=140),
            PreprocessMode.QUALITY: PreprocessConfig(dpi=600, binary_threshold=140),
        }
        return configs.get(mode, configs[PreprocessMode.QUALITY])

    def _denoise_image(self, img: np.ndarray, strength: int) -> np.ndarray:
        """Apply non-local means denoising."""
        if not self._cv2_available:
            return img
        # Skip if image is empty
        if img.size == 0 or img.shape[0] < 5 or img.shape[1] < 5:
            return img
        return self.cv2.fastNlMeansDenoising(img, h=strength)

    def _deskew_image(self, img: np.ndarray, threshold_deg: float) -> tuple[float, np.ndarray]:
        """Detect and correct skew angle."""
        if not self._cv2_available:
            return 0.0, img

        # Use probability Hough line transform
        edges = self.cv2.Canny(img, 50, 150)
        lines = self.cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=100,
            minLineLength=100,
            maxLineGap=10,
        )

        if lines is None or len(lines) == 0:
            return 0.0, img

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Normalize angle
            if angle > 45:
                angle -= 90
            elif angle < -45:
                angle += 90
            angles.append(angle)

        median_angle = np.median(angles)

        if abs(median_angle) < threshold_deg:
            return 0.0, img

        # Rotate image
        h, w = img.shape
        center = (w // 2, h // 2)
        M = self.cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = self.cv2.warpAffine(img, M, (w, h), borderValue=255)

        return float(median_angle), rotated

    def _enhance_contrast(self, img: np.ndarray, factor: float) -> np.ndarray:
        """Enhance image contrast."""
        if not self._cv2_available:
            return img
        # Apply gamma correction
        lookup_table = np.array(
            [min(255, int(((i / 255.0) ** (1.0 / factor)) * 255)) for i in range(256)],
            dtype=np.uint8,
        )
        return self.cv2.LUT(img, lookup_table)

    def _sharpen_image(self, img: np.ndarray) -> np.ndarray:
        """Sharpen image using unsharp masking."""
        if not self._cv2_available:
            return img
        # Skip if image is empty or too small
        if img.size == 0 or img.shape[0] < 3 or img.shape[1] < 3:
            return img
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return self.cv2.filter2D(img, -1, kernel)

    def _apply_threshold(self, img: np.ndarray, config: PreprocessConfig) -> np.ndarray:
        """Apply binary thresholding."""
        if not self._cv2_available:
            return img

        method_map = {
            "binary": self.cv2.THRESH_BINARY,
            "otsu": self.cv2.THRESH_BINARY + self.cv2.THRESH_OTSU,
            "adaptive": None,
        }

        method = method_map.get(config.threshold_method, self.cv2.THRESH_BINARY)

        if config.threshold_method == "adaptive":
            # Adaptive threshold for varying illumination
            return self.cv2.adaptiveThreshold(
                img,
                255,
                self.cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                self.cv2.THRESH_BINARY,
                11,
                config.binary_threshold - 80,
            )

        _, binary = self.cv2.threshold(img, config.binary_threshold, 255, method)
        return binary

    def _enhance_tables(self, img: np.ndarray, thickness: int) -> np.ndarray:
        """Enhance table borders for better structure recognition."""
        if not self._cv2_available:
            return img

        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # Skip if image is empty or too small
        if gray.size == 0 or gray.shape[0] < 10 or gray.shape[1] < 10:
            return img

        # Detect edges
        edges = self.cv2.Canny(gray, 50, 150)

        # Dilate to connect broken lines
        kernel = np.ones((3, 3), np.uint8)
        dilated = self.cv2.dilate(edges, kernel, iterations=1)

        # Apply morphology to strengthen horizontal and vertical lines
        horizontal_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (25, 1))
        vertical_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (1, 25))

        horizontal_lines = self.cv2.morphologyEx(dilated, self.cv2.MORPH_OPEN, horizontal_kernel)
        vertical_lines = self.cv2.morphologyEx(dilated, self.cv2.MORPH_OPEN, vertical_kernel)

        # Combine with original - ensure same type and channels
        if len(img.shape) == 3:
            # Convert lines to 3-channel and ensure same size
            h_lines_3ch = self.cv2.cvtColor(horizontal_lines, self.cv2.COLOR_GRAY2BGR)
            v_lines_3ch = self.cv2.cvtColor(vertical_lines, self.cv2.COLOR_GRAY2BGR)
            combined = self.cv2.add(img, h_lines_3ch)
            combined = self.cv2.add(combined, v_lines_3ch)
        else:
            combined = self.cv2.add(gray, horizontal_lines)
            combined = self.cv2.add(combined, vertical_lines)

        return combined

    def preprocess_batch(
        self,
        images: list[np.ndarray],
        mode: PreprocessMode = PreprocessMode.QUALITY,
    ) -> list[dict]:
        """Preprocess multiple images.

        Args:
            images: List of images as numpy arrays
            mode: Preprocessing quality mode

        Returns:
            List of preprocessing results
        """
        return [self.preprocess(img, page_num=i + 1, mode=mode) for i, img in enumerate(images)]

    def get_effective_dpi(self, original_dpi: int | None = None) -> int:
        """Calculate effective DPI after preprocessing."""
        if original_dpi is None:
            return self.config.dpi
        return int(original_dpi * self.config.scale_factor)
