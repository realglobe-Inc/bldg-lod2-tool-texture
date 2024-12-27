from collections import defaultdict
import itertools
from typing import Union

from shapely.geometry import Polygon, GeometryCollection, Point as GeoPoint
from shapely.ops import unary_union
import numpy as np


def get_polys_from_geometry_collections(geometry_collections: list[GeometryCollection]):
  """shapely オブジェクトリストの中で、ポリゴン形状をだけ抜き取る

  Args:
    geometry_collections (list[GeometryCollection]): shapely オブジェクトリスト

  Returns:
    list[Polygon]: ポリゴンリスト
  """

  polys: list[Polygon] = []
  for geometry_collection in geometry_collections:
    if not geometry_collection.is_empty:
      if isinstance(geometry_collection, Polygon):
        polys.append(geometry_collection)
      else:
        for poly in geometry_collection.geoms:
          if isinstance(poly, Polygon):
            polys.append(poly)

  return polys


def get_polys_from_polygon_ijs_list(polygon_ijs_list: list[list[tuple[float, float]]]):
  """複数ポリゴンの頂点リストから、ポリゴンリストを出す

  Args:
    polygon_ijs_list: list[list[tuple[float, float]]]

  Returns:
    list[Polygon]: ポリゴンリスト
  """

  geometry_collections: list[GeometryCollection] = []
  # validate_polygon_ijs_list(polygon_ijs_list)

  for polygon_ijs in polygon_ijs_list:
    poly: GeometryCollection = Polygon(polygon_ijs)
    geometry_collections.append(poly)

  polys = get_polys_from_geometry_collections(geometry_collections)

  return polys


def get_polygon_ijs_list(geometry_collections: list[GeometryCollection]):
  polygon_ijs_list: list[list[tuple[float, float]]] = []
  polys = get_polys_from_geometry_collections(geometry_collections)
  for poly in polys:
    polygon_ijs = list(poly.exterior.coords[:-1])
    polygon_ijs_list.append(polygon_ijs)

  return polygon_ijs_list


def calculate_shared_length(polygon1: Polygon, polygon2: Polygon) -> float:
  """
  2つのポリゴン間の共有辺の長さを計算します。

  Args:
      polygon1 (Polygon): 1つ目のポリゴン。
      polygon2 (Polygon): 2つ目のポリゴン。

  Returns:
      float: 共有辺の長さ。
  """
  return polygon1.intersection(polygon2).length


def find_final_parent(polygon_id: int, longest_neighbor_map: dict[int, tuple[int, float]]):
  """
  指定されたポリゴンIDの最終親を探します。

  Args:
    polygon_id (int): 探索を開始するポリゴンID。
    longest_neighbor_map (dict): 各ポリゴンIDから親ポリゴンIDへのマッピング。

  Returns:
    int: 最終的な親ポリゴンID。
  """
  current_id = polygon_id
  visited = set()  # 無限ループを防ぐため、訪問済みのIDを記録

  while current_id in longest_neighbor_map:
    parent_id = longest_neighbor_map[current_id][0]
    if parent_id == current_id or parent_id in visited:
        # 自己参照または既に訪れたIDに戻る場合は終了
      break
    visited.add(current_id)
    current_id = parent_id

  return current_id


def merge_small_polys_into_large_polys(
    polygon_ijs_list: list[list[tuple[float, float]]], small_threshold_area=40,
):
  """
  小さいポリゴンを共有辺の長さに基づいて大きなポリゴンに合併します。

  Args:
    polygon_ijs_list (list[list[tuple[float, float]]]): ポリゴンの頂点リスト。
    small_threshold_area (float, optional): 小さいポリゴンとみなす面積のしきい値。デフォルトは40。

  Returns:
    list[list[tuple[float, float]]]: 合併後のポリゴン頂点リスト。
  """
  origin_polys = get_polys_from_polygon_ijs_list(polygon_ijs_list)

  # 各ポリゴンのIDとその隣接ポリゴンのうち、最長共有エッジを持つポリゴンのIDを記録する辞書
  longest_neighbor_map: dict[int, tuple[int, float]] = {}
  # ポリゴンペアを生成して、共有エッジの長さを計算
  for (i, poly_a), (j, poly_b) in itertools.combinations(enumerate(origin_polys), 2):
    share_edge_length_sum = calculate_shared_length(poly_a, poly_b)
    # 両方のポリゴンについて、より長い共有エッジを持つポリゴンを更新
    if i not in longest_neighbor_map or longest_neighbor_map[i][1] < share_edge_length_sum:
      longest_neighbor_map[i] = (j, share_edge_length_sum)
    if j not in longest_neighbor_map or longest_neighbor_map[j][1] < share_edge_length_sum:
      longest_neighbor_map[j] = (i, share_edge_length_sum)

  small_polygon_ids = [
      polygon_id for polygon_id, origin_poly in enumerate(origin_polys) if origin_poly.area < small_threshold_area
  ]
  last_parent_polygon_id_small_polygon_ids_pair: dict[int, list[int]] = defaultdict(list)

  for small_polygon_id in small_polygon_ids:
    last_polygon_parent_id = find_final_parent(small_polygon_id, longest_neighbor_map)
    last_parent_polygon_id_small_polygon_ids_pair[last_polygon_parent_id].append(small_polygon_id)

  merged_polygon_ids: list[int] = []
  merged_polygon_ijs_list: list[list[tuple[float, float]]] = []
  for last_parent_polygon_id, small_polygon_ids in last_parent_polygon_id_small_polygon_ids_pair.items():
    group_polygon_ids = [last_parent_polygon_id, *small_polygon_ids]
    target_polys = [Polygon(polygon_ijs_list[polygon_id]) for polygon_id in group_polygon_ids]
    target_polys_area = unary_union(target_polys)
    target_polygon_ijs_list = get_polygon_ijs_list([target_polys_area])
    merged_polygon_ijs_list.extend(target_polygon_ijs_list)
    merged_polygon_ids.extend(group_polygon_ids)

  not_merged_polygon_ijs_list = [
      polygon_ijs_list[polygon_id]
      for polygon_id in range(len(polygon_ijs_list)) if polygon_id not in merged_polygon_ids
  ]

  return merged_polygon_ijs_list + not_merged_polygon_ijs_list


