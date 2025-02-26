import argparse
import math
import os
import tempfile
from glob import glob
from typing import Optional

import cv2
import numpy as np


def copy_gml(input_dir: str, rel_obj_path: str, output_dir: str):
    # TODO
    pass


def rotateToXZ(vs):
    if len(vs) < 3:
        raise Exception("Invalid array size")

    normal = np.zeros(3)
    for i in range(len(vs)):
        a, b, c = vs[i], vs[(i + 1) % len(vs)], vs[(i + 2) % len(vs)]
        normal += np.cross(b - a, c - b)
    normal = normal / np.linalg.norm(normal)

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

    rz = np.array([
        [c, -s, 0],
        [s, c, 0],
        [0, 0, 1]
    ])

    normal = rz @ normal

    inner_product_x = np.clip(np.inner(normal, np.array([0.0, 1.0, 0.0])), -1, 1)
    theta_x = np.arccos(inner_product_x)

    if normal[2] > 0.0:
        theta_x *= -1.0

    c_x = np.cos(theta_x)
    s_x = np.sin(theta_x)
    r_x = np.array([
        [1, 0, 0],
        [0, c_x, -s_x],
        [0, s_x, c_x]
    ])

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


def calc_offsets(image_sizes: [tuple[int, int]]) -> tuple[tuple[int, int], list[tuple[int, int]]]:
    # 横に長い順
    indices = sorted(range(len(image_sizes)), key=lambda i: image_sizes[i][0], reverse=True)

    # 縦と横の比率が極端にならないように横に並べる
    n_row = 1
    widths: list[int]
    heights: list[int]
    aspect: Optional[float] = None
    while True:
        ws = [0] * n_row
        hs = [0] * n_row

        for index in indices:
            w, h = image_sizes[index]
            min_index = ws.index(min(ws))
            ws[min_index] += w
            if h > hs[min_index]:
                hs[min_index] = h

        texture_width = 2 ** math.ceil(math.log2(max(ws)))
        texture_height = 2 ** math.ceil(math.log2(sum(hs)))

        a = texture_width / texture_height
        if a <= 2.0:
            # 横の長さが縦の2倍以内
            if aspect is not None and 1 / a > aspect:
                # 逆に縦が長くなりすぎた
                n_row -= 1
                break
            widths = ws
            heights = hs
            break

        n_row += 1
        widths = ws
        heights = hs
        aspect = a

    texture_width: int = 2 ** math.ceil(math.log2(max(widths)))
    texture_height: int = 2 ** math.ceil(math.log2(sum(heights)))

    offsets: list[tuple[int, int]] = [(-1, -1)] * len(indices)
    ws = [0] * n_row
    for index in indices:
        min_index = ws.index(min(ws))
        width_offset = ws[min_index]
        height_offset = sum(heights[i] for i in range(min_index))
        offsets[index] = (width_offset, height_offset)

        w, _ = image_sizes[index]
        ws[min_index] += w

    return (texture_width, texture_height), offsets


