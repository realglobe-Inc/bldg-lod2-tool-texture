import argparse
import math
import os
from typing import Optional

import cv2
import numpy as np
from lxml import etree


def copy_gml(input_dir: str, area_id: str, output_dir: str, output_format: str,
             face_vertices_list_map: dict[str, list[list[tuple[float, float]]]]):
    input_path = os.path.join(input_dir, f"{area_id}_op.gml")

    # GMLファイルを解析
    tree = etree.parse(input_path)
    root = tree.getroot()

    # app:surfaceDataMemberのnamespaceを取得
    namespaces = {'app': 'http://www.opengis.net/citygml/appearance/2.0'}

    # app:Appearance要素を取得
    for appearance in root.findall(".//app:Appearance", namespaces):
        for surface_data_member in appearance.findall("app:surfaceDataMember", namespaces):
            parameterized_texture = surface_data_member.find('app:ParameterizedTexture', namespaces)
            if parameterized_texture is not None:
                image_uri = parameterized_texture.find('app:imageURI', namespaces)
                if image_uri is None or image_uri.text is None:
                    continue
                bldg_id = os.path.splitext(os.path.basename(image_uri.text))[0]
                if bldg_id not in face_vertices_list_map or os.path.dirname(image_uri.text) != f"{area_id}_appearance":
                    continue
                image_uri.text = f"{area_id}_appearance/{bldg_id}.{output_format}"

                face_vertices_list = face_vertices_list_map[bldg_id]

                mime_type = parameterized_texture.find('app:mimeType', namespaces)
                if mime_type is not None:
                    mime_type.text = f'image/{output_format}'

                targets = parameterized_texture.findall('app:target', namespaces)
                for i, target in enumerate(targets):
                    if i >= len(face_vertices_list):
                        break
                    face_vertices = face_vertices_list[i]
                    texture_coordinates = target.find('.//app:textureCoordinates', namespaces)
                    if texture_coordinates is not None:
                        texture_coordinates.text = " ".join(
                            [f"{x} {y}" for (x, y) in face_vertices + face_vertices[0:1]])

    output_path = os.path.join(output_dir, f"{area_id}_op.gml")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print("WRITE:", output_path)
    tree.write(output_path, encoding='utf-8', xml_declaration=True, pretty_print=True)


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


def rectify_images(input_dir: str, area_id: str, bldg_id: str, output_dir: str, output_format: str, z_threshold: float,
                   margin_px: int = 3) -> list[list[tuple[float, float]]]:
    output_obj_path: str = os.path.join(input_dir, "obj", f"{area_id}_op", f"{bldg_id}.obj")

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
    mtl: {str, str} = {}
    texture_path: Optional[str] = None
    if mtllib_value is not None:
        mtl_path = os.path.abspath(os.path.join(os.path.dirname(output_obj_path), mtllib_value))
        mtl: {str, str} = read_mtl(mtl_path)
    if usemtl_value is not None and usemtl_value in mtl:
        texture_rel_path = mtl[usemtl_value]
        texture_path = os.path.abspath(os.path.join(os.path.dirname(mtl_path), texture_rel_path))

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
            vs = np.array([np.array(v_values[v_index - 1]) for v_index, _ in v_vt_indices])
            vts = np.array([np.array(vt_values[vt_index - 1]) for _, vt_index in v_vt_indices])

            height_max = np.abs(vs[:, 2].max() - vs[:, 2].min())
            x_distance = np.abs(vs[:, 0].max() - vs[:, 0].min())
            y_distance = np.abs(vs[:, 1].max() - vs[:, 1].min())
            distance = math.sqrt(x_distance ** 2 + y_distance ** 2)

            src_points = vts * np.array([orig_w, orig_h])
            # objファイルは左下が始点だが、OpenCVは左上が始点
            src_points[:, 1] = orig_h - src_points[:, 1]
            mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
            cv2.fillPoly(mask, [src_points.astype(np.int32)], 255)
            kernel = np.ones((2 * margin_px + 1, 2 * margin_px + 1), np.uint8)  # 直径 11 (5ピクセル + 中心1) のカーネル
            dilated_mask = cv2.dilate(mask, kernel, iterations=1)
            src_image = orig_image.copy()
            src_image[dilated_mask == 0] = (255, 255, 255)

            if height_max < z_threshold:
                dst_points = src_points.copy()
                dst_image = src_image.copy()
            else:
                x_width = np.abs(vts[:, 0].max() - vts[:, 0].min())
                y_width = np.abs(vts[:, 1].max() - vts[:, 1].min())

                min_x = vs[:, 0].min()
                min_y = vs[:, 1].min()
                min_z = vs[:, 2].min()
                vs -= np.array([min_x, min_y, min_z])
                new_vs, normal = rotateToXZ(vs)

                min_x = new_vs[:, 0].min()
                min_y = new_vs[:, 1].min()
                min_z = new_vs[:, 2].min()
                new_vs -= np.array([min_x, min_y, min_z])

                min_x = new_vs[:, 0].min()
                min_y = new_vs[:, 2].min()
                max_x = new_vs[:, 0].max()
                max_y = new_vs[:, 2].max()

                pixel_per_meter = math.ceil(math.sqrt((x_width * orig_w) ** 2 + (y_width * orig_h) ** 2) / distance)

                reverse_x = False

                for i in range(len(vts)):
                    ni = (i + 1) % len(vts)
                    if (src_points[i][0] - src_points[ni][0]) * (new_vs[i][0] - new_vs[ni][0]) < 0:
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
                dst_w = int(max_x + 2 * margin_px)
                dst_h = int(max_y + 2 * margin_px)

                if len(src_points) == 3:
                    af = cv2.getAffineTransform(src_points[:, :2].astype(np.float32),
                                                dst_points[:, :2].astype(np.float32))
                    dst_image = cv2.warpAffine(src_image, af, (dst_w, dst_h), borderMode=cv2.BORDER_CONSTANT,
                                               borderValue=(255, 255, 255))
                else:
                    homo, _ = cv2.findHomography(src_points, dst_points)
                    dst_image = cv2.warpPerspective(orig_image, homo, (dst_w, dst_h), borderMode=cv2.BORDER_CONSTANT,
                                                    borderValue=(255, 255, 255))

            x_coords = dst_points[:, 0]
            y_coords = dst_points[:, 1]
            min_x = max(int(np.floor(x_coords.min())) - 2 * margin_px, 0)
            min_y = max(int(np.floor(y_coords.min())) - 2 * margin_px, 0)
            max_x = min(int(np.ceil(x_coords.max())) + 2 * margin_px, orig_w)
            max_y = min(int(np.ceil(y_coords.max())) + 2 * margin_px, orig_h)

            cropped_image = dst_image[min_y: max_y, min_x:max_x]
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
        (offset_x, offset_y) = offsets[i]
        rel_texture_points = rectified_texture_points[i]
        f_value = f_values[i]

        h, w, _ = image.shape
        combined_image[offset_y:offset_y + h, offset_x:offset_x + w] = image
        # 新しいvtを計算
        new_vt_index = len(new_vt_values)
        texture_points = rel_texture_points + np.array([offset_x, offset_y])
        # OpenCVは左上が始点だが、objファイルは左下が始点
        texture_points[:, 1] = texture_height - texture_points[:, 1]
        new_vt_value = texture_points / np.array([texture_width, texture_height])
        new_vt_values.extend(new_vt_value)
        new_f_value = [(f_value[j][0], 1 + new_vt_index + j) for j in range(len(f_value))]
        new_f_values.append(new_f_value)
        face_vertices_list.append(new_vt_value.tolist())

    output_image_path = os.path.join(output_dir, f"{area_id}_appearance", f"{bldg_id}.{output_format}")
    print("WRITE:", output_image_path)
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

    output_obj_path = os.path.join(output_dir, "obj", f"{area_id}_op", f"{bldg_id}.obj")
    os.makedirs(os.path.dirname(output_obj_path), exist_ok=True)
    print("WRITE:", output_obj_path)
    with open(output_obj_path, "w") as obj_file:
        for line in new_lines:
            obj_file.write(f"{line}\n")

    return face_vertices_list


