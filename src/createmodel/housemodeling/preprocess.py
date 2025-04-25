import os
from typing import Final, Optional
import math

import numpy as np
import numpy.typing as npt
from PIL import Image
import shapely.geometry as geo
from shapely.geometry import Point
from sklearn.neighbors import NearestNeighbors

from .roof_layer_info import RoofLayerInfo
from ..lasmanager import PointCloud
from ...util.log import Log, LogLevel, ModuleType


class Preprocess:
    """前処理クラス"""

    NO_POINT = -1
    NOISE_POINT = -2

    _grid_size: Final[float]
    _image_size: Final[int]
    _expand_rate: Final[float]

    def __init__(
        self,
        grid_size: float,
        image_size: int,
        expand_rate: Optional[float] = None,
        building_id: Optional[str] = None,
    ) -> None:
        """コンストラクタ

        Args:
            grid_size(float): 点群の間隔(meter)
            image_size(int): 出力する画像のサイズ(pixel)
            expand_rate(float, optional): 画像の拡大率 (Default: 1)
        """

        self._grid_size = grid_size
        self._image_size = image_size
        self._expand_rate = expand_rate if expand_rate is not None else 1.0
        self._building_id = building_id

        """コンストラクタ
      """
        self._XYZ = "xyz"
        self._RGB = "rgb"
        self._IND = "ind"

    def preprocess(
        self,
        cloud: PointCloud,
        ground_height: float,
        footprint: geo.Polygon,
        debug_mode: bool = False,
    ) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.uint8], RoofLayerInfo]:
        """前処理

        点群から機械学習モデルへの入力用の画像を作成する

        Args:
          cloud(PointCloud): 建物点群
          ground_height (float): 地面の高さm
          footprint(geo.Polygon): 建物外形ポリゴン
          debug_mode (bool, optional): デバッグモード (Default: False)

        Returns:
          NDArray[np.uint8]: (image_size, image_size, 3)のRGB画像データ
          NDArray[np.uint8]: (image_size, image_size)の高さのグレースケール画像データ
          RoofLayerInfo: 壁線で点群クラスタリングした、屋根のレイヤー情報
        """

        # 屋根線検出、バルコニー検出用の画像を作成
        pc_xyz = cloud.get_points().copy()
        pc_rgb = cloud.get_colors().copy()

        pc_x_min, pc_y_min, _ = pc_xyz.min(axis=0)
        pc_x_max, pc_y_max, _ = pc_xyz.max(axis=0)

        width = math.ceil((pc_x_max - pc_x_min) / self._grid_size) + 1
        height = math.ceil((pc_y_max - pc_y_min) / self._grid_size) + 1

        xs = np.arange(width) * self._grid_size + pc_x_min
        ys = -np.arange(height) * self._grid_size + pc_y_max
        xx, yy = np.meshgrid(xs, ys)
        xy = np.dstack([xx, yy]).reshape(-1, 2)

        nn = NearestNeighbors(
            n_neighbors=1, algorithm="kd_tree", leaf_size=30, n_jobs=4
        )
        nn.fit(pc_xyz[:, 0:2])
        inds = nn.kneighbors(xy, return_distance=False)[:, 0]

        origin_dsm_grid_xyzs = pc_xyz[inds]
        masked_dsm_grid_xyzs = pc_xyz[inds]
        masked_dsm_grid_rgbs = pc_rgb[inds] / 256

        lower, upper = ground_height - 5, ground_height + 25
        masked_depth_image = (
            (np.clip(pc_xyz[:, 2][inds], lower, upper) - lower) / (upper - lower) * 255
        )

        for i, (x, y) in enumerate(xy):
            p = Point(x, y)
            if not footprint.contains(p):
                masked_dsm_grid_xyzs[i] = 0
                masked_dsm_grid_rgbs[i] = 255
                masked_depth_image[i] = 255

        origin_dsm_grid_xyzs = origin_dsm_grid_xyzs.reshape(height, width, 3).astype(
            np.float_
        )
        masked_dsm_grid_xyzs = masked_dsm_grid_xyzs.reshape(height, width, 3).astype(
            np.float_
        )
        masked_dsm_grid_rgbs = masked_dsm_grid_rgbs.reshape(height, width, 3).astype(
            np.uint8
        )
        masked_depth_image = masked_depth_image.reshape(height, width).astype(np.uint8)

        debug_dir = os.path.join("debug", self._building_id)
        roof_layer_info = RoofLayerInfo(
            origin_dsm_grid_xyzs=origin_dsm_grid_xyzs,
            masked_dsm_grid_xyzs=masked_dsm_grid_xyzs,
            masked_dsm_grid_rgbs=masked_dsm_grid_rgbs,
            debug_dir=debug_dir,
            debug_mode=debug_mode,
        )

        # 画像を拡大
        if self._expand_rate != 1:
            expanded_size = (
                round(width * self._expand_rate),
                round(height * self._expand_rate),
            )
            heat_dsm_grid_rgbs = np.array(
                Image.fromarray(masked_dsm_grid_rgbs).resize(expanded_size),
                dtype=np.uint8,
            )
            heat_depth_image = np.array(
                Image.fromarray(masked_depth_image, "L").resize(expanded_size),
                dtype=np.uint8,
            )
            expanded_width, expanded_height = expanded_size
        else:
            heat_dsm_grid_rgbs = masked_dsm_grid_rgbs
            heat_depth_image = masked_depth_image
            expanded_width = width
            expanded_height = height

        # モデル入力用の正方形画像に変換(余白は白で埋める)
        square_heat_dsm_grid_rgbs = np.full(
            (self._image_size, self._image_size, 3), 255, dtype=np.uint8
        )
        square_heat_depth_image = np.full(
            (self._image_size, self._image_size), 255, dtype=np.uint8
        )

        top = (self._image_size - expanded_height) // 2
        if top >= 0:
            s_top = 0
            s_top_end = expanded_height
            top_end = top + expanded_height
        else:
            # 上下にはみ出す
            # はみ出す時点で続ける意味があるかわからない
            Log.output_log_write(
                LogLevel.WARN,
                ModuleType.MODEL_ELEMENT_GENERATION,
                f"建物の上下幅({expanded_height})が屋根線取得処理の入力サイズ({self._image_size})を超えています: {self._building_id}",
            )
            s_top = -top
            s_top_end = s_top + self._image_size
            top = 0
            top_end = self._image_size

        left = (self._image_size - expanded_width) // 2
        if left >= 0:
            s_left = 0
            s_left_end = expanded_width
            left_end = left + expanded_width
        else:
            # 左右にはみ出す
            # はみ出す時点で続ける意味があるかわからない
            Log.output_log_write(
                LogLevel.WARN,
                ModuleType.MODEL_ELEMENT_GENERATION,
                f"建物の左右幅({expanded_width})が屋根線取得処理の入力サイズ({self._image_size})を超えています: {self._building_id}",
            )
            s_left = -left
            s_left_end = s_left + self._image_size
            left = 0
            left_end = self._image_size

        square_heat_dsm_grid_rgbs[top:top_end, left:left_end] = heat_dsm_grid_rgbs[
            s_top:s_top_end, s_left:s_left_end
        ]
        square_heat_depth_image[top:top_end, left:left_end] = heat_depth_image[
            s_top:s_top_end, s_left:s_left_end
        ]

        return square_heat_dsm_grid_rgbs, square_heat_depth_image, roof_layer_info
