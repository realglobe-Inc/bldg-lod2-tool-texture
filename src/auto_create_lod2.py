import argparse
import glob
import os
import re
import shutil
import sys
from pathlib import Path

from .create_model.model_creator import ModelCreator
from .phase_consistency.main_manager import MainManager
from .texture_mapping.texture_main import TextureMain
from .util.city_gml_info import CityGmlManager
from .util.config import Config
from .util.log import Log, ModuleType, LogLevel
from .util.param_manager import ParamManager
from .util.result_type import ResultType


def _delete_module_tmp_folder() -> None:
    """中間フォルダの削除(モジュールごと)"""
    if os.path.isdir(Config.OUTPUT_MODEL_OBJ_DIR):
        shutil.rmtree(Config.OUTPUT_MODEL_OBJ_DIR)
    if os.path.isdir(Config.OUTPUT_PHASE_OBJ_DIR):
        shutil.rmtree(Config.OUTPUT_PHASE_OBJ_DIR)
    if os.path.isdir(Config.OUTPUT_PHASE_OBJ_DIR):
        shutil.rmtree(Config.OUTPUT_PHASE_OBJ_DIR)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser()
    parser.add_argument("param", help="パラメータ")

    args = parser.parse_args()

    # 中間フォルダがある場合は削除
    if os.path.isdir(Config.OUTPUT_OBJ_DIR):
        shutil.rmtree(Config.OUTPUT_OBJ_DIR)

    # 中間フォルダの作成
    os.makedirs(Config.OUTPUT_OBJ_DIR)

    try:
        param_manager = ParamManager()
        change_params = param_manager.read(args.param)

    except Exception as e:
        param_manager.debug_log_output = False
        log = Log(param_manager, args.param)
        log.output_log_write(LogLevel.ERROR, ModuleType.NONE, e)
        log.log_footer()
        sys.exit()

    buildings: list[CityGmlManager.BuildInfo] = []
    try:
        ret_city_gml_read = ResultType.ERROR  # CityGML入力結果初期化

        # ログクラスインスタンス化
        log = Log(param_manager, args.param)

        # パラメータがデフォルトに変更された場合
        for change_param in change_params:
            message = f"{change_param.name} Value change to {change_param.value}"
            log.output_log_write(LogLevel.WARN, ModuleType.NONE, message)

        # CityGMLファイル一覧の取得
        city_gml_files = glob.glob(
            os.path.join(param_manager.city_gml_folder_path, "*.gml")
        )

        if len(city_gml_files) == 0:
            # 入力CityGMLファイルがない場合
            log.output_log_write(
                LogLevel.ERROR, ModuleType.NONE, "CityGML file not found"
            )

        buildings_for_summary = []
        for city_gml_file_path in city_gml_files:
            # 入力ファイル名
            file_name = os.path.basename(city_gml_file_path)

            # 処理対象のファイル名のログを出力
            log.process_start_log(file_name)

            # CityGML入力
            log.module_start_log(ModuleType.INPUT_CITY_GML, file_name)

            city_gml = CityGmlManager(param_manager)
            # CityGML読み込み
            ret_city_gml_read, buildings = city_gml.read_file(
                file_name=file_name,
                target_coord_areas=param_manager.target_coord_areas,
                target_building_ids=param_manager.target_building_ids,
                debug_mode=param_manager.debug_mode,
            )

            log.module_result_log(ModuleType.INPUT_CITY_GML, ret_city_gml_read)

            if ret_city_gml_read is not ResultType.ERROR:
                # OBJの処理

                # モデル要素生成
                log.module_start_log(ModuleType.MODEL_ELEMENT_GENERATION, file_name)

                model_creator = ModelCreator(param_manager)
                ret_model_element_generation = model_creator.create(
                    buildings, debug_mode=param_manager.debug_mode
                )

                log.module_result_log(
                    ModuleType.MODEL_ELEMENT_GENERATION, ret_model_element_generation
                )

                # モデル要素生成中間出力フォルダ確認
                files = glob.glob(os.path.join(Config.OUTPUT_MODEL_OBJ_DIR, "*.obj"))
                if not files:
                    log.output_log_write(
                        LogLevel.ERROR,
                        ModuleType.NONE,
                        "ModelElementGeneration Module Not Output Obj File",
                    )
                    buildings_for_summary.extend(buildings)
                    _delete_module_tmp_folder()  # 中間フォルダの削除
                    continue

                # 位相一貫性補正
                log.module_start_log(ModuleType.CHECK_PHASE_CONSISTENCY, file_name)

                main_manager = MainManager(param_manager)
                ret_check_phase_consistency = main_manager.check_and_correction(
                    buildings
                )

                log.module_result_log(
                    ModuleType.CHECK_PHASE_CONSISTENCY, ret_check_phase_consistency
                )

                # 位相一貫性補正中間出力フォルダ確認
                files = glob.glob(os.path.join(Config.OUTPUT_PHASE_OBJ_DIR, "*.obj"))

                if not files:
                    log.output_log_write(
                        LogLevel.ERROR,
                        ModuleType.NONE,
                        "CheckPhaseConsistency Module Not Output Obj File",
                    )
                    buildings_for_summary.extend(buildings)
                    _delete_module_tmp_folder()  # 中間フォルダの削除
                    continue

                # テクスチャ自動張付け
                if param_manager.output_texture:
                    log.module_start_log(ModuleType.PASTE_TEXTURE, file_name)

                    texture_main = TextureMain(param_manager)
                    ret_paste_texture = texture_main.texture_main(
                        buildings, file_name, param_manager.texture_image_format
                    )

                    log.module_result_log(ModuleType.PASTE_TEXTURE, ret_paste_texture)

                else:
                    input_obj_dir = Config.OUTPUT_PHASE_OBJ_DIR
                    output_obj_dir = Config.OUTPUT_TEX_OBJ_DIR
                    if os.path.isdir(output_obj_dir):
                        shutil.rmtree(output_obj_dir)  # 既存フォルダは削除
                    os.mkdir(output_obj_dir)

                    pathlist = sorted(
                        [
                            p
                            for p in Path(input_obj_dir).glob("**/*")
                            if re.search(r"/*\.obj", str(p))
                        ]
                    )
                    for path in pathlist:
                        shutil.copyfile(
                            path, os.path.join(output_obj_dir, os.path.basename(path))
                        )

                    # 最終出力にOBJファイルを出力する場合
                    if param_manager.output_obj:
                        # 出力フォルダの作成
                        optional_output_obj_dir = os.path.join(
                            param_manager.output_folder_path,
                            "obj",
                            os.path.splitext(file_name)[0],
                        )
                        if not os.path.isdir(optional_output_obj_dir):
                            os.makedirs(optional_output_obj_dir)

                        pathlist = sorted(
                            [
                                p
                                for p in Path(input_obj_dir).glob("**/*")
                                if re.search(r"/*\.obj", str(p))
                            ]
                        )
                        for path in pathlist:
                            shutil.copyfile(
                                path,
                                os.path.join(
                                    optional_output_obj_dir, os.path.basename(path)
                                ),
                            )

                if param_manager.output_city_gml:
                    # CityGML出力
                    log.module_start_log(ModuleType.OUTPUT_CITY_GML, file_name)
                    # CityGML書き込み
                    ret_city_gml_write = city_gml.write_file(
                        file_name=file_name,
                        image_format=param_manager.texture_image_format,
                    )
                    log.module_result_log(
                        ModuleType.OUTPUT_CITY_GML, ret_city_gml_write
                    )

                # summary用にモデル化結果を保存
                buildings_for_summary.extend(buildings)

            # 中間フォルダの削除(モジュールごと)
            _delete_module_tmp_folder()

        # 中間フォルダの削除(temp)
        if os.path.isdir(Config.OUTPUT_OBJ_DIR):
            shutil.rmtree(Config.OUTPUT_OBJ_DIR)

    except Exception as e:
        log.output_log_write(LogLevel.ERROR, ModuleType.NONE, e)
        buildings_for_summary.extend(buildings)

    finally:
        if ret_city_gml_read is not ResultType.ERROR:
            # モデル化結果サマリー出力
            log.output_summary(buildings_for_summary)

        # 実行ログファイルと標準出力にフッタ出力
        log.log_footer()
