import os
import shutil

import cv2
import numpy as np

from .city_gml_info import CityGmlInfo
from .util.cvsupportjp import Cv2Japanese
from .util.parammanager import ParamManager


class LayoutTexture:

    def __init__(self, param_manager: ParamManager, citygml_infos: list[CityGmlInfo]):
        """コンストラクタ

        Args:
          param_manager (ParamManager): パラメータファイル管理クラス
          citygml_infos (list[CityGmlInfo]): CityGml情報リスト
        """
        self._pm = param_manager
        self._citygml_infos = citygml_infos
        self._aw = 0
        self._ah = 0
        self._max_rect_w = 0
        self._max_rect_h = 0
        self._last_rect_w = 0
        self._last_rect_h = 0
        self._rect_num_unfini_ary = []
        self._rect_num_build_unfini_ary = []
        self._rect_num_comple_ary = []
        self._input_rect_ary = []
        self._free_space_ary = []
        self._build_count = 0
        self._new_ranges = []  # 出力画像に入る建物数のリスト(アトラス化後)
        self._temp_size_ary = []  # 出力画像サイズのリスト(アトラス化後)

    def layout_texture_main(self):
        """アトラス化メイン"""

        # CityGMLファイル毎に処理
        for citygml_info in self._citygml_infos:
            temp_rect_ary = []
            ranges = []
            init_width = 0
            init_height = 0
            range = 0
            range_count = 0
            bld_count = 1
            self._new_ranges.clear()
            self._temp_size_ary.clear()
            self._rect_num_unfini_ary.clear()
            self._input_rect_ary.clear()

            ranges = self._set_range(citygml_info)

            for building in citygml_info.buildings:
                # 指定棟数ごとに処理
                if (
                    (self._pm.output_width == building.input_image_width)
                    and (self._pm.output_height == building.input_image_height)
                ) or (
                    (self._pm.output_width < building.input_image_width)
                    or (self._pm.output_height < building.input_image_height)
                ):
                    output_image_path = os.path.join(
                        self._pm.output_appearance_folder_path,
                        os.path.basename(building.input_image_path),
                    )
                    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)

                    # 入力画像サイズが出力画像サイズより大きい場合、アトラス化対象外とする
                    input_image_full_path = os.path.join(
                        os.path.dirname(citygml_info.input_city_gml_path),
                        building.input_image_path,
                    )
                    shutil.copyfile(
                        input_image_full_path,
                        output_image_path,
                    )
                    building.output_image_path = os.path.join(
                        "appearance", os.path.basename(building.input_image_path)
                    )
                    building.output_image_width = building.input_image_width
                    building.output_image_height = building.input_image_height
                    for poly in building.polygon_infos:
                        poly.out_texcoord = poly.in_texcoord.copy()
                    continue

                for poly in building.polygon_infos:
                    inputRect = self.RectInfo()
                    inputRect.w = poly.useW
                    inputRect.h = poly.useH
                    inputRect.imgPath = building.input_image_path
                    inputRect.rectID = poly.coord_ring
                    self._input_rect_ary.append(inputRect)

                    # 初期サイズ更新
                    if init_width < poly.useW:
                        init_width = poly.useW
                    if init_height < poly.useH:
                        init_height = poly.useH

                if range < len(ranges):
                    if ranges[range] == bld_count - range_count:
                        # アトラス化
                        self.pack_blf(self._pm.output_width, self._pm.output_height)
                        # outImgW = self._get_area_w()
                        # outImgH = self._get_area_h()
                        temp_rect_ary.extend(self._input_rect_ary)

                        # 初期化
                        self._input_rect_ary.clear()
                        range_count += ranges[range]
                        range += 1
                        init_width = 0
                        init_height = 0
                bld_count += 1

            # データのコピーと画像出力
            range = 0
            range_count = 0
            iter1 = iter(temp_rect_ary)
            iter2 = iter(self._temp_size_ary)
            out_w = 0
            out_h = 0
            out_path = None
            bld_count = 1

            for building in citygml_info.buildings:
                if (
                    (self._pm.output_width == building.input_image_width)
                    and (self._pm.output_height == building.input_image_height)
                ) or (
                    (self._pm.output_width < building.input_image_width)
                    or (self._pm.output_height < building.input_image_height)
                ):
                    continue

                # 白紙の出力画像を作成
                if range < len(self._new_ranges):
                    if 1 == bld_count - range_count:
                        temp = next(iter2)
                        out_w = int(temp[0])
                        out_h = int(temp[1])
                        val_h = 1
                        val_w = 1
                        while val_h < out_h:
                            val_h *= 2
                        out_h = val_h
                        while val_w < out_w:
                            val_w *= 2
                        out_w = val_w
                        output = np.full(
                            (out_h, out_w, 3), self._pm.background_color, dtype="uint8"
                        )

                        out_path = os.path.join(
                            "appearance", "atlas_" + str(range) + ".png"
                        )

                # オリジナル画像のオープン
                img_full_path = os.path.join(
                    os.path.dirname(citygml_info.input_city_gml_path),
                    building.input_image_path,
                )
                img = Cv2Japanese.imread(img_full_path)

                building.output_image_path = out_path
                building.output_image_width = out_w
                building.output_image_height = out_h

                # 指定棟数ごとに処理
                for poly in building.polygon_infos:
                    temp = next(iter1)
                    if poly.coord_ring == temp.rectID:
                        poly.useX = temp.x
                        poly.useY = temp.y

                        arrays_r = poly.in_texcoord

                        min_ver = [poly.minX, poly.minY]
                        # max_ver = [poly.maxX, poly.maxY]
                        polygon_w = int(poly.maxX) - int(poly.minX)
                        polygon_h = int(poly.maxY) - int(poly.minY)

                        back = np.full(
                            (polygon_h, polygon_w, 3),
                            self._pm.background_color,
                            dtype="uint8",
                        )
                        mask = np.full((polygon_h, polygon_w), 0, dtype="uint8")

                        dst = img[
                            int(min_ver[1]) : int(min_ver[1]) + polygon_h,
                            int(min_ver[0]) : int(min_ver[0]) + polygon_w,
                        ]
                        poly_ver = arrays_r - [min_ver[0], min_ver[1]]

                        cv2.fillPoly(
                            mask,
                            [poly_ver.astype(np.int64)],
                            color=(255, 255, 255),
                        )
                        cv2.polylines(
                            mask,
                            [poly_ver.astype(np.int64)],
                            isClosed=True,
                            color=(255, 255, 255),
                        )

                        polygon = np.where(mask[:, :, np.newaxis] == 0, back, dst)

                        # テクスチャ貼付け
                        output[
                            int(poly.useY) : int(poly.useY) + polygon.shape[0],
                            int(poly.useX) : int(poly.useX) + polygon.shape[1],
                        ] = polygon

                        # 四角形で貼り付ける場合
                        # img_temp = img[int(poly.min_y):
                        #               int(poly.min_y) + int(poly.useH),
                        #               int(poly.min_x):
                        #               int(poly.min_x) + int(poly.useW)]
                        # output[int(poly.useY):
                        #       int(poly.useY) + int(poly.useH),
                        #       int(poly.useX):
                        #       int(poly.useX) + int(poly.useW)] = img_temp

                        # 貼り付け先の座標に変換
                        uv_set = np.array(
                            [building.output_image_width, building.output_image_height]
                        )
                        # xy_set = (arrays_r
                        #        - np.minimum.reduce(arrays_r
                        #            - [poly.useX, poly.useY]))
                        xy_set = arrays_r - (
                            np.minimum.reduce(arrays_r - [poly.useX, poly.useY])
                            - [poly.marginX, poly.marginY]
                        )
                        # XY座標→UV左上原点→UV左下原点に変換
                        poly.out_texcoord = abs((xy_set + 0.5) / uv_set - [0, 1])

                if range < len(self._new_ranges):
                    if self._new_ranges[range] == bld_count - range_count:
                        # 画像出力
                        # cv2.imwrite(self._pm.output_gml_folder_path + "\\"
                        #                 z  + building.output_image_path, output)
                        image_path = os.path.join(
                            self._pm.output_root_folder_path, building.output_image_path
                        )
                        image_dir_path = os.path.dirname(image_path)
                        os.makedirs(image_dir_path, exist_ok=True)
                        Cv2Japanese.imwrite(image_path, output)
                        # 初期化
                        range_count += self._new_ranges[range]
                        range += 1
                bld_count += 1
            temp_rect_ary.clear()

    def _set_range(self, citygml_info: CityGmlInfo):
        """処理する棟数の区分け

        Args:
            citygml_info (CityGmlInfo): CityGml情報リスト

        Return;
            ranges(List):メッシュ区分毎の建物数のリスト
        """
        ranges = []
        bld_count = 0
        Mesh = 0

        for i, building in enumerate(citygml_info.buildings, 1):
            if (
                (self._pm.output_width == building.input_image_width)
                and (self._pm.output_height == building.input_image_height)
            ) or (
                (self._pm.output_width < building.input_image_width)
                or (self._pm.output_height < building.input_image_height)
            ):
                continue

            if bld_count == 0:
                Mesh = building.mesh_code

            if Mesh != building.mesh_code:
                ranges.append(bld_count)
                bld_count = 0
                Mesh = building.mesh_code
            bld_count += 1

        if bld_count != 0:
            ranges.append(bld_count)

        return ranges

    def pack_blf(self, area_w: int, area_h: int):
        """BLF法(Bottom-Left Algorithm)で矩形を配置

        Args:
            area_w (int): 矩形配置枠の横幅初期値
            area_h (int): 矩形配置枠の高さ幅初期値
        """
        # 初期サイズ(1つ目の矩形が入るサイズ)
        self._aw = area_w
        self._ah = area_h

        b_ret = False

        while True:
            # 前処理
            self._pack_blf1()

            # 本処理(未配置がなくなるまで続ける)
            un_fini_cnt = len(self._rect_num_unfini_ary)
            while un_fini_cnt:
                b_ret = self._pack_blf2()
                if b_ret is False:
                    # 次の画像に移る
                    print("NextImage")
                    break
                un_fini_cnt = len(self._rect_num_unfini_ary)

            if self._build_count != 0:
                self._new_ranges.append(self._build_count)
                self._temp_size_ary.append([self._max_rect_w, self._max_rect_h])
                self._max_rect_w = 0
                self._max_rect_h = 0
                self._last_rect_w = 0
                self._last_rect_w = 0
                self._aw = area_w
                self._ah = area_h

            if b_ret:
                print("AtlasComplete")
                break

    def _pack_blf1(self):
        """BLF法前処理"""
        # 空き領域を初期化
        self._clear_flag_rect()

        # 並べる
        # self._align_rect()

        self._free_space_ary[0].w = 0
        self._free_space_ary[0].h = 0

    def _pack_blf2(self):
        """BLF法本処理"""
        # 矩形を配置
        # NMAX = self._aw * 2
        NMAX = self._aw
        NMAY = self._ah

        # 矩形を配置可能な座標
        minX = NMAX
        minY = NMAY

        # 配置対象
        trgIdx = self._rect_num_unfini_ary[0]
        trgRect = self._input_rect_ary[trgIdx]

        # BL安定点候補の個数分ループ
        foundIdx = -1
        freeSpCnt = len(self._free_space_ary)
        for ic in range(freeSpCnt):
            space = self._free_space_ary[ic]
            if trgRect.w >= space.w and trgRect.h >= space.h:
                x1 = space.x
                y1 = space.y
                x2 = space.x + trgRect.w
                y2 = space.y + trgRect.h
                if y1 < minY or (y1 == minY and x1 < minX):
                    # 配置済み矩形との衝突をチェック
                    if self._is_recthit(x1, y1, x2, y2) is False:
                        # 衝突している矩形は無い
                        # 配置予定座標を記憶
                        minX = x1
                        minY = y1
                        foundIdx = ic

        if minX >= NMAX or minY >= NMAY:
            # 入る場所が無いので別画像にする
            if self._build_count == 0:
                # 建物一棟分で範囲超過した場合エリアを拡大
                self._expand_area_size()
            else:
                # ひとつ前の最大縦横幅に戻す
                self._max_rect_w = self._last_rect_w
                self._max_rect_h = self._last_rect_h

            # 建物の途中で別画像になった場合、処理中のポリゴンをやり直す
            self._rect_num_unfini_ary = self._rect_num_build_unfini_ary.copy()
            return False
        else:
            # 入る場所があったので配置
            trgRect.x = minX
            trgRect.y = minY

            if self._max_rect_w < (trgRect.x + trgRect.w):
                self._max_rect_w = trgRect.x + trgRect.w
            if self._max_rect_h < (trgRect.y + trgRect.h):
                self._max_rect_h = trgRect.y + trgRect.h

            trgRect.flag = True
            self._rect_num_comple_ary.append(trgIdx)
            self._rect_num_unfini_ary[0:1] = []

            if (len(self._input_rect_ary) == trgIdx + 1) or (
                self._input_rect_ary[trgIdx + 1].imgPath != trgRect.imgPath
            ):
                # 建物一棟分の最後
                self._rect_num_build_unfini_ary = self._rect_num_unfini_ary.copy()
                self._build_count += 1
                self._last_rect_w = self._max_rect_w
                self._last_rect_h = self._max_rect_h

            # 配置に使ったBL安定点はもう使えないため除去する
            if foundIdx >= 0:
                self._free_space_ary[foundIdx : foundIdx + 1] = []

            blPonitAry = []

            # エリア枠と矩形で作れるBL安定点候補を追加登録
            cx1 = trgRect.x
            cx2 = trgRect.x + trgRect.w
            cy1 = trgRect.y
            cy2 = trgRect.y + trgRect.h

            newRect1 = self.RectInfo()
            newRect1.x = cx2
            newRect1.y = 0
            newRect1.w = 0
            newRect1.h = cy1
            blPonitAry.append(newRect1)

            newRect2 = self.RectInfo()
            newRect2.x = 0
            newRect2.y = cy2
            newRect2.w = cx1
            newRect2.h = 0
            blPonitAry.append(newRect2)

            # 現矩形と配置済み矩形との間で作れるBL安定点候補を追加登録
            compCnt = len(self._rect_num_comple_ary)
            for rt in range(compCnt):
                compIdx = self._rect_num_comple_ary[rt]
                compRect = self._input_rect_ary[compIdx]

                px1 = compRect.x
                px2 = compRect.x + compRect.w
                py1 = compRect.y
                py2 = compRect.y + compRect.h

                # 現矩形が配置済み矩形の左側にある場合
                if cx2 <= px1 and cy2 > py2:
                    newRect = self.RectInfo()
                    newRect.x = cx2
                    newRect.y = py2
                    newRect.w = px1 - cx2
                    newRect.h = cy1 - py2 if cy1 > py2 else 0
                    blPonitAry.append(newRect)

                # 現矩形が配置済み矩形の右側にある場合
                if px2 <= cx1 and py2 > cy2:
                    newRect = self.RectInfo()
                    newRect.x = px2
                    newRect.y = cy2
                    newRect.w = cx1 - px2
                    newRect.h = py1 - cy2 if py1 > cy2 else 0
                    blPonitAry.append(newRect)

                # 現矩形が配置済み矩形の上側にある場合
                if cy2 <= py1 and cx2 > px2:
                    newRect = self.RectInfo()
                    newRect.x = px2
                    newRect.y = cy2
                    newRect.w = cx1 - px2 if cx1 > px2 else 0
                    newRect.h = py1 - cy2
                    blPonitAry.append(newRect)

                # 現矩形が配置済み矩形の下側にある場合
                if py2 <= cy1 and px2 > cx2:
                    newRect = self.RectInfo()
                    newRect.x = cx2
                    newRect.y = py2
                    newRect.w = px1 - cx2 if px1 > cx2 else 0
                    newRect.h = cy1 - py2
                    blPonitAry.append(newRect)

            # 得られたBL安定点候補を登録する
            for ic in range(len(blPonitAry)):
                bl = blPonitAry[ic]

                if bl.x < 0 or bl.x >= self._aw or bl.y < 0 or bl.y >= self._ah:
                    continue

                isHit = False
                for compRt in range(compCnt):
                    compIdx = self._rect_num_comple_ary[compRt]
                    compRect = self._input_rect_ary[compIdx]

                    if (
                        compRect.x <= bl.x
                        and bl.x < compRect.x + compRect.w
                        and compRect.y <= bl.y
                        and bl.y < compRect.y + compRect.h
                    ):
                        # 配置済み矩形の中にBL安定点候補が入っている
                        isHit = True
                        break

                if isHit:
                    continue

                # 空き領域を追加登録
                space = self.RectInfo()
                space.x = bl.x
                space.y = bl.y
                space.w = bl.w
                space.h = bl.h
                self._free_space_ary.insert(0, space)

        return True

    def _clear_flag_rect(self):
        """全矩形の配置済みフラグを初期化"""
        if len(self._rect_num_unfini_ary) != 0:
            self._rect_num_comple_ary.clear()
            # self._rect_num_build_unfini_ary = self._rect_num_unfini_ary.copy()

        else:
            self._rect_num_unfini_ary.clear()
            self._rect_num_build_unfini_ary.clear()
            self._rect_num_comple_ary.clear()

            rectCnt = len(self._input_rect_ary)
            for ic in range(rectCnt):
                self._rect_num_unfini_ary.append(ic)
                self._rect_num_build_unfini_ary.append(ic)

        # 空き領域を初期化
        space = self.RectInfo()
        space.x = 0
        space.y = 0
        space.w = self._aw
        space.h = self._ah
        self._free_space_ary.clear()
        self._free_space_ary.append(space)
        self._build_count = 0
        self._max_rect_w = 0
        self._max_rect_h = 0

    def _expand_area_size(self):
        """配置先エリアのサイズを拡大"""
        # 縦横サイズを別々に拡大していく場合
        if self._aw > self._ah:
            # 幅が高さより大きいので、高さを拡大
            self._ah *= 2
        else:
            # 幅を拡大
            self._aw *= 2

    def _align_rect(self):
        """矩形を横一列に並べる"""
        # 配置先エリアの少し下に並べる
        lx = 0
        ly = self._ah + 16
        lh = 0
        rectCnt = len(self._rect_num_unfini_ary)
        for ic in range(rectCnt):  # 未配置
            idx = self._rect_num_unfini_ary[ic]
            rect = self._input_rect_ary[idx]
            if lh < rect.h:
                # その段の高さの最大値を更新
                lh = rect.h

            if lx + rect.w >= self._aw:
                # 一定幅を超えてしまったので、段を変える
                lx = 0
                ly += lh
                lh = rect.h

            rect.x = lx
            rect.y = ly
            lx += rect.w

    def _is_recthit(self, ax1: float, ay1: float, ax2: float, ay2: float):
        """配置済みの全矩形と、与えられた矩形領域が重なるかどうかチェック
            重なってたら true を、重なってなければ false を返す

        Args:
            ax1 (float): 対象矩形の左上x座標
            ay1 (float): 対象矩形の左上y座標
            ax2 (float): 対象矩形の右上x座標
            ay2 (float): 対象矩形の右上y座標
        """
        if ax2 > self._aw or ay2 > self._ah:
            # 配置先エリアをオーバーしてる
            return True

        compCnt = len(self._rect_num_comple_ary)
        for ic in range(compCnt):  # 配置済み矩形
            rect = self._input_rect_ary[self._rect_num_comple_ary[ic]]
            if (
                ax1 < (rect.x + rect.w)
                and rect.x < ax2
                and ay1 < (rect.y + rect.h)
                and rect.y < ay2
            ):
                return True
        return False

    def _get_area_w(self):
        """配置領域幅取得"""
        return self._aw

    def _get_area_h(self):
        """配置領域高さ取得"""
        return self._ah

    class RectInfo:
        def __init__(self) -> None:
            """コンストラクタ"""
            self.rectID = None  # ID
            self.imgPath = None  # 元画像のパス
            self.x = 0  # 配置位置　左下X
            self.y = 0  # 配置位置　左下Y
            self.w = 0  # 矩形幅
            self.h = 0  # 矩形高さ
            self.flag = False  # 配置フラグ
