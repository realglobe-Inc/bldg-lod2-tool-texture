import datetime
import inspect
import json
import logging
import os
import shutil
from enum import IntEnum
from logging import getLogger, config

from .param_manager import ParamManager
from .result_type import ResultType


class ModuleType(IntEnum):
    """モジュール情報"""

    INPUT_CITY_GML = 0  # CityGML入力
    MODEL_ELEMENT_GENERATION = 1  # モデル要素生成
    CHECK_PHASE_CONSISTENCY = 2  # 位相一貫性
    PASTE_TEXTURE = 3  # テクスチャ貼付け
    OUTPUT_CITY_GML = 4  # CityGML出力
    NONE = 5  # モジュール不明


class LogLevel(IntEnum):
    """ログレベル"""

    ERROR = 50  # エラー
    MODEL_ERROR = 40  # モデルエラー
    WARN = 30  # 警告
    INFO = 20  # お知らせ
    DEBUG = 10  # デバッグ


class Singleton(object):
    def __new__(cls, *args, **kargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance


class Log(Singleton):
    """ログクラス
    シングルトン
    """

    log_conf = []
    _MAIN_LOG_FILE_PATH = "main_log.txt"
    _main_log_file = []  # 実行ログ
    _module_log_file = ["", "", "", "", ""]  # モジュールログ
    _standard_log = []  # 標準出力
    FORMAT_ON = 0  # フォーマット設定あり
    FORMAT_OFF = 1  # フォーマット設定なし
    # モジュール情報
    MODULE_LIST = {
        ModuleType.INPUT_CITY_GML: ["InputCityGML", "input_city_gml_log.txt"],
        ModuleType.MODEL_ELEMENT_GENERATION: [
            "ModelElementGeneration",
            "model_element_generation_log.txt",
        ],
        ModuleType.CHECK_PHASE_CONSISTENCY: [
            "CheckPhaseConsistency",
            "check_phase_consistency_log.txt",
        ],
        ModuleType.PASTE_TEXTURE: ["PasteTexture", "paste_texture_log.txt"],
        ModuleType.OUTPUT_CITY_GML: ["OutputCityGML", "output_city_gml_log.txt"],
    }
    RESULT_MESSAGE = ["SUCCESS", "WARNING", "ERROR"]  # モジュール実行結果メッセージ
    debug_flag = False  # DEBUGログを出力するかのフラグ

    def __init__(self, param: ParamManager, param_file):
        """ログクラスコンストラクタ
            ロガー作成、ヘッダ部分出力
            モジュールごとのログファイルに開始ログ出力

        Args:
            param (ParamManager): パラメータ情報
            param_file: パラメータファイルパス
        """
        # パラメータ情報からの読み込み情報
        log_folder_path = param.output_log_folder_path  # ログ出力先
        Log.debug_flag = param.debug_log_output  # デバッグログ出力フラグ
        Log.delete_flag = param.delete_error_flag  # エラーデータ削除フラグ
        Log._las_swap_xy = param.las_swap_xy  # las座標のxy入れ替えフラグ
        # 外部標定要素から算出する回転行列のモード
        Log._rotate_matrix_mode = param.rotate_matrix_mode

        # 出力フォルダ等に記載する時刻を揃えるためParamManagerで取得した時刻を使用する
        create_time = param.time.strftime("%Y%m%d_%H%M%S")
        time_log_folder = f"output_log_{create_time}"

        # 環境設定ファイルパス取得
        config_file = os.path.join(os.path.dirname(__file__), "log_config.json")
        # 環境設定用の辞書作成
        with open(config_file, "r") as f:
            Log.log_conf = json.load(f)

        # ログレベル設定
        logging.addLevelName(LogLevel.MODEL_ERROR, "MODEL_ERROR")
        logging.addLevelName(LogLevel.ERROR, "ERROR")

        path_err = False
        try:
            if not os.path.isdir(log_folder_path):
                os.makedirs(log_folder_path)

            output_log_folder_path = os.path.join(log_folder_path, time_log_folder)

        except Exception:
            path_err = True
            output_log_folder_path = os.path.join("output_log", time_log_folder)

        Log.output_log_folder_path = output_log_folder_path

        # フォルダが存在する場合は削除
        if os.path.isdir(Log.output_log_folder_path):
            shutil.rmtree(Log.output_log_folder_path)

        os.makedirs(Log.output_log_folder_path)

        # 実行ログファイルパス作成
        main_log_path = os.path.join(
            Log.output_log_folder_path, Log._MAIN_LOG_FILE_PATH
        )

        # 既に出力ファイルがあったら削除
        if os.path.isfile(main_log_path):
            os.remove(main_log_path)

        # 実行ログファイル出力先設定
        handlers = Log.log_conf["handlers"]
        handlers["MainLogFile"]["filename"] = main_log_path
        handlers["MainLogFileNoForm"]["filename"] = main_log_path

        # logger環境設定
        config.dictConfig(Log.log_conf)

        # 実行ログと標準出力のロガー作成
        Log._standard_log.append(getLogger("Console"))
        Log._standard_log.append(getLogger("ConsoleNoForm"))
        Log._main_log_file.append(getLogger("MainLogFile"))
        Log._main_log_file.append(getLogger("MainLogFileNoForm"))

        # ヘッダ出力
        self.__log_header(Log._main_log_file[Log.FORMAT_OFF], param_file)
        self.__log_header(Log._standard_log[Log.FORMAT_OFF], param_file)

        if path_err:
            message = f'OutputLogFolderPath Value change "{log_folder_path}"'
            message += ' to "output_log"'
            self.output_log_write(LogLevel.WARN, ModuleType.NONE, message)

    def __log_header(self, logger, param_file):
        """実行ログファイルヘッダ出力

        Args:
            logger: ログ出力先
            param_file: パラメータファイルパス
        """
        self._start_time = datetime.datetime.now()  # 実行開始時間

        # 実行ログファイルへのヘッダ出力
        logger.info("run_texture_mapping")
        logger.info(f"Version : {ParamManager.SYSTEM_VERSION}")
        logger.info(f"Start Time : {self._start_time}\n")
        logger.info("Module Information List")

        for module_type in Log.MODULE_LIST:
            # モジュール情報出力
            module = Log.MODULE_LIST[module_type]
            logger.info(f"{module[0]} Module")
            logger.info(f"LogFileName : {module[1]}")

        logger.info(f"\nInput Parameter File Path : {param_file}")
        logger.info(f"DebugFlag : {Log.debug_flag}")
        logger.info(f"LasSwapXY : {Log._las_swap_xy}")
        logger.info(f"RotateMatrixMode : {Log._rotate_matrix_mode}\n")

    @staticmethod
    def __create_logger(module: ModuleType):
        """ロガー作成

        Args:
            module (ModuleType): モジュール情報
        """
        # モジュールタイプがNONE以外はログファイル作成
        if module != ModuleType.NONE and Log._module_log_file[module] == "":
            # モジュールログ出力用のロガー作成
            Log._module_log_file[module] = getLogger(f"{Log.MODULE_LIST[module][0]}Log")

            # モジュールログファイルパス作成
            module_log_file_path = os.path.join(
                Log.output_log_folder_path, Log.MODULE_LIST[module][1]
            )

            # 既に出力ファイルが存在していたら削除
            if os.path.isfile(module_log_file_path):
                os.remove(module_log_file_path)

            # ロガーの出力先設定
            fh = logging.FileHandler(module_log_file_path, encoding="utf-8")

            if not Log.debug_flag:
                # 出力ログレベル設定
                fh.setLevel(logging.INFO)

            # ロガーフォーマット設定
            fmt = logging.Formatter(Log.log_conf["formatters"]["Versatility"]["format"])
            fh.setFormatter(fmt)
            Log._module_log_file[module].addHandler(fh)

    @classmethod
    def output_log_write(
        cls, level: LogLevel, module: ModuleType, message=None, standard_flag=False
    ):
        """ログ出力
            モジュールごとのログファイルに出力

        Args:
            module (ModuleType): モジュール情報
            level : ログレベル情報
            message: ログメッセージ
            standard_flag: 標準出力するかのフラグ情報
        """
        if module is not ModuleType.NONE:
            # 出力ログメッセージ作成
            module_name = f"{Log.MODULE_LIST[module][0]} Module"
            message = f"{module_name} : {message}"
            if Log.debug_flag and level >= LogLevel.WARN:
                caller = "\n     [DEBUG] : Caller : relative path = "
                caller += f"{os.path.relpath(inspect.stack()[1].filename)}, "
                caller += f"function = {inspect.stack()[1].function}, "
                caller += f"line = {inspect.stack()[1].lineno}"
                message += caller

            # 標準出力にログ出力
            if standard_flag:
                Log._standard_log[Log.FORMAT_ON].log(level, message)

            Log._module_log_file[module].log(level, message)
        else:
            # 実行ログファイルと標準出力にログ出力
            Log._main_log_file[Log.FORMAT_ON].log(level, message)
            Log._standard_log[Log.FORMAT_ON].log(level, message)

    @classmethod
    def module_start_log(cls, module: ModuleType, city_gml_filename: str = ""):
        """実行ログ、標準出力、モジュールログへのモジュール実行開始のログ出力
            モジュールログ出力用のロガーを作成

        Args:
            module (ModuleType): モジュール情報
            city_gml_filename (str, optional): 処理対象ファイル名. Defaults to ''.
        """
        # モジュール名取得
        module_name = f"{Log.MODULE_LIST[module][0]} Module"

        # 実行ログファイルログ出力
        Log._main_log_file[Log.FORMAT_ON].info(f"{module_name} Run")

        # 標準出力にログ出力
        Log._standard_log[Log.FORMAT_ON].info(f"{module_name} Run")

        # ロガー作成
        cls.__create_logger(module)

        # モジュールログファイルに開始ログ出力
        Log._module_log_file[module].info("--------------------------------------")
        Log._module_log_file[module].info(f"start processing {city_gml_filename}")
        Log._module_log_file[module].info(f"{Log.MODULE_LIST[module][0]} Module Run")

    @classmethod
    def process_start_log(cls, city_gml_filename: str = ""):
        """実行ログ、標準出力に処理対象のCityGMLファイル名のログを出力する

        Args:
            city_gml_filename (str, optional): 処理対象ファイル名. Defaults to ''.
        """
        # 実行ログファイルログ出力
        Log._main_log_file[Log.FORMAT_OFF].info(
            "--------------------------------------"
        )
        Log._main_log_file[Log.FORMAT_ON].info(f"{city_gml_filename} processing")

        # 標準出力にログ出力
        print("--------------------------------------")
        Log._standard_log[Log.FORMAT_ON].info(f"start processing {city_gml_filename}")
