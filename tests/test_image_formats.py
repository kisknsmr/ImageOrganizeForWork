"""
対応画像フォーマットの回帰テスト。

「宣言だけして実際には開けない形式」を作らないことを保証する。
（従来 .heic が宣言だけされており、取り込み後の解析で必ず失敗していた）
"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from src import image_formats
from src.config import config


def _sample_image(size=(64, 48)) -> Image.Image:
    """Laplacian が 0 にならないようディテールのある画像を作る。"""
    img = Image.new("RGB", size)
    for x in range(size[0]):
        for y in range(size[1]):
            img.putpixel((x, y), ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256))
    return img


class TestDeclaredExtensions(unittest.TestCase):
    def test_all_declared_extensions_are_openable(self):
        """宣言している拡張子はすべて Pillow が開けること"""
        image_formats.ensure_openers_registered()
        Image.init()
        openable = {
            ext.lower()
            for ext, fmt in Image.registered_extensions().items()
            if fmt in Image.OPEN
        }
        undecodable = sorted(set(config.IMAGE_EXTENSIONS) - openable)
        self.assertEqual(
            undecodable, [], f"開けないのに対応と宣言している形式がある: {undecodable}"
        )

    def test_common_photo_extensions_are_covered(self):
        """実運用で頻出する形式が漏れていないこと"""
        for ext in ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp', '.gif'):
            self.assertIn(ext, config.IMAGE_EXTENSIONS)

    def test_image_and_video_sets_do_not_overlap(self):
        """同じ拡張子が画像と動画の両方に属さないこと（分岐先が曖昧になる）"""
        overlap = set(config.IMAGE_EXTENSIONS) & set(config.VIDEO_EXTENSIONS)
        self.assertEqual(overlap, set(), f"画像/動画で重複: {sorted(overlap)}")

    def test_common_video_extensions_are_covered(self):
        # .ts / .m2ts はレコーダーやビデオカメラの録画で頻出する。
        # 拡張子が漏れると 03 Others へ振り分けられてしまう
        for ext in ('.mp4', '.mov', '.avi', '.mkv', '.m4v', '.ts', '.m2ts', '.mts'):
            self.assertIn(ext, config.VIDEO_EXTENSIONS)


class TestDecodeGrayscale(unittest.TestCase):
    def test_decodes_opencv_supported_format(self):
        buf = io.BytesIO()
        _sample_image().save(buf, format="PNG")
        img = image_formats.decode_grayscale(buf.getvalue(), "sample.png")
        self.assertIsNotNone(img)
        self.assertEqual(img.ndim, 2)

    def test_falls_back_to_pillow_for_heic(self):
        """OpenCV が読めない HEIC でも Pillow 経由でデコードできること"""
        if '.heic' not in config.IMAGE_EXTENSIONS:
            self.skipTest("pillow-heif が未導入のため HEIC は対象外")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.heic")
            _sample_image().save(path, format="HEIF")
            with open(path, "rb") as fp:
                data = fp.read()

        # OpenCV 単体では読めないことを確認してから、フォールバックを検証する
        import cv2
        self.assertIsNone(
            cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE),
            "OpenCV が HEIC を読めるならこのフォールバックの前提が変わっている",
        )

        img = image_formats.decode_grayscale(data, "s.heic")
        self.assertIsNotNone(img, "Pillow へのフォールバックが機能していない")
        self.assertEqual(img.ndim, 2)

    def test_returns_none_for_garbage(self):
        self.assertIsNone(image_formats.decode_grayscale(b"not an image", "x.jpg"))


if __name__ == '__main__':
    unittest.main()
