import math
import pathlib
from typing import Any, Optional

import cv2
import numpy as np


def find_start(UV, w: int, h: int):
    """UV座標から、アトラス化画像内にある各画像の左上の位置を取得

    Args:
        UV (np.ndarray): UV座標
        w (int): 横方向の画像サイズ
        h (int): 縦方向の画像サイズ

    Returns
        tuple[int, int]: 左上のピクセル座標
    """
    U_min = UV[:, 0].min()
    V_max = UV[:, 1].max()
    return math.floor((1 - V_max) * h), math.floor(U_min * w)


def find_end(UV, w: int, h: int):
    """UV座標から、アトラス化画像内にある各画像の右下の位置を取得

    Args:
        UV (np.ndarray): UV座標
        w (int): 横方向の画像サイズ
        h (int): 縦方向の画像サイズ

    Returns
        tuple[int, int]: 右下のピクセル座標
    """
    U_max = UV[:, 0].max()
    V_min = UV[:, 1].min()
    return math.ceil((1 - V_min) * h), math.ceil(U_max * w)


def write_wall_to_atlas(
    proj_img,
    dst_image,
    x_start: int,
    y_start: int,
):
    """画像をアトラス化画像に貼り付ける

    Args:
        proj_img (np.ndarray): 逆射影変換された画像
        dst_image (np.ndarray): 貼り付け先の画像データ(入力atlas化画像)
        x_start (int): 横方向のスタート位置
        y_start (int): 縦方向のスタート位置

    Returns
        np.ndarray: 貼り付け後の画像データ
    """
    h, w, _ = proj_img.shape
    if h == 1 and w == 1:
        result_image = dst_image.copy()
    else:
        result_image = dst_image.copy()
        result_image[y_start : y_start + h, x_start : x_start + w] = proj_img

    return result_image


def write_roof_to_atlas(
    src_image,
    dst_image,
    x_start: int,
    y_start: int,
    x_end: Optional[int] = None,
    y_end: Optional[int] = None,
):
    """屋根の画像をアトラス化画像に貼り付ける

    Args:
        src_image (np.ndarray): 入力atlas化画像
        dst_image (np.ndarray): 出力入力atlas化画像
        x_start (int): 横方向のスタート位置
        y_start (int): 縦方向のスタート位置
        x_end (int): 横方向の終了位置
        y_end (int): 縦方向の終了位置

    """

    result_image = dst_image.copy()
    result_image[y_start:y_end, x_start:x_end] = src_image[y_start:y_end, x_start:x_end]

    return result_image


class Put:
    """逆射影変換を施すクラス"""

    def __init__(
        self,
        seitaika_logs: list[dict[str, Any]],
        roof_infos: list[dict[str, Any]],
    ):
        self._seitaika_logs = seitaika_logs  # 正対化ログ

        self._new_w = None  # アトラス化画像の横方向のサイズ
        self._new_h = None  # アトラス化画像の縦方向のサイズ
        self._roof_infos = roof_infos  # 正対化ツールによる屋根の情報出力

        self._UVs = []  # 壁面画像のUV座標
        self._UVs_roof = []  # 屋根画像のUV座標

    def read_UVs(self):
        """
        logファイルから逆変換した画像UVを読み出す (texture)
        """
        for seitaika_log in self._seitaika_logs:
            UV = seitaika_log["texture"]
            self._UVs.append(np.array(UV))

    def read_UVs_roof(self):
        """
        logファイルから逆変換した画像UVを読み出す (texture)
        """
        for roof_info in self._roof_infos:
            UV = roof_info["texture"]
            self._UVs_roof.append(np.array(UV))

    def read_default_atlas(self):
        """
        入力のアトラス化画像のサイズ入手
        """
        self.atlas = pathlib.Path(self._seitaika_logs[0]["texture_file_path"])
        self._new_h = self._seitaika_logs[0]["h"]
        self._new_w = self._seitaika_logs[0]["w"]

        self.src_image = cv2.imread(str(self.atlas))
        self.result_image = self.src_image.copy()

    def write(self, i, proj_img):
        """
        元画像のUVsとHWから、ピクセルを割り出しマスクで足していく
        Args:
            output_dir: 新規作成するアトラス化した画像の出力先のディレクトリ
        """
        assert type(self._new_w) is int and type(self._new_h) is int
        assert self.atlas is not None

        w, h = self._new_w, self._new_h
        y, x = find_start(self._UVs[i], w, h)
        self.result_image = write_wall_to_atlas(proj_img, self.result_image, x, y)