def rectify_images(input_dir: str, rel_obj_path: str, output_dir: str, output_format: str, temp_dir: str,
                   z_threshold: float):
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()

    obj_path: str = os.path.join(input_dir, rel_obj_path)

    # 正対化した面画像のパス
    rectified_image_paths: [str] = []
    # 正対化した面画像のサイズ
    rectified_image_sizes: [tuple[int, int]] = []
    # 正対化面画像内でポリゴンに対応する点の位置
    rectified_texture_vertices: [tuple[float, float, float]] = []

    texture_path: Optional[str] = None
    mtl_path: Optional[str] = None

    # 面ごとに正対化画像をつくる
    new_lines = []
    with open(obj_path, "r") as obj_text:
        geo_vs = []
        tex_vs = []

        mtl: {str, str} = {}

        face_index = 0
        for line in obj_text:
            new_line = line
            elems = line.strip().split()
            command = elems.pop(0) if len(elems) > 0 else None
            if command is None:
                pass
            elif command.lower() == "mtllib":
                mtl_path = os.path.abspath(os.path.join(os.path.dirname(obj_path), elems[0]))
                mtl = read_mtl(mtl_path)
            elif command.lower() == "usemtl":
                assert mtl_path is not None
                texture_name = elems[0]
                texture_rel_path = mtl[texture_name]
                texture_path = os.path.abspath(os.path.join(os.path.dirname(mtl_path), texture_rel_path))
            elif command.lower() == "v":
                geo_vs.append([float(elems[0]), float(elems[1]), float(elems[2])])
            elif command.lower() == "vt":
                tex_vs.append([float(elems[0]), float(elems[1])])
                # 正対化すると座標は変わる
                new_line = None
            elif command.lower() == "f":
                assert texture_path is not None

                if len(elems) < 3 or len(elems[0].split("/")) < 2:
                    continue

                face_file_name = f"{os.path.splitext(os.path.basename(obj_path))[0]}_{face_index}.png"
                face_index += 1
                face_file_path = os.path.join(temp_dir, os.path.dirname(rel_obj_path), face_file_name)

                vs = np.empty(0)
                us = np.empty(0)

                for elem in elems:
                    arg = elem.split("/")
                    vi, ui = arg[0], arg[1]
                    vs = np.append(vs, np.array(geo_vs[int(vi) - 1]))
                    us = np.append(us, np.array(tex_vs[int(ui) - 1]))
                vs = vs.reshape(len(elems), 3)
                us = us.reshape(len(elems), 2)
                height_max = np.abs(vs[:, 2].max() - vs[:, 2].min())

                if height_max < z_threshold:
                    # TODO そのまま
                    pass
                else:
                    # texture_height = np.abs(us[:, 1].max() - us[:, 1].min())
                    texture_width = np.abs(us[:, 0].max() - us[:, 0].min())

                    min_x = vs[:, 0].min()
                    min_y = vs[:, 1].min()
                    min_z = vs[:, 2].min()
                    vs -= np.array([min_x, min_y, min_z])
                    new_vs, normal = rotateToXZ(vs)

                    min_x = new_vs[:, 0].min()
                    min_y = new_vs[:, 1].min()
                    min_z = new_vs[:, 2].min()
                    new_vs -= np.array([min_x, min_y, min_z])

                    image = cv2.imread(texture_path)

                    h, w, _ = image.shape
                    min_x = new_vs[:, 0].min()
                    min_y = new_vs[:, 2].min()
                    max_x = new_vs[:, 0].max()
                    max_y = new_vs[:, 2].max()

                    # TODO なんかおかしい。小さい領域が大きくなる
                    pixel_per_meter = math.ceil(texture_width * w / height_max)
                    new_w = math.ceil((max_x - min_x) * pixel_per_meter)
                    new_h = math.ceil((max_y - min_y) * pixel_per_meter)
                    print("DEBUDEBU 1", face_index, texture_width, w, height_max, pixel_per_meter)

                    src_points = np.empty(0)
                    reverse_x = False
                    # reverse_y = False
                    for i in range(len(new_vs)):
                        src_x = us[i][0] * w
                        src_y = (1 - us[i][1]) * h
                        src_points = np.append(src_points, [src_x, src_y])
                    src_points = src_points.reshape(len(vs), 2)

                    for i in range(len(us)):
                        ni = (i + 1) % len(us)
                        if (src_points[i][0] - src_points[ni][0]) * (new_vs[i][0] - new_vs[ni][0]) < 0:
                            reverse_x = True
                        # if (src_points[i][1] - src_points[ni][1]) * (new_vs[i][1] - new_vs[ni][1]) < 0:
                        #   reverse_y = True

                    dst_points = np.empty(0)
                    for i in range(len(new_vs)):
                        if reverse_x:
                            dx = ((max_x - min_x) - new_vs[i][0]) * pixel_per_meter
                        else:
                            dx = new_vs[i][0] * pixel_per_meter
                        if reverse_x:
                            dy = ((max_y - min_y) - new_vs[i][2]) * pixel_per_meter
                        else:
                            dy = new_vs[i][2] * pixel_per_meter
                        dst_points = np.append(dst_points, [dx, dy])
                    dst_points = dst_points.reshape(len(vs), 2)

                    if len(src_points) == 3:
                        af = cv2.getAffineTransform(src_points[:, :2].astype(np.float32),
                                                    dst_points[:, :2].astype(np.float32))
                        dst_image = cv2.warpAffine(image, af, (new_w, new_h))
                    else:
                        homo, _ = cv2.findHomography(src_points, dst_points)
                        dst_image = cv2.warpPerspective(image, homo, (new_w, new_h))
                    mask = np.zeros_like(dst_image)
                    # cv2.fillPoly(mask, [dst_points.reshape((-1, 1, 2)).astype(np.int32)], (255, 255, 255))
                    # dst_image = cv2.bitwise_and(dst_image, mask)
                    h_dst, w_dst, _ = dst_image.shape

                    print("WRITE:", face_file_path, elems)
                    os.makedirs(os.path.dirname(face_file_path), exist_ok=True)
                    cv2.imwrite(face_file_path, dst_image)

                    rectified_image_paths.append(face_file_path)
                    rectified_image_sizes.append((w_dst, h_dst))
                    rectified_texture_vertices.append(tuple(dst_points))

            if new_line is not None:
                new_lines.append(new_line)

    # 面画像の配置を計算
    (texture_width, texture_height), offsets = calc_offsets(rectified_image_sizes)

    combined_image = np.full((texture_height, texture_width, 3), 255, dtype=np.uint8)

    for image_path, (offset_x, offset_y), (w, h) in zip(rectified_image_paths, offsets, rectified_image_sizes):
        rectified_image = cv2.imread(image_path)
        combined_image[offset_y:offset_y + h, offset_x:offset_x + w] = rectified_image

    output_rel_path = os.path.relpath(os.path.splitext(texture_path)[0] + f".{output_format}", start=input_dir)
    output_path = os.path.join(output_dir, output_rel_path)
    print("BAKABAKA 1", texture_path)
    print("BAKABAKA 2", output_rel_path)
    print("WRITE:", output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, combined_image)

    mtl_rel_path = os.path.relpath(mtl_path, start=input_dir)
    return mtl_rel_path, output_rel_path


