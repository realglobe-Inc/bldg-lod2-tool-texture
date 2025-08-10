import glob
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Optional, Union

import laspy
import math
import numpy as np
import shapely.geometry as geo
from PIL import Image, ImageDraw
from numpy.typing import NDArray
from shapely import Polygon, Point

from .create_model_exception import ModelingException
from .message import ModelingMessage
from ..util.log import Log, LogLevel, ModuleType


class PointCloud:
    """点群データ管理クラス"""

    _cloud: NDArray[np.float_]
    _colors: NDArray[np.float_]
    _init: bool
    _init_color: bool
    _index: list[int]

    @property
    def index(self) -> list[int]:
        """点群のインデックス情報のゲッター

        Returns:
            list[int]: インデックス番号のリスト
        """
        return self._index

    @index.setter
    def index(self, value: list[int]):
        """インデックス情報のセッター

        Args:
            value (list[int]): 点群のインデックス情報(紐づけたいデータがある場合)
        """
        self._index = value

    def __init__(self) -> None:
        """コンストラクタ"""
        self._cloud = np.empty([0, 0])
        self._colors = np.empty([0, 0])
        self._init = False
        self._init_color = False
        self._index = []

    def add_points(self, points: NDArray):
        """点群追加

        Args:
            points (NDArray): 点群配列
        """
        if self._init:
            self._cloud = np.append(self._cloud, points, axis=0)
        else:
            self._cloud = points
            self._init = True

    def get_points(self, offset=np.array([0.0, 0.0, 0.0])):
        """点群取得

        Args:
            offset (NDArray, optional): 座標点のオフセット値.
                                       Defaults to np.array([0.0, 0.0, 0.0]).

        Returns:
            NDArray: 点群配列
        """
        cloud = self._cloud
        offset_size = np.linalg.norm(offset, ord=2)
        if len(cloud) > 0 and offset_size != 0:
            cloud = cloud + offset

        return cloud

    def add_colors(self, colors: NDArray):
        """色追加

        Args:
            colors (NDArray): 色配列
        """
        if self._init_color:
            self._colors = np.append(self._colors, colors, axis=0)
        else:
            self._colors = colors
            self._init_color = True

    def get_colors(self):
        """色取得

        Returns:
            NDArray: 色配列
        """
        return self._colors

    @property
    def min(self) -> Optional[NDArray[np.float_]]:
        """各座標の最小値

        Returns:
            NDArray:
                各座標の最小値配列
                点が格納されていない場合はNoneを返却

        """
        if len(self._cloud) < 1:
            return None

        return np.min(self._cloud, axis=0)

    @property
    def max(self) -> Optional[NDArray[np.float_]]:
        """各座標の最大値

        Returns:
            NDArray:
                各座標の最大値配列
                点が格納されていない場合はNoneを返却
        """
        if len(self._cloud) < 1:
            return None

        return np.max(self._cloud, axis=0)

    def thin_out(self, n: int) -> "PointCloud":
        """点群データを間引く

        Args:
            n (int): 何点に1点を残すか指定する値

        Returns:
            PointCloud: 間引かれた点群データ
        """
        result = PointCloud()
        if len(self._cloud) > 0:
            result.add_points(self._cloud[::n])
            if len(self._colors) > 0:
                result.add_colors(self._colors[::n])
            if len(self._index) > 0:
                result.index = self._index[::n]
        return result

    def __str__(self):
        return f"({self._cloud.shape}, {self._colors.shape}, {len(self.index)})"

    def __repr__(self):
        return (
            f"PointCloud({self._cloud.shape}, {self._colors.shape}, {len(self.index)})"
        )

    def save_debug_image(
        self,
        output_file_path: Path,
        grid_size: float,
        canvas_size: tuple[int, int] = None,
        offset_xy: tuple[float, float] = None,
        polygons: list[Polygon] | None = None,
    ) -> tuple[tuple[int, int], tuple[float, float]]:
        """
        点群のデバッグ画像を生成し、保存する。

        :param output_file_path: 画像を保存するパス。
        :param grid_size: 画像の1ピクセルの幅に相当する座標系上の距離。
        :param canvas_size: 画像のサイズ。指定しない場合、点群の座標範囲とgrid_sizeに基づいて計算される。
        :param offset_xy: 画像の始点に合わせる座標。指定しない場合、点群の座標範囲の始点が利用される。
        :param polygons: 座標列からなるポリゴンのリスト。画像上に追加で描画される。
        :return: 画像サイズと画像の始点に合わせる座標。
        """
        # 画像の範囲を取得する
        min_x, min_y = self._cloud[:, :2].min(axis=0)
        max_x, max_y = self._cloud[:, :2].max(axis=0)

        if canvas_size is not None:
            width, height = canvas_size
        else:
            width = int(math.ceil((max_x - min_x) / grid_size))
            height = int(math.ceil((max_y - min_y) / grid_size))
        if offset_xy is not None:
            offset_x, offset_y = offset_xy
        else:
            offset_x, offset_y = min_x, min_y

        # 白い背景の画像を作成する
        buff = np.full((height, width, 3), 255, dtype=np.uint8)

        # 点座標をピクセル座標に変換する
        pixel_x = ((self._cloud[:, 0] - offset_x) / grid_size).astype(int)
        pixel_y = ((self._cloud[:, 1] - offset_y) / grid_size).astype(int)

        # Get colors
        colors = self._colors
        if len(colors) > 0 and (colors.max() >= 256).any():
            colors = (colors / 256).astype(np.uint8)

        # ピクセルを塗る
        for i in range(len(self._cloud)):
            if i < len(colors):
                buff[pixel_y[i], pixel_x[i]] = colors[i]
            else:
                # iがcolorsの範囲外なら黒に設定する
                buff[pixel_y[i], pixel_x[i]] = [0, 0, 0]

        image = Image.fromarray(buff)
        for polygon in polygons if polygons is not None else []:
            # polygonの座標から画像の位置を計算して線を引く
            draw = ImageDraw.Draw(image)
            coords = list(polygon.exterior.coords)
            pixel_coords = [
                ((x - offset_x) / grid_size, (y - offset_y) / grid_size)
                for x, y in coords
            ]
            draw.line(pixel_coords, fill=(255, 0, 0), width=1)

        # 画像を保存する
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_file_path)

        return (width, height), (offset_x, offset_y)


