import numpy as np


def merge_close_vertices(polygon_ijs_list: list[list[tuple[float, float]]], threshold: float = 1e-5):
  """
  近い点をマージする

  Args:
      polygon_ijs_list (list[list[tuple[float, float]]]): 頂点のリスト
      threshold (float): マージとみなす距離のしきい値

  Returns:
      list[list[tuple[float, float]]]
  """
  # 頂点を一意化
  vertex_ijs = list(set([
      polygon_ij
      for polygon_ijs in polygon_ijs_list
      for polygon_ij in polygon_ijs
  ]))

  merged_vertice_ijs = []
  change_map = {}  # 変更前後の頂点対応を保持

  for vertex_ij in vertex_ijs:
    merged_to_existing = False

    for merged_vertex_ij in merged_vertice_ijs:
      # 距離が threshold 以下ならマージ
      if np.linalg.norm(np.array(vertex_ij) - np.array(merged_vertex_ij)) < threshold:
        # i+j の合計値が小さい方を残す
        if sum(vertex_ij) < sum(merged_vertex_ij):
          change_map[merged_vertex_ij] = vertex_ij  # 既存を新規にマップ
          merged_vertice_ijs.remove(merged_vertex_ij)
          merged_vertice_ijs.append(vertex_ij)
        else:
          change_map[vertex_ij] = merged_vertex_ij  # 新規を既存にマップ
        merged_to_existing = True
        break

    if not merged_to_existing:
      merged_vertice_ijs.append(vertex_ij)

  # 変更マップを適用してポリゴンを更新
  merged_polygon_ijs_list: list[list[tuple[float, float]]] = []
  for polygon_ijs in polygon_ijs_list:
    merged_polygon_ijs = [
        change_map.get(polygon_ij, polygon_ij)  # 変更された頂点に置換
        for polygon_ij in polygon_ijs
    ]
    merged_polygon_ijs_list.append(merged_polygon_ijs)

  return merged_polygon_ijs_list
