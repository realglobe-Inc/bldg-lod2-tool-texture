from collections import defaultdict
import statistics
import copy

from shapely.geometry import Polygon

from .utils.polys import get_grid_point_ijs
from .utils.points import find_closest_point
from .extra_roof_line.polygon_devision import PolygonDevision
from .roof_layer_info import RoofLayerInfo


class ModelEdgeHeightInfo:
  """3Dモデルを作るとき、エッジの高さを先に取得して、設計安定性を上げる"""

  @property
  def fixed_sorted_edge_wall_bottom_top_pair(self):
    """エッジの壁面の高さ情報

    Returns:
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジの壁面の高さ情報
    """
    return self._fixed_sorted_edge_wall_bottom_top_pair

  @property
  def fixed_polygon_zs_list(self):
    """エッジの屋根面のの高さ情報

    Returns:
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジの屋根面のの高さ情報
    """
    return self._fixed_polygon_zs_list

  @property
  def fixed_roof_polygon_vertex_xys(self):
    """屋根面頂点の2次元座標(x,y)

    Returns:
      list[tuple[float, float]]: 屋根面頂点の2次元座標(x,y)
    """
    return self._fixed_roof_polygon_vertex_xys

  @property
  def fixed_roof_polygon_vertex_ijs(self):
    """屋根面頂点の2次元座標(i,j)

    Returns:
      list[tuple[float, float]]: 屋根面頂点の2次元座標(x,y)
    """
    return self._fixed_roof_polygon_vertex_ijs

  @property
  def fixed_inner_polygons(self):
    """区切られた各屋根面ポリゴン

    Returns:
      list[list[int]]: 区切られた各屋根面ポリゴン
    """
    return self._fixed_inner_polygons

  def __init__(
      self,
      roof_layer_info: RoofLayerInfo,
      roof_polygon_vertex_ijs: list[tuple[float, float]] = [],
      roof_polygon_vertex_xys: list[tuple[float, float]] = [],
      inner_polygons: list[list[int]] = [],
      outer_polygon: list[int] = [],
      polygon_balcony_flags: list[bool] = [],
      ground_height: float = 0,
  ):
    """コンストラクタ

    Args:
      roof_layer_info (RoofLayerInfo): DSM点群から屋根の階層分離をするための情報
      roof_polygon_vertex_ijs (list[tuple[float, float]]): 屋根面頂点の2次元座標(i,j)
      roof_polygon_vertex_xys (list[tuple[float, float]]): 屋根面頂点の2次元座標(x,y)
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      outer_polygon (list[int]): 屋根面の外形ポリゴン
      polygon_balcony_flags (list[bool]): ポリゴンがバルコニーか
      ground_height (float): 地面の高さm
    """
    self._roof_layer_info = roof_layer_info
    self._roof_polygon_vertex_ijs = roof_polygon_vertex_ijs
    self._roof_polygon_vertex_xys = roof_polygon_vertex_xys
    self._inner_polygons = inner_polygons
    self._outer_polygon = outer_polygon
    self._polygon_balcony_flags = polygon_balcony_flags
    self._ground_height = ground_height

    # 屋根の最低高さ
    self._min_roof_height = self._ground_height + 0.1

    # ポリゴンの屋根階層クラス分析図のリスト
    self._layer_number_point_ijs_pairs = self._get_layer_number_point_ijs_pairs()

    # ポリゴンそれぞれの屋根レイヤー
    self._polygon_layer_numbers = self._get_polygon_layer_numbers(self._layer_number_point_ijs_pairs)

    # 頂点 -> 高さ 検索時に使う
    self._point_id_polygon_layer_zs_pair = self._get_point_id_polygon_layer_zs_pair()

    # 外周ポリゴンのエッジリスト
    self._outer_polygon_sorted_edges = self._get_polygon_sorted_edges(self._outer_polygon)

    # 内部ポリゴン -> エッジ 検索時に使う
    self._polygon_id_inner_polygon_sorted_edges_pair: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for polygon_id, inner_polygon in enumerate(self._inner_polygons):
      inner_polygon_sorted_edges = self._get_polygon_sorted_edges(inner_polygon)
      self._polygon_id_inner_polygon_sorted_edges_pair[polygon_id] = inner_polygon_sorted_edges

    # エッジ -> 内部ポリゴン 検索時に使う
    self._polygon_sorted_edge_polygon_ids_pair: dict[tuple[int, int], list[int]] = defaultdict(list)
    for polygon_id, inner_polygon_sorted_edges in self._polygon_id_inner_polygon_sorted_edges_pair.items():
      for inner_polygon_sorted_edge in inner_polygon_sorted_edges:
        self._polygon_sorted_edge_polygon_ids_pair[inner_polygon_sorted_edge].append(polygon_id)

    # 壁面生成のためエッジの高さ
    sorted_edge_wall_bottom_top_pair = self._get_sorted_edge_wall_bottom_top_pair()

    # 屋根面生成のためエッジの高さ
    polygon_zs_list = self._get_polygon_zs_list()

    # X型交差屋根のエッジの中間点を追加
    (
        self._fixed_roof_polygon_vertex_ijs,
        self._fixed_roof_polygon_vertex_xys,
        self._fixed_inner_polygons,
        self._fixed_sorted_edge_wall_bottom_top_pair,
        self._fixed_polygon_zs_list,
    ) = self._fix_twisted_edge(
        roof_polygon_vertex_ijs,
        roof_polygon_vertex_xys,
        inner_polygons,
        sorted_edge_wall_bottom_top_pair,
        polygon_zs_list,
    )

  def _get_layer_number_point_ijs_pairs(self):
    """ポリゴン毎にポリゴン内部領域に入っている頂点(i,j)の屋根レイヤーを出す

    Return:
      list[dict[int, list[tuple[float, float]]]]: ポリゴン毎のポリゴン内部領域に入っている頂点(i,j)の屋根レイヤー
    """

    layer_number_point_ijs_pairs: list[dict[int, list[tuple[float, float]]]] = []
    for inner_polygon in self._inner_polygons:
      polygon_ijs = [self._roof_polygon_vertex_ijs[point_id] for point_id in inner_polygon]
      layer_number_point_ijs_pair = PolygonDevision.get_layer_number_grid_ijs_pair(
          self._roof_layer_info, polygon_ijs
      )

      layer_number_point_ijs_pairs.append(layer_number_point_ijs_pair)

    return layer_number_point_ijs_pairs

  def _get_polygon_layer_numbers(
      self, layer_number_point_ijs_pairs: list[dict[int, list[tuple[float, float]]]],
  ):
    """ポリゴン毎にポリゴンがどの屋根レイヤーか出す

    Args:
      layer_number_point_ijs_pair (list[dict[int, list[tuple[float, float]]]]): ポリゴン毎にポリゴン内部領域に入っている頂点(i,j)の屋根レイヤーを出したもの

    Return:
      list[int]: ポリゴン毎にポリゴンがどの屋根レイヤーか出したもの
    """

    polygon_layer_numbers: list[int] = []
    for layer_number_point_ijs_pair in layer_number_point_ijs_pairs:
      majority_layer_number = PolygonDevision.get_majority_layer_number(layer_number_point_ijs_pair)
      polygon_layer_numbers.append(majority_layer_number)

    return polygon_layer_numbers

  def _get_point_id_polygon_layer_zs_pair(self):
    # 頂点 -> 高さ 検索時に使う
    point_id_polygon_layer_zs_pair: dict[int, dict[int, dict[int, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for polygon_id, inner_polygon in enumerate(self._inner_polygons):
      # ポリゴンの中にある頂点(ノイズを除いて)
      polygon_layer_number = self._polygon_layer_numbers[polygon_id]
      layer_number_point_ijs_pair = self._layer_number_point_ijs_pairs[polygon_id]
      available_polygon_ijs = layer_number_point_ijs_pair[polygon_layer_number]
      for point_id in inner_polygon:
        is_balcony_polygon = self._polygon_balcony_flags[polygon_id]
        if is_balcony_polygon:
          # バルコニーポリゴンの場合、バルコニーポリゴンの内部のDSM点群の一番小さい高さにする
          balcony_z = self._get_balcony_z(polygon_id) if is_balcony_polygon else self._min_roof_height
          point_id_polygon_layer_zs_pair[point_id][polygon_layer_number][polygon_id] = balcony_z
        else:
          # 頂点と一番近い頂点をの座標(i,j)をポリゴン内部から検索
          point_ij = self._roof_polygon_vertex_ijs[point_id]
          nearest_layer_number_point_ij = find_closest_point(point_ij, available_polygon_ijs)
          # ポリゴンの頂点での壁の高さを取得
          nearest_z = self._roof_layer_info.ij_to_z(*nearest_layer_number_point_ij) if nearest_layer_number_point_ij is not None else 0
          # 高さが取得できてなくて nearest_z が 0 の場合、地面高さ + 0.1 とする。
          point_z = max(nearest_z, self._min_roof_height)
          # 頂点(i,j)周辺の高さを保存(屋根レイヤー毎に)
          point_id_polygon_layer_zs_pair[point_id][polygon_layer_number][polygon_id] = point_z

    return point_id_polygon_layer_zs_pair

  def _get_polygon_sorted_edges(self, polygon: list[int]):
    """ポリゴンのエッジリストを取得

    Args:
      polygon (list[int]): ポリゴンの頂点番号

    Return:
      list[tuple[int, int]]: ポリゴンのエッジリスト
    """

    sorted_edges: list[tuple[int, int]] = []
    for index, point_id in enumerate(polygon):
      next_index = (index + 1) % len(polygon)
      next_point_id = polygon[next_index]

      sorted_edge = tuple(sorted([point_id, next_point_id]))

      sorted_edges.append(sorted_edge)

    return sorted_edges

  def _get_sorted_edge_wall_bottom_top_pair(self):
    """
    ポリゴンのエッジが壁の場合、エッジに壁の高さを付与

    Returns:
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジに描く壁の高さ
    """
    sorted_edge_wall_bottom_top_pair: dict[
        tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]
    ] = {}

    for polygon_id, inner_polygon_sorted_edges in self._polygon_id_inner_polygon_sorted_edges_pair.items():
      for inner_polygon_sorted_edge in inner_polygon_sorted_edges:
        point_id1, point_id2  = inner_polygon_sorted_edge

        # エッジが外周ポリゴンに含まれる場合、壁を作る
        if inner_polygon_sorted_edge in self._outer_polygon_sorted_edges:
          polygon_layer = self._polygon_layer_numbers[polygon_id]
          average_z1 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id1][polygon_layer].values())
          average_z2 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id2][polygon_layer].values())
          sorted_edge_wall_bottom_top_pair[inner_polygon_sorted_edge] = (
              (self._ground_height, average_z1), (self._ground_height, average_z2)
          )
          continue

        # エッジを共有しているポリゴンは二つ
        polygon_id1, polygon_id2 = self._polygon_sorted_edge_polygon_ids_pair[inner_polygon_sorted_edge]
        polygon_layer1 = self._polygon_layer_numbers[polygon_id1]
        polygon_layer2 = self._polygon_layer_numbers[polygon_id2]

        # エッジの二つの内部ポリゴンの屋根レイヤーが違う場合、壁を作る
        if polygon_layer1 != polygon_layer2:
          # その頂点で屋根レイヤーの高さ平均
          average_z1_1 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id1][polygon_layer1].values())
          average_z1_2 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id1][polygon_layer2].values())
          min_z1 = min(average_z1_1, average_z1_2)
          max_z1 = max(average_z1_1, average_z1_2)

          average_z2_1 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id2][polygon_layer1].values())
          average_z2_2 = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id2][polygon_layer2].values())
          min_z2 = min(average_z2_1, average_z2_2)
          max_z2 = max(average_z2_1, average_z2_2)

          sorted_edge_wall_bottom_top_pair[inner_polygon_sorted_edge] = (
              (min_z1, max_z1), (min_z2, max_z2)
          )

    return sorted_edge_wall_bottom_top_pair

  def _get_polygon_zs_list(self):
    """
    複数のポリゴンの頂点高さリストを取得

    Returns:
      list[list[float]]: 複数のポリゴンの頂点高さリスト
    """
    polygon_zs_list: list[list[float]] = []
    for polygon_id, inner_polygon in enumerate(self._inner_polygons):
      polygon_zs: list[float] = []
      polygon_layer_number = self._polygon_layer_numbers[polygon_id]
      for point_id in inner_polygon:
        average_z = statistics.mean(self._point_id_polygon_layer_zs_pair[point_id][polygon_layer_number].values())
        polygon_zs.append(average_z)

      polygon_zs_list.append(polygon_zs)

    return polygon_zs_list

  def _get_twisted_edge_middle_point_rate_pair(
      self,
      inner_polygons: list[list[int]],
      polygon_zs_list: list[list[float]],
  ):
    """X交差しているエッジの中間点までの距離率を取得

    Args:
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      polygon_zs_list (list[list[float]]): エッジの屋根面のの高さ情報

    Returns:
      dict[tuple[int, int], tuple[float, float]]: X交差しているエッジの中間点までの距離率
    """
    twisted_edge_middle_point_rate_pair: dict[tuple[int, int], tuple[float, float]] = {}
    for inner_polygon_sorted_edges in self._polygon_id_inner_polygon_sorted_edges_pair.values():
      for inner_polygon_sorted_edge in inner_polygon_sorted_edges:
        twisted_edge_zs = self._get_twisted_edge_zs(
            inner_polygon_sorted_edge, inner_polygons, polygon_zs_list
        )
        if twisted_edge_zs is not None:
          (point1_z1, point1_z2), (point2_z1, point2_z2) = twisted_edge_zs

          height_z1 = abs(point1_z1 - point1_z2)
          height_z2 = abs(point2_z1 - point2_z2)

          point_rate1 = height_z1 / (height_z2 + height_z1)
          twisted_edge_middle_point_rate_pair[inner_polygon_sorted_edge] = point_rate1

    return twisted_edge_middle_point_rate_pair

  def _get_twisted_edge_zs(
      self,
      sorted_edge: tuple[int, int],
      inner_polygons: list[list[int]],
      polygon_zs_list: list[list[float]],
  ):
    """エッジが X交差しているか確認
    ### X交差している
    - 交際条件１
      - 頂点１は、向こうの高さが低い、こっちの高さが高い
      - 頂点２は、こっちの高さが高い、向こうの高さが低い
    - 交際条件２
      - 頂点１は、向こうの高さが高い、こっちの高さが低い
      - 頂点２は、こっちの高さが低い、向こうの高さが高い

    ### その他全部：一般エッジ

    Args:
      sorted_edge (tuple[int, int]): エッジ
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      polygon_zs_list (list[list[float]]): エッジの屋根面のの高さ情報

    Return:
      Union[tuple[tuple[float, float], tuple[float, float]], None]: エッジの二つ頂点でそれぞれ二つの高さ（壁の頂点の上と下の二つの高さ）
    """

    # 頂点１, 頂点２
    point_id1, point_id2 = sorted_edge

    # エッジを共有しているポリゴンは二つ
    polygon_ids = self._polygon_sorted_edge_polygon_ids_pair[sorted_edge]
    if len(polygon_ids) != 2:
      return None

    polygon_id1, polygon_id2 = polygon_ids

    # polygon_layer1 = self._polygon_layer_numbers[polygon_id1]
    # polygon_layer2 = self._polygon_layer_numbers[polygon_id2]

    # # エッジの両方のポリゴンが必ず同じ屋根レイヤーの条件で発生
    # if polygon_layer1 != polygon_layer2:
    #   return None

    polygon1 = inner_polygons[polygon_id1]
    polygon2 = inner_polygons[polygon_id2]

    polygon1_point1_index = polygon1.index(point_id1)
    polygon1_point2_index = polygon1.index(point_id2)
    polygon2_point1_index = polygon2.index(point_id1)
    polygon2_point2_index = polygon2.index(point_id2)

    # こっちのポリゴン
    polygon1_zs = polygon_zs_list[polygon_id1]
    # 向こうのポリゴン
    polygon2_zs = polygon_zs_list[polygon_id2]

    # 頂点１のこっちのポリゴンの高さ
    polygon1_z1 = polygon1_zs[polygon1_point1_index]
    # 頂点１の向こうのポリゴンの高さ
    polygon2_z1 = polygon2_zs[polygon2_point1_index]
    # 頂点２のこっちのポリゴンの高さ
    polygon1_z2 = polygon1_zs[polygon1_point2_index]
    # 頂点２の向こうのポリゴンの高さ
    polygon2_z2 = polygon2_zs[polygon2_point2_index]

    # X交差している
    # - 交際条件１
    #   - 頂点１は、向こうの高さが低い、こっちの高さが高い
    #   - 頂点２は、こっちの高さが高い、向こうの高さが低い
    twisted_pattern1 = (polygon1_z1 < polygon2_z1) and (polygon1_z2 > polygon2_z2)

    # X交差している
    # - 交際条件２
    #   - 頂点１は、向こうの高さが高い、こっちの高さが低い
    #   - 頂点２は、こっちの高さが低い、向こうの高さが高い
    twisted_pattern2 = (polygon1_z1 > polygon2_z1) and (polygon1_z2 < polygon2_z2)

    if twisted_pattern1 or twisted_pattern2:
      return ((polygon1_z1, polygon2_z1), (polygon1_z2, polygon2_z2))

    return None

  def _get_balcony_z(self, polygon_id: int):
    balcony_polygon = self._inner_polygons[polygon_id]
    balcony_polygon_ijs = [
        self._roof_polygon_vertex_ijs[point_id] for point_id in balcony_polygon
    ]
    balcony_poly = Polygon(balcony_polygon_ijs)

    grid_point_ijs = get_grid_point_ijs(balcony_poly)
    grid_point_zs = [
        self._roof_layer_info.ij_to_z(*grid_point_ij) for grid_point_ij in grid_point_ijs
    ]
    min_grid_point_z = min(grid_point_zs)
    # 高さが取得できてなくて min_grid_point_z が 0 の場合、地面高さ + 0.1 とする。
    balcony_z = max(min_grid_point_z, self._min_roof_height)

    return balcony_z

  def _fix_twisted_edge(
      self,
      roof_polygon_vertex_ijs: list[tuple[float, float]],
      roof_polygon_vertex_xys: list[tuple[float, float]],
      inner_polygons: list[list[int]],
      sorted_edge_wall_bottom_top_pair: dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]],
      polygon_zs_list: list[list[float]],
  ):
    """X型交差屋根のエッジに中間点を追加

    Args:
      roof_polygon_vertex_ijs (list[tuple[float, float]]): 屋根面頂点の2次元座標(i,j)
      roof_polygon_vertex_xys (list[tuple[float, float]]): 屋根面頂点の2次元座標(x,y)
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      sorted_edge_wall_bottom_top_pair (dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]): エッジの壁面の高さ情報
      polygon_zs_list (list[list[float]]): エッジの屋根面のの高さ情報

    Returns:
      list[tuple[float, float]]: 屋根面頂点の2次元座標(i,j)
      list[tuple[float, float]]: 屋根面頂点の2次元座標(x,y)
      list[list[int]]: 区切られた各屋根面ポリゴン
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジの壁面の高さ情報
      list[list[float]]: エッジの屋根面のの高さ情報
    """
    twisted_edge_middle_point_rate_pair = self._get_twisted_edge_middle_point_rate_pair(
        inner_polygons, polygon_zs_list
    )
    if not (twisted_edge_middle_point_rate_pair):
      return (
          roof_polygon_vertex_ijs,
          roof_polygon_vertex_xys,
          inner_polygons,
          sorted_edge_wall_bottom_top_pair,
          polygon_zs_list,
      )

    fixed_inner_polygons = copy.deepcopy(inner_polygons)
    fixed_roof_polygon_vertex_xys = copy.deepcopy(roof_polygon_vertex_xys)
    fixed_roof_polygon_vertex_ijs = copy.deepcopy(roof_polygon_vertex_ijs)
    fixed_sorted_edge_wall_bottom_top_pair = copy.deepcopy(sorted_edge_wall_bottom_top_pair)
    fixed_polygon_zs_list = copy.deepcopy(polygon_zs_list)

    for twisted_edge, middle_point_rate in twisted_edge_middle_point_rate_pair.items():
      new_point_id = len(fixed_roof_polygon_vertex_xys)

      # xy, ij の中間点を追加
      edge_point1 = twisted_edge[0]
      edge_point2 = twisted_edge[1]
      edge_xy1 = roof_polygon_vertex_xys[edge_point1]
      edge_xy2 = roof_polygon_vertex_xys[edge_point2]
      edge_ij1 = roof_polygon_vertex_ijs[edge_point1]
      edge_ij2 = roof_polygon_vertex_ijs[edge_point2]

      middle_point_xy = self._calculate_midpoint(edge_xy1, edge_xy2, middle_point_rate)
      middle_point_ij = self._calculate_midpoint(edge_ij1, edge_ij2, middle_point_rate)
      fixed_roof_polygon_vertex_xys.append(middle_point_xy)
      fixed_roof_polygon_vertex_ijs.append(middle_point_ij)

      # 屋根高さ z の中間値を追加
      edge_point1_zs, edge_point2_zs = self._get_twisted_edge_zs(
          twisted_edge, inner_polygons, polygon_zs_list
      )
      bottom_z1, top_z1 = sorted(edge_point1_zs)
      bottom_z2, top_z2 = sorted(edge_point2_zs)
      middle_point_z = statistics.mean([bottom_z1, top_z1, bottom_z2, top_z2])
      polygon_ids = self._polygon_sorted_edge_polygon_ids_pair[twisted_edge]
      for polygon_id in polygon_ids:
        point_index1 = fixed_inner_polygons[polygon_id].index(edge_point1)
        point_index2 = fixed_inner_polygons[polygon_id].index(edge_point2)
        min_point_index = min(point_index1, point_index2)
        max_point_index = max(point_index1, point_index2)

        # min_point_index, max_point_index 中間に入れる
        if max_point_index - min_point_index == 1:
          fixed_polygon_zs_list[polygon_id].insert(min_point_index + 1, middle_point_z)
          fixed_inner_polygons[polygon_id].insert(min_point_index + 1, new_point_id)
        else:
          fixed_polygon_zs_list[polygon_id].append(middle_point_z)
          fixed_inner_polygons[polygon_id].append(new_point_id)

      # X型交差屋根の壁をを削除
      if fixed_sorted_edge_wall_bottom_top_pair.keys() in twisted_edge:
        fixed_sorted_edge_wall_bottom_top_pair.pop(twisted_edge)

      # 新しい二つの三角壁を追加
      new_edge1 = (edge_point1, new_point_id)
      new_edge2 = (edge_point2, new_point_id)
      # top_z, bottom_z の高さを一緒にする -> 三角壁を生成
      fixed_sorted_edge_wall_bottom_top_pair[new_edge1] = (
          (bottom_z1, top_z1), (middle_point_z, middle_point_z)
      )
      fixed_sorted_edge_wall_bottom_top_pair[new_edge2] = (
          (bottom_z2, top_z2), (middle_point_z, middle_point_z)
      )

    return (
        fixed_roof_polygon_vertex_ijs,
        fixed_roof_polygon_vertex_xys,
        fixed_inner_polygons,
        fixed_sorted_edge_wall_bottom_top_pair,
        fixed_polygon_zs_list,
    )

  def _calculate_midpoint(
      self,
      edge_xy1: tuple[float, float],
      edge_xy2: tuple[float, float],
      middle_point_rate: float,
  ):
    """ポリゴンのエッジリストを取得

    Args:
      edge_xy1 (tuple[float, float]): エッジの視点
      edge_xy2 (tuple[float, float]): エッジの終点
      middle_point_rate (float): 視点から中間点までの比率(max: 1)

    Return:
      tuple[float, float]: エッジの中間点
    """
    x1, y1 = edge_xy1
    x2, y2 = edge_xy2
    # 中間点の x 座標
    x = x1 + (x2 - x1) * middle_point_rate
    # 中間点の y 座標
    y = y1 + (y2 - y1) * middle_point_rate
    return (x, y)
