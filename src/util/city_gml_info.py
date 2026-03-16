from .result_type import ProcessResult, ResultType


class CityGmlManager:
    """CityGML建物情報クラス"""

    class BuildInfo:
        """CityGML出力建物形状情報クラス(建物毎)"""

        def __init__(self):
            """コンストラクタ"""
            self.build_id = ""  # 建物ID(OBJファイル名は同一)
            self.paste_texture = ProcessResult.SKIP  # テクスチャ貼付け結果
