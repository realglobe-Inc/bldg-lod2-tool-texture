import datetime
import json
import os
from pathlib import Path


def fix_relative_path(path):
    # pathlibで統一して簡潔にする
    return str(Path(path).expanduser().resolve())


class ParamManager:
    """パラメータファイル管理クラス"""

    class ChangeParam:
        """エラー値が入力された場合にデフォルト値に変更したパラメータ通知用クラス

        Returns:
            _type_: _description_
        """

        @property
        def name(self):
            """パラメータ名

            Returns:
                string: パラメータ名
            """
            return self._name

        @property
        def value(self):
            """デフォルト設定値

            Returns:
                Any: デフォルト設定値(パラメータによって値が異なる)
            """
            return self._value

        def __init__(self, name: str, value) -> None:
            """コンストラクタ

            Args:
                name (string): パラメータ名
                value (Any): 設定値
            """
            self._name = name
            self._value = value

    # クラス変数
    # jsonファイルのキー
    KEY_FILE_PATH = "FilePath"
    KEY_INPUT_OBJ_FOLDER_PATH = "InputOBJFolderPath"
    KEY_OUTPUT_ROOT_FOLDER_PATH = "OutputRootFolderPath"
    KEY_OUTPUT_W = "OutputWidth"
    KEY_OUTPUT_H = "OutputHeight"
    KEY_BACKGROUND_COLOR = "BackGroundColor"
    KEY_EXTENTPIXEL = "Extentpixel"

    # jsonファイルキーリスト
    KEYS = [
        KEY_FILE_PATH,
        KEY_INPUT_OBJ_FOLDER_PATH,
        KEY_OUTPUT_ROOT_FOLDER_PATH,
        KEY_OUTPUT_W,
        KEY_OUTPUT_H,
        KEY_BACKGROUND_COLOR,
        KEY_EXTENTPIXEL,
    ]

    def __init__(self) -> None:
        """コンストラクタ"""
        self.input_obj_folder_path = ""  # OBJ入力フォルダパス
        self.output_root_folder_path = ""  # 出力ルートフォルダパス
        self.output_obj_folder_path = ""  # OBJ出力フォルダパス
        self.output_appearance_folder_path = ""  # テクスチャ出力フォルダパス
        self.output_width = 0  # 出力画像幅
        self.output_height = 0  # 出力画像高さ
        self.background_color = 0  # 背景色
        self.extent_pixel = 0  # ポリゴン余白

        # 作業用パラメータ
        self.time = datetime.datetime.now()  # 処理開始時刻

    def read(self, file_path) -> list[ChangeParam]:
        """jsonファイル読み込み関数

        Args:
            file_path (string): jsonファイルパス

        Raises:
            FileNotFoundError: filePathで指定されたファイルが存在しない
            Exception: ファイル/フォルダパスが文字列ではない場合,または空文字の場合

        Returns:
            list[ChangeParam]: 入力エラーによりデフォルト値を採用したパラメータリスト
        """

        # change_params = []  # デフォルト値に変更したパラメータリスト

        if not os.path.isfile(file_path):
            # ファイルが存在しない場合
            raise FileNotFoundError("parameter file does not exist.")

        # ファイルが存在する場合
        try:
            print(file_path)
            # UTF-8で読み込むように修正 (Shift-JISから変更)
            jsonLoad = json.load(open(file_path, encoding="utf-8", mode="r"))
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            try:
                # 失敗した場合はShift-JISでも試す
                jsonLoad = json.load(open(file_path, encoding="Shift-JIS", mode="r"))
            except json.decoder.JSONDecodeError as e:
                r = e.lineno
                c = e.colno
                raise (
                    Exception(f"json file decoding error: {e.msg} line {r} column {c}.")
                )

        # 値の取得

        # キーが存在しない場合のフォールバック（旧キー名への対応）
        input_key = self.KEY_INPUT_OBJ_FOLDER_PATH
        if input_key not in jsonLoad[self.KEY_FILE_PATH]:
            input_key = "InputGMLFolderPath"

        output_key = self.KEY_OUTPUT_ROOT_FOLDER_PATH
        if output_key not in jsonLoad[self.KEY_FILE_PATH]:
            output_key = "OutputGMLFolderPath"

        self.input_obj_folder_path = fix_relative_path(
            Path(jsonLoad[self.KEY_FILE_PATH][input_key]).expanduser()
        )
        self.output_root_folder_path = fix_relative_path(
            Path(jsonLoad[self.KEY_FILE_PATH][output_key]).expanduser()
        )

        # 統合された入出力構造
        self.output_obj_folder_path = os.path.join(self.output_root_folder_path, "obj")
        self.output_appearance_folder_path = os.path.join(
            self.output_root_folder_path, "appearance"
        )

        self.output_width = jsonLoad[self.KEY_OUTPUT_W]
        self.output_height = jsonLoad[self.KEY_OUTPUT_H]
        self.background_color = jsonLoad[self.KEY_BACKGROUND_COLOR]
        self.extent_pixel = jsonLoad[self.KEY_EXTENTPIXEL]

        if (
            type(self.input_obj_folder_path) is not str
            or not self.input_obj_folder_path
        ):
            # 文字列ではない or 空文字の場合
            raise Exception("Input OBJ folder path is invalid.")
        if not os.path.isdir(self.input_obj_folder_path):
            # 入力フォルダが存在しない場合
            raise Exception("Input OBJ folder not found.")

        if (
            type(self.output_root_folder_path) is not str
            or not self.output_root_folder_path
        ):
            # 文字列ではない or 空文字の場合
            raise Exception("Output root folder path is invalid.")

        if type(self.output_width) is not int:
            raise Exception(ParamManager.KEY_OUTPUT_W + " is invalid.")

        if type(self.output_height) is not int:
            raise Exception(ParamManager.KEY_OUTPUT_H + " is invalid.")

        if type(self.background_color) is not int or not (
            0 <= self.background_color <= 255
        ):
            raise Exception(ParamManager.KEY_BACKGROUND_COLOR + " is invalid.")

        if type(self.extent_pixel) is not int:
            raise Exception(ParamManager.KEY_EXTENTPIXEL + " is invalid.")
