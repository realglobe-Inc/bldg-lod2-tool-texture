import argparse
import math
import os
from glob import glob
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from src.util.logging import setup_logger


def rotate_to_xz(vs):
    if len(vs) < 3:
        raise Exception("Invalid array size")

    normal = np.zeros(3)
    for i in range(len(vs)):
        a, b, c = vs[i], vs[(i + 1) % len(vs)], vs[(i + 2) % len(vs)]
        normal += np.cross(b - a, c - b)
    norm = np.linalg.norm(normal)
    if norm < 1e-12:
        return None, None
    normal = normal / norm

    normal_save = normal.copy()

    normal_xy = np.array([normal[0], normal[1], 0])
    if np.linalg.norm(normal_xy) > 0:
        normal_xy = normal_xy / np.linalg.norm(normal_xy)
    if normal[0] == 0 and normal[1] == 0:
        normal_xy[1] = 1

    inner_product = np.clip(np.inner(normal_xy, np.array([0.0, 1.0, 0.0])), -1, 1)

    theta = np.arccos(inner_product)

    if normal[0] < 0:
        theta *= -1

    c = np.cos(theta)
    s = np.sin(theta)

    rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    normal = rz @ normal

    inner_product_x = np.clip(np.inner(normal, np.array([0.0, 1.0, 0.0])), -1, 1)
    theta_x = np.arccos(inner_product_x)

    if normal[2] > 0.0:
        theta_x *= -1.0

    c_x = np.cos(theta_x)
    s_x = np.sin(theta_x)
    r_x = np.array([[1, 0, 0], [0, c_x, -s_x], [0, s_x, c_x]])

    new_vs = np.empty(0)

    for i in range(len(vs)):
        new_vs = np.append(new_vs, r_x @ rz @ vs[i])

    new_vs = new_vs.reshape(len(vs), 3)

    return new_vs, normal_save


def read_mtl(mtl_path: str):
    mtl = {}
    with open(mtl_path, "r") as mtl_file:
        name = None
        for line in mtl_file:
            tokens = line.strip().split()
            if len(tokens) < 2:
                continue
            elif tokens[0].lower() == "newmtl":
                name = tokens[1]
            elif tokens[0].lower() == "map_kd":
                if name is not None:
                    mtl[name] = tokens[1]
                    name = None
    return mtl


def calc_width_and_height(
    image_sizes: list[tuple[int, int]], n_row: int
) -> tuple[tuple[int, int], list[int]]:
    """
    :return: 返り値の最後は行ごとの高さ
    """
    widths: list[int] = [0] * n_row
    heights: list[int] = [0] * n_row
    for index in range(len(image_sizes)):
        w, h = image_sizes[index]
        min_index = widths.index(min(widths))
        widths[min_index] += w
        heights[min_index] = max(heights[min_index], h)
    width = 2 ** math.ceil(math.log2(max(widths)))
    height = 2 ** math.ceil(math.log2(sum(heights)))
    return (width, height), heights


def calc_offsets(
    image_sizes: list[tuple[int, int]],
) -> tuple[tuple[int, int], list[tuple[int, int]]]:
    # # 横に長い順
    # indices = sorted(range(len(image_sizes)), key=lambda i: image_sizes[i][0], reverse=True)
    # そのまま
    indices = list(range(len(image_sizes)))

    # 縦と横の長さが極端にならないように並べる
    best_n_row: Optional[int] = None
    best_w: Optional[int] = None
    best_h: Optional[int] = None
    best_hs: Optional[list[int]] = None
    for n_row in range(1, len(image_sizes) + 1):
        (w, h), hs = calc_width_and_height(image_sizes, n_row)
        if (
            (best_w is None or best_h is None)
            or w * h < best_w * best_h
            or (w * h == best_w * best_h and w + h < best_w + best_h)
        ):
            best_n_row = n_row
            best_w = w
            best_h = h
            best_hs = hs

    assert best_n_row is not None and best_w is not None and best_h is not None
    offsets: list[tuple[int, int]] = [(-1, -1)] * len(indices)
    ws = [0] * best_n_row
    for index in indices:
        min_index = ws.index(min(ws))
        width_offset = ws[min_index]
        height_offset = sum(best_hs[:min_index])
        offsets[index] = (width_offset, height_offset)

        w, _ = image_sizes[index]
        ws[min_index] += w

    return (best_w, best_h), offsets


