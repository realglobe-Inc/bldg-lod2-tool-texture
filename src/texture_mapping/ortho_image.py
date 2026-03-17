import os
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
            # GeoTIFFタグやワールドファイル（.tfw等）はrasterioが自動的に処理する
            with rasterio.open(path) as ds:
                self._image_size = [ds.width, ds.height]
                self._valid_image_range[0] = self._image_size[0] - 1
                self._valid_image_range[1] = self._image_size[1] - 1

                # アフィン変換行列を取得
                self._transform = ds.transform
                # 座標からピクセルへの変換のために逆行列を計算
                self._inv_transform = ~self._transform
        except Exception as e:
            print(f"Warning: Failed to load ortho image {filename} with rasterio: {e}")
            return False

        return self._inv_transform is not None

    def get_image_pos(self, point, image_pos) -> int:
        """絶対座標に対応する画像座標と、画像内に座標が存在するかを判定する

        Args:
            point (float[]): 絶対座標(x,y,z)
            image_pos (float[]): 画像座標(x,y)

        Returns:
            int: 画像内に座標が存在するか(0:存在しない 1:存在する)
        """
        if self._inv_transform is None:
            return 0

        # rasterioの逆アフィン変換を使用して、地理座標(x, y)からピクセル座標(col, row)を計算
        # point[0] は X座標、point[1] は Y座標
        px, py = self._inv_transform * (point[0], point[1])

        image_pos[0] = px
        image_pos[1] = py

        if (
            image_pos[0] < 0
            or image_pos[1] < 0
            or image_pos[0] > self._valid_image_range[0]
            or image_pos[1] > self._valid_image_range[1]
        ):
            return 0

        return 1
