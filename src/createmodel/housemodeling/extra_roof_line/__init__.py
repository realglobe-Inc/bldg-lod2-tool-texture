from collections import defaultdict
import os
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .polygon_devision import PolygonDevision
from ..extra_roof_line.utils.merge_close_vertices import merge_close_vertices
from ..extra_roof_line.utils.line_group import LineGroup
from ..utils.polys import ensure_counter_clockwise, get_polys_from_polygon_ijs_list, validate_polygon_ijs_list
from ..roof_layer_info import RoofLayerInfo
from ....util.objinfo import BldElementType, ObjInfo
from ....createmodel.createmodelexception import ModelingException
from ....createmodel.message import ModelingMessage


class ExtraRoofLine:
  @property
  def new_polygon_vertex_xys(self):
    """
    Returns:
      list[tuple[float, float]]: ポリゴン分割後の頂点リスト(x,y)
    """

    return self._new_polygon_vertex_xys

  @property
  def new_polygon_vertex_ijs(self):
    """
    Returns:
      list[tuple[float, float]]: ポリゴン分割後の頂点リスト(i,j)
    """

    return self._new_polygon_vertex_ijs

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
      id: str,
      shape: Polygon,
      inner_polygon_ijs_list_before: list[list[tuple[float, float]]],
      roof_layer_info: RoofLayerInfo,
      grid_size: float,
      debug_mode: bool = False
  ):
    """
    HEAT が出せてない屋根線を追加

    Args:
      id (str): 建物id
      shape (Polygon): 建物外形ポリゴン
      inner_polygon_ijs_list_before (list[list[tuple[float, float]]]): 複数のポリゴンの頂点(i,j)リスト
      roof_layer_info (RoofLayerInfo): DSM点群から屋根の階層分離をするための情報
      grid_size (float): 点群の間隔(meter)
      debug_mode (bool): デバッグモード
    """
    self._id = id
    self._shape = shape
    self._inner_polygon_ijs_list_before: list[list[tuple[float, float]]] = [
        ensure_counter_clockwise(inner_polygon_ijs) for inner_polygon_ijs in inner_polygon_ijs_list_before
    ]
    self._roof_layer_info = roof_layer_info
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

    try:
      self._inner_polygon_ijs_list_after = self._get_inner_polygon_ijs_list_after(
          self._inner_polygon_ijs_list_before
      )
    except Exception as e:
      print(f"To Do: 屋根ポリゴン分割のバグ修正({e})")
      # traceback.print_exc()
      self._inner_polygon_ijs_list_after = self._inner_polygon_ijs_list_before

    validate_polygon_ijs_list(self._inner_polygon_ijs_list_after)

    self._new_polygon_vertex_ijs = list(set([
        polygon_ij
        for polygon_ijs in self._inner_polygon_ijs_list_after
        for polygon_ij in polygon_ijs
    ]))

    self._inner_polygon_xys_list, self._outer_polygon_xys = self._to_polygon_xys(
        self._inner_polygon_ijs_list_after,
    )

    self._new_polygon_vertex_xys = [self._ij_to_xy(ij) for ij in self._new_polygon_vertex_ijs]

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
        self._roof_layer_info.masked_dsm_grid_rgbs,
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

  def _get_inner_polygon_ijs_list_after(self, inner_polygon_ijs_list_before: list[list[tuple[float, float]]]):
    """
    HEATの不完全な屋根線で作られたポリゴン(inner_polygon_ijs_list_before)にから一部の不完全なポリガンを分割する

    Args:
      inner_polygon_ijs_list_before (list[list[tuple[float, float]]]): 複数のポリゴンの頂点(i,j)リスト

    Return
      list[list[tuple[float, float]]]: 複数のポリゴンの頂点(i,j)リスト
    """

    tmp_inner_polygon_ijs_list_after: list[list[tuple[float, float]]] = []
    self._has_splited_polygon = False

    edge_added_new_point_ijs_pair: dict[
        tuple[tuple[float, float], tuple[float, float]], list[tuple[float, float]]
    ] = defaultdict(list)
    for polygon_ijs_before in inner_polygon_ijs_list_before:
      polygon_devision = PolygonDevision(polygon_ijs_before, self._roof_layer_info, self._debug_mode)
      tmp_inner_polygon_ijs_list_after.extend(polygon_devision.splited_polygon_ijs_list)

      if polygon_devision.has_splited_polygon:
        self._has_splited_polygon = True

        polys = get_polys_from_polygon_ijs_list(polygon_devision.splited_polygon_ijs_list)
        polys_area = unary_union(polys)

        # ポリゴンが分割された場合、新しい頂点が生成される。外注ポリゴンを取得
        splited_polygon_outer_ijs: list[tuple[float, float]] = ensure_counter_clockwise(
            list(polys_area.exterior.coords[:-1])
        )

        # ポリゴン分割によって、新しく追加された頂点は他のポリゴンにも追加しないといけない
        for index, polygon_ij in enumerate(polygon_ijs_before):
          next_index = (index + 1) % len(polygon_ijs_before)
          next_polygon_ij = polygon_ijs_before[next_index]

          sorted_edge = tuple(sorted([polygon_ij, next_polygon_ij]))

          splited_polygon_outer_ij_index = splited_polygon_outer_ijs.index(polygon_ij)
          next_splited_polygon_outer_ij_index = splited_polygon_outer_ijs.index(next_polygon_ij)
          index_distance = abs(next_splited_polygon_outer_ij_index - splited_polygon_outer_ij_index)

          if (index_distance != 1 or index_distance != (len(splited_polygon_outer_ijs) - 1)):
            start_index = (splited_polygon_outer_ij_index + 1) % len(splited_polygon_outer_ijs)
            end_index = next_splited_polygon_outer_ij_index
            curren_index = start_index

            while curren_index != end_index:
              new_polygon_outer_ij = splited_polygon_outer_ijs[curren_index]

              # エッジを基準に、追加された頂点を他のポリゴンにも追加する
              edge_added_new_point_ijs_pair[sorted_edge].append(new_polygon_outer_ij)
              curren_index = (curren_index + 1) % len(splited_polygon_outer_ijs)

    # エッジを基準に、追加された頂点を他のポリゴンにも追加する
    tmp_inner_polygon_ijs_list_after2: list[list[tuple[float, float]]] = []
    for before_polygon_ijs in tmp_inner_polygon_ijs_list_after:
      after_polygon_ijs: list[tuple[float, float]] = []
      for index, before_polygon_ij in enumerate(before_polygon_ijs):
        after_polygon_ijs.append(before_polygon_ij)
        next_index = (index + 1) % len(before_polygon_ijs)
        next_before_polygon_ij = before_polygon_ijs[next_index]

        sorted_edge = tuple(sorted([before_polygon_ij, next_before_polygon_ij]))
        new_point_ijs = edge_added_new_point_ijs_pair.get(sorted_edge) or []
        if new_point_ijs:
          is_same_index_direction = (sorted_edge == (before_polygon_ij, next_before_polygon_ij))
          sorted_new_point_ijs = sorted(new_point_ijs) if is_same_index_direction else reversed(sorted(new_point_ijs))
          after_polygon_ijs.extend(sorted_new_point_ijs)

      tmp_inner_polygon_ijs_list_after2.append(after_polygon_ijs)

    validate_polygon_ijs_list(tmp_inner_polygon_ijs_list_after2)

    # 傾きと切片で同じ直線上にある頂点をグループ化
    tmp_line_group = self._get_line_group(tmp_inner_polygon_ijs_list_after2)
    tmp_polys = get_polys_from_polygon_ijs_list(tmp_inner_polygon_ijs_list_after2)
    tmp_polys_area: Polygon = unary_union(tmp_polys)

    tmp_outer_polygon_edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for index, coord in enumerate(tmp_polys_area.exterior.coords):
      next_coord = tmp_polys_area.exterior.coords[(index + 1) % len(tmp_polys_area.exterior.coords)]
      sorted_edge: tuple[tuple[float, float], tuple[float, float]] = tuple(sorted([coord, next_coord]))
      tmp_outer_polygon_edges.append(sorted_edge)

    tmp_inner_polygon_ijs_list_after3: list[list[tuple[float, float]]] = []
    for tmp_inner_polygon_ijs in tmp_inner_polygon_ijs_list_after2:
      new_inner_polygon_ijs: list[tuple[float, float]] = []
      for index, coord in enumerate(tmp_inner_polygon_ijs):
        next_index = ((index + 1) % len(tmp_inner_polygon_ijs))
        next_next_index = ((index + 2) % len(tmp_inner_polygon_ijs))
        next_coord = tmp_inner_polygon_ijs[next_index]
        next_next_coord = tmp_inner_polygon_ijs[next_next_index]

        line_group_key = tmp_line_group.get_line_group_key(coord, next_coord)
        next_line_group_key = tmp_line_group.get_line_group_key(next_coord, next_next_coord)

        # ポリゴンのトゲ削除
        if line_group_key == next_line_group_key:
          _, coord2, _ = sorted([coord, next_coord, next_next_coord])

          if next_coord != coord2:
            continue

        new_inner_polygon_ijs.append(next_coord)

      tmp_inner_polygon_ijs_list_after3.append(new_inner_polygon_ijs)

    # 傾きと切片で同じ直線上にあるエッジの頂点をグループ化
    tmp_line_group2 = self._get_line_group(tmp_inner_polygon_ijs_list_after3)

    # ポリゴンに頂点を追加する
    new_polys: list[Polygon] = []
    inner_polygon_ijs_list_after: list[list[tuple[float, float]]] = []
    for tmp_inner_polygon_ijs in tmp_inner_polygon_ijs_list_after3:
      new_inner_polygon_ijs = []
      for index, inner_polygon_ij in enumerate(tmp_inner_polygon_ijs):
        next_index = (index + 1) % len(tmp_inner_polygon_ijs)
        next_inner_polygon_ij = tmp_inner_polygon_ijs[next_index]
        tmp_line_group2.add_line(inner_polygon_ij, next_inner_polygon_ij)

        # 始点と終点の直線上に中間点がある場合、中間点も挟む
        line_point_ijs = tmp_line_group2.get_line_group(inner_polygon_ij, next_inner_polygon_ij)
        if line_point_ijs is not None:
          sorted_line_point_ijs = sorted(list(line_point_ijs))
          start_index = sorted_line_point_ijs.index(inner_polygon_ij)
          end_index = sorted_line_point_ijs.index(next_inner_polygon_ij)

          # 始点、中間点、終点を追加
          is_added = False
          range_direction = -1 if start_index > end_index else 1
          for sorted_point_ij_index in range(start_index, end_index, range_direction):
            new_inner_polygon_ij = sorted_line_point_ijs[sorted_point_ij_index]
            if new_inner_polygon_ij not in new_inner_polygon_ijs:
              new_inner_polygon_ijs.append(new_inner_polygon_ij)
              is_added = True

          if is_added is False:
            if inner_polygon_ij not in new_inner_polygon_ijs:
              new_inner_polygon_ijs.append(inner_polygon_ij)
        else:
          # 始点を追加
          if inner_polygon_ij not in new_inner_polygon_ijs:
            new_inner_polygon_ijs.append(inner_polygon_ij)

      new_poly = Polygon(new_inner_polygon_ijs)
      validate_polygon_ijs_list([new_inner_polygon_ijs])

      new_polys.append(new_poly)
      inner_polygon_ijs_list_after.append(new_inner_polygon_ijs)

    new_polys_area = unary_union(new_polys)
    assert len(new_polys_area.interiors) == 0, "分割されたポリゴンに隙間があります"
    if not len(new_polys_area.interiors) == 0:
      raise ModelingException(ModelingMessage.ERR_POLYGON_DIVISION_FAIL)

    merged_inner_polygon_ijs_list_after = merge_close_vertices(inner_polygon_ijs_list_after)

    if self._debug_mode:
      extra_roof_line_poligons_2d = ObjInfo()
      for polygon_idx, tmp_inner_polygon_ijs in enumerate(merged_inner_polygon_ijs_list_after):
        polygon_layer_ijs: list[tuple[float, float, float]] = []
        for i, j in tmp_inner_polygon_ijs:
          polygon_layer_ijs.append((i, j, 2 * polygon_idx))
        extra_roof_line_poligons_2d.append_faces(BldElementType.ROOF, [polygon_layer_ijs])

      debug_dir = os.path.join('debug', self._id)
      Path(debug_dir).mkdir(parents=True, exist_ok=True)
      extra_roof_line_poligons_2d_path = os.path.join(debug_dir, 'extra_roof_line_poligons_2d.obj')
      extra_roof_line_poligons_2d.write_file(file_path=extra_roof_line_poligons_2d_path)

    return merged_inner_polygon_ijs_list_after

  def _to_polygon_xys(self, inner_polygon_ijs_list: list[list[tuple[float, float]]]):
    """
    複数の内部ポリゴンの頂点(i,j)リスト(inner_polygon_ijs_list)にから
    複数の内部ポリゴンの頂点(x,y)リストと外周ポリゴンの頂点(x,y)リスト変換

    Args:
      inner_polygon_ijs_list (list[list[tuple[float, float]]]): 複数の内部ポリゴンの頂点(i,j)リスト

    Return
      list[list[tuple[float, float]]]: 複数の内部ポリゴンの頂点(x,y)リスト
      list[tuple[float, float]]: 外周ポリゴンの頂点(x,y)リスト
    """

    after_polygon_xys_list = [
        [self._ij_to_xy(polygon_ij) for polygon_ij in polygon_ijs]
        for polygon_ijs in inner_polygon_ijs_list
    ]
    xy_polys = get_polys_from_polygon_ijs_list(after_polygon_xys_list)
    # ij_polys = get_polys_from_polygon_ijs_list(inner_polygon_ijs_list)

    xy_polys_area = unary_union(xy_polys)
    # ij_polys_area = unary_union(ij_polys)

    assert isinstance(xy_polys_area, Polygon), 'ポリゴン分割に失敗しました'
    if not isinstance(xy_polys_area, Polygon):
      raise ModelingException(ModelingMessage.ERR_POLYGON_DIVISION_FAIL)

    after_outer_polygon_xys = list(xy_polys_area.exterior.coords[:-1])

    return after_polygon_xys_list, after_outer_polygon_xys

  def _ij_to_xy(self, ij: tuple[float, float]):
    """
    ij 座標(画像の Pixel 座標)を xy 座標(DSM 座標)に変換

    Args:
      ij (float): 画像の Pixel 座標

    Return
      tuple[float, float]: DSM 座標
    """

    # 可能な xy 座標範囲
    x_coords = [point[0] for point in self._shape.exterior.coords]
    y_coords = [point[1] for point in self._shape.exterior.coords]
    x_min = min(x_coords)
    x_max = max(x_coords)
    y_min = min(y_coords)
    y_max = max(y_coords)

    # xy 座標と ij 座標の間隔比率
    x_width = x_max - x_min
    y_height = y_max - y_min
    j_height, i_width = self._roof_layer_info.masked_dsm_grid_rgbs.shape[:2]
    x_width_per_i_width = x_width / i_width
    y_height_per_j_height = y_height / j_height

    # ij -> xy の変換
    i, j = ij
    x = x_min + (j * y_height_per_j_height)
    y = y_max - (i * x_width_per_i_width)

    # float 演算浮動小数点誤差の制御パッチ : 丸めて誤差を抑える
    return round(x, 6), round(y, 6)

  def _get_line_group(self, inner_polygon_ijs_list: list[list[tuple[float, float]]]):
    """傾きと切片で同じ直線上にあるエッジの頂点をグループ化

    Args:
      inner_polygon_ijs_list: list[list[tuple[float, float]]]

    Return
      LineGroup: 同じ直線上にあるエッジの頂点
    """
    line_group = LineGroup()
    for inner_polygon_ijs in inner_polygon_ijs_list:
      for index, inner_polygon_ij in enumerate(inner_polygon_ijs):
        next_index = (index + 1) % len(inner_polygon_ijs)
        next_inner_polygon_ij = inner_polygon_ijs[next_index]
        line_group.add_line(inner_polygon_ij, next_inner_polygon_ij)

    return line_group
