import datetime
import json
import os
from enum import IntEnum
from typing import Union


class ParamManager:
    """パラメータファイル管理クラス"""

    class RotateMatrixMode(IntEnum):
        """外部標定要素から算出する回転行列のモード"""

        XYZ = 0
        """R = Rx(ω)Ry(Φ)Rz(κ)
            """
        ZYX = 1
        """R = Rz(κ)Ry(Φ)Rx(ω)
            """

    TEXTURE_OUTPUT_WIDTH_MAX = 4096
    TEXTURE_OUTPUT_HEIGHT_MAX = 4096

    # デバッグログ設定のデフォルト値
    DEFAULT_DEBUG_LOG_OUTPUT = False
    # 位相一貫補正のデフォルト値
    DEFAULT_PHASE_CONSISTENCY_DELETE_ERROR_OBJECT = False
    # objファイル出力のデフォルト値
    DEFAULT_OUTPUT_OBJ = True
    # LASのXY座標swapフラグ
    DEFAULT_LAS_SWAP_XY = False
    DEFAULT_TEXTURE_IMAGE_FORMAT = "png"

    def __init__(self) -> None:
        """コンストラクタ"""
        self.texture_folder_path: str = ""  # テクスチャフォルダパス
        self.ex_calib_element_path: str = ""  # 外部標定要素ファイルパス
        self.camera_info_path: str = ""  # 内部標定要素ファイルパス
        self.output_folder_path: str = ""  # CityGML出力フォルダパス
        self.output_log_folder_path: str = ""  # ログ出力先
        # デバッグログ出力フラグ
        self.debug_log_output: bool = ParamManager.DEFAULT_DEBUG_LOG_OUTPUT
        # 位相一貫性検査エラー時OBJ削除フラグ
        self.delete_error_flag: bool = (
            ParamManager.DEFAULT_PHASE_CONSISTENCY_DELETE_ERROR_OBJECT
        )
        self.output_obj: bool = ParamManager.DEFAULT_OUTPUT_OBJ  # obj出力フラグ
        # lasのxy座標のswapフラグ
        self.las_swap_xy: bool = ParamManager.DEFAULT_LAS_SWAP_XY
        # 外部標定要素から算出する回転行列のモード
        self.rotate_matrix_mode: ParamManager.RotateMatrixMode = (
            ParamManager.RotateMatrixMode.XYZ
        )
        # テクスチャー横幅最大値(4096まで設定可)
        self.texture_output_width_max: int = ParamManager.TEXTURE_OUTPUT_WIDTH_MAX
        # テクスチャー縦幅最大値(4096まで設定可)
        self.texture_output_height_max: int = ParamManager.TEXTURE_OUTPUT_HEIGHT_MAX
        self.texture_image_format: str = ParamManager.DEFAULT_TEXTURE_IMAGE_FORMAT

        # 作業用パラメータ
        self.time = datetime.datetime.now()  # 処理開始時刻
