from .polygon_info import PolygonInfo


class BuildingInfo:
    """建物情報クラス"""

    @property
    def input_image_path(self):
        """
        入力テクスチャイメージのファイルのパス

        Returns:
          str: 入力テクスチャイメージのファイルのパス
        """
        return self._input_image_path

    @property
    def input_image_width(self):
        """
        入力テクスチャイメージの横幅

        Returns:
          str: 入力テクスチャイメージの横幅
        """
        return self._input_image_width

    @property
    def input_image_height(self):
        """
        入力テクスチャイメージの縦幅

        Returns:
          str: 入力テクスチャイメージの縦幅
        """
        return self._input_image_height

    @property
    def mime_type(self):
        """
        拡張子タイプ

        Returns:
          str: 拡張子タイプ
        """
        return self._mime_type

    @property
    def polygon_infos(self):
        """
        ポリゴン情報リスト

        Returns:
          list[PolygonInfo]: ポリゴン情報リスト
        """
        return self._polygon_infos

    def __init__(
        self,
        mime_type: str,
        input_image_path: str,
        input_image_height: int,
        input_image_width: int,
    ):
        """コンストラクタ"""
        self._mime_type = mime_type

        self._input_image_path = input_image_path
        self._input_image_width = input_image_width
        self._input_image_height = input_image_height
        self.output_image_width = 0
        self.output_image_height = 0
        self.mesh_code = 0  # 4次+5次メッシュ

        self.output_image_path = None
        self.out_imgsize = 0  # 出力画像サイズ

        self._polygon_infos: list[PolygonInfo] = []  # ポリゴン情報リスト

    def add_polygon_info(self, uri, ring, coords, imgSize, extentPixel):

        poly = PolygonInfo()
        poly.target_uri = uri
        poly.coord_ring = ring
        poly.in_texcoord = coords

        if (int(coords.max(axis=0)[0]) - int(coords.min(axis=0)[0])) == 0 or (
            int(coords.max(axis=0)[1]) - int(coords.min(axis=0)[1])
        ) == 0:
            # 面積なし(Line)の場合は幅2pixポリゴンとして切り出す
            extentPixel = 2

        poly.marginX = extentPixel
        poly.marginY = extentPixel
        poly.minX = coords.min(axis=0)[0] - extentPixel
        poly.minY = coords.min(axis=0)[1] - extentPixel
        poly.maxX = coords.max(axis=0)[0] + extentPixel
        poly.maxY = coords.max(axis=0)[1] + extentPixel

        if poly.minX < 0:
            poly.minX = 0
            poly.marginX = 0
        if poly.minY < 0:
            poly.minY = 0
            poly.marginY = 0
        if poly.maxX > imgSize[0]:
            poly.maxX = imgSize[0]
        if poly.maxY > imgSize[1]:
            poly.maxY = imgSize[1]

        poly.useW = poly.maxX - poly.minX
        poly.useH = poly.maxY - poly.minY
        poly.flag = False

        self._polygon_infos.append(poly)
