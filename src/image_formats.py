"""
対応画像フォーマットの決定。

方針は「**実際に開ける形式だけを対応と宣言する**」。
宣言だけして開けない形式があると、スキャンで DB に取り込まれた後の解析や
サムネイル生成で必ず失敗する（従来の .heic がこの状態だった）。

そのため拡張子リストは固定値ではなく、起動時に Pillow へ問い合わせて組み立てる。
"""
import logging
from typing import FrozenSet

logger = logging.getLogger(__name__)


#: 写真整理として意味のある候補。ここに挙げたもののうち、
#: 実際に Pillow が開けるものだけが最終的な対応リストに残る。
#:
#: 意図的に除外しているもの:
#:   - ベクタ/文書系（.eps .ps .wmf .emf .pdf）— 写真ではなく、ラスタ化に外部依存が要る
#:   - 科学データ系（.fits .grib .bufr .h5 .hdf）— 誤検出でライブラリが汚れる
#:   - アイコン/ゲームテクスチャ系（.ico .cur .icns .dds .blp .ftc）— 写真ではない
_CANDIDATE_IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({
    # JPEG 系（.jfif/.jpe はメールやブラウザ保存で普通に出てくる）
    '.jpg', '.jpeg', '.jpe', '.jfif',
    # PNG 系
    '.png', '.apng',
    # 近年のカメラ・スマホ・Web
    '.webp', '.avif', '.avifs', '.heic', '.heif', '.hif',
    # スキャン・入稿・業務データ
    '.tif', '.tiff', '.psd',
    # 一般的なラスタ
    '.bmp', '.dib', '.gif',
    # JPEG 2000
    '.jp2', '.j2k', '.jpf', '.jpx', '.j2c', '.jpc',
    # 古めだが実データで遭遇しうるもの
    '.tga', '.pcx', '.ppm', '.pgm', '.pbm', '.pnm', '.sgi', '.qoi',
})


#: 動画は OpenCV(FFMPEG バックエンド) が読む。拡張子から可否を静的に判定できないため、
#: FFMPEG が一般に扱えるコンテナを列挙する。
#: 注意:
#:   - .mpg/.mpeg は Pillow にも MPEG プラグインとして登録されているが、
#:     フレームを取り出せるのは OpenCV 側なので画像側には入れない。
#:   - .ts は TypeScript のソースと拡張子が衝突するが、本アプリはメディア整理が
#:     目的なので MPEG-TS（レコーダー/カメラの録画）として扱う。
VIDEO_EXTENSIONS: FrozenSet[str] = frozenset({
    '.mp4', '.mov', '.m4v', '.avi', '.mkv', '.wmv', '.webm',
    '.mpg', '.mpeg', '.mts', '.m2ts', '.3gp', '.3g2', '.flv',
    # MPEG-TS 系（デジタル放送の録画、ビデオカメラの分割ファイル）
    '.ts', '.m2t',
    # DVD-Video / Windows Media
    '.vob', '.asf',
})


_openers_registered = False


def ensure_openers_registered() -> None:
    """
    Pillow に標準で入っていないオープナーを登録する（冪等）。

    未導入でも致命的ではない（その形式が対応リストから外れるだけ）ので、
    ImportError は握りつぶして情報ログに留める。
    """
    global _openers_registered
    if _openers_registered:
        return
    _openers_registered = True

    try:
        import pillow_heif
    except ImportError:
        logger.info(
            "pillow-heif が未導入のため HEIC/HEIF は対象外になります。"
            "iPhone の写真を扱う場合は `pip install pillow-heif` を実行してください。"
        )
        return

    try:
        pillow_heif.register_heif_opener()
    except Exception as exc:  # 環境依存の初期化失敗も対象外扱いに留める
        logger.warning("pillow-heif の初期化に失敗しました: %s", exc)


def decode_grayscale(data: bytes, path_for_log: str = ""):
    """
    画像バイト列をグレースケールの numpy 配列にする（読めなければ None）。

    OpenCV は HEIC / AVIF / PSD などを読めない。imdecode の失敗を戻り値 None で
    済ませていたため、これらの形式はブレ判定・pHash から無言で除外され、
    「一覧には出るが重複・類似・ブレ検出に一切かからない」状態になっていた。
    imdecode が失敗したら Pillow で開き直す。

    cv2 / numpy / PIL は呼び出し時に import する（config 経由で全モジュールが
    このモジュールを読み込むため、起動コストを上げない）。
    """
    import io

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is not None:
        return img

    ensure_openers_registered()
    try:
        with Image.open(io.BytesIO(data)) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            return np.array(pil_img.convert("L"))
    except Exception as exc:
        logger.warning("画像をデコードできませんでした (%s): %s", path_for_log, exc)
        return None


def resolve_image_extensions() -> FrozenSet[str]:
    """候補のうち、この環境の Pillow が実際に開ける拡張子だけを返す。"""
    from PIL import Image

    ensure_openers_registered()
    Image.init()

    openable = {
        ext.lower()
        for ext, fmt in Image.registered_extensions().items()
        if fmt in Image.OPEN
    }
    supported = frozenset(_CANDIDATE_IMAGE_EXTENSIONS & openable)

    missing = _CANDIDATE_IMAGE_EXTENSIONS - openable
    if missing:
        logger.info("この環境で開けないため対象外: %s", ' '.join(sorted(missing)))

    return supported
