import os
import pathlib
from enum import Enum
from typing import Union

import cv2
import numpy as np
from shapely import LineString
from shapely import Point
from shapely import Polygon

from .photo_image import PhotoImage
from ..util.cv_support_jp import Cv2Japanese
from ..util.face_info import MaterialInfo
from ..util.log import Log, ModuleType, LogLevel
from ..util.obj_info import BldElementType, ObjInfo


class VerticalObject:
    """建物情報クラス"""

    def __init__(
        self,
        obj_path: str,
        photo_num: int,
        photo_list: list[PhotoImage],
        texture_output_width_max: int,
        texture_output_height_max: int,
    ) -> None:
        """コンストラクタ

        Args:
          obj_path (str): OBJフォルダパス
          photo_num (int): 写真枚数
          photo_list (list[PhotoImage]): 写真のリスト
          texture_output_width_max (int): テクスチャー横幅最大値(4096まで設定可)
          texture_output_height_max (int): テクスチャー縦幅最大値(4096まで設定可)
        """
        self._photo_num = photo_num  # 写真数
        self._photo_list = photo_list  # 写真リスト

        # テクスチャ画像出力オブジェクト作成
        self._tex_collection = DstTextureFile(
            texture_output_width_max, texture_output_height_max
        )
        self._roof_texture = list()  # 屋根面テクスチャ情報
        self._wall_texture = list()  # 壁面テクスチャ情報

        self._vertex_roof = list()
        self._vertex_wall = list()

        # OBJファイル読み出し
        self._obj_info = ObjInfo()
        self._obj_info.read_file(obj_path)
        self._obj_filename = os.path.splitext(os.path.basename(obj_path))[0]

        # 屋根面の座標配列読み込み
        polygon_list_r = self._obj_info.get_polygon_list(BldElementType.ROOF)
        if polygon_list_r:
            for poly in polygon_list_r:
                ar = np.zeros((0, 3))
                for pos in poly:
                    ar = np.append(ar, np.array([[pos.x, pos.y, pos.z]]), axis=0)
                self._vertex_roof.append(ar)

        # 壁面の座標配列読み込み
        polygon_list_w = self._obj_info.get_polygon_list(BldElementType.WALL)
        if polygon_list_w:
            for poly in polygon_list_w:
                ar = np.zeros((0, 3))
                for pos in poly:
                    ar = np.append(ar, np.array([[pos.x, pos.y, pos.z]]), axis=0)
                self._vertex_wall.append(ar)

    def select_roof_texture(self):
        """屋根面テクスチャ画像を検索してセットする"""
        tex_collection = self._tex_collection

        # 屋根用テクスチャ情報オブジェクトを確保
        self._roof_texture = [TextureInfo() for i in range(len(self._vertex_roof))]

        # 屋根面のテクスチャ画像として使用する写真を決定する
        # 屋根面枚数分のテクスチャを全画像から検索
        for r_idx, ver_roof in enumerate(self._vertex_roof):
            tex_coord = np.zeros((len(ver_roof), 2))  # 画像上の座標
            roof_coord = np.zeros((len(ver_roof), 2))
            max_area, area = 0.0, 0.0
            roof_valid = [0] * len(ver_roof)
            set_idx = 0  # 写真のインデックス

            for i in range(self._photo_num):
                # 屋根面一枚分の座標の、画像範囲内の頂点位置数を求める
                in_count = 0
                for j, ver in enumerate(ver_roof):
                    roof_valid[j] = self._photo_list[i].get_image_pos(ver, tex_coord[j])
                    if roof_valid[j]:
                        in_count += 1

                if in_count < len(ver_roof):
                    continue

                # 全点が画像上の点であれば面積最大の画像を選択する
                point = [0] * len(tex_coord)
                for num, tex in enumerate(tex_coord):
                    point[num] = Point(tex)
                area = Polygon(point).area
                if area < max_area:
                    continue
                max_area = area
                set_idx = i
                roof_coord = tex_coord.copy()

            if np.all(roof_coord == 0):
                # テクスチャ画像が見つかったか
                continue

            # テクスチャ画像が未登録の場合は追加
            if set_idx not in (
                srcTex.ref_image_index for srcTex in tex_collection.src_texture
            ):

                # 参照テクスチャ画像オブジェクトを作成
                new_src_tex = tex_collection.get_new_src_texture()
                new_src_tex.ref_image_index = set_idx
                new_src_tex.ref_image = self._photo_list[set_idx]

            # 屋根面の座標配列を追加
            for tex in tex_collection.src_texture:
                if tex.ref_image_index == set_idx:
                    self._roof_texture[r_idx].tex_ver = tex.append_texture_coord(
                        roof_coord
                    )
                    self._roof_texture[r_idx].tex_info = tex
                    self._roof_texture[r_idx].pol_area = max_area

                    ref_img = self._photo_list[set_idx].filename
                    Log.output_log_write(
                        LogLevel.DEBUG,
                        ModuleType.PASTE_TEXTURE,
                        "roof refImage:" + ref_img,
                    )

    def select_wall_texture(self):
        """壁面テクスチャ画像を検索してセットする"""
        # テクスチャ画像出力オブジェクト
        tex_collection = self._tex_collection

        # 壁面用テクスチャ情報オブジェクトを確保
        self._wall_texture = [TextureInfo() for i in range(len(self._vertex_wall))]

        for w_idx, wall in enumerate(self._vertex_wall):
            set_idx = 0  # 写真のインデックス
            r_common = list()
            r_tmp = list()
            max_area, area = 0.0, 0.0
            roof_idx = 0
            img_pos_chk = True
            set_wall_img_pos = np.zeros((len(wall), 2))

            # 接地する屋根面の検索/屋根面と一致する頂点の検索
            for i in range(len(self._vertex_roof)):
                r_tmp = [r for r in self._vertex_roof[i] if r in wall]

                # 2頂点以上接地している屋根面が対象
                if 1 < len(r_tmp):
                    if len(r_common) != 0:
                        # すでに入っている屋根面の方が高い位置にある場合
                        if r_tmp[0][2] < r_common[0][2]:
                            continue
                    r_common = r_tmp.copy()
                    roof_idx = i

            # 全写真から壁面に最適なテクスチャを検索
            for i in range(self._photo_num):
                roof_img_pos = np.zeros((len(self._vertex_roof[roof_idx]), 2))
                wall_img_pos = np.zeros((len(wall), 2))

                img_pos_chk = True

                # 対象の屋根面が画像の範囲内にあるか
                for num, r_ver in enumerate(self._vertex_roof[roof_idx]):
                    if not self._photo_list[i].get_image_pos(r_ver, roof_img_pos[num]):
                        # 指定範囲は画像外
                        img_pos_chk = False
                        break

                # 対象の壁面が画像の範囲内にあるか
                for num, w_ver in enumerate(wall):
                    if not self._photo_list[i].get_image_pos(w_ver, wall_img_pos[num]):
                        # 指定範囲は画像外
                        img_pos_chk = False
                        break

                if not img_pos_chk:
                    # 対象の屋根面と壁面が画像の範囲内にない
                    continue

                # 陰面判定
                if self._judge_hidden_surface(
                    wall, wall_img_pos, roof_img_pos, r_common
                ):
                    # 陰面あり
                    continue

                # 壁面用テクスチャ情報保持
                # より最適なテクスチャが見つかった場合は上書き
                # 全点が画像上の点であれば面積最大の画像を選択する
                point = [0] * len(wall_img_pos)
                for num, tex in enumerate(wall_img_pos):
                    point[num] = Point(tex)
                area = Polygon(point).area
                if area < max_area:
                    continue
                max_area = area
                set_idx = i
                set_wall_img_pos = wall_img_pos.copy()

            if np.all(set_wall_img_pos == 0):
                # テクスチャ画像が見つかったか
                continue

            # テクスチャ画像が未登録の場合は追加
            if set_idx not in (
                srcTex.ref_image_index for srcTex in tex_collection.src_texture
            ):
                # 参照テクスチャ画像オブジェクトを作成
                new_src_tex = tex_collection.get_new_src_texture()
                new_src_tex.ref_image_index = set_idx
                new_src_tex.ref_image = self._photo_list[set_idx]

            # 壁面毎のテクスチャ情報を追加
            for tex in tex_collection.src_texture:
                if tex.ref_image_index == set_idx:
                    self._wall_texture[w_idx].tex_ver = tex.append_texture_coord(
                        set_wall_img_pos
                    )
                    self._wall_texture[w_idx].tex_info = tex
                    self._wall_texture[w_idx].pol_area = max_area

                    ref_img = self._photo_list[set_idx].filename
                    Log.output_log_write(
                        LogLevel.DEBUG,
                        ModuleType.PASTE_TEXTURE,
                        f"wall refImage: {ref_img}",
                    )

    def _judge_hidden_surface(self, wall, wall_img_pos, roof_img_pos, r_common):
        """壁面の陰面判定

        Args:
          wall (float[]): 壁面の座標(絶対座標)
          wall_img_pos (float[]): 壁面の座標(画像座標)
          roof_img_pos (float[]): 屋根面の座標(画像座標)
          r_common (float[]): 壁面座標のうち、屋根面と重複している座標(絶対座標)

        Returns:
          bool: 陰面あり(True)/陰面なし(False)
        """
        prev_flag = FaceInfo.NONE
        next_flag = FaceInfo.NONE
        prev_ver = [0 for i in range(2)]
        img_pos_chk = True
        # 壁面の最初の頂点を最後に追加する(一周確認を行う)
        wall_around = np.append(wall, [wall[0]], axis=0)
        for num, w_ver in enumerate(wall_around):
            img_pos_chk = False

            if any(np.array_equal(ary, w_ver) for ary in np.array(r_common)):
                next_flag = FaceInfo.ROOF
            else:
                next_flag = FaceInfo.NOT_ROOF

            w_num = num
            if num == len(wall_img_pos):
                w_num = 0

            # 屋根面の頂点を含む(陰面判定対象)
            if prev_flag == FaceInfo.NOT_ROOF and next_flag == FaceInfo.ROOF:
                # 屋根面→屋根面以外
                tuple_equal = np.where(
                    [
                        np.array_equal(ary, wall_img_pos[w_num])
                        for ary in np.array(roof_img_pos)
                    ]
                )
                img_pos_chk = self._is_occluded_by_self(
                    tuple_equal[0][0], prev_ver, roof_img_pos
                )

            elif prev_flag == FaceInfo.ROOF and next_flag == FaceInfo.NOT_ROOF:
                # 屋根面以外→屋根面
                tuple_equal = np.where(
                    [np.array_equal(ary, prev_ver) for ary in np.array(roof_img_pos)]
                )
                img_pos_chk = self._is_occluded_by_self(
                    tuple_equal[0][0], wall_img_pos[w_num], roof_img_pos
                )

            if img_pos_chk:
                # 陰面である
                return img_pos_chk

            if num == len(wall_img_pos):
                # 追加した最後の頂点まで検索したら抜ける
                break

            prev_flag = next_flag
            prev_ver = wall_img_pos[num]

        return img_pos_chk

    @staticmethod
    def _is_occluded_by_self(index, img_base_pt, ver_img_pt):
        """ある頂点の底面(地盤)位置が自身の陰面かどうかを判定する

        Args:
          index (int): 交差判定対象の面のインデックス
          img_base_pt (float[]): 判定対象の頂点
          ver_img_pt (float[]): 交差判定を行う面の座標情報

        Returns:
          bool: 陰面(True)/陰面ではない(False)
        """
        num_ver = len(ver_img_pt)

        a = []
        for img_pt in ver_img_pt:
            a.append((img_pt[0], img_pt[1]))

        polygon = Polygon(a)
        if polygon.contains(Point(img_base_pt[0], img_base_pt[1])):
            return True

        # 頂点と写真中心を結ぶ直線と、頂点に隣接しない線分が交差するかどうかで判定する
        for i in range(num_ver):
            ie = (i + 1) % num_ver
            # 頂点と隣接する線分は検証対象外
            if (i == index) or (ie == index):
                continue

            line1 = LineString(
                [
                    (img_base_pt[0], img_base_pt[1]),
                    (ver_img_pt[index][0], ver_img_pt[index][1]),
                ]
            )
            line2 = LineString(
                [
                    (ver_img_pt[i][0], ver_img_pt[i][1]),
                    (ver_img_pt[ie][0], ver_img_pt[ie][1]),
                ]
            )
            if line1.touches(line2):
                return True
            # if Geometry::isCrossing(img_base_pt, ver_img_pt[index], ver_img_pt[i], ver_img_pt[ie]):
            # 交差する場合は陰面
            #    return TRUE

        return False

    def output_texture(
        self, obj_dir: str, output_dir: str, mtl_file_name: str, image_format: str
    ):
        """テクスチャ画像・情報の出力

        Args:
          obj_dir (str): OBJファイル出力先フォルダパス
          output_dir (str): テクスチャ情報出力先のフォルダパス
          mtl_file_name (str): マテリアルファイルパス
          image_format (str): 出力形式

        Returns:
          bool: テクスチャ画像出力結果
        """
        # テクスチャ画像の出力
        ret = self._tex_collection.output_texture(
            os.path.join(output_dir, self._obj_filename),
            image_format,
            self._obj_filename,
        )

        if ret:
            for num, roof in enumerate(self._roof_texture):
                if roof.pol_area != 0:
                    out_tex_ver = roof.tex_info.output_coord[roof.tex_ver]
                    p = list()
                    for ver in out_tex_ver:
                        p.append(Point(ver[0], ver[1]))
                    self._obj_info.append_texture(BldElementType.ROOF, num, p)

            for num, wall in enumerate(self._wall_texture):
                if wall.pol_area != 0:
                    out_tex_ver = wall.tex_info.output_coord[wall.tex_ver]
                    p = list()
                    for ver in out_tex_ver:
                        p.append(Point(ver[0], ver[1]))
                    self._obj_info.append_texture(BldElementType.WALL, num, p)

            # マテリアル情報設定
            mtl_info = MaterialInfo(self._obj_filename)
            img_path = os.path.join(
                pathlib.Path(output_dir).name, self._obj_filename + "." + image_format
            )
            # テクスチャ画像パスの区切り文字は/固定とする
            mtl_info.map_kd = img_path.replace(os.path.sep, "/")

            self._obj_info.mtl_file_name = mtl_file_name
            self._obj_info.set_mtl_info(mtl_info)

            output_path = os.path.join(obj_dir, self._obj_filename + ".obj")
            self._obj_info.write_file(output_path)

        return ret

    def output_optional_obj(
        self, obj_dir: str, texture_dir: str, mtl_file_name: str, image_format: str
    ):
        """オプションのOBJ出力処理(最終結果にOBJファイルを出力する場合の処理)

        Args:
          obj_dir (str): OBJファイル出力先フォルダパス
          texture_dir (str): テクスチャ画像フォルダパス
          mtl_file_name (str): マテリアルファイルパス
          image_format (str): 画像形式

        Note:
          output_texture()を先に呼び出す必要がある\n
          オプション出力のOBJファイルはCityGMLのテクスチャ画像を参照するため、
          この処理ではテクスチャ画像の出力はせず、output_texture()に任せる
        """
        # obj出力フォルダ基点のテクスチャ画像の相対パス
        relpath = os.path.relpath(texture_dir, obj_dir)

        for num, roof in enumerate(self._roof_texture):
            if roof.pol_area != 0:
                out_tex_ver = roof.tex_info.output_coord[roof.tex_ver]
                p = list()
                for ver in out_tex_ver:
                    p.append(Point(ver[0], ver[1]))
                self._obj_info.append_texture(BldElementType.ROOF, num, p)

        for num, wall in enumerate(self._wall_texture):
            if wall.pol_area != 0:
                out_tex_ver = wall.tex_info.output_coord[wall.tex_ver]
                p = list()
                for ver in out_tex_ver:
                    p.append(Point(ver[0], ver[1]))
                self._obj_info.append_texture(BldElementType.WALL, num, p)

        # マテリアル情報設定
        mtl_info = MaterialInfo(self._obj_filename)
        image_path = os.path.join(relpath, self._obj_filename + "." + image_format)
        # テクスチャ画像パスの区切り文字は/固定とする
        mtl_info.map_kd = image_path.replace(os.path.sep, "/")

        self._obj_info.mtl_file_name = mtl_file_name
        self._obj_info.set_mtl_info(mtl_info)

        output_path = os.path.join(obj_dir, self._obj_filename + ".obj")
        self._obj_info.write_file(output_path, swap_xy=False)


