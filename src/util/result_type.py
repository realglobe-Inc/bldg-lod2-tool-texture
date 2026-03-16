from enum import IntEnum


class ResultType(IntEnum):
    """モジュール実行結果"""

    SUCCESS = 0  # 実行成功
    WARN = 1  # 警告あり
    ERROR = 2  # 実行失敗
