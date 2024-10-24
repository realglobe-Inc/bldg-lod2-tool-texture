import os
from typing import Optional

from shapely.geometry import Polygon
import numpy as np

from .extra_roof_line import ExtraRoofLine
from .house_model import HouseModel
from .coordinates_converter import CoordConverterForCartesianAndImagePos
from .model_surface_creation.extract_roof_surface import extract_roof_surface
from .model_surface_creation.optimize_roof_edge import optimize_roof_edge
from .model_surface_creation.utils.geometry import Point
from .balcony_detection import BalconyDetection
from .roof_edge_detection import RoofEdgeDetection
from ..lasmanager import PointCloud
from .preprocess import Preprocess


class CreateHouseModel:
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
      bulding_id(str): 建物ID
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
    self._min_ground_height = min_ground_height
    self._output_folder_path = output_folder_path
    self._balcony_segmentation_checkpoint_path = balcony_segmentation_checkpoint_path
    self._roof_edge_detection_checkpoint_path = roof_edge_detection_checkpoint_path
    self._grid_size = grid_size
    self._expand_rate = expand_rate
    self._use_gpu = use_gpu
    self._debug_mode = debug_mode

    # 作成に使用するためのデータを作成
    preprocess = Preprocess(grid_size=grid_size, image_size=self._image_size, expand_rate=expand_rate, building_id=building_id)
    result_preprocess = preprocess.preprocess(self._cloud, min_ground_height, shape, debug_mode)
    self._square_dsm_grid_rgbs, self._depth_image, self._roof_layer_info = result_preprocess

    self._coord_converter = self._get_coord_converter()
    roof_edge_detection = RoofEdgeDetection(self._roof_edge_detection_checkpoint_path, self._use_gpu)
    tmp_roof_edge_vertice_ijs, tmp_roof_edges = roof_edge_detection.infer(self._square_dsm_grid_rgbs)

    # 画像座標から平面直角座標への変換
    tmp_roof_vertex_xys = np.array([
        self._coord_converter.image_point_to_cartesian_point(i, j)
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

    roof_polygon_vertex_xy_points, outer_polygon, inner_polygons = self._get_roof_polygon_xy(
        tmp_roof_polygon_vertex_xy_points, tmp_outer_polygon, tmp_inner_polygons,
    )

    self._balcony_flags = self._get_balcony_flags(roof_polygon_vertex_xy_points, inner_polygons)

    self._create_model(
        roof_polygon_vertex_xy_points=roof_polygon_vertex_xy_points,
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        balcony_flags=self._balcony_flags,
    )

  def _get_coord_converter(self):
    """
    座標変換 : 画像 image pos(i,j) <-> DSM(x,y)
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
    coord_converter = CoordConverterForCartesianAndImagePos(
        grid_size=expanded_grid_size,
        cartesian_coord_upper_left=cartesian_coord_upper_left,
    )

    return coord_converter

  def _get_balcony_flags(
      self,
      roof_polygon_vertex_xy_points: list[Point],
      inner_polygons: list[int],
  ):
    # 平面直角座標から画像座標への変換
    image_points = [
        Point(*self._coord_converter.cartesian_point_to_image_point(cartesian_point.x, cartesian_point.y))
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

  def _create_model(
      self,
      roof_polygon_vertex_xy_points: list[Point],
      inner_polygons: list[int],
      outer_polygon: list[int],
      balcony_flags: list[bool],
  ):
    # 3Dモデルの生成
    model = HouseModel(id=self._building_id, shape=self._shape)
    model.new_create_model_surface(
        point_cloud=self._cloud.get_points().copy(),
        roof_polygon_vertex_xys=np.array([(point.x, point.y) for point in roof_polygon_vertex_xy_points]),
        inner_polygons=inner_polygons,
        outer_polygon=outer_polygon,
        ground_height=self._min_ground_height,
        balcony_flags=balcony_flags,
        roof_layer_info=self._roof_layer_info,
        debug_mode=self._debug_mode,
    )

    # model.create_model_surface(
    #     point_cloud=self._cloud.get_points().copy(),
    #     roof_polygon_vertex_xys=np.array([(point.x, point.y) for point in roof_polygon_vertex_xy_points]),
    #     inner_polygons=inner_polygons,
    #     outer_polygon=outer_polygon,
    #     ground_height=self._min_ground_height,
    #     balcony_flags=balcony_flags
    # )

    model.simplify(threshold=5)

    # 壁面非水密エラー修正
    model.rectify()

    # objファイルの作成
    file_name = f'{self._building_id}.obj'
    obj_path = os.path.join(self._output_folder_path, file_name)
    model.output_obj(path=obj_path)
    breakpoint()

  def _get_delta_i_average_and_delta_j_average(
      self,
      tmp_roof_polygon_vertex_xy_points: list[Point],
  ):
    tmp_roof_polygon_vertex_from_heat_ijs: list[tuple[float, float]] = []
    delta_i_sum = 0
    delta_j_sum = 0
    for point in tmp_roof_polygon_vertex_xy_points:
      nearest_x, nearest_y = self._roof_layer_info.find_nearest_xy(point.x, point.y)
      nearest_i, nearest_j = self._roof_layer_info.xy_to_ij(nearest_x, nearest_y)

      left, upper = self._roof_layer_info.origin_dsm_grid_xyzs[0, 0][:2]
      heat_vertex_i = (upper - point.y) / self._grid_size
      heat_vertex_j = (point.x - left) / self._grid_size
      tmp_roof_polygon_vertex_from_heat_ijs.append((heat_vertex_i, heat_vertex_j))
      delta_i_sum += (heat_vertex_i - nearest_i)
      delta_j_sum += (heat_vertex_j - nearest_j)

    delta_i_average = delta_i_sum / len(tmp_roof_polygon_vertex_from_heat_ijs)
    delta_j_average = delta_j_sum / len(tmp_roof_polygon_vertex_from_heat_ijs)
    return (delta_i_average, delta_j_average, tmp_roof_polygon_vertex_from_heat_ijs)

  def _ij_to_xy(self, i: float, j: float, delta_i_average: float, delta_j_average: float):
    left, upper = self._roof_layer_info.origin_dsm_grid_xyzs[0, 0][:2]
    x = float(left + (j + delta_j_average) * self._grid_size)
    y = float(upper - (i + delta_i_average) * self._grid_size)
    return (x, y)

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
      if not Polygon(polygon_ijs).is_valid:
        breakpoint()

    return fixed_roof_polygon_vertex_ijs

  def _get_roof_polygon_xy(
      self,
      tmp_roof_polygon_vertex_xy_points,
      tmp_outer_polygon,
      tmp_inner_polygons,
  ):
    (
        delta_i_average,
        delta_j_average,
        tmp_roof_polygon_vertex_from_heat_ijs,
    ) = self._get_delta_i_average_and_delta_j_average(tmp_roof_polygon_vertex_xy_points)

    tmp_roof_polygon_vertex_ijs = self._get_roof_polygon_vertex_ijs(
        tmp_roof_polygon_vertex_from_heat_ijs=tmp_roof_polygon_vertex_from_heat_ijs,
        polygons=[tmp_outer_polygon, *tmp_inner_polygons],
        delta_i_average=delta_i_average,
        delta_j_average=delta_j_average,
    )

    inner_polygon_ijs_list_before: list[list[tuple[int, int]]] = []
    for inner_polygon in tmp_inner_polygons:
      inner_polygon_ijs_list = [tmp_roof_polygon_vertex_ijs[point_id] for point_id in inner_polygon]
      inner_polygon_ijs_list_before.append(inner_polygon_ijs_list)

    extra_roof_line = ExtraRoofLine(
        shape=self._shape,
        inner_polygon_ijs_list_before=inner_polygon_ijs_list_before,
        roof_layer_info=self._roof_layer_info,
        delta_i_average=delta_i_average,
        delta_j_average=delta_j_average,
        grid_size=self._grid_size,
        debug_mode=self._debug_mode,
    )

    roof_polygon_vertex_xy_points = tmp_roof_polygon_vertex_xy_points
    outer_polygon = tmp_outer_polygon
    inner_polygons = tmp_inner_polygons
    if extra_roof_line.has_splited_polygon:
      roof_polygon_vertex_xy_points = [
          Point(*new_polygon_vertex_xy)
          for new_polygon_vertex_xy in extra_roof_line.new_polygon_vertex_xys
      ]
      outer_polygon = extra_roof_line.new_outer_polygon
      inner_polygons = extra_roof_line.new_inner_polygons

    tmp_inner_polys: list[Polygon] = []
    for inner_polygon in tmp_inner_polygons:
      poly = Polygon([
          (tmp_roof_polygon_vertex_xy_points[point_id].x, tmp_roof_polygon_vertex_xy_points[point_id].y)
          for point_id in inner_polygon
      ])
      tmp_inner_polys.append(poly)

    roof_polygon_vertex_xys = np.array(
        [(point.x, point.y) for point in roof_polygon_vertex_xy_points]
    )
    xy_polys: list[Polygon] = []
    for inner_polygon in inner_polygons:
      xy_poly = Polygon([
          tuple(roof_polygon_vertex_xys[point_id])
          for point_id in inner_polygon
      ])
      xy_polys.append(xy_poly)

    # roof_polygon_vertex_xy_points = tmp_roof_polygon_vertex_xy_points
    # outer_polygon = tmp_outer_polygon
    # inner_polygons = tmp_inner_polygons

    return roof_polygon_vertex_xy_points, outer_polygon, inner_polygons
