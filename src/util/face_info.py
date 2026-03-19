from loguru import logger


class IndexInfo:
    """インデックス情報クラス"""

    def __init__(self, pos=-1, tex=-1, norm=-1):
        """コンストラクタ

        Args:
            pos (int): 座標番号
            tex (int): テクスチャ座標番号
            norm (int): 法線番号

        """
        self._pos = pos
        self._tex = tex
        self._norm = norm

    def set(self, str):
        """文字列からインデックス値設定

        Obj ファイル内のインデックス情報文字列(座標値[/テクスチャ座標値[/法線値]])

        Args:
            str (str): Obj ファイル内のインデックス情報文字列

        raise:
            ValueError  文字列から番号へのパース失敗時
            SyntaxError インデックス情報に誤りがある場合

        """

        s_list = str.split("/")
        list_len = len(s_list)
        if list_len == 1:
            self._pos = int(s_list[0])
        elif list_len == 2:
            self._pos = int(s_list[0])
            if s_list[1]:
                self._tex = int(s_list[1])
        elif list_len == 3:
            self._pos = int(s_list[0])
            if s_list[1]:
                self._tex = int(s_list[1])
            if s_list[2]:
                self._norm = int(s_list[2])
        elif list_len == 0:
            raise SyntaxError(f"{str} : index values required.")
        else:
            raise SyntaxError(f"{str} : too many index values.")

    def get_str(self) -> str:
        """Objファイル出力用インデックス値文字列作成

        Returns:
            str: Objファイル出力用インデックス値文字列
        """

        r_str = ""
        if self._pos != -1:
            r_str = str(self._pos)

        if self._tex != -1:
            r_str += "/" + str(self._tex)

        if self._norm != -1:
            r_str += "/" + str(self._norm)

        return r_str

    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, value):
        self._pos = value

    @property
    def tex(self):
        return self._tex

    @tex.setter
    def tex(self, value):
        self._tex = value

    @property
    def norm(self):
        return self._norm


class MaterialInfo:
    """マテリアル情報クラス"""

    def __init__(self, name):
        """コンストラクタ

        Args:
            name (str): マテリアル名
        """
        self._name = name  # マテリアル名
        self._ka = None  # アンビエントカラー
        self._kd = None  # ディフューズカラー
        self._map_ka = ""  # テクスチャ画像ファイル(アンビエントカラー)
        self._map_kd = ""  # テクスチャ画像ファイル(ディフューズカラー)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def map_kd(self) -> str:
        return self._map_kd

    @map_kd.setter
    def map_kd(self, value: str):
        self._map_kd = value

    def get_str(self) -> list:
        """mtl ファイル出力用文字列リストを作成

        Returns:
            str[]: mtl ファイル出力用文字列リスト
        """
        r_list = []
        newmtl_str = "newmtl " + self._name + "\n\n"
        r_list.append(newmtl_str)
        if self._ka is not None:
            ka_str = "Ka " + self._ka.get_str() + "\n"
            r_list.append(ka_str)
        if self._kd is not None:
            kd_str = "Kd " + self._kd.get_str() + "\n"
            r_list.append(kd_str)
        if self._map_ka:
            map_ka_str = "map_Ka " + self._map_ka + "\n"
            r_list.append(map_ka_str)
        if self._map_kd:
            map_kd_str = "map_Kd " + self._map_kd + "\n"
            r_list.append(map_kd_str)
        r_list.append("\n")

        logger.debug(r_list)

        return r_list


class FaceInfo:
    """面情報クラス"""

    def __init__(self):
        """コンストラクタ"""
        self._indices = []  # インデックス情報リスト

    @property
    def indices(self) -> list:
        return self._indices

    def append(self, index_info):
        """インデックス情報追加

        Args:
            index_info (IndexInfo): インデックス情報
        """
        self._indices.append(index_info)

    def append_texture(self, texture_list):
        """テクスチャ情報付加

        Args:
            texture_list (int[]): テクスチャ番号リスト
        """
        if len(self._indices) != len(texture_list):
            return

        for i, index_info in enumerate(self._indices):
            index_info.tex = texture_list[i]

    def set_by_str(self, s_list) -> tuple:
        """値セット (Obj ファイル内の f 行文字列から)

        Args:
            s_list (str[]): Obj ファイル内 f 行文字列

        returns:
            list<int>, list<int>: 座標インデックスリスト, テクスチャ座標インデックスリスト
        """

        pos_list = []
        tex_list = []
        for str in s_list[1:]:
            index = IndexInfo()
            index.set(str)
            self._indices.append(index)
            pos_list.append(index.pos)
            tex_list.append(index.tex)

        return pos_list, tex_list

    def get_str(self, swap_xy=False) -> str:
        """Objファイル出力用インデックス文字列を作成

        Args:
            swap_xy (bool, optional):\
                True:xy座標を入れ替える, False:xy座標を入れ替えない.\
                Defaults to False.

        Returns:
            str: Objファイル出力用インデックス文字列
        """

        target = self._indices
        if swap_xy:
            # 頂点のxy座標を入れ替える場合
            target = reversed(self._indices)

        r_str = ""
        for index in target:
            if r_str:
                r_str += " "
            else:
                r_str = "f "
            r_str += index.get_str()

        logger.debug(f"r_str = {r_str}")
        return r_str


class FaceInfos:
    """部材毎の面情報クラス"""

    def __init__(self):
        """コンストラクタ_"""
        self._faces = []  # 面情報リスト

    @property
    def faces(self):
        return self._faces

    def append(self, face):
        """面情報追加

        Args:
            face (FaceInfo): 追加する面情報
        """
        self._faces.append(face)

    def append_texture(self, index_no, texture_index_list):
        """テクスチャ情報追加

        Args:
            index_no (int): 追加対象の面番号
            texture_index_list (int[]): テクスチャインデックス番号リスト
        """
        if index_no >= len(self._faces):
            return

        self._faces[index_no].append_texture(texture_index_list)

    def append_by_str(self, s_list) -> tuple:
        """面情報追加

        Args:
            s_list (str[]): Obj ファイル内 f 行文字列

        returns:
            list<int>, list<int>: 座標インデックスリスト, テクスチャ座標インデックスリスト
        """

        face = FaceInfo()
        index, tex = face.set_by_str(s_list)
        self._faces.append(face)

        return index, tex

    def get_str(self, swap_xy=False) -> list:
        """Objファイル出力用インデックス文字列リストを作成

        Args:
            swap_xy (bool, optional):\
                True:xy座標を入れ替える, False:xy座標を入れ替えない.\
                Defaults to False.

        Returns:
            list: objファイル出力用インデックス文字列リスト
        """

        r_list = []
        for face in self._faces:
            str = face.get_str(swap_xy) + "\n"
            r_list.append(str)

        return r_list

    def remove_face(self, face):
        """面情報削除

        Args:
            face(FaceInfo): 削除する面情報
        """
        self._faces.remove(face)
