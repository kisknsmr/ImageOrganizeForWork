"""
ユーティリティモジュール
外部ライブラリに依存しない軽量なヘルパー関数を提供。
テストを高速に実行でき、cv2 / PyQt 等がなくても動作する。
"""
import os


def path_under_root(path: str, root: str) -> bool:
    """
    パスが指定ルートの直下またはそのサブディレクトリであるとき True。
    差分スキャンで「このスキャン対象ルートの下のパスか」を判定するために使用。
    - D:\\Photos\\a.jpg は D:\\Photos の下 → True
    - D:\\Photos2\\a.jpg は D:\\Photos の下ではない（別フォルダ）→ False
    """
    root_norm = os.path.normpath(root)
    root_prefix = os.path.normcase(root_norm + os.sep)
    root_norm_c = os.path.normcase(root_norm)
    p = os.path.normcase(os.path.normpath(path))
    return p == root_norm_c or p.startswith(root_prefix)


def format_eta(seconds: float) -> str:
    """
    残り時間をフォーマット（HH:MM:SS または MM:SS）
    """
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def hamming_dist(h1: int, h2: int) -> int:
    """
    ハミング距離を計算（2つのハッシュ値の違い）
    """
    return (h1 ^ h2).bit_count()


def format_file_size(size_bytes: int) -> str:
    """
    ファイルサイズを人間が読みやすい形式にフォーマット (例: "1.5 MB")
    """
    if size_bytes < 0:
        return "不明"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_file_size_kb(size_bytes: int) -> str:
    """
    ファイルサイズをKB表示に統一（小数点なし） (例: "1536 KB")
    """
    if size_bytes < 0:
        return "不明"
    kb = size_bytes / 1024.0
    return f"{int(kb)} KB"
