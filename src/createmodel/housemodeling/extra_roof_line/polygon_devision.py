import os
from typing import Union
from collections import defaultdict

import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry import Point as GeoPoint
from shapely.ops import unary_union
import cv2

from ....createmodel.housemodeling.extra_roof_line.utils.merge_close_vertices import merge_close_vertices
from ....createmodel.createmodelexception import CreateModelException
from ....createmodel.message import CreateModelMessage
from ..roof_layer_info import RoofLayerInfo
from ..model_surface_creation.utils.geometry import Point


class PolygonDevision:
  """
  HEATの屋根のポリゴンが一部不完全なため、ポリゴンを分割
  """

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
    self._origin_polygon_ijs = polygon_ijs_before
    self._layer_number_grid_ijs_pair = PolygonDevision.get_layer_number_grid_ijs_pair(
        self._roof_layer_info,
        self._origin_polygon_ijs,
    )

  def can_split(self):
    """
    ポリゴン分割可能か確認。

    Args:
      vertices (list[Point]): 頂点リスト
      polygon (list[int]): ポリゴンの頂点番号リスト
      layer_class: (npt.NDArray[np.int_]) DSM点群の画像座標 (i,j) 二次元アレイに壁点を起点としてクラスタリングした屋根のレイヤー番号を記録したもの

    Returns:
      bool: ポリゴン分割可能の場合 True
    """

    if len(self._origin_polygon_ijs) <= 4:
      return False

    majority_layer_number = PolygonDevision.get_majority_layer_number(self._layer_number_grid_ijs_pair)
    if majority_layer_number == RoofLayerInfo.NOISE_POINT:
      return False

    noise_grid_ijs = self._layer_number_grid_ijs_pair.get(RoofLayerInfo.NOISE_POINT) or []
    noise_grid_count = len(noise_grid_ijs)
    total_grid_count = sum(len(v) for v in self._layer_number_grid_ijs_pair.values())
    grid_count_without_noise = total_grid_count - noise_grid_count
    if grid_count_without_noise < 30:
      return False

    majority_grid_count = len(self._layer_number_grid_ijs_pair[majority_layer_number])
    majority_grid_rate = majority_grid_count / grid_count_without_noise
    if grid_count_without_noise == 0 or majority_grid_rate > 0.95:
      return False

    has_angle_over_200 = False
    counter_clockwised_origin_polygon_ijs = PolygonDevision._ensure_counterclockwise(self._origin_polygon_ijs)
    polygon_length = len(counter_clockwised_origin_polygon_ijs)
    for index, current_polygon_ij in enumerate(counter_clockwised_origin_polygon_ijs):
      prev_index = polygon_length - 1 if (index - 1) == -1 else index - 1
      next_index = 0 if (index + 1) == polygon_length else index + 1

      next_polygon_ijs = counter_clockwised_origin_polygon_ijs[next_index]
      prev_polygon_ijs = counter_clockwised_origin_polygon_ijs[prev_index]

      angle = self._calculate_angle_between_points(current_polygon_ij, prev_polygon_ijs, next_polygon_ijs)
      if angle > 200:
        has_angle_over_200 = True

    return has_angle_over_200

  def get_splited_polygon_ijs_list(self, debug_image_file_name: str):
    """
    ポリゴンを分割

    Args:
      debug_image_file_name (str): デバッグイメージのファイル名

    Returns:
      tuple[float, float]: 各頂点の(i, j)座標のリスト
    """

    # 共通部ポリゴンリスト = 分割対象ポリゴン ∩ DSM屋根レイヤーポリゴン
    intersection_polygon_ijs_list: list[list[tuple[float, float]]] = []
    for layer_number in self._layer_number_grid_ijs_pair.keys():
      if layer_number < 0:
        continue

      layer_area_polygon_ijs_list = self._roof_layer_info.layer_number_layer_area_polygon_ijs_list_pair[layer_number]

      # 領域（[self._origin_polygon_ijs]）と（layer_area_polygon_ijs_list）の共通部ポリゴン取得
      layer_area_intersection_polygon_ijs_list = self._get_intersection_polygon_ijs_list(
          [self._origin_polygon_ijs], layer_area_polygon_ijs_list
      )
      intersection_polygon_ijs_list.extend(layer_area_intersection_polygon_ijs_list)

    # DSMノイズ領域のポリゴンリスト = 分割対象ポリゴン - 共通部ポリゴンリスト
    origin_poly = Polygon(self._origin_polygon_ijs)
    intersection_area = unary_union([Polygon(polygon_ijs) for polygon_ijs in intersection_polygon_ijs_list])

    noise_area = origin_poly.difference(intersection_area)
    noise_area_polygon_ijs_list: list[list[tuple[float, float]]] = []
    if not noise_area.is_empty:
      if isinstance(noise_area, MultiPolygon):
        for poly in noise_area.geoms:
          polygon_ijs = list(dict.fromkeys(poly.exterior.coords))
          noise_area_polygon_ijs_list.append(polygon_ijs)
      elif isinstance(noise_area, Polygon):
        polygon_ijs = list(dict.fromkeys(noise_area.exterior.coords))
        noise_area_polygon_ijs_list.append(polygon_ijs)

    # 分割されたポリゴンリスト = 共通部ポリゴンリスト + DSMノイズ領域のポリゴンリスト
    merged_polygon_ijs_list_tmp = [*intersection_polygon_ijs_list, *noise_area_polygon_ijs_list]

    # 小さいポリゴンを大きいポリゴンと合併
    merged_polygon_ijs_list = PolygonDevision.merge_small_polygon_into_large_polygon(
        merged_polygon_ijs_list_tmp, 40
    )

    # float 演算浮動小数点誤差の制御パッチ : 丸めて誤差を抑える
    rounded_polygon_ijs_list = []
    for polygon_ijs in merged_polygon_ijs_list:
      rounded_polygon_ijs = [(round(i, 6), round(j, 6)) for i, j in polygon_ijs]

      fixed_rounded_polys: list[Polygon] = []
      fixed_rounded_poly_or_multi_poly = Polygon(rounded_polygon_ijs).buffer(0)
      if isinstance(fixed_rounded_poly_or_multi_poly, MultiPolygon):
        fixed_rounded_polys = list(fixed_rounded_poly_or_multi_poly.geoms)
      else:
        fixed_rounded_polys = [fixed_rounded_poly_or_multi_poly]

      for fixed_rounded_poly in fixed_rounded_polys:
        fixed_rounded_polygon_ijs = [
            (round(i, 6), round(j, 6)) for i, j in list(fixed_rounded_poly.exterior.coords[:-1])
        ]
        if fixed_rounded_poly.area == 0 or len(fixed_rounded_polygon_ijs) < 3:
          continue
        else:
          rounded_polygon_ijs_list.append(fixed_rounded_polygon_ijs)

    merged_polygon_ijs_list_2 = merge_close_vertices(rounded_polygon_ijs_list)

    if self._debug_mode:
      self._save_splited_polygons_image(merged_polygon_ijs_list_2, debug_image_file_name)

    self._validate_splited_poylgon_ijs(self._origin_polygon_ijs, merged_polygon_ijs_list_2)

    return merged_polygon_ijs_list_2

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

  def _remove_same_vertices_on_polygon(self, polygon_ijs: list[tuple[float, float]]):
    """
    ポリゴン内部に同じ点が連続にあるのを防ぐ

    Args:
      polygon_ij (list[tuple[float, float]]): ポリゴンの頂点番号リスト

    Returns:
      list[tuple[float, float]]: 交差している領域のポリゴンリスト
    """

    new_polygon_ijs = []
    for current_polygon_ij in polygon_ijs:
      if len(new_polygon_ijs) == 0:
        new_polygon_ijs.append(current_polygon_ij)
      else:
        prev_polygon_ij = new_polygon_ijs[-1]
        next_polygon_ij = new_polygon_ijs[0]

        if prev_polygon_ij != current_polygon_ij and next_polygon_ij != current_polygon_ij:
          new_polygon_ijs.append(current_polygon_ij)

    return new_polygon_ijs

  def _get_intersection_polygon_ijs_list(
      self,
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
    intersection_polygon_ijs: list[list[tuple[float, float]]] = []
    if not intersection.is_empty:
      if isinstance(intersection, MultiPolygon):
        for poly in intersection.geoms:
          polygon_ijs = [coord for coord in poly.exterior.coords[:-1]]
          intersection_polygon_ijs.append(polygon_ijs)
      elif isinstance(intersection, Polygon):
        polygon_ijs = [coord for coord in intersection.exterior.coords[:-1]]
        intersection_polygon_ijs.append(polygon_ijs)

    return intersection_polygon_ijs

  def _is_inside_origin_polygon(self, splited_polygon_ijs: list[tuple[float, float]]):
    """
    ポリゴンのに他のポリゴン達が含まれているか確認する

    Args:
      splited_polygon_ijs (list[tuple[float, float]]): ポリゴンの頂点座標(i,j)リスト

    Returns:
      bool: 各頂点の(i, j)座標のリスト
    """
    origin_poly = Polygon(self._origin_polygon_ijs)
    splited_poly = Polygon(splited_polygon_ijs)

    result = splited_poly.difference(origin_poly)
    return result.area <= 1e-9

  def _save_splited_polygons_image(
      self,
      splited_polygons_ijs_list: list[list[tuple[float, float]]],
      debug_image_file_name: str,
  ):
    """
    ポリゴン同士の交差している領域を求める

    Args:
      splited_polygons_ijs_list (list[list[tuple[float, float]]]): ポリゴンの(i,j)頂点のリスト
      debug_image_file_name (str): デバッグイメージのファイル名

    Returns:
      list[Polygon]: 交差している領域のポリゴンリスト
    """

    height, width = self._roof_layer_info.dsm_grid_rgbs.shape[:2]
    image_layer_splited_polygons_image = np.full((height, width, 3), 255, dtype=np.uint8)

    # ポリゴンのエッジ
    polygons_np = [
        np.array(filterd_polygon_ijs, np.int32)[:, ::-1].reshape((-1, 1, 2))
        for filterd_polygon_ijs in splited_polygons_ijs_list
    ]
    edge_color = self._roof_layer_info.get_color(RoofLayerInfo.ROOF_LINE_POINT)
    cv2.polylines(image_layer_splited_polygons_image, polygons_np, isClosed=True, color=edge_color, thickness=1)

    # ポリゴンの頂点
    point_color = self._roof_layer_info.get_color(RoofLayerInfo.ROOF_VERTICE_POINT)
    for filterd_polygon_ijs in splited_polygons_ijs_list:
      for i, j in filterd_polygon_ijs:
        cv2.circle(image_layer_splited_polygons_image, (round(j), round(i)), 0, point_color, -1)

    image_layer_splited_polygons_path = os.path.join(
        self._roof_layer_info.debug_dir, debug_image_file_name,
    )
    cv2.imwrite(image_layer_splited_polygons_path, image_layer_splited_polygons_image)

  def _validate_splited_poylgon_ijs(
      self,
      origin_polygon_ijs: list[tuple[float, float]],
      splited_polygon_ijs_list: list[list[tuple[float, float]]],
  ):
    """
    分割されたポリゴンの整合性をチェックする

    Args:
      origin_polygon_ijs (list[tuple[float, float]]): 元のポリゴンの頂点座標(i,j)リスト
      splited_polygon_ijs_list (list[list[tuple[float, float]]]): 分割されたポリゴン達の頂点番号リスト

    Raises:
      CreateModelException: 屋根ポリゴン分割で失敗
    """

    polys = [Polygon(polygon_ijs) for polygon_ijs in splited_polygon_ijs_list]
    for poly in polys:
      # 不正ポリゴン
      assert poly.is_valid, "不正ポリゴンです"
      if not poly.is_valid:
        raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)
      # 小さいポリゴン
      assert poly.area >= 1e-9, "ポリゴンが小さすぎます"
      if not poly.area >= 1e-9:
        raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)

  def _calculate_slope(self, point1_ij: tuple[float, float], point2_ij: tuple[float, float]) -> float:
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
  def get_majority_layer_number(layer_number_grid_ijs_pair: dict[int, list[tuple[float, float]]]):
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

      if layer_count > layer_count_max and layer_number != RoofLayerInfo.NOISE_POINT:
        layer_count_max = layer_count
        majority_layer_number = layer_number

    return majority_layer_number

  @ staticmethod
  def point_id_to_ij(vertices: list[Point], point_id: list[int]) -> tuple[float, float]:
    """
    頂点IDを(i, j)座標に変換する。

    Args:
      vertices (list[Point]): 頂点リスト
      point_id (int): 頂点ID

    Returns:
      tuple[float, float]: 各頂点の(i, j)座標のリスト
    """
    return (int(vertices[point_id].x), int(vertices[point_id].y))

  @ staticmethod
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

    height, width = roof_layer_info.dsm_grid_rgbs.shape[:2]
    poly = Polygon(origin_polygon_ijs)
    layer_number_grid_ijs_pair: dict[int, list[tuple[float, float]]] = {}
    for i in range(height):
      for j in range(width):
        is_inside_polygon = poly.contains(GeoPoint(i, j))
        if is_inside_polygon:
          layer_number = roof_layer_info.layer_class[i, j]

          if layer_number_grid_ijs_pair.get(layer_number) is None:
            layer_number_grid_ijs_pair[layer_number] = []

          layer_number_grid_ijs_pair[layer_number].append((i, j))
    return layer_number_grid_ijs_pair

  @ staticmethod
  def _ensure_counterclockwise(polygon_ijs: list[tuple[float, float]]):
    """
    ポリゴンの頂点が反時計回りになるようにする

    Args:
      polygon_ijs (list[tuple[float, float]]): ポリゴンの頂点座標(i,j)リスト

    Returns:
      list[int]: 反時計回りにしたポリゴン
    """
    poly = Polygon(polygon_ijs)
    if not poly.exterior.is_ccw:
        # 時計回りなら反転させる
      return polygon_ijs[::-1]

    return polygon_ijs

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

  @staticmethod
  def merge_small_polygon_into_large_polygon(
      polygon_ijs_list: list[list[tuple[float, float]]],
      area_threashold: int,
  ):
    """
    小さなポリゴンを周辺の大きなポリゴンに合成する

    Args:
      polygon_ijs_list (list[list[tuple[float, float]]]): ポリゴンの頂点座標(i,j)リスト

    Returns:
      list[list[tuple[float, float]]]: 合成後のポリゴンの頂点座標(i,j)リスト
    """
    poly_to_index_poly_from_indexes_pair: dict[int, list[int]] = defaultdict(list)
    poly_indexes_for_merging: set[int] = set()
    polys = [Polygon(polygon_ijs) for polygon_ijs in polygon_ijs_list]

    # ポリゴンの合成対象を見つける
    for poly_from_index, poly in enumerate(polys):
      can_be_merged = poly.area <= area_threashold
      if can_be_merged:
        max_intersection_length = 0
        poly_to_index = -1
        for poly_to_index_tmp, other_poly in enumerate(polys):
          if poly_from_index == poly_to_index_tmp:
            continue

          intersection = poly.intersection(other_poly)
          if intersection.length > max_intersection_length:
            max_intersection_length = intersection.length
            poly_to_index = poly_to_index_tmp

        if poly_to_index != -1:
          poly_indexes_for_merging.add(poly_from_index)
          poly_indexes_for_merging.add(poly_to_index)
          poly_to_index_poly_from_indexes_pair[poly_to_index].append(poly_from_index)

    merged_polys: list[Polygon] = []
    merged_polygon_ijs_list: list[list[tuple[float, float]]] = []
    merged_indexes: set[int] = set()

    # 変化のないポリゴンを追加
    for poly_from_index, poly in enumerate(polys):
      if poly_from_index not in poly_indexes_for_merging:
        polygon_from_ijs = [coord for coord in poly.exterior.coords[:-1]]
        merged_polygon_ijs_list.append(polygon_from_ijs)
        merged_polys.append(Polygon(polygon_from_ijs))

    # 合成されたポリゴンを処理
    for poly_to_index in poly_to_index_poly_from_indexes_pair.keys():
      if poly_to_index in merged_indexes:
        continue

      # 親子関係を解決し、すべてのポリゴンを集める
      poly_from_indexes = PolygonDevision.gather_polygon_indices(
          poly_to_index_poly_from_indexes_pair,
          poly_to_index,
          [],
      )
      merged_indexes.update(poly_from_indexes)

      # ポリゴンの合成
      poly_to = polys[poly_to_index]
      poly_froms = [polys[poly_from_index] for poly_from_index in poly_from_indexes]
      merged_poly_area = unary_union([poly_to, *poly_froms]).buffer(0)
      tmp_merged_polys: list[Polygon] = []
      if isinstance(merged_poly_area, MultiPolygon):
        tmp_merged_polys = list(merged_poly_area.geoms)
      else:
        tmp_merged_polys = [merged_poly_area]

      merged_polys.extend(tmp_merged_polys)
      tmp_merged_polygon_ijs = [
          list(poly.exterior.coords[:-1])
          for poly in tmp_merged_polys
      ]
      merged_polygon_ijs_list.extend(tmp_merged_polygon_ijs)

    return merged_polygon_ijs_list

  @staticmethod
  def gather_polygon_indices(
      poly_to_index_poly_from_indexes_pair: dict,
      poly_to_index: int,
      result_poly_from_indexes: list[int],
  ):
    # すでに処理済みか確認
    if poly_to_index in result_poly_from_indexes:
      return result_poly_from_indexes

    # 現在のインデックスを追加
    result_poly_from_indexes.append(poly_to_index)

    # 子ポリゴンのインデックスを取得
    child_poly_from_indexes = poly_to_index_poly_from_indexes_pair.get(poly_to_index, [])

    # 再帰的に子ポリゴンのインデックスを取得
    for child_poly_from_index in child_poly_from_indexes:
      PolygonDevision.gather_polygon_indices(
          poly_to_index_poly_from_indexes_pair,
          child_poly_from_index,
          result_poly_from_indexes,
      )

    return result_poly_from_indexes