def rectify_images(
    obj_path: str,
    output_dir: str,
    output_format: str,
    pixel_per_meter: float,
    margin_px: int = 4,
) -> list[list[tuple[float, float]]]:
    bldg_id = os.path.splitext(os.path.basename(obj_path))[0]
    output_obj_path = obj_path

    mtllib_value: Optional[str] = None
    v_values: list[tuple[float, float, float]] = []
    vt_values: list[tuple[float, float]] = []
    usemtl_value: Optional[str] = None
    f_values: list[list[tuple[int, int]]] = []

    # vtの行番号
    vt_line_indices: set[int] = set()
    # fの行番号から何番目のfか
    f_line_map: dict[int, int] = {}

    lines: list[str] = []
    with open(output_obj_path, "r") as obj_text:
        for line in obj_text:
            line_index = len(lines)
            lines.append(line.rstrip())

            elems = line.strip().split()
            command = elems.pop(0) if len(elems) > 0 else None
            if command is None:
                pass
            elif command.lower() == "mtllib":
                mtllib_value = elems[0]
            elif command.lower() == "usemtl":
                usemtl_value = elems[0]
            elif command.lower() == "v":
                value = (float(elems[0]), float(elems[1]), float(elems[2]))
                v_values.append(value)
            elif command.lower() == "vt":
                vt_line_indices.add(line_index)
                value = (float(elems[0]), float(elems[1]))
                vt_values.append(value)
            elif command.lower() == "f":
                if len(elems[0].split("/")) < 2:
                    continue
                f_line_map[line_index] = len(f_values)
                value = [tuple(map(int, elem.split("/")[:2])) for elem in elems]
                f_values.append(value)

    mtl_path: Optional[str] = None
    mtl: dict[str, str] = {}
    texture_path: Optional[str] = None
    if mtllib_value is not None:
        mtl_path = os.path.abspath(
            os.path.join(os.path.dirname(output_obj_path), mtllib_value)
        )
        mtl: dict[str, str] = read_mtl(mtl_path)
    if usemtl_value is not None and usemtl_value in mtl:
        texture_rel_path = mtl[usemtl_value]
        texture_path = os.path.abspath(
            os.path.join(os.path.dirname(mtl_path), texture_rel_path)
        )

    # 正対化した面画像
    rectified_images: list[np.ndarray] = []
    # 正対化した面画像でポリゴンに対応する点の位置
    rectified_texture_points: list[np.ndarray] = []
    if texture_path is not None:
        orig_image = cv2.imread(texture_path)
        orig_h, orig_w, _ = orig_image.shape
        f = 0
        for v_vt_indices in f_values:
            f += 1
            vs = np.array(
                [np.array(v_values[v_index - 1]) for v_index, _ in v_vt_indices]
            )
            vts = np.array(
                [np.array(vt_values[vt_index - 1]) for _, vt_index in v_vt_indices]
            )

            src_points = vts * np.array([orig_w, orig_h])
            # objファイルは左下が始点だが、OpenCVは左上が始点
            src_points[:, 1] = orig_h - src_points[:, 1]
            mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
            cv2.fillPoly(mask, [src_points.astype(np.int32)], 255)
            kernel = np.ones((margin_px + 1, margin_px + 1), np.uint8)
            dilated_mask = cv2.dilate(mask, kernel, iterations=1)
            src_image = orig_image.copy()
            src_image[dilated_mask == 0] = (255, 255, 255)

            min_x = vs[:, 0].min()
            min_y = vs[:, 1].min()
            min_z = vs[:, 2].min()
            vs -= np.array([min_x, min_y, min_z])
            new_vs, normal = rotate_to_xz(vs)
            if new_vs is None:
                # 縮退した面の場合、ダミーの小さい白い画像を用意する
                dummy_image = np.full((1, 1, 3), 255, dtype=np.uint8)
                rectified_images.append(dummy_image)
                rectified_texture_points.append(np.zeros((len(vs), 2)))
                continue

            min_x = new_vs[:, 0].min()
            min_y = new_vs[:, 1].min()
            min_z = new_vs[:, 2].min()
            new_vs -= np.array([min_x, min_y, min_z])

            min_x = new_vs[:, 0].min()
            min_y = new_vs[:, 2].min()
            max_x = new_vs[:, 0].max()
            max_y = new_vs[:, 2].max()

            reverse_x = False

            for i in range(len(vts)):
                ni = (i + 1) % len(vts)
                if (src_points[i][0] - src_points[ni][0]) * (
                    new_vs[i][0] - new_vs[ni][0]
                ) < 0:
                    reverse_x = True

            dst_points = np.empty(0)
            for i in range(len(new_vs)):
                if reverse_x:
                    dx = ((max_x - min_x) - new_vs[i][0]) * pixel_per_meter
                    dy = ((max_y - min_y) - new_vs[i][2]) * pixel_per_meter
                else:
                    dx = new_vs[i][0] * pixel_per_meter
                    dy = new_vs[i][2] * pixel_per_meter
                dst_points = np.append(dst_points, [dx, dy])
            dst_points = dst_points.reshape(len(vs), 2)
            dst_points = dst_points + 2 * np.array([margin_px, margin_px])
            max_x = dst_points[:, 0].max()
            max_y = dst_points[:, 1].max()
            dst_w = int(max_x + margin_px)
            dst_h = int(max_y + margin_px)

            if len(src_points) == 3:
                af = cv2.getAffineTransform(
                    src_points[:, :2].astype(np.float32),
                    dst_points[:, :2].astype(np.float32),
                )
                dst_image = cv2.warpAffine(
                    src_image,
                    af,
                    (dst_w, dst_h),
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255),
                )
            else:
                homo, _ = cv2.findHomography(src_points, dst_points)
                dst_image = cv2.warpPerspective(
                    orig_image,
                    homo,
                    (dst_w, dst_h),
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255),
                )

            image_h, image_w, _ = dst_image.shape
            x_coords = dst_points[:, 0]
            y_coords = dst_points[:, 1]
            min_x = max(int(np.floor(x_coords.min())) - margin_px, 0)
            min_y = max(int(np.floor(y_coords.min())) - margin_px, 0)
            max_x = min(int(np.ceil(x_coords.max())) + margin_px, image_w)
            max_y = min(int(np.ceil(y_coords.max())) + margin_px, image_h)

            cropped_image = dst_image[min_y:max_y, min_x:max_x]
            rectified_images.append(cropped_image)
            dst_points -= np.array([min_x, min_y])
            rectified_texture_points.append(dst_points)

    # 面画像の配置を計算
    image_sizes = [image.shape[:2][::-1] for image in rectified_images]
    (texture_width, texture_height), offsets = calc_offsets(image_sizes)

    combined_image = np.full((texture_height, texture_width, 3), 255, dtype=np.uint8)

    new_vt_values: list[tuple[float, float]] = []
    new_f_values: list[list[tuple[int, int]]] = []
    face_vertices_list: list[list[tuple[float, float]]] = []
    for i in range(len(f_values)):
        image = rectified_images[i]
        offset_x, offset_y = offsets[i]
        rel_texture_points = rectified_texture_points[i]
        f_value = f_values[i]

        h, w, _ = image.shape
        combined_image[offset_y : offset_y + h, offset_x : offset_x + w] = image
        # 新しいvtを計算
        new_vt_index = len(new_vt_values)
        texture_points = rel_texture_points + np.array([offset_x, offset_y])
        # OpenCVは左上が始点だが、objファイルは左下が始点
        texture_points[:, 1] = texture_height - texture_points[:, 1]
        new_vt_value = texture_points / np.array([texture_width, texture_height])
        new_vt_values.extend(new_vt_value)
        new_f_value = [
            (f_value[j][0], 1 + new_vt_index + j) for j in range(len(f_value))
        ]
        new_f_values.append(new_f_value)
        face_vertices_list.append(new_vt_value.tolist())

    output_image_path = os.path.join(
        output_dir, "appearance", f"{bldg_id}.{output_format}"
    )
    # print("output:", output_image_path)
    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    cv2.imwrite(output_image_path, combined_image)

    vt_done = False
    new_lines: list[str] = []
    for i in range(len(lines)):
        if i in vt_line_indices:
            # vtは全部置き換え
            if vt_done:
                continue
            for vt in new_vt_values:
                new_lines.append(f"vt {vt[0]} {vt[1]}")
            vt_done = True
        elif i in f_line_map:
            # fも置き換え
            f_index = f_line_map[i]
            f_value = new_f_values[f_index]

            new_lines.append(f"f {' '.join([f'{v}/{vt}' for (v, vt) in f_value])}")
        else:
            new_lines.append(lines[i])

    # 出力先パスの修正
    output_obj_path = os.path.join(output_dir, "obj", f"{bldg_id}.obj")
    os.makedirs(os.path.dirname(output_obj_path), exist_ok=True)
    with open(output_obj_path, "w") as obj_file:
        obj_file.write(f"mtllib {bldg_id}.mtl\n")
        obj_file.write(f"usemtl {bldg_id}\n")
        for line in new_lines:
            if line.startswith("mtllib ") or line.startswith("usemtl "):
                continue
            obj_file.write(f"{line}\n")

    # MTLファイルの作成
    mtl_dst = os.path.join(output_dir, "obj", f"{bldg_id}.mtl")
    with open(mtl_dst, "w") as f:
        f.write(f"newmtl {bldg_id}\n")
        f.write(f"map_Kd ../appearance/{bldg_id}.{output_format}\n")

    return face_vertices_list


