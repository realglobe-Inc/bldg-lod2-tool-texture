import os

import cv2
import numpy as np
import rasterio


class OrthoImage:
    """オルソ画像（GeoTIFF）情報クラス"""

    def __init__(self) -> None:
        """コンストラクタ"""
        self.filename = None
        self.photo_dir = None
        self._image_size = [0, 0]  # width, height
        self._transform = None
        self._inv_transform = None
        self._valid_image_range = [0, 0]
        self._bbox = None  # (min_x, min_y, max_x, max_y) in world coords

    def set_ortho_param(self, photo_dir: str, filename: str) -> bool:
        """オルソ画像情報をセットする

        Args:
            photo_dir (str): オルソ画像フォルダパス
            filename (str): オルソ画像ファイル名

        Returns:
            bool: 関数実行結果
        """
        self.filename = filename
        self.photo_dir = photo_dir
        path = os.path.join(photo_dir, filename)
        if not os.path.isfile(path):
            return False

        try:
            # rasterioを使用してGeoTIFFを開く
            with rasterio.open(path) as ds:
                self._image_size = [ds.width, ds.height]
                self._valid_image_range[0] = self._image_size[0] - 1
                self._valid_image_range[1] = self._image_size[1] - 1

                # アフィン変換行列を取得
                self._transform = ds.transform
                # 座標からピクセルへの変換のために逆行列を計算
                self._inv_transform = ~self._transform

                # BBoxの計算 (左上, 右上, 右下, 左下)
                l, b, r, t = ds.bounds
                self._bbox = (l, b, r, t)

        except Exception as e:
            print(f"Warning: Failed to load ortho image {filename} with rasterio: {e}")
            return False

        return self._inv_transform is not None

    def get_image_pos(self, point, image_pos) -> int:
        """絶対座標に対応する画像座標と、画像内に座標が存在するかを判定する"""
        if self._inv_transform is None:
            return 0

        px, py = self._inv_transform * (point[0], point[1])
        image_pos[0] = px
        image_pos[1] = py

        if (
            image_pos[0] < 0
            or image_pos[1] < 0
            or image_pos[0] >= self._image_size[0]
            or image_pos[1] >= self._image_size[1]
        ):
            return 0

        return 1

    def get_patch(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """指定された範囲の画像パッチを取得する"""
        path = os.path.join(self.photo_dir, self.filename)
        # GeoTIFFは通常巨大なので、rasterioのWindowed Readを使用する
        with rasterio.open(path) as ds:
            # Window(col_off, row_off, width, height)
            from rasterio.windows import Window

            window = Window(x, y, w, h)
            # dataは (bands, height, width)
            data = ds.read(window=window, boundless=True, fill_value=255)
            # (height, width, bands) に変換。BGR順にする
            # rasterioは通常RGB。OpenCVはBGR。
            if data.shape[0] >= 3:
                res = np.transpose(data[:3], (1, 2, 0))
                res = res[:, :, ::-1]  # RGB -> BGR
            elif data.shape[0] == 1:
                res = cv2.cvtColor(data[0], cv2.COLOR_GRAY2BGR)
            else:
                res = np.full((h, w, 3), 255, dtype=np.uint8)
            return res.astype(np.uint8)


class OrthoImageCollection:
    """複数のオルソ画像を統合して管理するクラス"""

    def __init__(self, photo_dir: str) -> None:
        self.photo_dir = photo_dir
        self.orthos = []
        self._scan_folder()
        self.filename = "ortho_collection"
        self._bbox = None
        self._px_size = None
        self._image_size = [0, 0]
        self._valid_image_range = [0, 0]
        self._setup_global_params()

    def _scan_folder(self):
        if not os.path.isdir(self.photo_dir):
            return
        files = [
            f
            for f in os.listdir(self.photo_dir)
            if f.lower().endswith((".tif", ".tiff", ".jpg", ".jpeg", ".png"))
        ]
        for f in files:
            ortho = OrthoImage()
            if ortho.set_ortho_param(self.photo_dir, f):
                self.orthos.append(ortho)

    def _setup_global_params(self):
        if not self.orthos:
            return
        # 全体のBBoxを計算
        l_list = [o._bbox[0] for o in self.orthos]
        b_list = [o._bbox[1] for o in self.orthos]
        r_list = [o._bbox[2] for o in self.orthos]
        t_list = [o._bbox[3] for o in self.orthos]
        self._bbox = (min(l_list), min(b_list), max(r_list), max(t_list))

        # 解像度は最初のオルソ画像に合わせる
        first = self.orthos[0]
        self._px_size = (abs(first._transform.a), abs(first._transform.e))

        # 全体解像度を算出
        w_px = int(round((self._bbox[2] - self._bbox[0]) / self._px_size[0]))
        h_px = int(round((self._bbox[3] - self._bbox[1]) / self._px_size[1]))
        self._image_size = [w_px, h_px]
        self._valid_image_range = [w_px - 1, h_px - 1]

    def get_image_pos(self, point, image_pos) -> int:
        """絶対座標に対応する全画像空間でのピクセル座標を返す"""
        if self._bbox is None:
            return 0
        # point[0]=X, point[1]=Y
        px = (point[0] - self._bbox[0]) / self._px_size[0]
        # Yは上が0、下がh_px
        py = (self._bbox[3] - point[1]) / self._px_size[1]

        image_pos[0] = px
        image_pos[1] = py

        if (
            image_pos[0] < 0
            or image_pos[1] < 0
            or image_pos[0] >= self._image_size[0]
            or image_pos[1] >= self._image_size[1]
        ):
            # コレクション全体の範囲外
            return 0

        # いずれかの実画像に含まれているか確認
        for ortho in self.orthos:
            l, b, r, t = ortho._bbox
            if l <= point[0] <= r and b <= point[1] <= t:
                return 1
        return 0

    def get_patch(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """仮想的な全体画像空間からパッチを切り出す（実ファイルから合成）"""
        if self._bbox is None:
            return np.full((h, w, 3), 255, dtype=np.uint8)

        # パッチがカバーする世界座標のBBox
        min_x = self._bbox[0] + x * self._px_size[0]
        max_y = self._bbox[3] - y * self._px_size[1]
        max_x = min_x + w * self._px_size[0]
        min_y = max_y - h * self._px_size[1]

        return self.get_patch_world((min_x, min_y, max_x, max_y), self._px_size)

    def get_patch_world(self, world_bbox, pixel_size) -> np.ndarray:
        """世界座標系のBBoxに対応するパッチを、複数のファイルから合成して取得する
        world_bbox: (min_x, min_y, max_x, max_y)
        pixel_size: (px_w, px_h) - 1ピクセルあたりの世界座標単位での大きさ
        """
        min_x, min_y, max_x, max_y = world_bbox
        w_px = int(round((max_x - min_x) / pixel_size[0]))
        h_px = int(round((max_y - min_y) / pixel_size[1]))

        patch = np.full((h_px, w_px, 3), 255, dtype=np.uint8)

        for ortho in self.orthos:
            # orthoのBBoxと要求BBoxの重なり
            o_l, o_b, o_r, o_t = ortho._bbox
            inter_l = max(min_x, o_l)
            inter_b = max(min_y, o_b)
            inter_r = min(max_x, o_r)
            inter_t = min(max_y, o_t)

            if inter_l < inter_r and inter_b < inter_t:
                # 重なりあり
                # ortho内でのピクセル範囲
                # Y座標はGeoTIFFでは上が小、下が大（row）
                px1, py1 = ortho._inv_transform * (inter_l, inter_t)
                px2, py2 = ortho._inv_transform * (inter_r, inter_b)

                # 整数化
                ix1, iy1 = int(round(px1)), int(round(py1))
                ix2, iy2 = int(round(px2)), int(round(py2))
                iw, ih = ix2 - ix1, iy2 - iy1

                if iw <= 0 or ih <= 0:
                    continue

                sub_patch = ortho.get_patch(ix1, iy1, iw, ih)

                # patch内での位置
                # patchの(0,0)は (min_x, max_y) に対応
                dx = int(round((inter_l - min_x) / pixel_size[0]))
                dy = int(round((max_y - inter_t) / pixel_size[1]))

                # sub_patchのサイズをリサイズ（必要なら）
                # 通常、同じコレクションなら解像度は同じはず
                dh, dw = sub_patch.shape[:2]

                # patchの範囲内に収める
                target_w = min(dw, w_px - dx)
                target_h = min(dh, h_px - dy)

                if target_w > 0 and target_h > 0:
                    patch[dy : dy + target_h, dx : dx + target_w] = sub_patch[
                        :target_h, :target_w
                    ]

        return patch
