import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

# srcをPYTHONPATHに追加
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.texture_mapping.texture_main import TextureMain
from src.util.param_manager import ParamManager
from src.util.log import Log, ModuleType


def main():
    parser = argparse.ArgumentParser(
        description="TextureMainを単独で実行するためのスクリプト"
    )

    # 必須パラメータ
    parser.add_argument("--texture_dir", required=True, help="写真画像フォルダパス")
    parser.add_argument(
        "--ex_calib", required=True, help="外部標定要素ファイルパス(.txt/.csv)"
    )
    parser.add_argument(
        "--camera_info", required=True, help="カメラ情報ファイルパス(.txt)"
    )
    parser.add_argument("--output_dir", required=True, help="結果出力フォルダパス")

    # オプションパラメータ
    parser.add_argument(
        "--input_obj_dir",
        help="入力OBJフォルダパス",
    )
    parser.add_argument(
        "--image_format",
        default="png",
        choices=["png", "jpg"],
        help="出力テクスチャ形式 (デフォルト: png)",
    )
    parser.add_argument(
        "--building_ids",
        nargs="+",
        help="処理対象の建物ID (指定しない場合は入力フォルダ内の全OBJを対象)",
    )
    args = parser.parse_args()

    # 1. パラメータ管理クラスの準備
    params = ParamManager()
    params.texture_folder_path = args.texture_dir
    params.ex_calib_element_path = args.ex_calib
    params.camera_info_path = args.camera_info
    params.output_folder_path = args.output_dir
    params.texture_image_format = args.image_format

    # ログ出力先の設定 (出力フォルダ内の logs フォルダ)
    params.output_log_folder_path = os.path.join(args.output_dir, "logs")

    # 2. 中間ディレクトリとログの準備
    # システムの一時ディレクトリを使用して中間フォルダを作成
    temp_dir_obj = tempfile.TemporaryDirectory()
    base_temp_dir = temp_dir_obj.name
    output_phase_obj_dir = os.path.join(base_temp_dir, "phase_consistency")
    output_tex_obj_dir = os.path.join(base_temp_dir, "texture_mapping")

    # ログクラスの初期化
    log = Log(params, None)
    log.process_start_log("texture_mapping")
    log.module_start_log(ModuleType.PASTE_TEXTURE, "texture_mapping")

    # 3. 入力OBJのディレクトリ設定
    raw_input_dir = args.input_obj_dir if args.input_obj_dir else output_phase_obj_dir
    if not os.path.isdir(raw_input_dir):
        print(f"エラー: 入力OBJフォルダが見つかりません: {raw_input_dir}")
        sys.exit(1)

    # 4. OBJファイルの処理 (部材ラベルの付与)
    processed_obj_dir = os.path.join(base_temp_dir, "processed_obj")
    os.makedirs(processed_obj_dir, exist_ok=True)

    print(f"OBJファイルを処理中: {raw_input_dir} -> {processed_obj_dir}")
    obj_files_to_process = list(Path(raw_input_dir).glob("*.obj"))
    for obj_path in obj_files_to_process:
        try:
            # Obj3Dを介して部材ラベルを追加したOBJを一時ディレクトリに保存
            obj = Obj3D.load(obj_path)
            output_path = Path(processed_obj_dir) / obj_path.name
            obj.save(output_path)
        except Exception as e:
            print(f"警告: OBJファイル {obj_path.name} の処理に失敗しました: {e}")

    # 以降の処理では処理済みOBJのディレクトリを使用する
    input_dir = processed_obj_dir

    # 5. 建物情報のリストを作成
    buildings = []
    if args.building_ids:
        # IDが指定されている場合
        buildings = args.building_ids
    else:
        # フォルダ内の全OBJを対象とする
        obj_files = list(Path(input_dir).glob("*.obj"))
        if not obj_files:
            print(f"エラー: 入力フォルダにOBJファイルがありません: {input_dir}")
            sys.exit(1)

        for obj_path in obj_files:
            buildings.append(obj_path.stem)

    print(f"処理対象建物数: {len(buildings)}")

    # 6. TextureMainの実行
    tm = TextureMain(params)
    # TextureMain内部で中間ディレクトリが参照されるため、
    # 明示的に代入する。
    tm.input_obj_dir = input_dir
    tm.output_obj_dir = output_tex_obj_dir

    try:
        res = tm.texture_main(
            buildings=buildings,
            image_format=args.image_format,
        )
        print(f"実行完了。結果ステータス: {res}")
    except Exception as e:
        print(f"実行中にエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


class Obj3D:
    """OBJファイルの3D形状だけを表すクラス"""

    _vertices: NDArray[np.float64]  # (N,3)
    _raw_faces: list[list[int]]
    _faces: list[NDArray[np.float64]]  # [(N, 3)]

    _precision: int | None = None

    def __init__(
        self,
        vertices: NDArray[np.float64],  # (N,3)
        raw_faces: list[list[int]],
        precision: int | None = None,
    ):
        """
        Obj3Dオブジェクトを初期化します。

        :param vertices: 頂点座標のリスト
        :param raw_faces: 面の頂点インデックスのリスト
        """
        output_precision = min(precision, 6) if precision is not None else 6

        filtered_vertices = []
        vertex_indices = {}
        filtered_faces = []
        for i, raw_face in enumerate(raw_faces):
            filtered_face = []
            for j, raw_vertex_idx in enumerate(raw_face):
                vertex = self._round_vertex(vertices[raw_vertex_idx], precision)
                vertex_tuple = (float(vertex[0]), float(vertex[1]), float(vertex[2]))
                vertex_idx = vertex_indices.get(vertex_tuple)
                if vertex_idx is None:
                    vertex_idx = len(filtered_vertices)
                    filtered_vertices.append(vertex)
                    vertex_indices[vertex_tuple] = vertex_idx

                # 連続した同一点は除去
                if len(filtered_face) == 0 or vertex_idx != filtered_face[-1]:
                    filtered_face.append(vertex_idx)
                else:
                    print(
                        f"{i}番目のポリゴンの{j}番目の点を重複点として削除: {vertex.round(output_precision).tolist()}"
                    )

            # 最後と最初の点が同じ場合は最後の点を除去
            if len(filtered_face) > 0 and filtered_face[0] == filtered_face[-1]:
                last_vertex_idx = filtered_face.pop()
                last_vertex = filtered_vertices[last_vertex_idx]
                print(
                    f"{i}番目のポリゴンの最後の点を重複点として削除: {last_vertex.round(output_precision).tolist()}"
                )

            # 2点以下になった面は除外
            if len(filtered_face) < 3:
                print(f"ポリゴンが3点未満となったため削除: {i}番目のポリゴン")
                continue

            filtered_faces.append(filtered_face)

        self._vertices = np.array(filtered_vertices)
        self._raw_faces = filtered_faces
        self._faces = [self._vertices[face] for face in filtered_faces]
        self._precision = precision

    @property
    def vertices(self) -> NDArray[np.float64]:  # (N, 3)
        return self._vertices

    @property
    def faces(self) -> list[NDArray[np.float64]]:  # [(N, 3)]
        return self._faces

    @classmethod
    def load(
        cls,
        file_path: Path,
        precision: int | None = None,
    ) -> "Obj3D":
        """
        OBJファイルから読み込んだObj3Dを返す

        :param file_path: OBJファイルのパス
        :param precision: 小数点以下の桁数
        :returns: Obj3Dオブジェクト
        """
        vertices = []
        raw_faces = []

        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if line.startswith("v "):
                    # 頂点座標の解析
                    parts = line.split()
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    if precision is not None:
                        x, y, z = (
                            round(x, precision),
                            round(y, precision),
                            round(z, precision),
                        )
                    vertices.append((x, y, z))
                elif line.startswith("f "):
                    # 面の解析
                    parts = line.split()
                    face_indices = []
                    for part in parts[1:]:
                        # OBJファイルのインデックスは1から始まるため、0から始まるように調整
                        index = int(part.split("/")[0]) - 1
                        face_indices.append(index)
                    raw_faces.append(face_indices)

        return cls(np.array(vertices), raw_faces)

    @staticmethod
    def _round_vertex(
        vertex: NDArray[np.float64],  # (3,)
        precision: int | None = None,
    ) -> NDArray[np.float64]:  # (3,)
        if precision is not None:
            return vertex.round(precision)
        return vertex

    def save(self, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            self._write(f)

    def _write(self, sink, precision: float | None = None):
        precision = precision if precision is not None else self._precision

        # 頂点を書き込み
        for vertex in self._vertices:
            x, y, z = vertex
            if precision is not None:
                sink.write(
                    f"v {round(x, precision)} {round(y, precision)} {round(z, precision)}\n"
                )
            else:
                sink.write(f"v {x} {y} {z}\n")

        sink.write("\n")

        # 面を書き込み
        def write_face(face: list[int]):
            # OBJファイルのインデックスは1から始まるため調整
            line = " ".join(map(str, map(lambda i: i + 1, face)))
            sink.write(f"f {line}\n")

        roof_face_indices, wall_face_indices, ground_face_indices = (
            self._roof_wall_ground()
        )
        sink.write(f"\n# Roof\n")
        for face_index in roof_face_indices:
            write_face(self._raw_faces[face_index])
        sink.write(f"\n# Wall\n")
        for face_index in wall_face_indices:
            write_face(self._raw_faces[face_index])
        sink.write(f"\n# Ground\n")
        for face_index in ground_face_indices:
            write_face(self._raw_faces[face_index])

    def _roof_wall_ground(
        self,
    ) -> tuple[list[int], list[int], list[int]]:
        """
        屋根面、壁面、底面を返す
        """
        tolerance = 1e-7

        # 地面と壁の判定閾値（度数法）
        threshold_degree = 1.0
        # 水平から1度以内 (cos(1°) ≈ 0.999847)
        ground_threshold = np.cos(np.radians(threshold_degree))
        # 垂直から1度以内 (sin(1°) ≈ 0.01745)
        wall_threshold = np.sin(np.radians(threshold_degree))

        # 高さが最低の面を地面、垂直の面を壁面、それ以外を屋根面とする
        roof_face_indices = []
        wall_face_indices = []
        ground_face_indices = []

        # 各面の最低Z座標を計算
        face_min_z = np.array([face[:, 2].min() for face in self.faces])
        ground_z = face_min_z.min()  # 地面の閾値

        for i, face in enumerate(self.faces):
            normal = None
            for j in range(len(face)):
                # 法線ベクトルのZ成分で面の種類を判定
                p1 = face[j % len(face)]
                p2 = face[(j + 1) % len(face)]
                p3 = face[(j + 2) % len(face)]

                # 2つのベクトルを計算
                v1 = p2 - p1
                v2 = p3 - p1

                # 外積を計算して法線ベクトルを求める
                raw_normal = np.cross(v1, v2)

                # 正規化
                normal_length = np.linalg.norm(raw_normal)
                if normal_length > tolerance:
                    normal = raw_normal / normal_length
                    break
            if normal is None:
                continue

            if (
                abs(normal[2]) > ground_threshold
                and face_min_z[i] - ground_z < tolerance
            ):  # 水平の底面
                # 地面
                ground_face_indices.append(i)
            elif abs(normal[2]) < wall_threshold:  # 垂直面
                # 壁面
                wall_face_indices.append(i)
            else:
                # 屋根
                roof_face_indices.append(i)

        return roof_face_indices, wall_face_indices, ground_face_indices


if __name__ == "__main__":
    main()
