# -*- coding:utf-8 -*-
import os
import shutil
import numpy as np
import math
import sys
from tqdm import tqdm
from pathlib import Path

from .building_info import BuildingInfo
from .city_gml_info import CityGmlInfo
from .stey_mesh import SetyMesh
from .util.cvsupportjp import Cv2Japanese
from .util.parammanager import ParamManager


class CityGmlManager:
    """OBJ/MTL処理クラス (旧CityGML処理クラス)"""

    def __init__(self, param_manager: ParamManager) -> None:
        """コンストラクタ"""
        self._pm = param_manager
        self.citygml_infos: list[CityGmlInfo] = []
        self.obj_data = {}  # 各OBJファイルの元データを保持

    def input_citygml(self):
        """OBJファイル情報入力"""
        # input_obj_folder_path 内の全OBJファイルを対象とする
        obj_files = sorted(
            [
                f
                for f in os.listdir(self._pm.input_obj_folder_path)
                if f.endswith(".obj")
            ]
        )

        for index, obj_file_name in enumerate(obj_files):
            obj_path = os.path.join(self._pm.input_obj_folder_path, obj_file_name)
            base_name = os.path.splitext(obj_file_name)[0]

            # OBJの読み込みと分類
            data = self._read_obj(obj_path)
            self.obj_data[base_name] = data

            # CityGmlInfoを互換性のために使用 (1つのOBJファイルを1つのGML単位とみなす)
            output_obj_path = os.path.join(
                self._pm.output_obj_folder_path, obj_file_name
            )
            city_gml_info = CityGmlInfo(
                input_city_gml_path=obj_path, output_city_gml_path=output_obj_path
            )
            self.citygml_infos.append(city_gml_info)

            # マテリアルごとにBuildingInfoを作成
            textures = {}

            for mtl_name, mtl_info in data["materials"].items():
                if "map_Kd" in mtl_info:
                    tex_path = mtl_info["map_Kd"]
                    # 相対パスを解決
                    full_tex_path = os.path.normpath(
                        os.path.join(os.path.dirname(obj_path), tex_path)
                    )

                    if os.path.exists(full_tex_path):
                        if tex_path not in textures:
                            image = Cv2Japanese.imread(full_tex_path)
                            if image is None:
                                continue
                            building = BuildingInfo(
                                mime_type=os.path.splitext(tex_path)[1][1:],
                                input_image_path=tex_path,
                                input_image_height=image.shape[0],
                                input_image_width=image.shape[1],
                            )
                            textures[tex_path] = building
                            city_gml_info.add_building_info(building)

                        building = textures[tex_path]

                        # このテクスチャを使用する面を追加
                        for face_idx in data["mtl_faces"].get(mtl_name, []):
                            # 屋根か壁のみをアトラス化対象とする
                            if (
                                face_idx in data["roof_faces"]
                                or face_idx in data["wall_faces"]
                            ):
                                face = data["faces"][face_idx]
                                # UV座標を取得
                                uv_indices = [idx[1] for idx in face]
                                if None in uv_indices:
                                    continue  # UVがない面はスキップ

                                uvs = np.array([data["uvs"][i - 1] for i in uv_indices])
                                # アトラス化用座標変換 (normalized -> pixel, flip Y)
                                coords = np.zeros_like(uvs)
                                coords[:, 0] = (
                                    uvs[:, 0] * building.input_image_width - 0.5
                                )
                                coords[:, 1] = (
                                    1.0 - uvs[:, 1]
                                ) * building.input_image_height - 0.5

                                building.add_polygon_info(
                                    uri=f"{base_name}#f{face_idx}",
                                    ring=f"face_{face_idx}",
                                    coords=coords,
                                    imgSize=[
                                        building.input_image_width,
                                        building.input_image_height,
                                    ],
                                    extentPixel=self._pm.extent_pixel,
                                )

        return self.citygml_infos

    def output_citygml(self):
        """OBJ/MTLファイル情報出力"""
        os.makedirs(self._pm.output_obj_folder_path, exist_ok=True)
        os.makedirs(self._pm.output_appearance_folder_path, exist_ok=True)

        for citygml_info in self.citygml_infos:
            obj_file_name = os.path.basename(citygml_info.input_city_gml_path)
            base_name = os.path.splitext(obj_file_name)[0]
            data = self.obj_data[base_name]

            # 新しいUVリストを準備
            new_uvs = list(data["uvs"])
            uv_map = {}  # (face_idx, vertex_in_face_idx) -> new_uv_idx

            # アトラス化された結果を反映
            new_materials = {}
            for building in citygml_info.buildings:
                if building.output_image_path:
                    # アトラス化されたテクスチャの相対パス (objディレクトリから見たパス)
                    rel_atlas_path = os.path.relpath(
                        os.path.join(
                            self._pm.output_root_folder_path, building.output_image_path
                        ),
                        self._pm.output_obj_folder_path,
                    )

                    # 新しいマテリアル名を作成 (アトラス画像ごとに)
                    atlas_mtl_base = os.path.splitext(
                        os.path.basename(building.output_image_path)
                    )[0]
                    atlas_mtl_name = f"atlas_{atlas_mtl_base}"
                    new_materials[atlas_mtl_name] = rel_atlas_path

                    for poly in building.polygon_infos:
                        # poly.target_uri から face_idx を復元
                        face_idx = int(poly.target_uri.split("#f")[1])

                        # UVの書き出し
                        face_uv_indices = []
                        for uv in poly.out_texcoord:
                            new_uvs.append(list(uv))
                            face_uv_indices.append(len(new_uvs))

                        for i, uv_idx in enumerate(face_uv_indices):
                            uv_map[(face_idx, i)] = uv_idx

            # OBJファイルの書き出し
            output_obj_path = os.path.join(
                self._pm.output_obj_folder_path, obj_file_name
            )
            output_mtl_name = base_name + ".mtl"
            output_mtl_path = os.path.join(
                self._pm.output_obj_folder_path, output_mtl_name
            )

            with open(output_obj_path, "w") as f:
                f.write(f"mtllib {output_mtl_name}\n")
                for v in data["vertices"]:
                    f.write(f"v {v[0]} {v[1]} {v[2]}\n")
                for uv in new_uvs:
                    f.write(f"vt {uv[0]} {uv[1]}\n")

                current_mtl = None
                groups = [
                    ("# Roof", data["roof_faces"]),
                    ("# Wall", data["wall_faces"]),
                    ("# Ground", data["ground_faces"]),
                ]

                for label, faces_indices in groups:
                    if not faces_indices:
                        continue
                    f.write(f"\n{label}\n")
                    for f_idx in faces_indices:
                        target_mtl = data["face_mtls"][f_idx]

                        # アトラス化されたマテリアルに置き換え
                        for building in citygml_info.buildings:
                            if any(
                                poly.target_uri == f"{base_name}#f{f_idx}"
                                for poly in building.polygon_infos
                            ):
                                atlas_mtl_base = os.path.splitext(
                                    os.path.basename(building.output_image_path)
                                )[0]
                                target_mtl = f"atlas_{atlas_mtl_base}"
                                break

                        if target_mtl != current_mtl:
                            f.write(f"usemtl {target_mtl}\n")
                            current_mtl = target_mtl

                        face = data["faces"][f_idx]
                        face_str = "f"
                        for i, idx in enumerate(face):
                            v_idx = idx[0]
                            vt_idx = uv_map.get((f_idx, i), idx[1])
                            if vt_idx:
                                face_str += f" {v_idx}/{vt_idx}"
                            else:
                                face_str += f" {v_idx}"
                        f.write(face_str + "\n")

            # MTLファイルの書き出し
            with open(output_mtl_path, "w") as f:
                # オリジナルのマテリアルをコピー（アトラス化されなかったもの用）
                for name, m_info in data["materials"].items():
                    is_atlased = False
                    if "map_Kd" in m_info:
                        for building in citygml_info.buildings:
                            if building.input_image_path == m_info["map_Kd"]:
                                is_atlased = True
                                break
                    if not is_atlased:
                        f.write(f"newmtl {name}\n")
                        for k, v in m_info.items():
                            f.write(f"  {k} {v}\n")

                # 新しいアトラスマテリアルを追加
                for m_name, tex_path in new_materials.items():
                    f.write(f"newmtl {m_name}\n")
                    f.write(f"  map_Kd {tex_path}\n")

    def _read_obj(self, path):
        vertices = []
        uvs = []
        faces = []
        materials = {}
        face_mtls = []
        mtl_faces = {}
        current_mtl = None

        with open(path, "r") as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "v":
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == "vt":
                    uvs.append([float(parts[1]), float(parts[2])])
                elif parts[0] == "f":
                    face = []
                    for p in parts[1:]:
                        v_parts = p.split("/")
                        v_idx = int(v_parts[0])
                        vt_idx = (
                            int(v_parts[1]) if len(v_parts) > 1 and v_parts[1] else None
                        )
                        face.append((v_idx, vt_idx))
                    faces.append(face)
                    face_mtls.append(current_mtl)
                    if current_mtl:
                        if current_mtl not in mtl_faces:
                            mtl_faces[current_mtl] = []
                        mtl_faces[current_mtl].append(len(faces) - 1)
                elif parts[0] == "mtllib":
                    mtl_path = os.path.join(os.path.dirname(path), parts[1])
                    materials.update(self._read_mtl(mtl_path))
                elif parts[0] == "usemtl":
                    current_mtl = parts[1]

        roof_faces, wall_faces, ground_faces = self._classify_faces(vertices, faces)

        return {
            "vertices": vertices,
            "uvs": uvs,
            "faces": faces,
            "materials": materials,
            "face_mtls": face_mtls,
            "mtl_faces": mtl_faces,
            "roof_faces": roof_faces,
            "wall_faces": wall_faces,
            "ground_faces": ground_faces,
        }

    def _read_mtl(self, path):
        materials = {}
        if not os.path.exists(path):
            return materials
        current_mtl = None
        with open(path, "r") as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "newmtl":
                    current_mtl = parts[1]
                    materials[current_mtl] = {}
                elif current_mtl:
                    materials[current_mtl][parts[0]] = " ".join(parts[1:])
        return materials

    def _classify_faces(self, vertices, faces):
        tolerance = 1e-7
        threshold_degree = 1.0
        ground_threshold = np.cos(np.radians(threshold_degree))
        wall_threshold = np.sin(np.radians(threshold_degree))

        roof_indices = []
        wall_indices = []
        ground_indices = []

        v_np = np.array(vertices)
        face_min_z = []
        for face in faces:
            v_indices = [idx[0] - 1 for idx in face]
            face_min_z.append(v_np[v_indices, 2].min())

        face_min_z = np.array(face_min_z)
        if len(face_min_z) == 0:
            return [], [], []
        ground_z = face_min_z.min()

        for i, face in enumerate(faces):
            v_indices = [idx[0] - 1 for idx in face]
            pts = v_np[v_indices]

            normal = None
            for j in range(len(pts)):
                p1 = pts[j % len(pts)]
                p2 = pts[(j + 1) % len(pts)]
                p3 = pts[(j + 2) % len(pts)]
                v1 = p2 - p1
                v2 = p3 - p1
                raw_normal = np.cross(v1, v2)
                normal_length = np.linalg.norm(raw_normal)
                if normal_length > tolerance:
                    normal = raw_normal / normal_length
                    break

            if normal is None:
                continue

            if (
                abs(normal[2]) > ground_threshold
                and face_min_z[i] - ground_z < tolerance
            ):
                ground_indices.append(i)
            elif abs(normal[2]) < wall_threshold:
                wall_indices.append(i)
            else:
                roof_indices.append(i)

        return roof_indices, wall_indices, ground_indices

    def removeNoneKeyFromDic(self, nsmap):
        return {}

    def get_mesh(self, lat, lon):
        return 0