def process(input_dir: str, output_dir: str, output_format="png", temp_dir: Optional[str] = None):
    # {input_dir}/{area_id}_op.gml
    # {input_dir}/{area_id}_appearance/{bldg_id}.jpg もしくは png
    # {input_dir}/obj/{area_id}_op/{area_id}_op.mtl
    # {input_dir}/obj/{area_id}_op/{bldg_id}.obj
    # ↓
    # {output_dir}/{area_id}_op.gml
    # {output_dir}/{area_id}_appearance/{bldg_id}.{output_format}
    # {output_dir}/obj/{area_id}_op/{area_id}_op.mtl
    # {output_dir}/obj/{area_id}_op/{bldg_id}.obj

    areas_path = os.path.join(input_dir, "obj")
    for _, area_names, _ in os.walk(areas_path):
        for area_name in area_names:
            if not area_name.endswith("_op"):
                continue
            area_id = area_name.removesuffix("_op")
            area_path = os.path.join(areas_path, area_name)
            bldg_ids: list[str] = []
            face_vertices_list_map: dict[str, list[list[tuple[float, float]]]] = {}
            for _, _, obj_names in os.walk(area_path):
                for obj_name in obj_names:
                    if not obj_name.endswith(".obj"):
                        continue
                    bldg_id = obj_name.removesuffix(".obj")
                    bldg_ids.append(bldg_id)
                    face_vertices_list_map[bldg_id] = rectify_images(input_dir, area_id, bldg_id, output_dir,
                                                                     output_format, z_threshold=0.2)

            mtl_output_path = os.path.join(output_dir, "obj", f"{area_id}_op", f"{area_id}_op.mtl")
            mtl_output_dir = os.path.dirname(mtl_output_path)
            os.makedirs(mtl_output_dir, exist_ok=True)
            print("WRITE:", mtl_output_path)
            with open(mtl_output_path, "w") as mtl_file:
                for bldg_id in bldg_ids:
                    texture_path = os.path.join(output_dir, f"{area_id}_appearance", f"{bldg_id}.{output_format}")
                    kd = os.path.relpath(texture_path, start=mtl_output_dir)
                    mtl_file.write(f"newmtl {bldg_id}\n")
                    mtl_file.write(f"map_Kd {kd}\n")

            copy_gml(input_dir, area_id, output_dir, output_format, face_vertices_list_map)


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