def process(
    input_dir: str, output_dir: str, output_format: str, pixel_per_meter: float
):
    obj_files = glob(os.path.join(input_dir, "*.obj"))
    bldg_ids: list[str] = []

    for obj_path in obj_files:
        obj_name = os.path.basename(obj_path)
        logger.info(f"Processing {obj_name}")

        bldg_id = os.path.splitext(obj_name)[0]
        bldg_ids.append(bldg_id)

        rectify_images(
            obj_path,
            output_dir,
            output_format,
            pixel_per_meter,
        )


def main():
    parser = argparse.ArgumentParser(description="JPEG画像を再保存するスクリプト")
    parser.add_argument("-i", "--input", required=True, help="入力ディレクトリのパス")
    parser.add_argument("-o", "--output", required=True, help="出力ディレクトリのパス")
    parser.add_argument(
        "--format", type=str, default="png", help="出力するテクスチャ画像の拡張子"
    )
    parser.add_argument(
        "--meter-per-pixel",
        type=float,
        default=0.16,
        help="出力するテクスチャ画像の1ピクセルが何メートルに相当するか",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="ログレベル (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--log-path", type=Path, default=None, help="ログファイルの出力先パス"
    )
    args = parser.parse_args()

    setup_logger(args.log_level, args.log_path)

    pixel_per_meter = 1 / args.meter_per_pixel
    process(args.input, args.output, args.format, pixel_per_meter)


if __name__ == "__main__":
    main()