def process(input_dir: str, output_dir: str, output_format="png", temp_dir: Optional[str] = None):
    obj_paths = glob(f"{input_dir}/**/*.obj", recursive=True)
    mtl_contents = {}
    for obj_path in obj_paths:
        print("PROCESSING:", obj_path)
        rel_obj_path = os.path.relpath(obj_path, start=input_dir)
        mtl_rel_path, texture_rel_path = rectify_images(input_dir, rel_obj_path, output_dir, output_format,
                                                        temp_dir=temp_dir, z_threshold=0.2)
        if mtl_rel_path in mtl_contents:
            mtl_contents[mtl_rel_path].append(texture_rel_path)
        else:
            mtl_contents[mtl_rel_path] = [texture_rel_path]

    # TODO mtlファイル作成

    gml_paths = glob(f"{input_dir}/**/*.gml", recursive=True)
    for gml_path in gml_paths:
        area_id, _ = os.path.splitext(os.path.basename(gml_path))
        obj_path = next((obj_path for obj_path in obj_paths if area_id in obj_path), None)
        if obj_path is None:
            continue
        rel_obj_path = os.path.relpath(obj_path, start=input_dir)
        copy_gml(input_dir, rel_obj_path, output_dir)


def main():
    parser = argparse.ArgumentParser(description="JPEG画像を再保存するスクリプト")
    parser.add_argument("-i", "--input", required=True, help="入力ディレクトリのパス")
    parser.add_argument("-o", "--output", required=True, help="出力ディレクトリのパス")
    parser.add_argument("--temp-dir", help="一時ディレクトリのパス")
    parser.add_argument('--format', type=str, default='png', help='Output image extension')
    args = parser.parse_args()

    process(args.input, args.output, args.format, temp_dir=args.temp_dir)


if __name__ == "__main__":
    main()