class FaceInfo(Enum):
    """面情報定義クラス"""

    NONE = 0
    ROOF = 1
    NOT_ROOF = 2


class SrcTexture:
    """テクスチャ画像クラス"""

    def __init__(self):
        """コンストラクタ"""
        # 参照する写真
        self.ref_image = None
        # 参照する写真のphotoListインデックス
        self.ref_image_index = 0
        # オリジナルのテクスチャ座標配列
        self.tex_coord = list()
        # 貼り付け先のテクスチャ座標配列
        self.output_coord = list()

        # 割り当て済みテクスチャ座標数
        self.num_tex_coord = -1
        # 参照フラグ
        self.ref_flag = 0

    def append_texture_coord(self, point):
        """テクスチャ座標を追加する

        Args:
          point (float[]): 追加する座標

        Returns:
          int: 追加された座標の合計数
        """
        self.num_tex_coord += 1
        self.tex_coord.append(point)
        return self.num_tex_coord


class TextureInfo:
    """テクスチャ情報クラス"""

    def __init__(self):
        """コンストラクタ"""
        # 参照テクスチャ
        self.tex_info = None
        # オリジナル画像での各頂点のテクスチャ座標インデックス
        self.tex_ver = 0
        # 設定された参照テクスチャにおける画像座標系での面積
        self.pol_area = 0


