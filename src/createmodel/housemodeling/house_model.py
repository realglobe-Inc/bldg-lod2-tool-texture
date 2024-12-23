from collections import defaultdict
import copy
from dataclasses import dataclass
import itertools
import os
from pathlib import Path
from typing import Union

import numpy as np
import numpy.typing as npt
from shapely.geometry import Polygon
from sklearn.cluster import DBSCAN
from shapely.ops import unary_union


from ...util.objinfo import BldElementType, ObjInfo
from .utils.polys import ensure_counter_clockwise
from .model_surface_creation.utils.triangulation import Triangle, triangulate
from .custom_itertools import pairwise
from .model_surface_creation.utils.geometry_3d import get_angle_degree_3d
from .model_surface_creation.utils.disjoint_set_union import DisjointSetUnion
from .roof_layer_info import RoofLayerInfo
from .model_edge_height_info import ModelEdgeHeightInfo


@dataclass(frozen=True)
class ModelPoint:
  position_id_2d: int
  position_id_3d: int
  order_id: int


@dataclass
class ModelFace:
  points: list[ModelPoint]
  type: BldElementType
  group_id: int

  def edges_2d(self):
    return pairwise([
        point.position_id_2d for point in self.points
    ], loop=True)

  def edges_3d(self):
    return pairwise([
        point.position_id_3d for point in self.points
    ], loop=True)

  @property
  def position_ids_2d(self):
    return [point.position_id_2d for point in self.points]

  @property
  def position_ids_3d(self):
    return [point.position_id_3d for point in self.points]


