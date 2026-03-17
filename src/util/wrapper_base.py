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


def copy_obj_and_mtl(input_dir: str, output_dir: str, new_ext: str = None):
    input_path = Path(input_dir)
    output_obj_dir = Path(output_dir) / "obj"
    output_obj_dir.mkdir(parents=True, exist_ok=True)

    # input_dir 直下の OBJ ファイルを探す
    for obj_file in input_path.glob("*.obj"):
        # OBJ をコピー
        shutil.copy2(obj_file, output_obj_dir / obj_file.name)

        # 関連する MTL を探してコピー
        with open(obj_file, "r") as f:
            for line in f:
                if line.strip().lower().startswith("mtllib "):
                    mtl_name = line.strip().split(None, 1)[1]
                    mtl_src = obj_file.parent / mtl_name
                    if mtl_src.exists():
                        mtl_dst = output_obj_dir / mtl_name
                        shutil.copy2(mtl_src, mtl_dst)
                        if new_ext:
                            update_mtl_texture_extension(mtl_dst, new_ext)
                    break


def get_textures_from_obj(obj_path: Path) -> list[Path]:
    textures = []
    if not obj_path.exists():
        return textures

    with open(obj_path, "r") as f:
        for line in f:
            if line.strip().lower().startswith("mtllib "):
                mtl_name = line.strip().split(None, 1)[1]
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
