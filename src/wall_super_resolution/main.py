import argparse
import json
import logging
import os
import shutil
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

import cv2
import yaml

from ..util.wrapper_base import copy_obj_and_mtl, get_texture_path_from_obj
from .cyclegan.dataset import DatasetDataLoader
from .cyclegan.model.cyclegan_model import CycleGANModel
from .cyclegan.util import util
from .src.postprocessing import PostProcessing
from .src.preprocessing import PreProcessing


def fix_relative_path(path):
    # pathlibで統一して簡潔にする
    return str(Path(path).expanduser().resolve())


def setup_logging(log_filename="debug.log", log_flag=False):
    # Create a logger
    logger = None

    # If DebugLogOutput is set to 'true', configure the logging
    if log_flag:
        logger = logging.getLogger(__name__)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(formatter)

        # Set the logging level
        logger.setLevel(logging.DEBUG)
        # Add the file handler to the logger
        logger.addHandler(file_handler)

    return logger


def write_log(log_root, action, filename=None):
    """
    Write a log entry to a log file.

    Parameters:
    - log_root: Path to the log file.
    - action: The action to log.
    - filename: Optional filename for additional information.
    """
    log_file = open(log_root, "a")

    if filename is not None:
        log_file.write(
            f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} : Execution of {filename}\n"
        )

    log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} : {action}\n")
    log_file.close()


def check_path(path, cfg, logger):
    """
    Check if a path exists and raise an error if it doesn't.

    Parameters:
    - path: Path to check.
    - cfg: Configuration information.
    - logger: Logger for logging messages.
    """
    try:
        if not os.path.exists(path):
            raise ValueError(f"Error : {path} not found")
    except ValueError as ve:
        handle_error(ve, cfg, logger)


def handle_error(logger, error, log_flag):
    """
    Handle errors, log the message, and exit the program.

    Parameters:
    - error: The error that occurred.
    - param: Parameter Information.
    - logger: Logger for logging messages.
    """
    if log_flag:
        logger.error(f"{error}")
    print(f"Error: {error}")
    raise SystemExit(1)


