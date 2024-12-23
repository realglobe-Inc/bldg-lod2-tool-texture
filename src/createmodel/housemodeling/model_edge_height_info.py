from collections import defaultdict
from enum import IntEnum
import statistics

from .utils.points import find_closest_point
from .extra_roof_line.polygon_devision import PolygonDevision
from .roof_layer_info import RoofLayerInfo


class EdgeType(IntEnum):
  """検査・補正結果
  """
  NORMAL = 0                    # エラーなし
  TWISTED = 1                    # エラーなし
  TRIANLGLE = 2                       # エラー有り


class ModelEdgeHeightInfo:
  """3Dモデルを作るとき、エッジの高さを先に取得して、設計安定性を上げる"""

  @property
  def sorted_edge_wall_bottom_top_pair(self):
    """エッジの壁面の高さ情報

    Returns:
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジの壁面の高さ情報
    """
    return self._sorted_edge_wall_bottom_top_pair

  @property
  def polygon_zs_list(self):
    """エッジの屋根面のの高さ情報

    Returns:
      dict[tuple[tuple[int, int]], tuple[tuple[float, float], tuple[float, float]]]: エッジの屋根面のの高さ情報
    """
    return self._polygon_zs_list

  def __init__(
      self,
      roof_layer_info: RoofLayerInfo,
      roof_polygon_vertex_ijs: list[tuple[float, float]] = [],
      inner_polygons: list[list[int]] = [],
      outer_polygon: list[int] = [],
      ground_height: float = 0,
  ):
    """コンストラクタ

    Args:
      roof_layer_info (RoofLayerInfo):
      roof_polygon_vertex_ijs (list[tuple[float, float]]): 屋根面頂点の2次元座標(i,j)
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      outer_polygon (list[int]): 屋根面の外形ポリゴン
    """
    self._roof_layer_info = roof_layer_info
    self._roof_polygon_vertex_ijs = roof_polygon_vertex_ijs
    self._inner_polygons = inner_polygons
    self._outer_polygon = outer_polygon
    self._ground_height = ground_height

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
    self._sorted_edge_wall_bottom_top_pair = self._get_sorted_edge_wall_bottom_top_pair()

    # 屋根面生成のためエッジの高さ
    self._polygon_zs_list = self._get_polygon_zs_list()

  def _get_layer_number_point_ijs_pairs(self):
    """ポリゴン毎にポリゴン内部領域に入っている頂点(i,j)がどの屋根レイヤーを出す

    Return:
      list[dict[int, list[tuple[float, float]]]]: ポリゴン毎にポリゴン内部領域に入っている頂点(i,j)の屋根レイヤーを出したもの
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
      avaliable_polygon_ijs = layer_number_point_ijs_pair[polygon_layer_number]
      for point_id in inner_polygon:
        # 頂点と一番近い頂点をの座標(i,j)をポリゴン内部から検索
        point_ij = self._roof_polygon_vertex_ijs[point_id]
        nearest_layer_number_point_ij = find_closest_point(point_ij, avaliable_polygon_ijs)
        # ポリゴンの頂点での壁の高さを取得
        nearest_z = self._roof_layer_info.ij_to_z(*nearest_layer_number_point_ij)
        # 頂点(i,j)周辺の高さを保存(屋根レイヤー毎に)
        point_id_polygon_layer_zs_pair[point_id][polygon_layer_number][polygon_id] = nearest_z

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

  def get_twisted_edge_middle_point_rate_pair(self):
    """X交差しているエッジの中間点までの距離率を取得

    Returns:
      dict[tuple[int, int], tuple[float, float]]: X交差しているエッジの中間点までの距離率
    """
    # To Do: 特殊なエッジの壁実装
    twisted_edge_middle_point_rate_pair: dict[tuple[int, int], tuple[float, float]] = {}
    for inner_polygon_sorted_edges in self._polygon_id_inner_polygon_sorted_edges_pair.values():
      for inner_polygon_sorted_edge in inner_polygon_sorted_edges:
        edge_type, edge_top_bottom = self.get_edge_type(inner_polygon_sorted_edge)
        if edge_type == EdgeType.TRIANLGLE and edge_top_bottom is not None:
          (point1_z1, point1_z2), (point2_z1, point2_z2) = edge_top_bottom

          height_z1 = abs(point1_z1 - point1_z2)
          height_z2 = abs(point2_z1 - point2_z2)

          point_rate1 = height_z1 / (height_z2 + height_z1)
          twisted_edge_middle_point_rate_pair[inner_polygon_sorted_edge] = point_rate1

    return twisted_edge_middle_point_rate_pair

  def get_edge_type(self, sorted_edge: tuple[int, int], edge_wall_threashold: int = 0.3):
    """エッジが X交差しているか、三角壁か、一般エッジか確認
    ### X交差している
    - 交際条件１
      - 頂点１は、向こうの高さが低い、こっちの高さが高い
      - 頂点２は、こっちの高さが高い、向こうの高さが低い
      - 両店で高低差は edge_wall_threashold 以上
    - 交際条件２
      - 頂点１は、向こうの高さが高い、こっちの高さが低い
      - 頂点２は、こっちの高さが低い、向こうの高さが高い
      - 両店で高低差は edge_wall_threashold 以上

    ### 三角壁
    - 交際条件１
      - 頂点１高低差だけ edge_wall_threashold 以上
    - 交際条件２
      - 頂点２高低差だけ edge_wall_threashold 以上

    ### その他全部：一般エッジ

    Args:
      sorted_edge (tuple[int, int]): エッジ
      edge_wall_threashold (int): X交差と三角形壁判定に必要な最低高さ(基本値 0.3)

    Return:
      EdgeType: エッジのタイプ（X交差、三角壁、普通）
      tuple[tuple[float, float], tuple[float, float]]: エッジの二つ頂点でそれぞれ二つの高さ（壁の頂点の上と下の二つの高さ）
    """

    # 頂点１, 頂点２
    point_id1, point_id2 = sorted_edge

    # エッジを共有しているポリゴンは二つ
    polygon_ids = self._polygon_sorted_edge_polygon_ids_pair[sorted_edge]
    if len(polygon_ids) != 2:
      return EdgeType.NORMAL, None

    polygon_id1, polygon_id2 = polygon_ids
    polygon_layer1 = self._polygon_layer_numbers[polygon_id1]
    polygon_layer2 = self._polygon_layer_numbers[polygon_id2]

    # エッジの両方のポリゴンが必ず同じ屋根レイヤーの条件で発生
    if polygon_layer1 != polygon_layer2:
      return EdgeType.NORMAL, None

    # 頂点１のこっちの高さ
    point1_z1 = self._point_id_polygon_layer_zs_pair[point_id1][polygon_layer1][polygon_id1]
    # 頂点１の向こうの高さ
    point1_z2 = self._point_id_polygon_layer_zs_pair[point_id1][polygon_layer1][polygon_id2]
    # 頂点２のこっちの高さ
    point2_z1 = self._point_id_polygon_layer_zs_pair[point_id2][polygon_layer1][polygon_id1]
    # 頂点２の向こうの高さ
    point2_z2 = self._point_id_polygon_layer_zs_pair[point_id2][polygon_layer1][polygon_id2]

    can_make_rectangle_wall = (abs(point1_z1 - point1_z2) > edge_wall_threashold) and (abs(point2_z1 - point2_z2) > edge_wall_threashold)
    # X交差している
    # - 交際条件１
    #   - 頂点１は、向こうの高さが低い、こっちの高さが高い
    #   - 頂点２は、こっちの高さが高い、向こうの高さが低い
    #   - 高低差は edge_wall_threashold
    twisted_pattern1 = (point1_z1 < point1_z2) and (point2_z1 > point2_z2) and can_make_rectangle_wall

    # X交差している
    # - 交際条件２
    #   - 頂点１は、向こうの高さが高い、こっちの高さが低い
    #   - 頂点２は、こっちの高さが低い、向こうの高さが高い
    #   - 高低差は edge_wall_threashold
    twisted_pattern2 = (point1_z1 > point1_z2) and (point2_z1 < point2_z2) and can_make_rectangle_wall

    if twisted_pattern1 or twisted_pattern2:
      return EdgeType.TWISTED, ((point1_z1, point1_z2), (point2_z1, point2_z2))

    # 三角壁
    # - 交際条件１
    #   - 頂点１高低差だけ edge_wall_threashold 以上
    # - 交際条件２
    #   - 頂点２高低差だけ edge_wall_threashold 以上
    point1_has_wall_heigth = (abs(point1_z1 - point1_z2) > edge_wall_threashold)
    point2_has_wall_heigth = (abs(point2_z1 - point2_z2) > edge_wall_threashold)
    can_make_traignle_wall = (
        (point1_has_wall_heigth and not point2_has_wall_heigth)
        or (not point1_has_wall_heigth and point2_has_wall_heigth)
    )

    if can_make_traignle_wall:
      return EdgeType.TRIANLGLE, None

    return EdgeType.NORMAL, None
