import os
from collections import defaultdict
from typing import Union

import cv2
import numpy as np
from shapely import Point as GeoPoint
from shapely import Polygon, MultiPolygon
from shapely.ops import unary_union

from .utils.merge_close_vertices import merge_close_vertices
from ..model_surface_creation.utils.geometry import Point
from ..roof_layer_info import RoofLayerInfo
from ..utils.polys import (
    ensure_counter_clockwise,
    get_polygon_ijs_list,
    get_polys_from_geometry_collections,
    merge_small_polys_into_large_polys,
    validate_polygon_ijs_list,
)


class PolygonDivision:
    """
    HEATの屋根のポリゴンが一部不完全なため、ポリゴンを分割
    """

    @property
    def has_split_polygon(self):
        """ポリゴンが分割されたか

        Returns:
          bool: ポリゴンが分割された場合、True
        """
        return self._has_split_polygon

    @property
    def split_polygon_ijs_list(self):
        """分割されたポリゴンリスト

        Returns:
          list[list[tuple[float, float]]]: 分割されたポリゴンリスト
        """
        return self._split_polygon_ijs_list

    def __init__(
        self,
        polygon_ijs_before: list[tuple[float, float]],
        roof_layer_info: RoofLayerInfo,
        debug_mode: bool = False,
    ):
        """
        頂点IDを(i, j)座標に変換する。

        Args:
          polygon_ijs_before (list[tuple[float,float]]): 分割する対象ポリゴンの頂点(i,j)リスト
          roof_layer_info (RoofLayerInfo): DSM点群から屋根の階層分離をするための情報
          debug_mode (bool): デバッグモード

        Returns:
          tuple[float, float]: 各頂点の(i, j)座標のリスト
        """

        self._roof_layer_info = roof_layer_info
        self._debug_mode = debug_mode
        self._origin_polygon_ijs = ensure_counter_clockwise(polygon_ijs_before)
        self._layer_number_grid_ijs_pair = (
            PolygonDivision.get_layer_number_grid_ijs_pair(
                self._roof_layer_info,
                self._origin_polygon_ijs,
            )
        )

        if self.can_split():
            self._split_polygon_ijs_list = self._get_split_polygon_ijs_list()
            self._has_split_polygon = True
        else:
            self._split_polygon_ijs_list = [self._origin_polygon_ijs]
            self._has_split_polygon = False

    def can_split(self):
        """
        ポリゴン分割可能か確認。

        Returns:
          bool: ポリゴン分割可能の場合 True
        """

        if len(self._origin_polygon_ijs) <= 4:
            return False

        majority_layer_number = PolygonDivision.get_majority_layer_number(
            self._layer_number_grid_ijs_pair
        )
        if majority_layer_number == RoofLayerInfo.NOISE_POINT:
            return False

        noise_grid_ijs = (
            self._layer_number_grid_ijs_pair.get(RoofLayerInfo.NOISE_POINT) or []
        )
        noise_grid_count = len(noise_grid_ijs)
        total_grid_count = sum(
            len(v) for v in self._layer_number_grid_ijs_pair.values()
        )
        grid_count_without_noise = total_grid_count - noise_grid_count
        if grid_count_without_noise < 30:
            return False

        majority_grid_count = len(
            self._layer_number_grid_ijs_pair[majority_layer_number]
        )
        majority_grid_rate = majority_grid_count / grid_count_without_noise
        if grid_count_without_noise == 0 or majority_grid_rate > 0.95:
            return False

        has_angle_over_200 = False
        polygon_length = len(self._origin_polygon_ijs)
        for index, current_polygon_ij in enumerate(self._origin_polygon_ijs):
            prev_index = (index - 1) % polygon_length
            next_index = (index + 1) % polygon_length

            next_polygon_ijs = self._origin_polygon_ijs[next_index]
            prev_polygon_ijs = self._origin_polygon_ijs[prev_index]

            angle = self._calculate_angle_between_points(
                current_polygon_ij, prev_polygon_ijs, next_polygon_ijs
            )
            if angle > 200:
                has_angle_over_200 = True

        return has_angle_over_200

    def _get_split_polygon_ijs_list(self):
        """
        ポリゴンを分割

        Returns:
          tuple[float, float]: 各頂点の(i, j)座標のリスト
        """

        # 共通部ポリゴンリスト = 分割対象ポリゴン ∩ DSM屋根レイヤーポリゴン
        intersection_polygon_ijs_list: list[list[tuple[float, float]]] = []
        layer_number_layer_area_polygon_ijs_list_pair = (
            self._roof_layer_info.get_layer_number_layer_area_polygon_ijs_list_pair()
        )
        for layer_number in self._layer_number_grid_ijs_pair.keys():
            if layer_number < 0:
                continue

            layer_area_polygon_ijs_list = layer_number_layer_area_polygon_ijs_list_pair[
                layer_number
            ]

            # 領域（[self._origin_polygon_ijs]）と（layer_area_polygon_ijs_list）の共通部ポリゴン取得
            layer_area_intersection_polygon_ijs_list = (
                self._get_intersection_polygon_ijs_list(
                    [self._origin_polygon_ijs], layer_area_polygon_ijs_list
                )
            )
            intersection_polygon_ijs_list.extend(
                layer_area_intersection_polygon_ijs_list
            )

        # DSMノイズ領域のポリゴンリスト = 分割対象ポリゴン - 共通部ポリゴンリスト
        origin_poly = Polygon(self._origin_polygon_ijs)
        intersection_area = unary_union(
            [Polygon(polygon_ijs) for polygon_ijs in intersection_polygon_ijs_list]
        )

        noise_area = origin_poly.difference(intersection_area)
        noise_area_polygon_ijs_list = get_polygon_ijs_list([noise_area])

        # 分割されたポリゴンリスト = 共通部ポリゴンリスト + DSMノイズ領域のポリゴンリスト
        merged_polygon_ijs_list_tmp = [
            *intersection_polygon_ijs_list,
            *noise_area_polygon_ijs_list,
        ]

        # 小さいポリゴンを大きいポリゴンと合併
        merged_polygon_ijs_list = merge_small_polys_into_large_polys(
            merged_polygon_ijs_list_tmp
        )

        # float 演算浮動小数点誤差の制御パッチ : 丸めて誤差を抑える
        rounded_polygon_ijs_list = []
        for polygon_ijs in merged_polygon_ijs_list:
            rounded_polygon_ijs = [(round(i, 6), round(j, 6)) for i, j in polygon_ijs]

            fixed_rounded_poly_or_multi_poly = Polygon(rounded_polygon_ijs).buffer(0)
            fixed_rounded_polys = get_polys_from_geometry_collections(
                [fixed_rounded_poly_or_multi_poly]
            )

            for fixed_rounded_poly in fixed_rounded_polys:
                fixed_rounded_polygon_ijs = [
                    (round(i, 6), round(j, 6))
                    for i, j in list(fixed_rounded_poly.exterior.coords[:-1])
                ]
                if fixed_rounded_poly.area == 0 or len(fixed_rounded_polygon_ijs) < 3:
                    continue
                else:
                    rounded_polygon_ijs_list.append(fixed_rounded_polygon_ijs)

        merged_polygon_ijs_list_2 = merge_close_vertices(rounded_polygon_ijs_list)
        if self._debug_mode:
            self._save_splited_polygons_image(
                merged_polygon_ijs_list_2,
                "roof_line_with_layer_class_step_4_split_polygon.png",
            )

        validate_polygon_ijs_list(merged_polygon_ijs_list_2)

        merged_polygon_ijs_list_3 = [
            ensure_counter_clockwise(polygon_ijs)
            for polygon_ijs in merged_polygon_ijs_list_2
        ]

        return merged_polygon_ijs_list_3

    def _calculate_angle_between_points(
        self,
        current_point_ij: tuple[float, float],
        prev_point_ij: tuple[float, float],
        next_point_ij: tuple[float, float],
    ):
        """
        ポリゴンの指定した頂点を基準に前後の頂点との角度を計算する

        Args:
          current_point_ij (tuple[float, float]): 角度を求めたいの頂点座標(i,j)
          prev_point_ij (tuple[float, float]): 前の頂点座標(i,j)
          next_point_ij (tuple[float, float]): 次の頂点座標(i,j)

        Returns:
          float: 頂点の角度（度数法）
        """

        # 前の頂点と次の頂点の傾きをそれぞれ計算
        prev_slope = self._calculate_slope(current_point_ij, prev_point_ij)
        next_slope = self._calculate_slope(current_point_ij, next_point_ij)

        # 前の頂点との角度 - 次の頂点との角度
        angle = prev_slope - next_slope

        # 角度が(-)の場合は360を足す
        if angle < 0:
            angle += 360

        return angle

    @staticmethod
    def _remove_same_vertices_on_polygon(polygon_ijs: list[tuple[float, float]]):
        """
        ポリゴン内部に同じ点が連続にあるのを防ぐ

        Args:
          polygon_ijs (list[tuple[float, float]]): ポリゴンの頂点番号リスト

        Returns:
          list[tuple[float, float]]: 交差している領域のポリゴンリスト
        """

        new_polygon_ijs: list[tuple[float, float]] = []
        for current_polygon_ij in polygon_ijs:
            if len(new_polygon_ijs) == 0:
                new_polygon_ijs.append(current_polygon_ij)
            else:
                prev_polygon_ij = new_polygon_ijs[-1]
                next_polygon_ij = new_polygon_ijs[0]

                if (
                    prev_polygon_ij != current_polygon_ij
                    and next_polygon_ij != current_polygon_ij
                ):
                    new_polygon_ijs.append(current_polygon_ij)

        return new_polygon_ijs

    @staticmethod
    def _get_intersection_polygon_ijs_list(
        area1_polygon_ijs_list: list[list[tuple[float, float]]],
        area2_polygon_ijs_list: list[list[tuple[float, float]]],
    ):
        """
        ポリゴン同士の交差している領域を求める

        Args:
          area1_polygon_ijs_list (list[list[tuple[float, float]]]): 領域1に入っているポリゴンの頂点座標(i,j)リスト
          area2_polygon_ijs_list (list[list[tuple[float, float]]]): 領域2に入っているポリゴンの頂点座標(i,j)リスト

        Returns:
          list[list[tuple[float, float]]]: 領域2と領域1の共通部に入っているポリゴンの頂点座標(i,j)リスト
        """

        # 差分を取得
        area_1: Union[MultiPolygon, Polygon] = unary_union(
            [Polygon(area_polygon_ijs) for area_polygon_ijs in area1_polygon_ijs_list]
        )
        area_2: Union[MultiPolygon, Polygon] = unary_union(
            [Polygon(area_polygon_ijs) for area_polygon_ijs in area2_polygon_ijs_list]
        )

        intersection: Union[MultiPolygon, Polygon] = area_1.intersection(area_2)
        intersection_polygon_ijs = get_polygon_ijs_list([intersection])

        return intersection_polygon_ijs

    def _is_inside_origin_polygon(self, split_polygon_ijs: list[tuple[float, float]]):
        """
        ポリゴンのに他のポリゴン達が含まれているか確認する

        Args:
          split_polygon_ijs (list[tuple[float, float]]): ポリゴンの頂点座標(i,j)リスト

        Returns:
          bool: 各頂点の(i, j)座標のリスト
        """
        origin_poly = Polygon(self._origin_polygon_ijs)
        split_poly = Polygon(split_polygon_ijs)

        result = split_poly.difference(origin_poly)
        return result.area <= 1e-9

    def _save_split_polygons_image(
        self,
        split_polygons_ijs_list: list[list[tuple[float, float]]],
        debug_image_file_name: str,
    ):
        """
        ポリゴン同士の交差している領域を求める

        Args:
          split_polygons_ijs_list (list[list[tuple[float, float]]]): ポリゴンの(i,j)頂点のリスト
          debug_image_file_name (str): デバッグイメージのファイル名

        Returns:
          list[Polygon]: 交差している領域のポリゴンリスト
        """

        height, width = self._roof_layer_info.masked_dsm_grid_rgb_image.shape[:2]
        image_layer_split_polygons_image = np.full(
            (height, width, 3), 255, dtype=np.uint8
        )

        # ポリゴンのエッジ
        polygons_np = [
            np.array(filtered_polygon_ijs, np.int32)[:, ::-1].reshape((-1, 1, 2))
            for filtered_polygon_ijs in split_polygons_ijs_list
        ]
        edge_color = self._roof_layer_info.get_color(RoofLayerInfo.ROOF_LINE_POINT)
        cv2.polylines(
            image_layer_split_polygons_image,
            polygons_np,
            isClosed=True,
            color=edge_color,
            thickness=1,
        )

        # ポリゴンの頂点
        point_color = self._roof_layer_info.get_color(RoofLayerInfo.ROOF_VERTICE_POINT)
        for filtered_polygon_ijs in split_polygons_ijs_list:
            for i, j in filtered_polygon_ijs:
                cv2.circle(
                    image_layer_split_polygons_image,
                    (round(j), round(i)),
                    0,
                    point_color,
                    -1,
                )

        image_layer_split_polygons_path = os.path.join(
            self._roof_layer_info.debug_dir,
            debug_image_file_name,
        )
        cv2.imwrite(image_layer_split_polygons_path, image_layer_split_polygons_image)

    @staticmethod
    def _calculate_slope(
        point1_ij: tuple[float, float], point2_ij: tuple[float, float]
    ) -> float:
        """
        2点間の傾きを計算する

        Args:
          point1_ij (tuple[float, float]): 頂点座標(i,j)
          point2_ij (tuple[float, float]): 頂点座標(i,j)

        Returns:
          float: i軸に対する傾き（角度）
        """
        dx = point2_ij[0] - point1_ij[0]
        dy = point2_ij[1] - point1_ij[1]
        return np.arctan2(dy, dx) * 180 / np.pi  # ラジアンから度に変換

    @staticmethod
    def get_majority_layer_number(
        layer_number_grid_ijs_pair: dict[int, list[tuple[float, float]]],
    ):
        """
        ポリゴン内で最も多く出現するレイヤー番号を取得する。

        Args:
          layer_number_grid_ijs_pair (dict[int, list[tuple[float, float]]]): レイヤー番号とそのポイント(i, j)のペアを含む辞書

        Returns:
          int: ポリゴン内で最も多く出現するレイヤー番号
        """
        layer_count_max = 0
        majority_layer_number = RoofLayerInfo.NOISE_POINT
        for layer_number, layer_points_ij in layer_number_grid_ijs_pair.items():
            layer_count = len(layer_points_ij)

            if (
                layer_count > layer_count_max
                and layer_number != RoofLayerInfo.NOISE_POINT
            ):
                layer_count_max = layer_count
                majority_layer_number = layer_number

        return majority_layer_number

    @staticmethod
    def point_id_to_ij(
        vertices: list[Point], point_id: list[int]
    ) -> tuple[float, float]:
        """
        頂点IDを(i, j)座標に変換する。

        Args:
          vertices (list[Point]): 頂点リスト
          point_id (int): 頂点ID

        Returns:
          tuple[float, float]: 各頂点の(i, j)座標のリスト
        """
        return int(vertices[point_id].x), int(vertices[point_id].y)

    @staticmethod
    def get_layer_number_grid_ijs_pair(
        roof_layer_info: RoofLayerInfo,
        origin_polygon_ijs: list[tuple[float, float]],
    ):
        """
        ポリゴン内のレイヤー番号と対応するポイントを取得する。

        Args:
          roof_layer_info (RoofLayerInfo): DSM点群から屋根の階層分離をするための情報
          origin_polygon_ijs (list[tuple[float, float]]): 元のポリゴンの頂点座標(i,j)リスト

        Returns:
          dict[int, list[tuple[float, float]]]: レイヤー番号とそのポイント(i, j)のペアを含む辞書
        """

        height, width = roof_layer_info.masked_dsm_grid_rgb_image.shape[:2]
        poly = Polygon(origin_polygon_ijs)
        layer_number_grid_ijs_pair: dict[int, list[tuple[float, float]]] = defaultdict(
            list
        )
        for i in range(height):
            for j in range(width):
                is_inside_polygon = poly.contains(GeoPoint(i, j))
                if is_inside_polygon:
                    layer_number = roof_layer_info.layer_class[i, j]
                    layer_number_grid_ijs_pair[layer_number].append((i, j))

        return layer_number_grid_ijs_pair

    @staticmethod
    def bresenham_line(ij_1: tuple[float, float], ij_2: tuple[float, float]):
        """
        Bresenhamのアルゴリズムを使って2点間の直線を描画する。

        Args:
          ij_1 (tuple[float, float]): 視点のピクセル座標
          ij_2 (tuple[float, float]): 終点のピクセル座標

        Returns:
          list[tuple[float, float]]: 線上のすべてのピクセル座標
        """
        i0, j0 = ij_1
        i1, j1 = ij_2
        pixels: list[tuple[float, float]] = []
        dx = abs(i1 - i0)
        dy = abs(j1 - j0)
        sx = 1 if i0 < i1 else -1
        sy = 1 if j0 < j1 else -1
        err = dx - dy

        while True:
            pixels.append((i0, j0))
            if i0 == i1 and j0 == j1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                i0 += sx
            if e2 < dx:
                err += dx
                j0 += sy

        return pixels
