import os


class Config:
    """static変数設定"""

    # システムバージョン
    SYSTEM_VERSION = "1.0.0"

    # OBJファイル出力先(中間出力物)
    OUTPUT_OBJ_DIR = os.path.join(".", "temp")  # 中間出力フォルダ
    # 位相一貫性補正後
    OUTPUT_PHASE_OBJ_DIR = os.path.join(OUTPUT_OBJ_DIR, "phase_consistency")
    # テクスチャ自動貼付け後
    OUTPUT_TEX_OBJ_DIR = os.path.join(OUTPUT_OBJ_DIR, "texture_mapping")
