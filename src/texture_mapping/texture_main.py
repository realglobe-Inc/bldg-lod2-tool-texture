import csv
import os
import re
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from .photo_image import PhotoImage
from .vertical_object import VerticalObject
from ..util.city_gml_info import CityGmlManager
from ..util.config import Config
from ..util.log import Log, ModuleType, LogLevel
from ..util.param_manager import ParamManager
from ..util.result_type import ResultType, ProcessResult


class TextureMain:
    """テクスチャ貼付けメインクラス"""

    def __init__(self, param_manager: ParamManager) -> None:
        """コンストラクタ

        Args:
          param_manager (ParamManager): パラメータ情報
        """
        self.input_obj_dir = Config.OUTPUT_PHASE_OBJ_DIR  # 入力OBJフォルダパス
        self.output_obj_dir = Config.OUTPUT_TEX_OBJ_DIR  # 出力OBJフォルダパス
        self.param_manager = param_manager  # パラメータ情報
        # オプション出力のOBJフォルダパス
        self.optional_output_obj_dir = ""

    def texture_main(
        self,
        buildings: list[CityGmlManager.BuildInfo],
        file_name: str,
        image_format: str,
    ) -> None:
        """テクスチャ張付け開始

        Args:
          buildings (list[CityGmlManager.BuildInfo]): 建物外形情報リスト
          file_name (str): 入力CityGMLファイル名(拡張子付き)
          image_format (str): 出力画像形式

        Raises:
          FileNotFoundError: OBJファイル入力先フォルダなし
          FileNotFoundError: 入力写真フォルダなし
          Exception: 内部標定要素情報パラメータエラー
          Exception: 入力写真なし
        """
        photo_list = list()
        photo_num = 0
        ex_calib = list()
        cam_info = list()
        calib_flag = False
        res_type = ResultType.SUCCESS

        try:
            # 中間フォルダの確認
            # 入力写真フォルダ確認でエラーした際に入力objをそのまま
            # 中間フォルダにコピーするため先に中間フォルダの作成を行う
            if os.path.isdir(self.output_obj_dir):
                shutil.rmtree(self.output_obj_dir)  # 既存フォルダは削除

            os.mkdir(self.output_obj_dir)

            # 最終出力にOBJファイルを出力する場合
            if self.param_manager.output_obj:
                # 出力フォルダの作成
                self.optional_output_obj_dir = os.path.join(
                    self.param_manager.output_folder_path,
                    "obj",
                    os.path.splitext(file_name)[0],
                )
                if not os.path.isdir(self.optional_output_obj_dir):
                    os.makedirs(self.optional_output_obj_dir)

            if not os.path.isdir(self.input_obj_dir):
                # OBJファイル入力先フォルダなし
                raise FileNotFoundError("Folder not found (OBJ folder)")

            if not os.path.isdir(self.param_manager.texture_folder_path):
                # 入力写真フォルダなし
                raise FileNotFoundError("Folder not found (Texture folder)")

            if not os.path.exists(self.param_manager.output_folder_path):
                # テクスチャ画像出力先フォルダなし
                os.makedirs(self.param_manager.output_folder_path)

            # 外部標定要素ファイル読み込み
            with open(self.param_manager.ex_calib_element_path) as f:
                reader = csv.reader(f, delimiter="\t")
                ex_calib = [row for row in reader]

            # カメラ情報ファイル読み込み
            with open(self.param_manager.camera_info_path) as f:
                reader = csv.reader(f, delimiter="\t")
                cam_info = [row for row in reader]

            # カメラ情報チェック
            calib_count = 0
            for idx, info in enumerate(cam_info[1]):
                if idx < 7:
                    if info == "":
                        raise Exception("cam_info data is insufficient")
                else:
                    if info != "":
                        calib_count += 1

            if calib_count == 3:
                # キャリブレーションデータが五つ揃っている時は有効
                calib_flag = True
                Log.output_log_write(
                    LogLevel.DEBUG, ModuleType.PASTE_TEXTURE, "calib ON"
                )

            # 写真情報読み込み
            for data in ex_calib[1:]:
                ret = True
                # 外部標定要素チェック
                if len(data) != 7:  # ファイル名,x,y,z,omega,phi,kappa
                    ret = False
                    Log.output_log_write(
                        LogLevel.WARN,
                        ModuleType.PASTE_TEXTURE,
                        "ex_calib data is insufficient",
                    )

                for idx, info in enumerate(data):  # 値が入っていない場合
                    if info == "":
                        ret = False
                        Log.output_log_write(
                            LogLevel.WARN,
                            ModuleType.PASTE_TEXTURE,
                            "ex_calib data including empty",
                        )
                if ret:
                    photo = PhotoImage()
                    ret = photo.set_photo_param(
                        self.param_manager.texture_folder_path,
                        data,
                        cam_info[1],
                        calib_flag,
                        self.param_manager.rotate_matrix_mode,
                    )
                    if ret:
                        photo_list.append(photo)
                        photo_num += 1
                    else:
                        Log.output_log_write(
                            LogLevel.WARN,
                            ModuleType.PASTE_TEXTURE,
                            f"PhotoFile Not Found {data[0]}",
                        )

            if photo_num < 1:
                raise Exception("Photo not found")

            # テクスチャ画像出力フォルダ作成
            # [メッシュコード]_[地物型]_[CRS]_[オプション]_appearance
            base_name = os.path.splitext(file_name)[0]
            texture_dir = os.path.join(
                self.param_manager.output_folder_path,
                f"{base_name.split('_op')[0]}_appearance",
            )
            if not os.path.isdir(texture_dir):
                os.mkdir(texture_dir)

            # マテリアルファイル名
            # YYYYMMDD_HHMMSS.mtl
            date = datetime.now().strftime("%Y%m%d_%H%M%S")
            mtl_file_name = date + ".mtl"

            file_list = os.listdir(self.input_obj_dir)
            building_list = [i for i in buildings if i.build_id + ".obj" in file_list]
            self._obj_num = len(building_list)

            if self._obj_num == 0:
                # フォルダ内にファイルが存在しない場合
                Log.output_log_write(
                    LogLevel.ERROR,
                    ModuleType.PASTE_TEXTURE,
                    f"{self.input_obj_dir}: obj folder do not have obj file.",
                )
                res_type = ResultType.WARN
            else:
                isatty = sys.stdout.isatty()
                pbar = tqdm(
                    total=len(building_list),
                    unit="bldg",
                    leave=False,
                    dynamic_ncols=isatty,
                    disable=not isatty,
                )
                for build in building_list:
                    # 建造物分テクスチャ貼付け処理
                    try:
                        pbar.set_description(build.build_id)
                        if not isatty:
                            print(f"Processing {build.build_id}")

                        id = build.build_id
                        build.paste_texture = ProcessResult.SKIP
                        path = os.path.join(self.input_obj_dir, f"{id}.obj")

                        Log.output_log_write(
                            LogLevel.DEBUG, ModuleType.PASTE_TEXTURE, f"bldid:{id}"
                        )

                        ver = VerticalObject(
                            path,
                            photo_num,
                            photo_list,
                            self.param_manager.texture_output_width_max,
                            self.param_manager.texture_output_height_max,
                        )
                        ver.select_roof_texture()
                        ver.select_wall_texture()
                        ret = ver.output_texture(
                            self.output_obj_dir,
                            texture_dir,
                            mtl_file_name,
                            image_format,
                        )
                        if self.param_manager.output_obj:
                            # マテリアルファイル名はCityGMLファイル名とする
                            ver.output_optional_obj(
                                obj_dir=self.optional_output_obj_dir,
                                texture_dir=texture_dir,
                                mtl_file_name=f"{base_name}.mtl",
                                image_format=image_format,
                            )

                        if not ret:
                            shutil.copyfile(
                                path,
                                os.path.join(
                                    self.output_obj_dir, os.path.basename(path)
                                ),
                            )
                            Log.output_log_write(
                                LogLevel.WARN,
                                ModuleType.PASTE_TEXTURE,
                                f"Texture not found id:{id}",
                            )
                            res_type = ResultType.WARN
                            build.paste_texture = ProcessResult.ERROR
                        else:
                            build.paste_texture = ProcessResult.SUCCESS

                    except Exception as e:
                        traceback.print_exc()
                        shutil.copyfile(
                            path,
                            os.path.join(self.output_obj_dir, os.path.basename(path)),
                        )
                        Log.output_log_write(
                            LogLevel.WARN, ModuleType.PASTE_TEXTURE, f"{str(e)} {path}"
                        )
                        res_type = ResultType.WARN
                        build.paste_texture = ProcessResult.ERROR

                    finally:
                        pbar.update(1)

                pbar.close()

            return res_type

        except FileNotFoundError as e:
            self._copy_folder()
            Log.output_log_write(LogLevel.MODEL_ERROR, ModuleType.PASTE_TEXTURE, e)
            return ResultType.WARN

        except Exception as e:
            self._copy_folder()
            Log.output_log_write(LogLevel.MODEL_ERROR, ModuleType.PASTE_TEXTURE, e)
            return ResultType.WARN

    def _copy_folder(self):
        """OBJ入力フォルダの中身を出力フォルダにコピー
        モジュール処理を中断した場合
        """
        if os.path.isdir(self.input_obj_dir):
            pathlist = sorted(
                [
                    p
                    for p in Path(self.input_obj_dir).glob("**/*")
                    if re.search(r"/*\.obj", str(p))
                ]
            )
            for path in pathlist:
                shutil.copyfile(
                    path, os.path.join(self.output_obj_dir, os.path.basename(path))
                )
                if self.param_manager.output_obj:
                    # 最終出力にOBJファイルを出力する場合
                    shutil.copyfile(
                        path,
                        os.path.join(
                            self.optional_output_obj_dir, os.path.basename(path)
                        ),
                    )
