import os
import shutil
from pathlib import Path


def update_mtl_texture_extension(mtl_path: Path, new_ext: str):
    if not mtl_path.exists():
        return

    with open(mtl_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().lower().startswith("map_kd "):
            parts = line.split()
            if len(parts) > 1:
                # 最後の要素がパス
                old_path = parts[-1]
                base, _ = os.path.splitext(old_path)
                new_path = base + "." + new_ext.lstrip(".")
                new_lines.append(f"{parts[0]} {new_path}\n")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(mtl_path, "w") as f:
        f.writelines(new_lines)


def write_mtl(mtl_path: Path, material_name: str, texture_rel_path: str):
    """
    MTLファイルを作成する。
    """
    mtl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mtl_path, "w") as f:
        f.write(f"newmtl {material_name}\n")
        f.write(f"map_Kd {texture_rel_path}\n")


def get_texture_path_from_obj(obj_path: Path) -> Path | None:
    """
    OBJファイルからテクスチャパスを1つ取得する。
    """
    textures = get_textures_from_obj(obj_path)
    if textures:
        return textures[0]
    return None


def copy_obj_and_mtl(input_dir: str, output_dir: str, new_ext: str = None):
    input_path = Path(input_dir)
    output_obj_dir = Path(output_dir) / "obj"
    output_obj_dir.mkdir(parents=True, exist_ok=True)

    # input_dir 直下の OBJ ファイルを探す
    for obj_file in input_path.glob("*.obj"):
        bldg_id = obj_file.stem
        # OBJ をコピーしつつ、mtllib を bldg_id.mtl に書き換える
        with open(obj_file, "r") as f:
            lines = f.readlines()

        new_obj_lines = []
        for line in lines:
            if line.strip().lower().startswith("mtllib "):
                new_obj_lines.append(f"mtllib {bldg_id}.mtl\n")
            else:
                new_obj_lines.append(line)

        with open(output_obj_dir / obj_file.name, "w") as f:
            f.writelines(new_obj_lines)

        # テクスチャパスを取得
        texture_path = get_texture_path_from_obj(obj_file)
        if texture_path:
            # 新しい拡張子が指定されている場合は変更
            if new_ext:
                texture_name = f"{bldg_id}.{new_ext.lstrip('.')}"
            else:
                texture_name = f"{bldg_id}{texture_path.suffix}"

            # MTLを作成
            write_mtl(
                output_obj_dir / f"{bldg_id}.mtl",
                bldg_id,
                f"../appearance/{texture_name}",
            )


def get_textures_from_obj(obj_path: Path) -> list[Path]:
    textures = []
    if not obj_path.exists():
        return textures

    with open(obj_path, "r") as f:
        for line in f:
            if line.strip().lower().startswith("mtllib "):
                parts = line.strip().split(None, 1)
                if len(parts) > 1:
                    mtl_name = parts[1]
                    mtl_path = obj_path.parent / mtl_name
                    if mtl_path.exists():
                        textures.extend(get_textures_from_mtl(mtl_path))
                break
    return textures


def get_textures_from_mtl(mtl_path: Path) -> list[Path]:
    textures = []
    if not mtl_path.exists():
        return textures

    with open(mtl_path, "r") as f:
        for line in f:
            if line.strip().lower().startswith("map_kd "):
                parts = line.strip().split(None, 1)
                if len(parts) > 1:
                    texture_rel_path = parts[1]
                    texture_path = mtl_path.parent / texture_rel_path
                    textures.append(texture_path.resolve())
    return list(set(textures))  # 重複を排除
