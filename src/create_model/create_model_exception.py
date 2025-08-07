class ModelingException(Exception):
    """モデル生成の例外クラス"""

    def __init__(self, *args: object) -> None:
        """コンストラクタ"""
        super().__init__(*args)