class HouseModel:
  """家屋モデルクラス
  """

  def __init__(
      self,
      id: str,
      roof_layer_info: RoofLayerInfo,
      roof_polygon_vertex_xys: list[tuple[float, float]] = [],
      roof_polygon_vertex_ijs: list[tuple[float, float]] = [],
      inner_polygons: list[list[int]] = [],
      outer_polygon: list[int] = [],
      ground_height: float = 0,
      polygon_balcony_flags: list[bool] = [],
      debug_mode: bool = False,
  ) -> None:
    """コンストラクタ

    Args:
      id(str): 建物ID
      roof_layer_info (RoofLayerInfo):
      roof_polygon_vertex_xys (list[tuple[float, float]]): 屋根面頂点の2次元座標(x,y)
      roof_polygon_vertex_ijs (list[tuple[float, float]]): 屋根面頂点の2次元座標(i,j)
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン
      outer_polygon (list[int]): 屋根面の外形ポリゴン
      ground_height (float): 地面の高さ
      balcony_height (float): バルコニーの高さ
      polygon_balcony_flags (list[bool]): ポリゴンのバルコニーフラグ
      debug_mode (bool): デバッグモード
    """
    self._id = id
    self._roof_layer_info = roof_layer_info
    self._roof_polygon_vertex_xys = roof_polygon_vertex_xys
    self._roof_polygon_vertex_ijs = roof_polygon_vertex_ijs
    self._inner_polygons = inner_polygons
    self._outer_polygon = outer_polygon
    self._ground_height = ground_height
    self._polygon_balcony_flags = polygon_balcony_flags
    self._debug_mode = debug_mode

    self._faces: list[ModelFace] = []
    self._points = np.zeros((0, 3), dtype=np.float_)

    model_edge_height_info = ModelEdgeHeightInfo(
        roof_layer_info=roof_layer_info,
        roof_polygon_vertex_ijs=roof_polygon_vertex_ijs,
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        ground_height=self._ground_height,
    )

    # 壁面を作る
    self._create_wall_faces(model_edge_height_info.sorted_edge_wall_bottom_top_pair)

    # 屋根面を作る
    self._create_roof_faces(model_edge_height_info.polygon_zs_list)

    # 床面を作る
    self._create_ground_face()

    # 屋根面の単純化
    self._simplify(threshold=5)

    # 壁面非水密エラー修正
    self._rectify()

  @property
  def id(self) -> str:
    """建物ID

    Returns:
      str: 建物ID
    """
    return self._id

  def _add_point(self, position: Union[tuple[float, float, float], npt.NDArray[np.float_]]) -> int:
    """点を追加する

    Args:
      position: Union[tuple[float, float, float], npt.NDArray[np.float_]]: 追加する点の3次元座標

    Returns:
      int: 3次元頂点番号

    Note:
      すでに同じ位置に点が存在している場合は、追加せずにその頂点番号を返す
    """
    position_np = np.array(position, dtype=np.float_)

    # 同じ位置の点が存在する場合には追加しない
    if len(self._points) > 0:
      distances = np.linalg.norm(self._points - position_np, axis=1)
      nearest_point_idx = np.argmin(distances)
      if distances[nearest_point_idx] < 1e-10:
        return int(nearest_point_idx)

    # _pointsの末尾に追加する
    self._points = np.concatenate([self._points, np.array([position_np])])
    return len(self._points) - 1

  def _add_roof(self, points: list[ModelPoint], face_group_id: int):
    """屋根面を追加する

    Args:
        points(list[ModelPoint]): 面の点のリスト (反時計回り)
        face_group_id(int): 面のグループ番号
    """
    self._faces.append(ModelFace(points, BldElementType.ROOF, face_group_id))

  def _add_wall(self, points: list[ModelPoint], face_group_id: int):
    """屋根面を追加する

    Args:
        points(list[ModelPoint]): 面の点のリスト (反時計回り)
        face_group_id(int): 面のグループ番号
    """
    self._faces.append(ModelFace(points, BldElementType.WALL, face_group_id))

  def _add_ground(self, points: list[ModelPoint], face_group_id: int):
    """地面の面を追加する

    Args:
      points(list[ModelPoint]): 面の点のリスト (反時計回り)
      face_group_id(int): 面のグループ番号
    """

    self._faces.append(ModelFace(points, BldElementType.GROUND, face_group_id))

  def _create_wall_faces(
      self,
      sorted_edge_wall_bottom_top_pair: dict[
          tuple[tuple[int, int]],
          tuple[tuple[float, float], tuple[float, float]]
      ],
  ):
    """壁面を作る
    """

    created_wall_edges: list[tuple[int, int]] = []

    for polygon in self._inner_polygons:
      polygon_xys_before = [self._roof_polygon_vertex_xys[point_id] for point_id in polygon]
      polygon_xys_after = ensure_counter_clockwise(polygon_xys_before)

      # 反時計回りに頂点(x,y)の順序を変更
      roof_polygon = copy.deepcopy(polygon)
      if polygon_xys_before[0] != polygon_xys_after[0]:
        roof_polygon = roof_polygon[::-1]

      for index, point_id in enumerate(roof_polygon):
        next_index = (index + 1) % len(roof_polygon)
        next_point_id = roof_polygon[next_index]
        before_edge = [point_id, next_point_id]
        sorted_edge = tuple(sorted(before_edge))

        if sorted_edge in created_wall_edges:
          continue

        # 壁だけ作る
        wall_bottom_top = sorted_edge_wall_bottom_top_pair.get(sorted_edge)
        if wall_bottom_top is None:
          continue

        x, y = self._roof_polygon_vertex_xys[point_id]
        next_x, next_y = self._roof_polygon_vertex_xys[next_point_id]

        if before_edge[0] != sorted_edge[0]:
          (next_bottom_z, next_top_z), (bottom_z, top_z) = wall_bottom_top
        else:
          (bottom_z, top_z), (next_bottom_z, next_top_z) = wall_bottom_top

        # 反時計回りになるように座標(x,y,z)配置
        wall_model_points = [
            ModelPoint(
                position_id_2d=point_id,
                position_id_3d=self._add_point((x, y, bottom_z)),
                order_id=index,
            ),
            ModelPoint(
                position_id_2d=point_id,
                position_id_3d=self._add_point((x, y, top_z)),
                order_id=index,
            ),
            ModelPoint(
                position_id_2d=next_point_id,
                position_id_3d=self._add_point((next_x, next_y, next_top_z)),
                order_id=next_index,
            ),
            ModelPoint(
                position_id_2d=next_point_id,
                position_id_3d=self._add_point((next_x, next_y, next_bottom_z)),
                order_id=next_index,
            ),
        ]

        created_wall_edges.append(sorted_edge)
        self._add_wall(wall_model_points, -2)

  def _create_roof_faces(self, polygon_zs_list: list[list[float]]):
    """屋根面を作る

    Args:
      polygon_zs_list (list[list[float]]): 複数のポリゴンの頂点高さリスト
    """

    # 2Dポリゴンの2D三角形分割
    polygon_id_triangles_pair = self._get_polygon_id_triangles_pair(
        self._roof_polygon_vertex_xys, self._inner_polygons,
    )

    for polygon_id, triangles in polygon_id_triangles_pair.items():
      polygon_zs = polygon_zs_list[polygon_id]
      for triangle in triangles:
        face_points: list[ModelPoint] = []
        triangle_xys_before = [
            self._roof_polygon_vertex_xys[triangle_vertex.point_id] for triangle_vertex in triangle
        ]
        triangle_xys_after = ensure_counter_clockwise(triangle_xys_before)

        # 反時計回りに頂点の順序を変更
        triangle_vertices = [triangle_vertex for triangle_vertex in triangle]
        if triangle_xys_after[0] != triangle_xys_before[0]:
          triangle_vertices = triangle_vertices[::-1]

        for triangle_vertex in triangle_vertices:
          x, y = self._roof_polygon_vertex_xys[triangle_vertex.point_id]
          z = polygon_zs[triangle_vertex.order_id]
          face_points.append(ModelPoint(
              position_id_2d=triangle_vertex.point_id,
              position_id_3d=self._add_point((x, y, z)),
              order_id=triangle_vertex.order_id,
          ))

        self._add_roof(face_points, polygon_id)

  def _create_ground_face(self):
    """床面を作る
    """
    ground_polygon_xys_before = [
        self._roof_polygon_vertex_xys[point_id] for point_id in self._outer_polygon
    ]

    ground_polygon_xys_after = ensure_counter_clockwise(
        [self._roof_polygon_vertex_xys[point_id] for point_id in self._outer_polygon]
    )[::-1]

    # 時計回りに頂点(x,y)の順序を変更
    floor_polygon = copy.deepcopy(self._outer_polygon)
    if ground_polygon_xys_before[0] != ground_polygon_xys_after[0]:
      floor_polygon = floor_polygon[::-1]

    floor_polygon_model_points = [
        ModelPoint(
            position_id_2d=point_id,
            position_id_3d=self._add_point((
                self._roof_polygon_vertex_xys[point_id][0],
                self._roof_polygon_vertex_xys[point_id][1],
                self._ground_height,
            )),
            order_id=i
        ) for i, point_id in enumerate(floor_polygon)
    ]

    self._add_ground(floor_polygon_model_points, -1)

  def _get_polygon_id_triangles_pair(
      self,
      roof_polygon_vertex_xys: list[tuple[float, float]],
      inner_polygons: list[list[int]],
  ):
    """モデル面の作成

    Args:
      roof_polygon_vertex_xys (list[tuple[float, float]]): 屋根面頂点の2次元座標(x,y)
      inner_polygons (list[list[int]]): 区切られた各屋根面ポリゴン

    Returns:
      dict[int, list[Triangle]]
    """

    polys: list[Polygon] = []
    triangle_polys: list[Polygon] = []
    polygon_xys_list: list[list[tuple[float, float]]] = []
    polygon_layer_xys_list: list[list[tuple[float, float, float]]] = []
    triangle_xys_list: list[list[tuple[float, float, float]]] = []

    polygon_id_triangles_pair: dict[int, list[Triangle]] = defaultdict(list)
    for polygon_id, polygon in enumerate(inner_polygons):
      polygon_xys: list[tuple[float, float]] = []
      polygon_layer_xys: list[tuple[float, float, float]] = []
      for point_id in polygon:
        x, y = roof_polygon_vertex_xys[point_id]
        polygon_xys.append((x, y))
        polygon_layer_xys.append((x, y, 0.5 * polygon_id))

      polys.append(Polygon(np.array(polygon_layer_xys)[:, :2]))
      polygon_layer_xys_list.append(polygon_layer_xys)
      polygon_xys_list.append(polygon_xys)

      poly_triangles = triangulate(polygon, roof_polygon_vertex_xys)

      for triangle in poly_triangles:
        triangle_xys: list[tuple[float, float, float]] = []
        for triangle_vertex in triangle:
          x, y = roof_polygon_vertex_xys[triangle_vertex.point_id]
          triangle_xys.append((x, y, 0))

        triangle_polys.append(Polygon(np.array(triangle_xys)[:, :2]))
        triangle_xys_list.append(triangle_xys)
        polygon_id_triangles_pair[polygon_id].append(triangle)

    poly_area = unary_union(polys)
    triangle_poly_area = unary_union(triangle_polys)

    if self._debug_mode:
      triangulation_before_polygons_2d = ObjInfo()
      triangulation_before_triangles_2d = ObjInfo()

      triangulation_before_polygons_2d.append_faces(BldElementType.ROOF, polygon_layer_xys_list)
      triangulation_before_triangles_2d.append_faces(BldElementType.ROOF, triangle_xys_list)

      debug_dir = os.path.join('debug', self._id)
      Path(debug_dir).mkdir(parents=True, exist_ok=True)
      triangulation_before_polygons_2d_obj_path = os.path.join(debug_dir, 'triangulation_before_polygons_2d.obj')
      triangulation_before_triangles_2d_obj_path = os.path.join(debug_dir, 'triangulation_before_triangles_2d.obj')

      triangulation_before_polygons_2d.write_file(file_path=triangulation_before_polygons_2d_obj_path)
      triangulation_before_triangles_2d.write_file(file_path=triangulation_before_triangles_2d_obj_path)

    assert isinstance(poly_area, Polygon), "分割されたポリゴンに隙間があります"
    assert len(poly_area.interiors) == 0, "分割されたポリゴンに隙間があります"

    assert isinstance(triangle_poly_area, Polygon), "分割された三角形に隙間があります"
    assert len(triangle_poly_area.interiors) == 0, "分割された三角形に隙間があります"

    return polygon_id_triangles_pair

  def _simplify(self, threshold: float):
    """屋根面の単純化

    同じ角度の隣接した面を一つにまとめる

    Args:
      threshold: 同じ角度と判定する閾値 (degree)
    """

    num_of_faces = len(self._faces)
    dsu = DisjointSetUnion(num_of_faces)

    # 面毎に法線を求める
    normals: list[npt.NDArray[np.float_]] = []
    for face in self._faces:
      normal = np.zeros(3, dtype=np.float_)
      a = face.points[0].position_id_3d
      for b, c in face.edges_3d():
        normal += np.cross(self._points[b] - self._points[a],
                           self._points[c] - self._points[a])

      normals.append(normal / np.linalg.norm(normal))

    # 統合しない面の組を列挙する
    rules: list[tuple[int, int]] = []
    for i, j in itertools.combinations(range(num_of_faces), 2):
      face_i = self._faces[i]
      face_j = self._faces[j]

      # 位置が同じで、出現順が異なる点を持つ2面は統合しない
      for point_i, point_j in itertools.product(face_i.points, face_j.points):
        if point_i.position_id_2d == point_j.position_id_2d and point_i.order_id != point_j.order_id:
          rules.append((i, j))

    # 同じ向きの隣り合った面を繋げる
    for i, j in itertools.combinations(range(num_of_faces), 2):
      face_i = self._faces[i]
      face_j = self._faces[j]

      # 面のタイプが異なる場合は除く
      if face_i.type != face_j.type:
        continue

      # 辺を列挙する (ただし片方の辺の向きは逆転させる)
      edges_i = set(face_i.edges_3d())
      edges_j = set([(b, a) for a, b in face_j.edges_3d()])

      # 辺を共有していない場合は除く
      intersection = set(edges_i) & set(edges_j)
      if len(intersection) == 0:
        continue

      # 統合しないペアが統合されないか調べる
      permitted = True
      for a, b in rules:
        # rootの組が一致する場合は、統合した場合に、不許可のペアが統合される
        if {dsu.root(i), dsu.root(j)} == {dsu.root(a), dsu.root(b)}:
          permitted = False
          break
      if not permitted:
        continue

      if get_angle_degree_3d(normals[i], normals[j]) < threshold:
        dsu.unite(i, j)

    groups = dsu.groups()

    simplified_faces: list[ModelFace] = []

    # 繋げた面毎に外形線を求める
    # 異なる向きの同じ辺をペアとして消すと、残った辺が外形線になる
    for group in groups:
      # 回転方向を維持するため、元と同じ順で格納する
      unique_edges: set[tuple[int, int]] = set()

      for face_id in group:
        face = self._faces[face_id]

        for a, b in face.edges_3d():
          if (b, a) in unique_edges:
            unique_edges.remove((b, a))
          else:
            unique_edges.add((a, b))

      # assert len(unique_edges) >= 3

      outer = self._to_polygon(list(unique_edges))

      simplified_faces.append(ModelFace(
          [ModelPoint(-1, position_id_3d, -1)
           for position_id_3d in outer],
          self._faces[group[0]].type,
          self._faces[group[0]].group_id,
      ))

    self._faces = simplified_faces

  def _rectify(self):
    """1) 連続点削除
       2) ソリッド非水密エラー修正
          多角形の線分上に頂点が存在する場合、その頂点を多角形に追加する
    """

    def find_onsegment_point(edge_3d: tuple[int, int], skip_list: set[int]) -> int:
      # 線分の頂点
      v0 = self._points[edge_3d[0]]
      v1 = self._points[edge_3d[1]]

      # 線分に存在する頂点を探す
      for i, point in enumerate(self._points):
        if i in skip_list:
          continue
        dist1 = np.linalg.norm(point - v0)
        dist2 = np.linalg.norm(point - v1)
        dist3 = np.linalg.norm(v0 - v1)
        if dist1 + dist2 - dist3 < 1e-03:
          return i
      return -1

    # 連続点を探索
    db = DBSCAN(eps=1e-02, min_samples=1).fit(self._points)
    labels = db.labels_
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    point_groups: list[list[int]] = list()
    for ci in range(n_clusters):
      inds = np.where(labels == ci)[0]
      point_groups.append(inds.tolist())

    # 連続点をグループ
    new_points = []
    index_conversion: dict[int, int] = dict()
    for group in point_groups:
      if len(group) == 1:
        new_points.append(self._points[group[0]])
        index_conversion[group[0]] = len(new_points) - 1
      else:
        # 平均点計算
        group_points = self._points[group]
        avg_point = np.mean(group_points, axis=0)
        # 平均点追加
        new_points.append(avg_point)
        for index in group:
          index_conversion[index] = len(new_points) - 1
    self._points = np.array(new_points)

    # 面の頂点リストを修正
    rectified_faces: list[ModelFace] = list()
    for face in self._faces:
      new_position_ids = list()
      for position_id in face.position_ids_3d:
        if index_conversion[position_id] not in new_position_ids:
          new_position_ids.append(index_conversion[position_id])

      rectified_faces.append(ModelFace(
          [ModelPoint(-1, position_id, -1) for position_id in new_position_ids],
          face.type,
          face.group_id,
      ))
    self._faces = rectified_faces

    # 面ごとに処理
    rectified_faces: list[ModelFace] = list()

    for face in self._faces:
      # 多角形の線分取得
      edges_3d = set(face.edges_3d())

      skip_list = set()
      for i1, i2 in edges_3d:
        skip_list.add(i1)
        skip_list.add(i2)

      # 線分上頂点の探索
      while True:
        rectified_edges: set[tuple[int, int, int]] = set()
        for edge_3d in edges_3d:
          i = find_onsegment_point(edge_3d, skip_list)
          if i >= 0:
            rectified_edges.add((edge_3d[0], edge_3d[1], i))
            skip_list.add(i)

        for edge in rectified_edges:
          edges_3d.remove((edge[0], edge[1]))
          edges_3d.add((edge[0], edge[2]))
          edges_3d.add((edge[2], edge[1]))

        if len(rectified_edges) == 0:
          break

      outer = self._to_polygon(list(edges_3d))

      rectified_faces.append(ModelFace(
          [ModelPoint(-1, position_id_3d, -1) for position_id_3d in outer],
          face.type,
          face.group_id,
      ))

    self._faces = rectified_faces

  def _to_polygon(self, direct_edges: list[tuple[int, int]]) -> list[int]:
    """有向辺から多角形を復元する

    Args:
      direct_edges: 頂点番号のペアのリスト (反時計回り)

    Returns:
      list[int]: 復元した多角形

    Notes:
      単純多角形のみ対応
    """

    cur: int = direct_edges[0][0]
    polygon: list[int] = []

    for _ in range(len(direct_edges)):
      targets = list(filter(lambda e: e[0] == cur, direct_edges))
      # assert len(targets) == 1, "単純多角形ではないデータが入力されています"
      polygon.append(cur)
      cur = targets[0][1]

    # assert len(set(polygon)) == len(polygon) and cur == direct_edges[0][0], \
    #    "単純多角形ではないデータが入力されています"

    return polygon

  def output_obj(self, path: str):
    """objファイル出力

    Args:
        path (str): 出力パス
    """
    if len(self._faces) == 0:
      return

    roofs = list(filter(lambda face: face.type == BldElementType.ROOF, self._faces))
    walls = list(filter(lambda face: face.type == BldElementType.WALL, self._faces))
    grounds = list(filter(lambda face: face.type == BldElementType.GROUND, self._faces))

    info = ObjInfo()
    info.append_faces(BldElementType.ROOF, [self._points[roof.position_ids_3d] for roof in roofs])
    info.append_faces(BldElementType.WALL, [self._points[wall.position_ids_3d] for wall in walls])
    info.append_faces(BldElementType.GROUND, [self._points[ground.position_ids_3d] for ground in grounds])

    info.write_file(file_path=path)
