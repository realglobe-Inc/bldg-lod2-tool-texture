import itertools
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ....createmodel.createmodelexception import CreateModelException
from ....createmodel.message import CreateModelMessage
from .polygon_devision import PolygonDevision
from ..roof_layer_info import RoofLayerInfo


class ExtraRoofLine:
  @property
  def new_polygon_vertex_xys(self):
    """
    Returns:
      list[tuple[float, float]]: 外周ポリゴンの要点番号リスト
    """

    return self._new_polygon_vertex_xys

  @property
  def new_outer_polygon(self):
    """
    Returns:
      list[list[int]]: 外周ポリゴンの要点番号リスト
    """

    return self._new_outer_polygon

  @property
  def new_inner_polygons(self):
    """
    Returns:
      list[list[int]]: 内部ポリゴンの要点番号リスト
    """

    return self._new_inner_polygons

  @property
  def has_splited_polygon(self):
    """
    Returns:
      bool: 分離されたポリゴンリストある場合 True
    """

    return self._has_splited_polygon

  def __init__(
      self,
      shape: Polygon,
      inner_polygon_ijs_list_before: list[list[tuple[float, float]]],
      roof_layer_info: RoofLayerInfo,
      delta_i_average: float,
      delta_j_average: float,
      grid_size: float,
      debug_mode: bool = False
  ):
    """
    HEAT が出せてない屋根線を追加

    Args:
      shape(Polygon): 建物外形ポリゴン
      inner_polygon_ijs_list_before (list[list[tuple[float, float]]]): 複数のポリゴンの頂点(i,j)リスト
      roof_layer_info (RoofLayerInfo): DSM点群から屋根の階層分離をするための情報
      delta_i_average (float): i <-> x 座標変換用
      delta_j_average (float): j <-> y 座標変換用
      grid_size (float): 点群の間隔(meter)
      debug_mode (bool): デバッグモード
    """
    self._shape = shape
    self._inner_polygon_ijs_list_before = inner_polygon_ijs_list_before
    self._roof_layer_info = roof_layer_info
    self._delta_i_average = delta_i_average
    self._delta_j_average = delta_j_average
    self._grid_size = grid_size
    self._debug_mode = debug_mode

    self._height, self._width = self._roof_layer_info.layer_class.shape

    if debug_mode:
      self._save_roof_line_with_layer_class_images(
          self._inner_polygon_ijs_list_before,
          'roof_line_with_layer_class_step_1_origin_polygons.png',
          'roof_line_with_layer_class_step_2_origin_roof_layers.png',
          'roof_line_with_layer_class_step_3_filled_origin_polygons.png',
      )

    self._inner_polygon_ijs_list_after = self._get_inner_polygon_ijs_list_after(
        self._inner_polygon_ijs_list_before
    )

    self._inner_polygon_xys_list, self._outer_polygon_xys = self._get_polygon_xys(
        self._shape,
        self._inner_polygon_ijs_list_after,
    )

    self._new_polygon_vertex_xys = list(set([
        polygon_xy
        for polygon_xys in [*self._inner_polygon_xys_list, self._outer_polygon_xys]
        for polygon_xy in polygon_xys
    ]))

    vertex_xy_point_id_pair = {
        vertex_ij: index for index, vertex_ij in enumerate(self._new_polygon_vertex_xys)
    }

    self._new_inner_polygons: list[list[int]] = []
    for inner_polygon_xys in self._inner_polygon_xys_list:
      self._new_inner_polygons.append(
          [vertex_xy_point_id_pair[inner_polygon_xy] for inner_polygon_xy in inner_polygon_xys]
      )

    self._new_outer_polygon: list[int] = [
        vertex_xy_point_id_pair[self_outer_polygon_xy]
        for self_outer_polygon_xy in self._outer_polygon_xys
    ]

    if self._debug_mode:
      self._save_roof_line_with_layer_class_images(
          self._inner_polygon_ijs_list_after,
          'roof_line_with_layer_class_step_5_splited_polygons.png',
          'roof_line_with_layer_class_step_6_splited_roof_layers.png',
          'roof_line_with_layer_class_step_7_filled_splited_polygons.png',
      )

  def _has_too_many_noise(self):
    has_too_many_noise = False
    for polygon_ijs in self._inner_polygon_ijs_list_after:
      layer_number_point_ijs_pair = PolygonDevision.get_layer_number_grid_ijs_pair(self._roof_layer_info, polygon_ijs)
      noise_point_ijs = layer_number_point_ijs_pair.get(RoofLayerInfo.NOISE_POINT) or []
      point_ijs_count_noise = len(noise_point_ijs)
      point_ijs_count_all = 0
      for point_ijs in layer_number_point_ijs_pair.values():
        point_ijs_count_all += len(point_ijs)

      if point_ijs_count_all >= 25 and (point_ijs_count_noise / point_ijs_count_all) > 0.4:
        print(point_ijs_count_all, point_ijs_count_noise)
        has_too_many_noise = True

    return has_too_many_noise

  def _save_roof_line_with_layer_class_images(
      self,
      inner_polygon_ijs_list: list[list[tuple[int, int]]],
      file_name_1: str,
      file_name_2: str,
      file_name_3: str,
  ):
    """
    屋根の壁処理のためのデバッグ用の画像を保存する。

    Args:
      inner_polygon_ijs_list (list[list[tuple[int, int]]]): ポリゴンリスト
      file_name_1 (str): デバッグイメージのファイル名
      file_name_2 (str): デバッグイメージのファイル名
      file_name_3 (str): デバッグイメージのファイル名
    """

    # RGBイメージの初期化
    dsm_grid_rgbs_of_roof_line_with_layer_class_as_is = np.full((self._height, self._width, 3), 255, dtype=np.uint8)
    dsm_grid_rgbs_of_roof_line_with_layer_class_to_be = np.full((self._height, self._width, 3), 255, dtype=np.uint8)
    polygon_edges_for_debug_image = set()

    for polygon_ijs in inner_polygon_ijs_list:
      poly = Polygon(polygon_ijs)
      coords = list(poly.exterior.coords)  # ポリゴンの外周座標リスト
      for i in range(len(coords) - 1):  # 視点と終点が同じ点だから終点は無視する
        sorted_coord = tuple(sorted([coords[i], coords[i + 1]]))  # 重複を防ぐため、sort
        polygon_edges_for_debug_image.add(sorted_coord)

    for polygon_ijs in inner_polygon_ijs_list:
      layer_number_point_ijs_pair = PolygonDevision.get_layer_number_grid_ijs_pair(self._roof_layer_info, polygon_ijs)
      majority_layer_number = PolygonDevision.get_majority_layer_number(layer_number_point_ijs_pair)
      for layer_number, layer_points_ij in layer_number_point_ijs_pair.items():
        for i, j in layer_points_ij:
          dsm_grid_rgbs_of_roof_line_with_layer_class_as_is[i, j] = self._roof_layer_info.get_color(layer_number)
          dsm_grid_rgbs_of_roof_line_with_layer_class_to_be[i, j] = self._roof_layer_info.get_color(majority_layer_number)

    self._roof_layer_info.save_roof_line_image(
        self._roof_layer_info.dsm_grid_rgbs,
        polygon_edges_for_debug_image,
        file_name_1,
    )
    self._roof_layer_info.save_roof_line_image(
        dsm_grid_rgbs_of_roof_line_with_layer_class_as_is,
        polygon_edges_for_debug_image,
        file_name_2,
    )
    self._roof_layer_info.save_roof_line_image(
        dsm_grid_rgbs_of_roof_line_with_layer_class_to_be,
        polygon_edges_for_debug_image,
        file_name_3,
    )

  def _get_inner_polygon_ijs_list_after(self, inner_polygon_ijs_list_before):
    tmp_inner_polygon_ijs_list_after: list[list[tuple[float, float]]] = []
    self._has_splited_polygon = False

    for polygon_ijs_before in inner_polygon_ijs_list_before:
      polygon_devision = PolygonDevision(polygon_ijs_before, self._roof_layer_info, self._debug_mode)
      if (polygon_devision.can_split()):
        splited_polygon_ijs_list = polygon_devision.get_splited_polygon_ijs_list(
            'roof_line_with_layer_class_step_4_splited_polygon.png',
        )
        tmp_inner_polygon_ijs_list_after.extend(splited_polygon_ijs_list)
        self._has_splited_polygon = True
      else:
        tmp_inner_polygon_ijs_list_after.append(polygon_ijs_before)

    tmp_polys: list[Polygon] = []
    for polygon_ijs in tmp_inner_polygon_ijs_list_after:
      tmp_polys.append(Polygon(polygon_ijs))

    for poly in tmp_polys:
      if not poly.is_valid:
        raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)

    # 傾きと切片で同じ直線上にある頂点をグループ化
    line_group_key_point_ijs_pair: dict[tuple[int, int], set[tuple[float, float]]] = {}
    poly_area: Polygon = unary_union(tmp_polys)
    for interior in poly_area.interiors:
      if interior.area == 0:
        for index, coord in enumerate(list(interior.coords[:-1])):
          next_coord = interior.coords[index + 1]
          line_group_key = self._get_line_group_key(coord, next_coord)
          line_group_key_point_ijs_pair.setdefault(line_group_key, set()).add(coord)
          line_group_key_point_ijs_pair.setdefault(line_group_key, set()).add(next_coord)

    # 傾きと切片で同じ直線上にある頂点を追加
    new_polys: list[Polygon] = []
    inner_polygon_ijs_list_after: list[list[tuple[float, float]]] = []
    for tmp_inner_polygon_ijs in tmp_inner_polygon_ijs_list_after:
      new_inner_polygon_ijs = []
      for index, inner_polygon_ij in enumerate(tmp_inner_polygon_ijs):
        next_index = 0 if (index + 1 == len(tmp_inner_polygon_ijs)) else index + 1
        next_inner_polygon_ij = tmp_inner_polygon_ijs[next_index]
        line_group_key = self._get_line_group_key(inner_polygon_ij, next_inner_polygon_ij)

        # 始点と終点の直線上に中間点がある場合、中間点も挟む
        line_point_ijs = line_group_key_point_ijs_pair.get(line_group_key)
        if line_point_ijs is not None:
          sorted_line_point_ijs = sorted(list(line_point_ijs))
          start_index = sorted_line_point_ijs.index(inner_polygon_ij)
          end_index = sorted_line_point_ijs.index(next_inner_polygon_ij)
          # 始点、中間点、終点を追加
          for sorted_point_ij_index in range(start_index, end_index):
            new_inner_polygon_ij = sorted_line_point_ijs[sorted_point_ij_index]
            if new_inner_polygon_ij not in new_inner_polygon_ijs:
              new_inner_polygon_ijs.append(new_inner_polygon_ij)
        else:
          # 始点を追加
          if inner_polygon_ij not in new_inner_polygon_ijs:
            new_inner_polygon_ijs.append(inner_polygon_ij)

      new_poly = Polygon(new_inner_polygon_ijs)
      if not new_poly.is_valid:
        raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)

      new_polys.append(new_poly)
      inner_polygon_ijs_list_after.append(new_inner_polygon_ijs)

    new_polys_area = unary_union(new_polys)
    if len(new_polys_area.interiors) > 0:
      raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)

    return inner_polygon_ijs_list_after

  def _get_line_group_key(
      self,
      start_point_ij: tuple[float, float],
      end_point_ij: tuple[float, float],
  ):
    (i1, j1) = start_point_ij
    (i2, j2) = end_point_ij
    if i2 != i1:  # 垂直線を除外
      a = (j2 - j1) / (i2 - i1)  # 傾き
      b = j1 - a * i1            # 切片
      key = (round(a, 6), round(b, 6))  # 丸めて誤差を調整
    else:
      key = ("vertical", i1)  # 垂直線の場合、i座標でグループ化

    return key

  def _get_polygon_xys(
      self,
      shape: Polygon,
      inner_polygon_ijs_list_after: list[list[tuple[float, float]]],
  ):
    vertex_ijs = list(set([
        polygon_ij
        for polygon_ijs in inner_polygon_ijs_list_after
        for polygon_ij in polygon_ijs
    ]))
    vertex_ij_point_id_pair = {vertex_ij: index for index, vertex_ij in enumerate(vertex_ijs)}

    tmp_inner_polygons: list[list[int]] = []
    for inner_polygon_ijs in inner_polygon_ijs_list_after:
      inner_polygon: list[int] = [
          vertex_ij_point_id_pair[vertex_ij] for vertex_ij in inner_polygon_ijs
      ]
      tmp_inner_polygons.append(inner_polygon)

    tmp_vertex_xys = [
        self._ij_to_xy(i, j, self._delta_i_average, self._delta_j_average) for i, j in vertex_ijs
    ]

    tmp_xy_polys: list[Polygon] = []
    for tmp_inner_polygon in tmp_inner_polygons:
      tmp_xy_polys.append(Polygon([tmp_vertex_xys[point_id] for point_id in tmp_inner_polygon]))

    tmp_fixed_polys: list[Polygon] = []
    for poly in tmp_xy_polys:
      fixed_poly = shape.intersection(poly)
      tmp_fixed_polys.append(fixed_poly)

    intersection_of_fixed_polys = []
    for poly_a, poly_b in itertools.combinations(tmp_fixed_polys, 2):
      intersection = poly_a.intersection(poly_b)
      if intersection.area > 0:
        intersection_of_fixed_polys.append(intersection)

    intersection_area = unary_union(intersection_of_fixed_polys)
    fixed_polys = []
    for tmp_fixed_poly in tmp_fixed_polys:
      fixed_poly = tmp_fixed_poly.difference(intersection_area)
      fixed_polys.append(fixed_poly)

    fixed_area = unary_union(fixed_polys)
    other_area = self._shape.difference(fixed_area)

    before_polygon_xys_list = []
    for area_or_poly in [*fixed_polys, other_area]:
      if not area_or_poly.is_empty:
        if isinstance(area_or_poly, Polygon):
          before_polygon_xys_list.append(list(area_or_poly.exterior.coords[:-1]))
        else:
          for poly in area_or_poly.geoms:
            if isinstance(poly, Polygon):
              before_polygon_xys_list.append(list(poly.exterior.coords[:-1]))

    after_polygon_xys_list = PolygonDevision.merge_small_polygon_into_large_polygon(
        before_polygon_xys_list, 0.0001
    )

    fixed_inner_xy_polys: list[Polygon] = [
        Polygon(inner_polygon_xys) for inner_polygon_xys in before_polygon_xys_list
    ]

    outer_xy_poly = unary_union(fixed_inner_xy_polys)
    if not isinstance(outer_xy_poly, Polygon):
      raise CreateModelException(CreateModelMessage.ERR_POLYGON_DIVISION_FAIL)

    after_outer_polygon_xys = list(outer_xy_poly.exterior.coords[:-1])

    return after_polygon_xys_list, after_outer_polygon_xys

  def _ij_to_xy(self, i: float, j: float, delta_i_average: float, delta_j_average: float):
    left, upper = self._roof_layer_info.origin_dsm_grid_xyzs[0, 0][:2]
    x = float(left + (j + delta_j_average) * self._grid_size)
    y = float(upper - (i + delta_i_average) * self._grid_size)
    return (x, y)