class LasFileInfo:
    """LASファイル情報クラス"""

    @property
    def path(self) -> str:
        """ファイルパス

        Returns:
            str: ファイルパス
        """
        return self._path

    @path.setter
    def path(self, value: str):
        """ファイルパス

        Args:
            value (str): ファイルパス
        """
        self._path = value

    @property
    def min_x(self) -> float:
        """最小x座標

        Returns:
            float: 最小x座標
        """
        return self._min_x

    @min_x.setter
    def min_x(self, value: float):
        """最小x座標

        Args:
            value (float): 最小x座標
        """
        self._min_x = value

    @property
    def min_y(self) -> float:
        """最小y座標

        Returns:
            float: 最小y座標
        """
        return self._min_y

    @min_y.setter
    def min_y(self, value: float):
        """最小y座標

        Args:
            value (float): 最小y座標
        """
        self._min_y = value

    @property
    def max_x(self) -> float:
        """最大x座標

        Returns:
            float: 最大x座標
        """
        return self._max_x

    @max_x.setter
    def max_x(self, value: float):
        """最大x座標

        Args:
            value (float): 最大x座標
        """
        self._max_x = value

    @property
    def max_y(self) -> float:
        """最大y座標

        Returns:
            float: 最大y座標
        """
        return self._max_y

    @max_y.setter
    def max_y(self, value: float):
        """最大y座標

        Args:
            value (float): 最大y座標
        """
        self._max_y = value

    def __init__(
        self, path: str, min_x: float, min_y: float, max_x: float, max_y: float
    ):
        """コンストラクタ

        Args:
            path (str): ファイルパス
            min_x (float): 最小座標x
            min_y (float): 最小座標y
            max_x (float): 最大座標x
            max_y (float): 最大座標y
        """
        self.path = path
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y

    def get_area_polygon(self):
        """データ範囲のバウンディングボックス

        Returns:
            shapely.geometry.box: LASデータ範囲のバウンディングボックス
        """
        box = geo.box(self.min_x, self.min_y, self.max_x, self.max_y)
        return box