def validate_polygon_ijs_list(polygon_ijs_list: list[list[tuple[float, float]]]):
  """ポリゴンの頂点リストのポリゴンが正しいか検証する

  Args:
    polygon_ijs_list (list[list[tuple[float, float]]]): ポリゴンの頂点リスト。
  """

  edge_polygon_ids_pair: dict[tuple[tuple[float, float], tuple[float, float]], list] = defaultdict(list)
  polys: list[Polygon] = []

  # ポリゴン形状検査
  for polygon_id, polygon_ijs in enumerate(polygon_ijs_list):
    assert len(polygon_ijs) >= 3, "不正ポリゴンです"

    poly: Polygon = Polygon(polygon_ijs)
    assert isinstance(poly, Polygon), "不正ポリゴンです"
    assert poly.is_valid, "不正ポリゴンです"
    assert poly.area >= 1e-9, "ポリゴンが小さすぎます"

    for index, polygon_ij in enumerate(polygon_ijs):
      next_index = (index + 1) % len(polygon_ijs)
      next_polygon_ij = polygon_ijs[next_index]
      sorted_edge = tuple(sorted([polygon_ij, next_polygon_ij]))
      edge_polygon_ids_pair[sorted_edge].append(polygon_id)

    polys.append(poly)

  # エッジ検査
  for edge, count in edge_polygon_ids_pair.items():
    assert len(count) <= 2, f"三つ以上のポリゴンが一つのエッジ({edge[0]}, {edge[1]})を持つことは不可能です"

  # 被っているポリゴン検査
  has_polys_collision = False
  indexed_polys = list(enumerate(polys))
  for (index_a, poly_a), (index_b, poly_b) in itertools.combinations(indexed_polys, 2):
    if not poly_a.intersection(poly_b).area == 0:
      print(f"ポリゴン{index_a}と{index_b}が被っています")
      has_polys_collision = True

  assert not has_polys_collision, 'ポリゴン被っています'

  # 内部ポリゴンの隙間検査
  polys_area = unary_union(polys)
  assert len(polys_area.interiors) == 0, "分割されたポリゴンに隙間があります"

  # 単一エッジの数検査
  outer_polygon_ijs = list(polys_area.exterior.coords[:-1])
  single_edge_count = sum([1 for polygon_ids in edge_polygon_ids_pair.values() if len(polygon_ids) == 1])
  assert single_edge_count == len(outer_polygon_ijs), "単一エッジの数と外周ポリゴンのエッジの数が一致しません"


def ensure_counter_clockwise(polygon_xyzs: list[Union[tuple[float, float, float], tuple[float, float]]]):
  """
  ポリゴンの頂点が反時計回りになるようにする

  Args:
    polygon_xyzs (list[tuple[float, float]]): ポリゴンの頂点座標リスト

  Returns:
    list[int]: 反時計回りにしたポリゴン
  """
  polygon_xys = np.array(polygon_xyzs)[:, :2]
  poly = Polygon(polygon_xys)
  if not poly.exterior.is_ccw:
    # 時計回りなら反転させる
    return polygon_xyzs[::-1]

  return polygon_xyzs


def get_grid_point_ijs(poly: Polygon):
  """ポリゴン内部に含まれる整数座標を探す

  Args:
    poly (Polygon): ポリゴン

  Returns:
    list[tuple[int, int]]: ポリゴン内部に含まれる整数座標
  """
  poly_min_i, poly_min_j, poly_max_i, poly_max_j = poly.bounds
  grid_point_ijs: list[tuple[int, int]] = []
  for i in range(int(poly_min_i), int(poly_max_i) + 1):
    for j in range(int(poly_min_j), int(poly_max_j) + 1):
      if poly.contains(GeoPoint(i, j)):  # 点がポリゴン内にあるかを判定
        grid_point_ijs.append((i, j))

  return grid_point_ijs
