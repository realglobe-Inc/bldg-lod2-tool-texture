import traceback
from collections import UserList
from pathlib import Path
from typing import Iterable

import alphashape
import numpy as np
from numpy.typing import NDArray
from shapely import Polygon

from .geo_util import GeoUtil
from ..las_manager import PointCloud


class ClusterInfo(object):
    """点群と推定面を管理するデータクラス"""

    @property
    def id(self) -> int:
        """id

        Returns:
            int: id
        """
        return self._id

    @id.setter
    def id(self, value: int):
        """id

        Args:
            value (int): id
        """
        self._id = value

    @property
    def points(self) -> PointCloud:
        """点群データ

        Returns:
            PointCloud: 点群データ
        """
        return self._points

    @points.setter
    def points(self, value: PointCloud):
        """点群データ

        Args:
            value (PointCloud): 点群データ
        """
        self._points = value

    @property
    def roof_polygon(self) -> Polygon:
        """屋根形状

        Returns:
            Polygon: 屋根形状
        """
        if self._roof_line is not None:
            return Polygon(self._roof_line)
        else:
            return None

    @property
    def parent(self) -> int:
        """親屋根id

        Returns:
            int: 親屋根id

        Node:
            -1の場合は親屋根なし
        """
        return self._parent

    @parent.setter
    def parent(self, value: int):
        """親屋根id

        Args:
            value (int): 親屋根id

        Node:
            -1の場合は親屋根なし
        """
        self._parent = value

    @property
    def children(self) -> list[int]:
        """子屋根リスト

        Returns:
            list[int]: 子屋根idリスト
        """
        return self._children

    @children.setter
    def children(self, value: list[int]):
        """子屋根リスト

        Args:
            value (list[int]): 子屋根idリスト
        """
        self._children = value

    @property
    def roof_height(self) -> float:
        """屋根の高さ

        Returns:
            float: 屋根の高さ
        """
        return self._roof_height

    @roof_height.setter
    def roof_height(self, value: float):
        """屋根の高さ

        Args:
            value (float): 屋根の高さ
        """
        self._roof_height = value

    @property
    def roof_line(self) -> NDArray:
        """2D屋根の形状の頂点座標列(終点は始点と異なる座標)

        Returns:
            NDArray: 2D屋根の形状の頂点座標列(終点は始点と異なる座標)
        """
        return self._roof_line

    @roof_line.setter
    def roof_line(self, value: NDArray):
        """2D屋根の形状の頂点座標列(終点は始点と異なる座標)

        Args:
            value (NDArray): 2D屋根の形状の頂点座標列(終点は始点と異なる座標)
        """
        self._roof_line = value

    def __init__(self, id=None, points=None) -> None:
        """コンストラクタ

        Args:
            id (int, optional): id. Defaults to None.
            points (PointCloud, optional): 点群. Defaults to None.
        """
        self._id = 0 if id is None else id
        self._points = PointCloud()
        if points is not None:
            self._points = points

        self._roof_polygon = None
        self._parent = -1
        self._children = []
        self._roof_height = 0
        self._roof_line = None

    def __lt__(self, other):
        """ソート関数

        Args:
            other (ClusterInfo): 比較対象

        Returns:
            bool: 比較結果
        """
        self_pt = len(self.points.get_points())
        other_pt = len(other.points.get_points())
        return self_pt < other_pt

    def __repr__(self):
        """オブジェクトを表す公式な文字列の作成

        Returns:
            str: 文字列
        """
        return repr(
            (
                self.id,
                self.points,
                self.roof_polygon,
                self.parent,
                self.children,
                self.roof_height,
            )
        )

    def get_contours(self) -> list[Polygon]:
        """点群のalpha shape形状を取得する

        Returns:
            list[Polygon]: ポリゴンのリスト
        """
        list = []
        try:
            if len(self._points.get_points()) > 0:
                geom = alphashape.alphashape(
                    self._points.get_points()[:, 0:2], alpha=2.0
                )
                separate_geoms = GeoUtil.separate_geometry(geom)
                list = [
                    poly
                    for poly in separate_geoms
                    if (type(poly) is Polygon and poly.area > 0)
                ]
        except Exception:
            traceback.print_exc()
            pass

        return list

    def save_debug_image(
        self,
        output_file_path: Path,
        grid_size: float,
        canvas_size: tuple[int, int] = None,
        offset_xy: tuple[float, float] = None,
    ) -> tuple[tuple[int, int], tuple[float, float], PointCloud]:
        """
        点群クラスタのデバッグ画像を生成し、保存する。

        :param output_file_path: 画像を保存するパス。
        :param grid_size: 画像の1ピクセルの幅に相当する座標系上の距離。
        :param canvas_size: 画像のサイズ。指定しない場合、点群クラスタの座標範囲とgrid_sizeに基づいて計算される。
        :param offset_xy: 画像の始点に合わせる座標。指定しない場合、点群クラスタの座標範囲の始点が利用される。
        :return: 画像サイズと画像の始点に合わせる座標とクラスタリングされた点群。
        """
        hash_val = hash(str(self.id))
        color = [
            (hash_val & 0xFF0000) >> 16,
            (hash_val & 0x00FF00) >> 8,
            hash_val & 0x0000FF,
        ]
        cloud = PointCloud()
        cloud.add_points(self.points.get_points())
        cloud.add_colors(np.full(self.points.get_points().shape, color, dtype=np.uint8))
        canvas_size, offset_xy = cloud.save_debug_image(
            output_file_path,
            grid_size,
            canvas_size=canvas_size,
            offset_xy=offset_xy,
            polygons=[self.roof_polygon] if self.roof_polygon is not None else None,
        )
        return canvas_size, offset_xy, cloud


class ClusterInfoList(UserList[ClusterInfo]):
    def __init__(self, init_list: Iterable[ClusterInfo] | None = None):
        super().__init__(list(init_list) if init_list is not None else [])

    def save_debug_image(
        self,
        output_dir_path: Path,
        grid_size: float,
        canvas_size: tuple[int, int] = None,
        offset_xy: tuple[float, float] = None,
        file_prefix: str = "",
    ):
        overlay_cloud: PointCloud | None = None
        all_polygons: list[Polygon] | None = None
        for cluster in self:
            _, _, saved_cloud = cluster.save_debug_image(
                output_dir_path / f"{file_prefix}cluster_{cluster.id}.png",
                grid_size,
                canvas_size=canvas_size,
                offset_xy=offset_xy,
            )
            if overlay_cloud is None:
                overlay_cloud = saved_cloud
            else:
                overlay_cloud.add_points(
                    np.vstack([overlay_cloud.get_points(), saved_cloud.get_points()])
                )
                overlay_cloud.add_colors(
                    np.vstack([overlay_cloud.get_colors(), saved_cloud.get_colors()])
                )
            if cluster.roof_polygon is not None:
                if all_polygons is None:
                    all_polygons = [cluster.roof_polygon]
                else:
                    all_polygons.append(cluster.roof_polygon)
        overlay_cloud.save_debug_image(
            output_dir_path / f"{file_prefix}clusters.png",
            grid_size,
            canvas_size=canvas_size,
            offset_xy=offset_xy,
            polygons=all_polygons,
        )
