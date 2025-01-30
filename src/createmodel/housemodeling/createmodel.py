from collections import Counter
import os
from typing import Optional

from shapely.geometry import Polygon
import numpy as np

from .model_edge_height_info import ModelEdgeHeightInfo
from .utils.polys import validate_polygon_ijs_list
from .extra_roof_line import ExtraRoofLine
from .house_model import HouseModel
from .coordinates_converter import DsmCoordHeatImagePosConverter
from .model_surface_creation.extract_roof_surface import extract_roof_surface
from .model_surface_creation.optimize_roof_edge import optimize_roof_edge
from .model_surface_creation.utils.geometry import Point
from .balcony_detection import BalconyDetection
from .roof_edge_detection import RoofEdgeDetection
from .preprocess import Preprocess
from ..lasmanager import PointCloud


class HouseModelBuilder:
  """複雑形状家屋の3Dモデルを作成"""

  def __init__(
      self,
      cloud: PointCloud,
      shape: Polygon,
      building_id: str,
      min_ground_height: float,
      output_folder_path: str,
      balcony_segmentation_checkpoint_path: str,
      roof_edge_detection_checkpoint_path: str,
      grid_size: float = 0.25,
      expand_rate: Optional[float] = None,
      use_gpu: bool = False,
      debug_mode: bool = False,
  ) -> None:
    """家屋3Dモデルの作成

    Args:
      cloud(PointCloud): 建物点群
      shape(Polygon): 建物外形ポリゴン
      building_id(str): 建物ID
      min_ground_height(float): 最低地面の高さ
      output_folder_path(str): 出力先フォルダ
      balcony_segmentation_checkpoint_path(str): バルコニーのセグメンテーションの学習済みモデルファイルパス
      roof_edge_detection_checkpoint_path(str): 屋根線検出の学習済みモデルファイルパス
      grid_size(float,optional): 点群の間隔(meter) (Default: 0.25),
      expand_rate(float, optional): 画像の拡大率 (Default: 1),
      use_gpu(bool, optional): 推論時のGPU使用の有無 (Default: False)
      debug_mode (bool, optional): デバッグモード (Default: False)
    """

    self._image_size = 256

    self._cloud = cloud
    self._shape = shape
    self._building_id = building_id
    self._ground_height = min_ground_height
    self._output_folder_path = output_folder_path
    self._balcony_segmentation_checkpoint_path = balcony_segmentation_checkpoint_path
    self._roof_edge_detection_checkpoint_path = roof_edge_detection_checkpoint_path
    self._grid_size = grid_size
    self._expand_rate = expand_rate
    self._use_gpu = use_gpu
    self._debug_mode = debug_mode

    # 作成に使用するためのデータを作成
    preprocess = Preprocess(grid_size=grid_size, image_size=self._image_size, expand_rate=expand_rate, building_id=building_id)
    (
        self._square_dsm_grid_rgbs,
        self._depth_image,
        self._roof_layer_info,
    ) = preprocess.preprocess(self._cloud, min_ground_height, shape, debug_mode)

    self._dsm_coord_heat_image_pos_converter = self._get_dsm_coord_heat_image_pos_converter()
    roof_edge_detection = RoofEdgeDetection(self._roof_edge_detection_checkpoint_path, self._use_gpu)
    tmp_roof_edge_vertice_ijs, tmp_roof_edges = roof_edge_detection.infer(self._square_dsm_grid_rgbs)

    # 重複があるか確認
    counter = Counter(tmp_roof_edge_vertice_ijs)
    duplicates = [point for point, count in counter.items() if count > 1]
    assert len(duplicates) == 0, f"重複点があります: {duplicates}"

    # 画像座標から平面直角座標への変換
    tmp_roof_vertex_xys = np.array([
        self._dsm_coord_heat_image_pos_converter.image_point_to_cartesian_point(i, j)
        for i, j in tmp_roof_edge_vertice_ijs
    ])

    # LoD2モデルデータの作成
    tmp_roof_polygon_vertex_xy_points, inner_edge, outer_edge = optimize_roof_edge(
        self._shape, tmp_roof_vertex_xys, tmp_roof_edges,
    )
    result_edges = inner_edge + outer_edge
    tmp_outer_polygon, tmp_inner_polygons = extract_roof_surface(
        tmp_roof_polygon_vertex_xy_points, result_edges,
    )

    # HEATのポリゴンが不完全な場合、ポリゴン分割
    (
        roof_polygon_vertex_xy_points,
        roof_polygon_vertex_ijs,
        outer_polygon,
        inner_polygons,
    ) = self._patch_for_heat_polygon(
        tmp_roof_polygon_vertex_xy_points, tmp_outer_polygon, tmp_inner_polygons,
    )

    # ポリゴンがバルコニーか
    polygon_balcony_flags = self._get_polygon_balcony_flags(roof_polygon_vertex_xy_points, inner_polygons)
    polygon_balcony_flags = [False for _ in polygon_balcony_flags]

    # バルコニーの屋根レイヤーを追加
    balcony_polygon_ijs_list = self._get_balcony_polygon_ijs_list(
        polygon_balcony_flags, roof_polygon_vertex_ijs, inner_polygons,
    )
    self._roof_layer_info.add_balcony_layers(balcony_polygon_ijs_list)

    # To Do : X型交差屋根に中間点の追加
    model_edge_height_info = ModelEdgeHeightInfo(
        roof_layer_info=self._roof_layer_info,
        roof_polygon_vertex_ijs=roof_polygon_vertex_ijs,
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        polygon_balcony_flags=polygon_balcony_flags,
        ground_height=self._ground_height,
    )
    twisted_edge_middle_point_rate_pair = model_edge_height_info.get_twisted_edge_middle_point_rate_pair()

    self._create_model(
        roof_polygon_vertex_xys=[(point.x, point.y) for point in roof_polygon_vertex_xy_points],
        roof_polygon_vertex_ijs=roof_polygon_vertex_ijs,
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        polygon_balcony_flags=polygon_balcony_flags,
    )

  def _get_dsm_coord_heat_image_pos_converter(self):
    """
    HEAT入力画像の座標(i,j)とDSM座標(x,y)を変換する Converter を生成

    Returns:
      DsmCoordHeatImagePosConverter: HEAT入力画像の座標(i,j)とDSM座標(x,y)を変換する Converter
    """
    min_x, min_y = self._cloud.get_points()[:, :2].min(axis=0)
    max_x, max_y = self._cloud.get_points()[:, :2].max(axis=0)
    expanded_grid_size = self._grid_size / (self._expand_rate if self._expand_rate is not None else 1)
    height = round((max_y - min_y) / expanded_grid_size) + 1
    width = round((max_x - min_x) / expanded_grid_size) + 1
    cartesian_coord_upper_left = (
        min_x - (self._image_size - width) / 2 * expanded_grid_size,
        max_y + (self._image_size - height) / 2 * expanded_grid_size,
    )
    dsm_coord_heat_image_pos_converter = DsmCoordHeatImagePosConverter(
        grid_size=expanded_grid_size,
        cartesian_coord_upper_left=cartesian_coord_upper_left,
    )

    return dsm_coord_heat_image_pos_converter

  def _get_polygon_balcony_flags(
      self,
      roof_polygon_vertex_xy_points: list[Point],
      inner_polygons: list[list[int]],
  ):
    """バルコニー領域を検出

    Args:
      roof_polygon_vertex_xy_points (list[Point]): 頂点のリスト
      inner_polygons (lit[list[int]]): 内部ポリゴンの頂点番号リスト

    Return:
      list[bool]: ポリゴンのバルコニーの場合 true
    """

    # 平面直角座標から画像座標への変換
    image_points = [
        Point(*self._dsm_coord_heat_image_pos_converter.cartesian_point_to_image_point(cartesian_point.x, cartesian_point.y))
        for cartesian_point in roof_polygon_vertex_xy_points
    ]

    # バルコニーセグメンテーション
    balcony_detection = BalconyDetection(self._balcony_segmentation_checkpoint_path, self._use_gpu)
    balcony_flags = balcony_detection.infer(
        dsm_grid_rgbs=self._square_dsm_grid_rgbs,
        depth_image=self._depth_image,
        image_points=image_points,
        polygons=inner_polygons,
        threshold=0.5
    )

    return balcony_flags

  def _get_balcony_polygon_ijs_list(
      self,
      polygon_balcony_flags: list[bool],
      roof_polygon_vertex_ijs: list[tuple[float, float]],
      inner_polygons: list[int],
  ):
    """バルコニポリゴンの頂点リスト(i,j)を取得

    Args:
      polygon_balcony_flags (list[bool]): ポリゴンがバルコニーか
      roof_polygon_vertex_ijs (list[tuple[float, float]]): 屋根面頂点の2次元座標(i,j)
      inner_polygons (list[int]): 内部ポリゴンの頂点番号リスト

    Returns:
      list[list[tuple[float, float]]]: バルコニポリゴンの頂点リスト(i,j)
    """
    balcony_polygon_ijs_list: list[list[tuple[float, float]]] = []
    for polygon_id, polygon_balcony_flag in enumerate(polygon_balcony_flags):
      if polygon_balcony_flag:
        balcony_polygon = inner_polygons[polygon_id]
        balcony_polygon_ijs = [roof_polygon_vertex_ijs[point_id] for point_id in balcony_polygon]
        balcony_polygon_ijs_list.append(balcony_polygon_ijs)

    return balcony_polygon_ijs_list

  def _create_model(
      self,
      roof_polygon_vertex_xys: list[tuple[float, float]],
      roof_polygon_vertex_ijs: list[tuple[float, float]],
      inner_polygons: list[int],
      outer_polygon: list[int],
      polygon_balcony_flags: list[bool],
  ):
    # 3Dモデルの生成
    model = HouseModel(
        id=self._building_id,
        roof_layer_info=self._roof_layer_info,
        roof_polygon_vertex_xys=roof_polygon_vertex_xys,
        roof_polygon_vertex_ijs=roof_polygon_vertex_ijs,
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        ground_height=self._ground_height,
        polygon_balcony_flags=polygon_balcony_flags,
        debug_mode=self._debug_mode,
    )

    # objファイルの作成
    file_name = f'{self._building_id}.obj'
    obj_path = os.path.join(self._output_folder_path, file_name)
    model.output_obj(path=obj_path)

    if self._debug_mode:
      debug_dir = os.path.join('debug', self._building_id)
      debug_obj_path = os.path.join(debug_dir, file_name)
      model.output_obj(path=debug_obj_path)

  def _xy_to_ij(self, xy: tuple[float, float]) -> tuple[float, float]:
    """
    xy 座標(DSM 座標)を ij 座標(画像の Pixel 座標)に変換

    Args:
      xy (tuple[float, float]): DSM 座標

    Return:
      tuple[float, float]: 画像の Pixel 座標
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

    # xy -> ij の変換
    x, y = xy
    j = float((x - x_min) / y_height_per_j_height)
    i = float((y_max - y) / x_width_per_i_width)

    return (round(i, 6), round(j, 6))

  def _get_roof_polygon_vertex_ijs(
      self,
      tmp_roof_polygon_vertex_from_heat_ijs: list[tuple[float, float]],
      polygons: list[list[int]],
      delta_i_average: float,
      delta_j_average: float,
  ):
    fixed_roof_polygon_vertex_ijs: list[tuple[float, float]]  = []
    for i, j in tmp_roof_polygon_vertex_from_heat_ijs:
      fixed_i = i - delta_i_average
      fixed_j = j - delta_j_average
      fixed_roof_polygon_vertex_ijs.append((fixed_i, fixed_j))

    for polygon in polygons:
      polygon_ijs = [fixed_roof_polygon_vertex_ijs[point_id] for point_id in polygon]
      validate_polygon_ijs_list([polygon_ijs])

    return fixed_roof_polygon_vertex_ijs

  def _patch_for_heat_polygon(
      self,
      tmp_roof_polygon_vertex_xy_points: list[Point],
      tmp_outer_polygon: list[int],
      tmp_inner_polygons: list[list[int]],
  ):
    """不完全なHEATの屋根ポリゴンのパッチ

    Args:
      tmp_roof_polygon_vertex_xy_points (list[Point]): 頂点のリスト
      tmp_outer_polygon (list[int]): 外周ポリゴンの頂点番号リスト
      tmp_inner_polygons (lit[list[int]]): 内部ポリゴンの頂点番号リスト

    Return:
      list[Point]: 頂点のリスト(x,y)
      list[tuple[float, float]]: 頂点のリスト(i,j)
      list[int]: 外周ポリゴンの頂点番号リスト
      list[list[int]]: 内部ポリゴンの頂点番号リスト
    """

    tmp_roof_polygon_vertex_ijs = [
        self._xy_to_ij((xy_point.x, xy_point.y)) for xy_point in tmp_roof_polygon_vertex_xy_points
    ]

    inner_polygon_ijs_list_before: list[list[tuple[int, int]]] = []
    for inner_polygon in tmp_inner_polygons:
      inner_polygon_ijs = [tmp_roof_polygon_vertex_ijs[point_id] for point_id in inner_polygon]
      inner_polygon_ijs_list_before.append(inner_polygon_ijs)

    validate_polygon_ijs_list(inner_polygon_ijs_list_before)

    extra_roof_line = ExtraRoofLine(
        id=self._building_id,
        shape=self._shape,
        inner_polygon_ijs_list_before=inner_polygon_ijs_list_before,
        roof_layer_info=self._roof_layer_info,
        grid_size=self._grid_size,
        debug_mode=self._debug_mode,
    )

    if extra_roof_line.has_splited_polygon:
      roof_polygon_vertex_xy_points = [
          Point(*new_polygon_vertex_xy)
          for new_polygon_vertex_xy in extra_roof_line.new_polygon_vertex_xys
      ]
      outer_polygon = extra_roof_line.new_outer_polygon
      inner_polygons = extra_roof_line.new_inner_polygons
      roof_polygon_vertex_ijs = extra_roof_line.new_polygon_vertex_ijs
    else:
      roof_polygon_vertex_xy_points = tmp_roof_polygon_vertex_xy_points
      outer_polygon = tmp_outer_polygon
      inner_polygons = tmp_inner_polygons
      roof_polygon_vertex_ijs = tmp_roof_polygon_vertex_ijs

    return roof_polygon_vertex_xy_points, roof_polygon_vertex_ijs, outer_polygon, inner_polygons
