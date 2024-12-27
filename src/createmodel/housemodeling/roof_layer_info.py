import itertools
import os
from pathlib import Path
from collections import defaultdict, deque
from typing import Union

from PIL import Image
import numpy as np
import numpy.typing as npt
import cv2
from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.createmodel.housemodeling.utils.polys import get_grid_point_ijs, get_polygon_ijs_list


class RoofLayerInfo:
  """
  DSM点群から屋根の階層分離をするための情報
  """

  NO_POINT = -1
  NOISE_POINT = -2
  ROOF_LINE_POINT = -3
  ROOF_VERTICE_POINT = -4
  WALL_HEIGHT_THRESHOLD = 0.2

  # 予約済み色（この色は屋根レイヤーの色として使われない）
  RESERVED_COLOR = {
      NO_POINT: [255, 255, 255],
      NOISE_POINT: [0, 0, 0],
      ROOF_LINE_POINT: [0, 255, 0],
      ROOF_VERTICE_POINT: [255, 0, 0],
  }

  @property
  def masked_dsm_grid_rgbs(self):
    """
    DSM点群のRGB画像

    Returns:
      npt.NDArray[np.float_]: DSM点群のRGB画像
    """

    return self._masked_dsm_grid_rgbs

  @property
  def origin_dsm_grid_xyzs(self):
    """
    DSM点群のRGB画像(i,j)のxyz座標

    Returns:
      npt.NDArray[np.float_]: DSM点群のRGB画像(i,j)のxyz座標
    """

    return self._origin_dsm_grid_xyzs

  @property
  def debug_dir(self):
    """
    デバッグ用ディレクトリー

    Returns:
      npt.NDArray[np.float_]: デバッグ用ディレクトリー
    """

    return self._debug_dir

  @property
  def layer_class(self):
    """
    DSM点群の画像座標 (i,j) 二次元アレイに壁点を起点としてクラスタリングした屋根のレイヤー番号を記録したもの

    Returns:
      npt.NDArray[np.int_]: DSM点群の画像座標 (i,j) 二次元アレイに壁点を起点としてクラスタリングした屋根のレイヤー番号を記録したもの
    """

    return self._layer_class

  @property
  def layer_number_layer_area_polygon_ijs_list_pair(self):
    """
    屋根レイヤーの外形ポリゴンの頂点

    Returns:
      dict[int, list[list[tuple[int, int]]]]: 屋根レイヤーの外形ポリゴンの頂点
    """

    return self._layer_number_layer_area_polygon_ijs_list_pair

  @property
  def wall_point_positions(self):
    """
    壁点リスト

    Returns:
      list[]: 壁点リスト
    """
    return self._wall_point_positions

  @property
  def layer_class_length(self):
    """
    クラスタリングされたレイヤー番号の数

    Returns:
      int: クラスタリングされたレイヤー番号の数
    """
    return self._layer_class_length

  def __init__(
      self,
      origin_dsm_grid_xyzs: npt.NDArray[np.float_],
      masked_dsm_grid_xyzs: npt.NDArray[np.float_],
      masked_dsm_grid_rgbs: npt.NDArray[np.int_],
      debug_dir: str,
      debug_mode: bool = False,
  ):
    """
    屋根線をイメージとして保存（デバッグ用）

    Args:
      origin_dsm_grid_xyzs (npt.NDArray[np.uint8]): DSM点群のRGB画像(i,j)のxyz座標(建築物領域以外も高さあり : 3D高さ検出用)
      masked_dsm_grid_xyzs (npt.NDArray[np.uint8]): DSM点群のRGB画像(i,j)のxyz座標(建築物領域以外は高さ0 : 壁検出用)
      masked_dsm_grid_rgbs (npt.NDArray[np.int_]): DSM点群のRGB画像(建築物領域以外は白色)
      debug_dir (str): 記録するファイル名
      debug_mode (bool): デバッグモード
    """

    self._origin_dsm_grid_xyzs = origin_dsm_grid_xyzs.copy()
    self._masked_dsm_grid_xyzs = masked_dsm_grid_xyzs.copy()
    self._masked_dsm_grid_rgbs = masked_dsm_grid_rgbs.copy()
    self._debug_mode = debug_mode
    self._debug_dir = debug_dir
    self._height, self._width = masked_dsm_grid_xyzs.shape[:2]
    self._layer_class = np.full((self._height, self._width), RoofLayerInfo.NO_POINT, dtype=np.int_)
    self._layer_class_length = 0

    self._color_palette = self.get_color_palette(RoofLayerInfo.RESERVED_COLOR.values())
    self._wall_point_positions = self._get_wall_point_positions()
    self._xy_ij = self._get_xy_ij_pair()
    self._init_layer_class()
    self._detect_and_mark_noise()
    self.get_layer_number_layer_area_polygon_ijs_list_pair()

    if self._debug_mode:
      Path(self._debug_dir).mkdir(parents=True, exist_ok=True)

      self._save_image_origin()
      self._save_image_wall_line(self.wall_point_positions)
      self.save_layer_image(self._layer_class)

  def xy_to_ij(self, x, y):
    """
    DSM座標(x,y)に対応する画像座標(i,j)を取得

    Args:
      x (float): 基準点のx
      y (float): 基準点のy

    Returns:
      tuple[int, int]: DSM座標(x,y)に対応する画像座標(i,j)
    """

    return self._xy_ij[(x, y)]

  def ij_to_z(self, i: Union[float, int], j: Union[float, int]):
    """画像座標(i,j)に対応するDSM座標(x,y)からz値を取得

    Args:
      i (float): 基準点のi
      j (float): 基準点のj

    Returns:
      float: 画像座標(i,j)に対応するDSM座標(x,y)のz値
    """

    height, width = self._masked_dsm_grid_xyzs.shape[:2]
    i_clipped = min(max(int(round(i)), 0), height - 1)
    j_clipped = min(max(int(round(j)), 0), width - 1)
    return float(self._masked_dsm_grid_xyzs[i_clipped, j_clipped, 2])

  def _get_wall_point_positions(self):
    """壁の点を設定する

    Returns:
      list[tuple[float, float]]: 壁の点の座標(i,j)リスト
    """

    height, width = self._masked_dsm_grid_xyzs.shape[:2]
    wall_point_positions: list[tuple[float, float]] = []
    for i, masked_dsm_grid_xyzs_j in enumerate(self._masked_dsm_grid_xyzs):
      for j, (x, y, z1) in enumerate(masked_dsm_grid_xyzs_j):
        if (x == 0 and y == 0 and z1 == 0):
          continue

        z2s: list[float] = []
        for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
          i2, j2 = i + di, j + dj
          if 0 <= i2 < height and 0 <= j2 < width:
            z2s.append(self._masked_dsm_grid_xyzs[i2, j2, 2])

        if self._is_wall_index(z1, z2s):
          wall_point_positions.append((i, j))

    return wall_point_positions

  def _get_xy_ij_pair(self):
    """DSM点群座標(x, y)に対応する画像座標(i, j)の辞書を取得

    Returns:
      dict[tuple[float, float], tuple[int, int]]: DSM点群座標(x, y)に対応する画像座標(i, j)の辞書
    """

    xy_ij: dict[tuple[float, float], tuple[int, int]] = {}
    for i, masked_dsm_grid_xyzs_j in enumerate(self._masked_dsm_grid_xyzs):
      for j, (x, y, _) in enumerate(masked_dsm_grid_xyzs_j):
        xy_ij[(x, y)] = (i, j)

    return xy_ij

  def _is_wall_index(self, z1: float, z2s: list[float]):
    """
    壁点を判定する

    Args:
      z1 (float): DSM点群のある点(x, y, z) の z 座標
      z2s (list[float]): DSM点群のある点(x, y, z) の前後左右の点の z 座標（最大4個）

    Returns:
      bool: 壁の点の場合 True
    """
    return any((z1 - z2) > RoofLayerInfo.WALL_HEIGHT_THRESHOLD for z2 in z2s)

  def _bfs_layer_fill(self, start_i: int, start_j: int):
    """
    BFS を使ってレイヤーの点を探索し、layer_class を更新

    Args:
      start_i (int): DSM点群のRGB画像の位置(i,j) の i
      start_j (int): DSM点群のRGB画像の位置(i,j) の j
    """

    queue = deque([(start_i, start_j)])  # BFS のためのキュー
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上下左右の方向

    # 初期地点の z 座標
    self._layer_class[start_i, start_j] = self._layer_class_length

    while queue:
      i, j = queue.popleft()

      # 現在の点の z 座標
      current_z = self._masked_dsm_grid_xyzs[i, j, 2]

      # 前後左右の点を探索
      for di, dj in directions:
        i2, j2 = i + di, j + dj

        # 境界チェック
        if 0 <= i2 < self._height and 0 <= j2 < self._width:
          if self._layer_class[i2, j2] == RoofLayerInfo.NO_POINT:
            neighbor_z = self._masked_dsm_grid_xyzs[i2, j2, 2]

            # z 座標の差が RoofLayerInfo.WALL_HEIGHT_THRESHOLD 以下なら、同じレイヤーと見なす
            if abs(current_z - neighbor_z) <= RoofLayerInfo.WALL_HEIGHT_THRESHOLD:
              self._layer_class[i2, j2] = self._layer_class_length
              queue.append((i2, j2))  # 探索対象としてキューに追加

  def _init_layer_class(self):
    """画像頂点(i,j)の屋根レイヤーを決める"""

    # wall_point_positions から BFS を開始して各レイヤーを探索
    for i, j in self._wall_point_positions:
      if self._layer_class[i, j] == RoofLayerInfo.NO_POINT:
        self._bfs_layer_fill(i, j)
        self._layer_class_length += 1  # 次のレイヤー番号に進む

  def _detect_and_mark_noise(self):
    """屋根レイヤーのノイズ処理をする"""
    for layer_number in range(self._layer_class_length):
      # 現在の layer_number に属する (i, j) のリストを収集
      layer_point_ijs = [(i, j) for i in range(self._height) for j in range(self._width)
                         if self._layer_class[i, j] == layer_number]

      if not layer_point_ijs:
        continue  # そのクラスに点がない場合はスキップ

      has_noise = True
      # ノイズの場合、そのクラス全体の点を RoofLayerInfo.NOISE_POINT にマーク
      for layer_point_ij in layer_point_ijs:
        if self._is_ok_point(layer_point_ij, layer_number):
          has_noise = False
          break

      if has_noise:
        for i, j in layer_point_ijs:
          self._layer_class[i, j] = RoofLayerInfo.NOISE_POINT

  def _is_ok_point(self, layer_point_ij: tuple[int, int], layer_number: int):
    """
    頂点(i,j)がノイズかどうかをチェックする

    Args:
      layer_point_ij: 頂点(i,j)
      layer_number (int): 壁点を起点としてクラスタリングした屋根のレイヤー番号

    Returns:
      bool: ノイズの点は False
    """
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上下左右の方向
    layer_point_i, layer_point_j = layer_point_ij

    ok_count = 0
    for di, dj in directions:
      i2, j2 = layer_point_i + di, layer_point_j + dj

      # 境界チェック
      if 0 <= i2 < self._height and 0 <= j2 < self._width:
        if self._layer_class[i2, j2] == layer_number:
          ok_count += 1
      else:
        ok_count += 1

    return ok_count == 4

  def _save_image_origin(self):
    """
    DSM点群のRGB画像原本をイメージとして保存（デバッグ用）
    """
    image_origin = Image.fromarray(self._masked_dsm_grid_rgbs, "RGB")
    image_origin_path = os.path.join(self._debug_dir, 'origin.png')
    image_origin.save(image_origin_path)

  def _save_image_wall_line(
      self,
      wall_point_positions: list[tuple[int, int]],
      file_name: str = 'wall_line.png',
  ):
    """
    壁の点をイメージとして保存（デバッグ用）

    Args:
      wall_point_positions (list[tuple[int, int]]): DSM点群のRGB画像で壁の点の位置(i, j)
      file_name (str): 記録するファイル名
    """
    masked_dsm_grid_rgbs_wall_line = self._masked_dsm_grid_rgbs.copy()
    for i, j in wall_point_positions:
      masked_dsm_grid_rgbs_wall_line[i, j] = [255, 0, 0]

    image_wall_line = Image.fromarray(masked_dsm_grid_rgbs_wall_line, "RGB")
    image_wall_line_path = os.path.join(self._debug_dir, file_name)
    image_wall_line.save(image_wall_line_path)

  def save_layer_image(self, layer_class: npt.NDArray[np.int_], file_name: str = 'layer.png'):
    """
    屋根レイヤーをイメージとして保存（デバッグ用）

    Args:
      layer_class (npt.NDArray[np.int_]): DSM点群の画像座標 (i,j) 二次元アレイに壁点を起点としてクラスタリングした屋根のレイヤー番号を記録したもの
      file_name (str): 記録するファイル名
    """
    height, width = layer_class.shape

    # 空の RGB 画像を作成 (すべて白で初期化)
    image_rgb = np.full((height, width, 3), 255, dtype=np.uint8)

    # i, j に基づいて各ピクセルに色を割り当て
    for i in range(height):
      for j in range(width):
        layer_number = layer_class[i, j]
        image_rgb[i, j] = self.get_color(layer_number)  # レイヤーに対応する色を設定

    image_layer = Image.fromarray(image_rgb, 'RGB')
    image_layer_path = os.path.join(self._debug_dir, file_name)
    image_layer.save(image_layer_path)

  def save_roof_line_image(
      self,
      masked_dsm_grid_rgbs: npt.NDArray[np.uint8],
      roof_lines: set[tuple[tuple[int, int], tuple[int, int]]],
      file_name: str = 'roof_line.png',
  ):
    """
    屋根線をイメージとして保存（デバッグ用）

    Args:
      masked_dsm_grid_rgbs (npt.NDArray[np.uint8]): DSM点群のRGB画像
      roof_lines (set[tuple[tuple[int, int], tuple[int, int]]]): 線のリスト
      file_name (str): 記録するファイル名
    """

    # RGB画像データをBGRに変換（OpenCVはBGRを使用）
    image_roof_line = cv2.cvtColor(masked_dsm_grid_rgbs.copy(), cv2.COLOR_RGB2BGR)

    # 線と点を一緒に描画
    for start_image_pos, end_image_pos in roof_lines:
        # 座標を整数にキャストして x, y を入れ替え
      start_image_pos = tuple(map(int, (start_image_pos[1], start_image_pos[0])))
      end_image_pos = tuple(map(int, (end_image_pos[1], end_image_pos[0])))

      # 緑色の線、太さ1
      cv2.line(
          image_roof_line,
          start_image_pos,
          end_image_pos,
          self.get_color(RoofLayerInfo.ROOF_LINE_POINT),  # 線の色
          1
      )

      # 赤色の点を描画
      cv2.circle(
          image_roof_line,
          start_image_pos,
          0,  # 点の半径
          self.get_color(RoofLayerInfo.ROOF_VERTICE_POINT),  # 赤色
          -1  # 塗りつぶし
      )

      cv2.circle(
          image_roof_line,
          end_image_pos,
          0,  # 点の半径
          self.get_color(RoofLayerInfo.ROOF_VERTICE_POINT),  # 赤色
          -1  # 塗りつぶし
      )

    # ファイルに保存
    image_roof_line_path = os.path.join(self._debug_dir, file_name)

    cv2.imwrite(image_roof_line_path, image_roof_line)

  def get_color_palette(self, reserved_colors: list[list[int]]):
    """屋根レイヤーの色の定義する

    Args:
      reserved_colors (list[list[int]]): 予約済みの色

    Return:
      list[list[int]]: 屋根レイヤーの色を定義
    """

    color_palette_all: list[tuple[int, int, int]] = []
    for color_variation_num in [255, 128, 64, 32, 16, 8]:
      # 0, 255 の組み合わせの色を先に出す
      # 次は 0, 128, 255 の組み合わせの色を先に出す
      base_colors = list(range(0, 256, color_variation_num))
      color_palette = list(itertools.product(base_colors, repeat=3))  # すべての組み合わせを生成
      color_palette_all += list(set(color_palette) - set(color_palette_all))

    # 予約された色は抜いておく
    color_palette_result = [
        list(color_palette) for color_palette in color_palette_all
        if (list(color_palette) not in reserved_colors)
    ]

    return color_palette_result

  def get_color(self, layer_number: int):
    """屋根レイヤーの色を出す

    Args:
      layer_number (int): 屋根レイヤー

    Return:
      list[int]: RGB色
    """

    # 4096 の色を作る
    if layer_number == RoofLayerInfo.NO_POINT:
      return [255, 255, 255]

    if layer_number == RoofLayerInfo.NOISE_POINT:
      return [0, 0, 0]

    if layer_number == RoofLayerInfo.ROOF_LINE_POINT:
      return [0, 255, 0]

    return self._color_palette[layer_number]

  def get_layer_number_layer_area_polygon_ijs_list_pair(self):
    """
    屋根レイヤーの外形ポリゴンの頂点を取得

    Returns:
      dict[int, list[list[tuple[int, int]]]]
    """

    layer_number_layer_area_polygon_ijs_list_pair: dict[int, list[list[tuple[int, int]]]] = {}

    height, width = self._layer_class.shape

    layer_number_point_ijs_pair: dict[int, list[tuple[int, int]]] = defaultdict(list)

    # i, j に基づいて各ピクセルに色を割り当て
    for i in range(height):
      for j in range(width):
        layer_number = self._layer_class[i, j]
        layer_number_point_ijs_pair[layer_number].append((i, j))

    # 空の RGB 画像を作成 (すべて白で初期化)
    image_rgb = np.full((height, width, 3), 255, dtype=np.uint8)
    outline_all_image_rgb = np.full((height, width, 3), 255, dtype=np.uint8)

    search_color = [1, 1, 1]

    layer_numbers = list(layer_number_point_ijs_pair.keys())
    layer_numbers.sort()

    # 前回までマージしたのポリゴンリスト
    last_merged_polygon_ijs: list[list[tuple[int, int]]] = []
    for layer_number in layer_numbers:
      if layer_number == -1:
        continue

      point_ijs = layer_number_point_ijs_pair.get(layer_number)
      if point_ijs is None:
        continue

      # i, j に基づいて各ピクセルに色を割り当て
      for i, j in point_ijs:
        image_rgb[i, j] = search_color  # マージしたポリゴンの色

      rgb_color = self.get_color(layer_number)  # レイヤーに対応する色
      mask = cv2.inRange(image_rgb, np.array(search_color), np.array(search_color))
      contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

      # 輪郭を単純化
      simplified_polygon_ijs: list[list[tuple[int, int]]] = []
      epsilon_factor = 0.01  # 輪郭の単純化度合いの調整 (この値を調整するとポリゴンの単純化が変わる)
      for contour in contours:
        epsilon = epsilon_factor * cv2.arcLength(contour, True)  # 輪郭の長さに基づいてepsilonを計算
        approx = cv2.approxPolyDP(contour, epsilon, True)  # 輪郭を単純化
        merged_outline_polygon_ijs = [(point[0][1], point[0][0]) for point in approx]

        # 頂点が二つ以下の場合はポリゴンではない
        if len(merged_outline_polygon_ijs) >= 3:
          if Polygon(merged_outline_polygon_ijs).is_valid:
            simplified_polygon_ijs.append(merged_outline_polygon_ijs)

      # 今回までマージしたポリゴンリスト
      merged_polygon_ijs: list[list[tuple[int, int]]] = simplified_polygon_ijs
      merged_polygon_ijs.extend(last_merged_polygon_ijs)
      merged_polygons_area = unary_union([Polygon(p) for p in merged_polygon_ijs])
      current_merged_polygon_ijs_list = get_polygon_ijs_list([merged_polygons_area])

      last_merged_polygon_ijs_union = unary_union([Polygon(p) for p in last_merged_polygon_ijs])
      current_merged_polygon_ijs_list_union = unary_union([Polygon(p) for p in current_merged_polygon_ijs_list])

      # layer_numberのポリゴンリスト = 今回までマージしたポリゴンリスト - 前回までマージしたのポリゴンリスト
      difference = current_merged_polygon_ijs_list_union.difference(last_merged_polygon_ijs_union)
      current_polygon_ijs_list = get_polygon_ijs_list([difference])

      layer_number_layer_area_polygon_ijs_list_pair[layer_number] = current_polygon_ijs_list

      # 前回までマージしたのポリゴンリスト
      last_merged_polygon_ijs = current_merged_polygon_ijs_list

      # 輪郭線を描画 (塗りつぶさない)
      if self._debug_mode:
        outline_part_image_rgb = np.full((height, width, 3), 255, dtype=np.uint8)

        polygon_np = [
            np.array(polygon_ijs, np.int32)[:, ::-1].reshape((-1, 1, 2))
            for polygon_ijs in current_polygon_ijs_list
        ]
        if len(polygon_np) > 0:
          cv2.fillPoly(outline_all_image_rgb, polygon_np, color=rgb_color)
          cv2.polylines(outline_part_image_rgb, polygon_np, isClosed=True, color=rgb_color, thickness=1)

        outline_part_image_rgb = cv2.cvtColor(outline_part_image_rgb, cv2.COLOR_BGR2RGB)
        outline_part_image_path = os.path.join(self._debug_dir, f"layer_area_{layer_number}.png")
        cv2.imwrite(outline_part_image_path, outline_part_image_rgb)

    if self._debug_mode:
      outline_all_image_rgb = cv2.cvtColor(outline_all_image_rgb, cv2.COLOR_BGR2RGB)
      outline_all_image_path = os.path.join(self._debug_dir, 'layer_area.png')
      cv2.imwrite(outline_all_image_path, outline_all_image_rgb)

    return layer_number_layer_area_polygon_ijs_list_pair

  def add_balcony_layers(self, balcony_polygon_ijs_list: list[list[tuple[float, float]]]):
    """
    複数のバルコニーポリゴンに屋根レイヤーを付与

    Args:
      balcony_polygon_ijs_list (list[list[tuple[float, float]]]): バルコニポリゴンの頂点リスト(i,j)
    """

    balcony_point_ijzs: set[tuple[int, int, float]] = set()
    for balcony_polygon_ijs in balcony_polygon_ijs_list:
      balcony_poly = Polygon(balcony_polygon_ijs)
      grid_point_ijs = get_grid_point_ijs(balcony_poly)
      for i, j in grid_point_ijs:
        height, width = self._layer_class.shape[:2]
        i_clipped = min(max(int(round(i)), 0), height - 1)
        j_clipped = min(max(int(round(j)), 0), width - 1)

        z = self.ij_to_z(i_clipped, j_clipped)
        balcony_point_ijzs.add((i_clipped, j_clipped, z))
        self._layer_class[i_clipped, j_clipped] = self._layer_class_length

      self._layer_class_length += 1

    if self._debug_mode and balcony_point_ijzs:
      # バルコニー領域を画像ファイルに保存
      height, width = self._layer_class.shape

      # 空のグレースケール画像を作成 (すべて白で初期化)
      image_gray = np.full((height, width), 255, dtype=np.uint8)

      max_z = np.max([z for _, _, z in balcony_point_ijzs])
      min_z = np.min([z for _, _, z in balcony_point_ijzs])

      # デバッグ用の色変更
      for i, j, z in balcony_point_ijzs:
        normalized_z = int(((z - min_z) / (max_z - min_z)) * 255)
        image_gray[i, j] = normalized_z  # 高いほど黒

      image_layer = Image.fromarray(image_gray, 'L')
      image_layer_path = os.path.join(self._debug_dir, 'balcony_height.png')
      image_layer.save(image_layer_path)