class DstTextureFile:
    """出力テクスチャファイルクラス"""

    def __init__(
        self,
        texture_output_width_max: Union[float],
        texture_output_height_max: Union[float],
    ):
        """コンストラクタ
        Args:
          texture_output_width_max (int): テクスチャー横幅最大値(4096まで設定可)
          texture_output_height_max (int): テクスチャー縦幅最大値(4096まで設定可)
        """
        # 入力テクスチャ画像
        self.src_texture = list()
        # 入力テクスチャ画像数
        self.num_src_tex = 0
        self._output_margin = 2

        self.texture_output_width_max = texture_output_width_max
        self.texture_output_height_max = texture_output_height_max

    def get_new_src_texture(self):
        """入力テクスチャオブジェクトを作成する

        Returns:
          tex_info: 入力テクスチャオブジェクト
        """
        tex_info = SrcTexture()
        self.src_texture.append(tex_info)
        self.num_src_tex += 1
        return tex_info

    def output_texture(self, output_path: str, image_format: str, obj_name: str = ""):
        """テクスチャ画像出力

        Args:
          output_path (str): テクスチャ情報出力先のフォルダパス
          image_format (str): 画像出力形式
          obj_name (str): 対象のオブジェクト名

        Returns:
          bool: テクスチャ出力成功(True)/テクスチャ出力画像なし(False)
        """

        def get_tex_poly_bbox(tex_ver, img_width, img_height):
            min_ver = np.floor(np.minimum.reduce(tex_ver)).astype(np.int32)
            max_ver = np.ceil(np.maximum.reduce(tex_ver)).astype(np.int32)
            if (
                (0 <= min_ver[0] - self._output_margin)
                and (0 <= min_ver[1] - self._output_margin)
                and (max_ver[0] + self._output_margin < img_width)
                and (max_ver[1] + self._output_margin < img_height)
            ):
                # 元画像をはみ出さない場合、マージンをつける
                min_ver = min_ver - self._output_margin
                max_ver = max_ver + self._output_margin
                output_margin = self._output_margin
            else:
                output_margin = 0

            polygon_w = max_ver[0] - min_ver[0] + 1
            polygon_h = max_ver[1] - min_ver[1] + 1

            return min_ver[0], min_ver[1], polygon_w, polygon_h, output_margin

        if self.num_src_tex < 1:
            return False

        # 出力画像サイズの計算 => output_h, output_w
        origin_w = 0
        origin_h = 0
        line_max_h = 0
        line_max_w = 0
        for srcTex in self.src_texture:
            img = Cv2Japanese.imread(
                os.path.join(srcTex.ref_image.photo_dir, srcTex.ref_image.filename)
            )
            for tex_ver in srcTex.tex_coord:
                _, _, polygon_w, polygon_h, _ = get_tex_poly_bbox(
                    tex_ver, img.shape[1], img.shape[0]
                )

                if self.texture_output_width_max < origin_w + polygon_w:
                    # 出力幅を超えたら次の行へ移動
                    origin_w = polygon_w
                    origin_h += line_max_h
                    line_max_h = polygon_h
                else:
                    origin_w += polygon_w
                    # 同じ行で最大の高さ
                    line_max_h = line_max_h if line_max_h > polygon_h else polygon_h

                # 最大行長さ
                line_max_w = line_max_w if line_max_w > origin_w else origin_w

        output_h = origin_h + line_max_h
        output_w = line_max_w

        # 出力画像サイズを2^nに補正
        val = 1
        while val < output_h:
            val *= 2
        output_h = val

        val = 1
        while val < output_w:
            val *= 2
        output_w = val

        # 白紙の出力画像を作成
        output = np.full((output_h, output_w, 3), 255, dtype="uint8")

        # テクスチャ貼り付け
        origin_h = 0
        origin_w = 0
        line_max_h = 0
        for srcTex in self.src_texture:
            # オリジナル画像のオープン
            img = Cv2Japanese.imread(
                os.path.join(srcTex.ref_image.photo_dir, srcTex.ref_image.filename)
            )
            for tex_ver in srcTex.tex_coord:
                min_x, min_y, polygon_w, polygon_h, output_margin = get_tex_poly_bbox(
                    tex_ver, img.shape[1], img.shape[0]
                )

                print(
                    f"[{obj_name}] Crop from {srcTex.ref_image.filename}: x={min_x}, y={min_y}, w={polygon_w}, h={polygon_h}"
                )

                # 背景画像（白画像）
                back = np.full((polygon_h, polygon_w, 3), 255, dtype="uint8")

                # マスク画像
                mask = np.full((polygon_h, polygon_w), 0, dtype="uint8")

                # 前景画像（テクスチャ）
                dst = img[min_y : min_y + polygon_h, min_x : min_x + polygon_w]

                # テクスチャポリコン座標の原点を(min_x, min_y)にする
                poly_ver = tex_ver - [min_x, min_y]

                # 前景（テクスチャポリコン+マージン）のマスクを生成
                cv2.fillPoly(mask, [poly_ver.astype(np.int64)], color=(255, 255, 255))
                cv2.polylines(
                    mask,
                    [poly_ver.astype(np.int64)],
                    isClosed=True,
                    color=(255, 255, 255),
                    thickness=output_margin * 2,
                )

                # 前景画像+背景画像
                polygon = np.where(mask[:, :, np.newaxis] == 0, back, dst)

                # 出力幅を超えたら次の行へ移動
                if output_w < origin_w + polygon_w:
                    origin_w = 0
                    origin_h += line_max_h
                    line_max_h = 0

                # テクスチャ貼付け
                output[
                    origin_h : origin_h + polygon_h, origin_w : origin_w + polygon_w
                ] = polygon

                # テクスチャポリコンの座標を貼り付け先の座標に変換
                xy_set = tex_ver - [min_x, min_y] + [origin_w, origin_h]

                # XY座標→UV左上原点→UV左下原点に変換
                uv_set = np.array([output_w, output_h])
                srcTex.output_coord.append(abs(xy_set / uv_set - [0, 1]))

                # 更新
                origin_w += polygon_w
                line_max_h = line_max_h if line_max_h > polygon_h else polygon_h

        # テクスチャ貼付け画像出力
        if self.texture_output_height_max < output_h:
            # 高さが指定サイズを超えた場合、最大の高さに合わせて縮小する
            h, w = output.shape[:2]
            output_w = round(w * (self.texture_output_height_max / h))
            output_rs = cv2.resize(
                output, dsize=(output_w, self.texture_output_height_max)
            )
            ret = Cv2Japanese.imwrite(output_path + "." + image_format, output_rs)
        else:
            ret = Cv2Japanese.imwrite(output_path + "." + image_format, output)

        return ret