class LasManager:
    """LASデータマネージャー"""

    def __init__(self, swap_xy=False) -> None:
        """コンストラクタ

        Args:
            swap_xy (bool, optional):\
                True:xy座標を入れ替えて保持する,\
                False:入力値のまま保持する. Defaults to False.
        """
        self._min_pos = np.array([0, 0])
        self._max_pos = np.array([0, 0])
        self._target_files = []
        self._building_polygon = Polygon()
        self._ground_polygon = Polygon()
        self._is_search_ground = False
        self._swap_xy = swap_xy

        # RGB情報を保持しているレコードフォーマットの番号
        self._COLOR_RECORD_FORMATS = [2, 3, 5, 7, 8, 10]

    def get_area_size(self):
        """点群範囲

        Returns:
            float, float: 幅[m], 高さ[m]
        """
        width = self._max_pos[0] - self._min_pos[0]
        height = self._max_pos[1] - self._min_pos[1]
        return width, height

    def read_header(self, folder_path: str, polygon: Polygon):
        """ヘッダ情報の読込

        Args:
            folder_path (str): LASフォルダパス
            polygon (Polygon): 読込対象範囲(平面直角座標系)

        Raises:
            ModelingException: LASフォルダが存在しない
            ModelingException: LASファイルが存在しない
            ModelingException: 読込対象範囲の点群データがない
        """
        class_name = self.__class__.__name__
        func_name = sys._getframe().f_code.co_name

        self._target_files = []  # 初期化
        if not os.path.isdir(folder_path):
            # フォルダが存在しない場合
            msg = "{}.{}, {}".format(
                class_name,
                func_name,
                ModelingMessage.ERR_MSG_LAS_MNG_LAS_FOLDER_NOT_FOUND,
            )
            raise ModelingException(msg)

        files = glob.glob(os.path.join(folder_path, "*.las")) + glob.glob(
            os.path.join(folder_path, "*.laz")
        )
        if len(files) == 0:
            # lasファイルが存在しない場合
            msg = "{}.{}, {}".format(
                class_name, func_name, ModelingMessage.ERR_MSG_LAS_MNG_LAS_NOT_FOUND
            )
            raise ModelingException(msg)

        min_pos = np.array([sys.float_info.max, sys.float_info.max])
        max_pos = np.array([-sys.float_info.max, -sys.float_info.max])
        for file in files:
            try:
                # headerの読み込み(pointにアクセスしないためopenを使用)
                with laspy.open(file) as las:
                    if self._swap_xy:
                        # xy座標を入れ替える
                        x_min = las.header.y_min
                        x_max = las.header.y_max
                        y_min = las.header.x_min
                        y_max = las.header.x_max
                    else:
                        # 入力値をそのまま使用する
                        x_min = las.header.x_min
                        x_max = las.header.x_max
                        y_min = las.header.y_min
                        y_max = las.header.y_max

                    # polygonとの重畳確認
                    las_polygon = Polygon(
                        [
                            (x_min, y_min),
                            (x_min, y_max),
                            (x_max, y_max),
                            (x_max, y_min),
                            (x_min, y_min),
                        ]
                    )

                    # 重畳しない場合はskip
                    if las_polygon.disjoint(polygon):
                        continue

                    file_info = LasFileInfo(file, x_min, y_min, x_max, y_max)

                    self._target_files.append(file_info)

                    if x_min < min_pos[1]:
                        min_pos[1] = x_min
                    if y_min < min_pos[0]:
                        min_pos[0] = y_min
                    if x_max > max_pos[1]:
                        max_pos[1] = x_max
                    if y_max > max_pos[0]:
                        max_pos[0] = y_max
            except Exception:
                # ヘッダ情報取得時のエラー
                msg = "{}.{}, {} ({})".format(
                    class_name,
                    func_name,
                    ModelingMessage.ERR_MSG_FAILED_TO_READ_LAS_FILE,
                    os.path.basename(file),
                )
                Log.output_log_write(
                    LogLevel.WARN, ModuleType.MODEL_ELEMENT_GENERATION, msg
                )

        if len(self._target_files) == 0:
            # 点群データ取得対象のデータがない場合
            msg = "{}.{}, {}".format(
                class_name, func_name, ModelingMessage.ERR_MSG_LAS_MNG_NO_LAS_FILE
            )
            raise ModelingException(msg)

        self._min_pos = min_pos
        self._max_pos = max_pos

    def get_points(
        self, building_polygon: Polygon, ground_polygon: Polygon = None
    ) -> tuple[PointCloud, Union[float, None], Union[float, None], int]:
        """点群データの取得

        Args:
            building_polygon (Polygon): 取得対象範囲
            ground_polygon (Polygon): 地面探索範囲

        Returns:
            PointCloud: 点群データ
            float:      最低地面の高さm(地面探索を行う場合、行わない場合はNone)
            float:      前処理用の地面の高さm(地面探索を行う場合、行わない場合はNone)
        """

        # 並列処理の準備
        cpu_num = multiprocessing.cpu_count()
        pool = multiprocessing.Pool(cpu_num)

        class_name = self.__class__.__name__
        func_name = sys._getframe().f_code.co_name

        self._building_polygon = geo.polygon.orient(building_polygon)
        if ground_polygon is not None:
            # 地面探索を行う場合
            self._ground_polygon = geo.polygon.orient(ground_polygon)
            self._is_search_ground = True
        else:
            # 地面探索を行わない場合
            self._ground_polygon = Polygon()
            self._is_search_ground = False

        # 点群の準備
        cloud = PointCloud()
        cloud_ground = PointCloud()

        min_height = None
        for file in self._target_files:
            box = file.get_area_polygon()
            if not self._building_polygon.disjoint(box) or (
                self._is_search_ground and not self._ground_polygon.disjoint(box)
            ):
                # 建物外形/地面探索範囲とLASデータ範囲が接している場合

                las = laspy.read(file.path)
                # 座標値の取得
                if self._swap_xy:
                    # xy座標を入れ替える
                    points = np.stack([las.y, las.x, las.z], axis=0).transpose((1, 0))
                else:
                    # 入力値をそのまま使用する
                    points = np.stack([las.x, las.y, las.z], axis=0).transpose((1, 0))

                # 色情報の取得
                pf: laspy.PointFormat = las.header.point_format
                if pf.id in self._COLOR_RECORD_FORMATS:
                    colors = np.stack([las.red, las.green, las.blue], axis=0).transpose(
                        (1, 0)
                    )

                    # 8bitデータ対応
                    if np.max(colors) < 256:  # 8bit画像？
                        colors *= 256
                else:
                    msg = "{}.{}, {}".format(
                        class_name,
                        func_name,
                        ModelingMessage.ERR_MSG_LAS_MNG_UNSUPPORTED_LAS_FORMAT,
                    )
                    raise ModelingException(msg)

                # polygonの最小外接長方形でpointをfilterする
                polygon_mbr: tuple[float, float, float, float] = (
                    self._ground_polygon
                    if self._is_search_ground
                    else self._building_polygon
                ).bounds  # type: ignore
                in_mbr = (
                    (polygon_mbr[0] <= points[:, 0])
                    & (points[:, 0] <= polygon_mbr[2])
                    & (polygon_mbr[1] <= points[:, 1])
                    & (points[:, 1] <= polygon_mbr[3])
                )

                # 並列化処理
                try:
                    # 屋根点取得 + 地面探索
                    ret = pool.map(self._check_point_in_polygon, points[in_mbr])
                    conv_ret = np.zeros((len(points), 2), dtype=np.int_)
                    # list -> NDArray
                    conv_ret[in_mbr] = np.array(ret, dtype=np.int_)
                    # polygon内の点のみ取得
                    ex_points = points[conv_ret[:, 0] == 1]
                    cloud.add_points(ex_points)

                    if pf.id in self._COLOR_RECORD_FORMATS:
                        # polygon内の点のみ取得
                        ex_colors = colors[conv_ret[:, 0] == 1]
                        cloud.add_colors(colors=ex_colors)
                    else:
                        msg = "{}.{}, {}".format(
                            class_name,
                            func_name,
                            ModelingMessage.ERR_MSG_LAS_MNG_UNSUPPORTED_LAS_FORMAT,
                        )
                        raise ModelingException(msg)

                    if self._is_search_ground:
                        # 地面探索範囲内の点のみ取得
                        target_points = points[
                            np.logical_and(conv_ret[:, 0] == 0, conv_ret[:, 1] == 1)
                        ]
                        cloud_ground.add_points(target_points)

                        if len(target_points) > 0:
                            # z座標の最小値
                            height = target_points[:, 2].min()

                            if min_height is None:
                                min_height = height
                            else:
                                if min_height > height:
                                    min_height = height  # 最小値の更新

                except Exception as e:
                    # 点群取得時のエラー
                    class_name = self.__class__.__name__
                    func_name = sys._getframe().f_code.co_name
                    msg = "{}.{}, {}".format(class_name, func_name, e)
                    Log.output_log_write(
                        LogLevel.WARN, ModuleType.MODEL_ELEMENT_GENERATION, msg
                    )

        if len(cloud.get_points()) == 0:
            # 建物点群がない場合
            msg = "{}.{}, {}".format(
                class_name, func_name, ModelingMessage.ERR_MSG_LAS_MNG_NO_POINTS
            )
            raise ModelingException(msg)

        ground_height = None
        if self._is_search_ground:
            points_xyz = cloud_ground.get_points()
            if len(points_xyz) == 0:
                # 地面点群がない場合
                msg = "{}.{}, {}".format(
                    class_name,
                    func_name,
                    ModelingMessage.ERR_MSG_LAS_MNG_NO_GROUND_POINTS,
                )
                raise ModelingException(msg)

            zs = points_xyz[:, 2]
            z_min = np.min(zs)
            z_max = np.max(zs)
            indices = np.logical_and(zs >= z_min, zs <= (z_min + z_max) / 2)
            zs = zs[indices]
            n_bins = int((np.max(zs) - np.min(zs) + 0.5) // 1.0)
            n_bins = max(n_bins, 2)
            hist, bins = np.histogram(zs, bins=n_bins)
            ind = np.argmax(hist)
            ground_height = (bins[ind] + bins[ind + 1]) / 2

        # 点の数が閾値を超えてたら後の処理（主にDBSCAN）でメモリが溢れないように間引く
        points_threshold = 4_000_000
        thin_rate = 1
        points = cloud.get_points()
        if len(points) > points_threshold:
            thin_rate = len(points) // points_threshold + 1
            print(f"点群を1/{thin_rate}に間引きます")
            cloud = cloud.thin_out(thin_rate)

        return cloud, min_height, ground_height, thin_rate

    def _check_point_in_polygon(self, pos: NDArray):
        """座標点のポリゴン内外判定

        Args:
            pos (NDArray): 座標点(x,y,z)を想定

        Returns:
            int: 1の場合はポリゴン内, 0の場合はポリゴン外
        """
        # 建物外形内か確認する
        pt = Point(pos[0], pos[1])
        is_building = 0
        if pt.within(self._building_polygon):
            is_building = 1

        # 地面探索実施時は、地面探索範囲内か確認する
        is_ground = 0
        if self._is_search_ground and pt.within(self._ground_polygon):
            is_ground = 1

        return [is_building, is_ground]