def format_elapsed_time(process_time):
    """
    Format elapsed time into a human-readable string.

    Parameters:
    - process_time: Elapsed time in seconds.

    Returns:
    - Formatted elapsed time string.
    """
    hours, remainder = divmod(process_time, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds"


def check_error(param):
    """
    Check the validity of configuration information, log errors,
    and exit the program if there are any.

    Parameters:
    - param: Parameter Information.
    """
    try:
        log_root = None
        logger = None
        if not param.get("OutputLogDir"):
            log_root = Path("main_log.txt")
            bug_root = Path("debug.log")
        else:
            log_dir = os.path.join(
                param["OutputLogDir"], f"outputlog_{time.strftime('%Y%m%d_%H%M%S')}"
            )
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            log_root = Path(os.path.join(log_dir, "main_log.txt"))
            bug_root = Path(os.path.join(log_dir, "debug.log"))

        if not param.get("DebugLogOutput"):
            param["DebugLogOutput"] = "false"
        elif param.get("DebugLogOutput") not in ["true", "false"]:
            param["DebugLogOutput"] = "false"

        # Initialize the logger conditionally based on DebugLogOutput
        logger = setup_logging(bug_root, (param["DebugLogOutput"] == "true"))

        if not param.get("InputDir") or not param.get("OutputDir"):
            raise ValueError(
                "'InputDir' and 'OutputDir' must be specified in the JSON file."
            )

        if not param.get("InputDir"):
            param["Device"] = "cuda"
        elif param.get("Device") not in ["cuda", "cpu"]:
            param["Device"] = "cuda"

    except ValueError as ve:
        if logger:
            handle_error(logger, ve, (param["DebugLogOutput"] == "true"))
        else:
            print(f"ValueError: {ve}")

    except Exception as e:
        if logger:
            handle_error(logger, e, (param["DebugLogOutput"] == "true"))
        else:
            print(f"An unexpected error occurred: {e}")

    return log_root, logger


def get_texture_check_list(city_gml_path: Union[str, Path]):
    tree = ET.parse(city_gml_path)
    root = tree.getroot()
    namespaces = {"app": "http://www.opengis.net/citygml/appearance/2.0"}
    texture_check_list: dict[str, bool] = {}

    for image_uri in root.findall(".//app:imageURI", namespaces):
        texture_check_list[image_uri.text] = False

    return texture_check_list


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("param_file", type=Path, nargs="?", default=None)
    parser.add_argument(
        "--cfg_file",
        type=Path,
        default=str(Path(__file__).resolve().parent / "src" / "config.yml"),
    )
    parser.add_argument("--input_dir", type=str, help="Input directory")
    parser.add_argument("--output_dir", type=str, help="Output directory")
    parser.add_argument("--device", type=str, help="Device (cuda/cpu)")
    parser.add_argument("--checkpoint", type=str, help="Path to the model checkpoint")
    parser.add_argument("--output_log_dir", type=str, help="Output log directory")
    parser.add_argument(
        "--debug_log_output", type=str, help="Debug log output (true/false)"
    )
    parser.add_argument("--meter_per_pixel", type=float, help="Meter per pixel")
    parser.add_argument("--output_format", type=str, help="Output format (png/jpg)")
    args = parser.parse_args()

    # Load parameter information from JSON file
    param = {}
    if args.param_file:
        with args.param_file.open("rt") as pf:
            param = json.load(pf)

    # Override or set from command line arguments
    if args.input_dir:
        param["InputDir"] = args.input_dir
    if args.output_dir:
        param["OutputDir"] = args.output_dir
    if args.device:
        param["Device"] = args.device
    if args.output_log_dir:
        param["OutputLogDir"] = args.output_log_dir
    if args.debug_log_output:
        param["DebugLogOutput"] = args.debug_log_output
    if args.meter_per_pixel:
        param["MeterPerPixel"] = str(args.meter_per_pixel)
    if args.output_format:
        param["OutputFormat"] = args.output_format

    if args.checkpoint:
        args.checkpoint = fix_relative_path(args.checkpoint)

    cfg_path = Path(args.cfg_file)
    with cfg_path.open("rt") as cf:
        cfg = yaml.safe_load(cf)

    # Enable Relative Path(.) and User Path(~)
    if param.get("InputDir"):
        param["InputDir"] = fix_relative_path(param["InputDir"])

    if param.get("OutputDir"):
        param["OutputDir"] = fix_relative_path(param["OutputDir"])

    if param.get("OutputLogDir"):
        param["OutputLogDir"] = fix_relative_path(param["OutputLogDir"])

    pixel_per_meter = 1 / float(param.get("MeterPerPixel", "0.16"))
    output_format = param.get("OutputFormat", "png").lower()

    # Check required fields in the configuration
    log_root, logger = check_error(param)

    # Create execution log
    start_time = time.time()
    with open(log_root, "w") as log_file:
        log_file.write(
            f"処理開始時刻 : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}\n"
        )
        log_file.write(f"指定パラメータ内容 : {json.dumps(param)}\n")
        log_file.write(f"各処理の詳細情報 : {json.dumps(cfg)}\n")

    cfg_process = cfg["processing"]
    processA_dir = Path(os.path.join(param["OutputDir"], "processA"))
    preprocessing = PreProcessing(
        logger=logger,
        overlap=cfg_process["overlap"],
        size=cfg_process["size"],
        pixel_per_meter=pixel_per_meter,
        z_threshold=cfg_process["z_threshold"],
        lower_limit=cfg_process["lower_limit"],
        upper_limit=cfg_process["upper_limit"],
    )

    cfg_cyclegan = cfg["cyclegan"]
    if args.checkpoint:
        cfg_cyclegan["checkpoint_path"] = args.checkpoint
    processB_dir = Path(os.path.join(param["OutputDir"], "processB"))
    dataset = DatasetDataLoader(cfg_cyclegan)
    model = CycleGANModel(cfg_cyclegan, param["Device"])
    model.setup(cfg_cyclegan)
    AtoB = cfg_cyclegan["direction"] == "AtoB"

    processC_dir = Path(os.path.join(param["OutputDir"], "processC"))
    postprocessing = PostProcessing(
        logger=logger,
        output_dir=processC_dir,
        overlap=cfg_process["overlap"],
        size=cfg_process["size"],
        z_threshold=cfg_process["z_threshold"],
    )

    obj_paths = sorted([p for p in Path(param["InputDir"]).glob("*.obj")])
    for obj_file in obj_paths:
        pbar_desc = f"{obj_file.name}"
        print(f"Processing {pbar_desc}")

        try:
            # Check object files
            index = obj_file.name.replace(".", "_")
            # Setting Sub Directories Paths (using temp directories for process)
            sub_processA_dir = processA_dir.joinpath(index)
            sub_processB_dir = processB_dir.joinpath(index)
            sub_processC_dir = processC_dir.joinpath(index)
            # Creating Sub Directories Paths
            if logger is not None:
                sub_processA_dir.mkdir(exist_ok=True, parents=True)
                sub_processB_dir.mkdir(exist_ok=True, parents=True)
                sub_processC_dir.mkdir(exist_ok=True, parents=True)

            # Check if the file is present
            check_path(obj_file, param, logger)

            original_texture_path = get_texture_path_from_obj(obj_file)
            if original_texture_path is None:
                continue

            # Copy OBJ and MTL to output directory
            output_obj_dir = Path(param["OutputDir"]).joinpath("obj")
            output_obj_dir.mkdir(exist_ok=True, parents=True)
            copy_obj_and_mtl(obj_file.parent, param["OutputDir"])

            # pre-processing
            write_log(log_root, "変換対象壁面の抽出および正対化開始", obj_file)

            try:
                preprocess_log = preprocessing.main_step(obj_file, sub_processA_dir)
            except Exception:
                traceback.print_exc()
                result = cv2.imread(str(original_texture_path))

                # Saving output results to appearance directory
                output_appearance_dir = Path(param["OutputDir"]).joinpath("appearance")
                output_appearance_dir.mkdir(exist_ok=True, parents=True)
                output_path = output_appearance_dir.joinpath(
                    os.path.basename(os.path.splitext(original_texture_path)[0])
                    + f".{output_format}"
                )
                cv2.imwrite(str(output_path), result)
                continue

            # cyclegan processing
            write_log(log_root, "壁面画像生成開始")
            for num_iw, img_iw in enumerate(preprocess_log["output_images"]):
                for num_ih, img_ih in enumerate(img_iw):
                    for num, img in enumerate(img_ih):
                        img = dataset.read_img(img["img"], img["path"])

                        model.set_input(img)
                        model.test()
                        visuals = model.get_current_visuals()  # get image results
                        result = util.tensor2im(visuals["fake_B" if AtoB else "fake_A"])
                        if logger is not None:
                            img_path = model.get_image_paths()  # get image paths
                            util.save_image(
                                result,
                                os.path.join(
                                    sub_processB_dir,
                                    os.path.basename(str(img_path)),
                                ),
                            )

                        result = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
                        preprocess_log["output_images"][num_iw][num_ih][num][
                            "img"
                        ] = result

            # post-processing
            write_log(log_root, "アトラス化画像再構成開始")

            try:
                result = postprocessing.main_step(preprocess_log, sub_processC_dir)
            except Exception:
                traceback.print_exc()
                if logger is not None:
                    logger.info(f"Failed PostProcessing: {obj_file}")
                else:
                    print(f"Failed PostProcessing: {obj_file}")
                result = cv2.imread(str(original_texture_path))

            # Saving output results to appearance directory
            output_appearance_dir = Path(param["OutputDir"]).joinpath("appearance")
            output_appearance_dir.mkdir(exist_ok=True, parents=True)
            output_path = output_appearance_dir.joinpath(
                os.path.basename(os.path.splitext(original_texture_path)[0])
                + f".{output_format}"
            )
            cv2.imwrite(str(output_path), result)

        except Exception as e:
            traceback.print_exc()
            if logger is not None:
                logger.error(f"Error processing {obj_file}: {e}")
            print(f"Error processing {obj_file}: {e}")

    # 画像形式の変更およびパスの調整
    output_obj_dir = Path(param["OutputDir"]).joinpath("obj")
    if output_obj_dir.exists():
        for mtl_file in output_obj_dir.rglob("*.mtl"):
            with open(mtl_file, "r") as file:
                lines = file.readlines()
            new_lines = []
            changed = False
            for line in lines:
                l = line.strip().lower()
                if l.startswith("map_kd"):
                    parts = line.strip().split(" ", 1)
                    if len(parts) > 1:
                        tex_filename = os.path.basename(parts[1])
                        ext = os.path.splitext(tex_filename)[1][1:]
                        # パスを ../appearance/filename.ext に書き換える
                        new_tex_path = f"../appearance/{os.path.splitext(tex_filename)[0]}.{output_format}"
                        line = f"  map_Kd {new_tex_path}\n"
                        changed = True
                new_lines.append(line)
            if changed:
                with open(mtl_file, "w") as file:
                    file.writelines(new_lines)

    end_time = time.time()
    process_time = end_time - start_time
    with open(log_root, "a") as log_file:
        log_file.write(
            f"\n処理終了時刻 : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}\n"
        )
        log_file.write(f"トータル処理時間 : {format_elapsed_time(process_time)}\n")

    # debug log
    if logger is not None:
        logger.info(f"Total processing time: {format_elapsed_time(process_time)}")
