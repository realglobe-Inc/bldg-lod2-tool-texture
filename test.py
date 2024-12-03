from shapely.geometry import Polygon
from shapely.ops import unary_union


def calculate_shared_length(polygon1: Polygon, polygon2: Polygon) -> float:
  """
  2つのポリゴン間の共有線の長さを計算。
  """
  return polygon1.intersection(polygon2).length


def find_parent_polygon(
    child: Polygon,
    polygons: list[Polygon],
    parent_map: dict[Polygon, Polygon]
) -> Polygon:
  """
  子ポリゴンの親ポリゴンを再帰的に探す。
  :param child: 子ポリゴン
  :param polygons: 候補のポリゴンリスト
  :param parent_map: すでに親が設定されているポリゴンのマップ
  :return: 親ポリゴン（最終的な大きなポリゴン）
  """
  max_shared_length = 0
  parent = None

  for candidate in polygons:
    if child == candidate:  # 自分自身を親にしない
      continue
    shared_length = calculate_shared_length(child, candidate)
    if shared_length > max_shared_length:
      max_shared_length = shared_length
      parent = candidate

  # 再帰的に親をたどる
  if parent in parent_map:
    return find_parent_polygon(parent, polygons, parent_map)

  return parent


def merge_small_polygons(
    small_polygons: list[Polygon],
    large_polygons: list[Polygon]
) -> list[Polygon]:
  """
  小さいポリゴンを大きなポリゴンに合併。
  :param small_polygons: 小さいポリゴンリスト
  :param large_polygons: 大きいポリゴンリスト
  :return: 合併後のポリゴンリスト
  """
  merged_polygons = large_polygons[:]  # 初期状態は大きなポリゴンリスト
  parent_map: dict[Polygon, Polygon] = {}  # 親子関係を保存

  for child in small_polygons:
    # 子ポリゴンの親ポリゴンを探す
    parent = find_parent_polygon(child, merged_polygons + small_polygons, parent_map)
    if parent:
      # 親を記録
      parent_map[child] = parent

  # 親子関係に基づいて合併
  for child, parent in parent_map.items():
    if parent in merged_polygons:
      # 親が大きいポリゴンの場合、その親と子を統合
      merged_polygons.remove(parent)
      merged_polygons.append(unary_union([child, parent]))

  return merged_polygons


# サンプルデータの準備
polygons: list[Polygon] = [
    Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),  # 小さいポリゴン1
    Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),  # 小さいポリゴン2
    Polygon([(2, 0), (3, 0), (3, 3), (2, 3)]),  # 大きいポリゴン1
    Polygon([(0, 1), (1, 1), (1, 2), (0, 2)])   # 小さいポリゴン3
]

# 小さいポリゴンと大きいポリゴンを分ける
threshold_area = 1.5
small_polygons: list[Polygon] = [p for p in polygons if p.area < threshold_area]
large_polygons: list[Polygon] = [p for p in polygons if p.area >= threshold_area]

# 合併実行
merged_result: list[Polygon] = merge_small_polygons(small_polygons, large_polygons)

# 結果を表示
for i, polygon in enumerate(merged_result):
  print(f"Polygon {i}: {polygon}")
