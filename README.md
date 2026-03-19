# LOD2建築物モデル自動作成ツールv2.0 (テクスチャ高精度化)

![image 8](https://user-images.githubusercontent.com/79615787/227534529-f858e8e7-1c56-49de-a5ab-5be177c1a0a9.png)

## 概要

本プロジェクトは、3D都市モデルのテクスチャを高精度化するためのツールセットです。
[Auto-Create-bldg-lod2-tool](https://github.com/Project-PLATEAU/Auto-Create-bldg-lod2-tool)をベースに、テクスチャマッピングの精度向上、歪みの補正（正対化）、およびAIを用いた鮮明化・超解像処理に特化して高度化を行っています。

## 処理手順 (process.sh による一括実行)

本リポジトリでは `process.sh` を実行することで、画像分割からテクスチャマッピング、高解像度化までの全行程を一括で実行できます。

| 順番 | 処理内容 | 使用ツール/スクリプト | 説明 |
| - | - | - | - |
| 1 | オルソ/地上画像分割 | `gdal_retile.py`, `magick` | 入力画像を処理しやすいサイズに分割します。 |
| 2 | テクスチャマッピング | `src.texture_mapping.main` | OBJファイルに対して、地上画像やオルソ画像をテクスチャとして貼り付けます。 |
| 3 | 正対化処理 | `src.rectify.main` | 貼り付けられたテクスチャを、壁面に対して正面を向くように補正し、解像度を統一します。 |
| 4 | テクスチャ鮮明化 | `src.deblur_gan_v2.predict` | DeblurGANv2を用いて、テクスチャのボケを抑制します。 |
| 5 | テクスチャ解像度向上 | `src.real_esrgan.inference_realesrgan` | Real-ESRGANを用いて、テクスチャの解像度を4倍に向上させます。 |

## 実行方法

Dockerコンテナ内蔵の `process.sh` を利用します。

### データの配置と出力先

Docker Compose を利用する場合、ローカルの `data` ディレクトリがコンテナ内の `/app/data` にマウントされます。デフォルト設定では、以下の構成でデータを配置してください。

```text
data/
├── input/
│   ├── obj/            # 入力OBJファイルを配置
│   ├── image/          # 地上画像ファイルを配置
│   ├── ortho/          # (オプション) オルソ画像を配置
│   ├── ex_calib.txt    # 外部評定要素ファイル
│   └── camera_info.txt # 内部評定要素ファイル
└── output/             # 処理結果がここに出力される
```

### 実行例

```bash
# Docker Compose を利用した実行
docker compose run --rm bldg-lod2-tool-texture ./process.sh
```

個別にパラメータを指定して実行する場合：

```bash
docker compose run --rm \
  -e MODE=FULL \
  -e INPUT_OBJ_DIR=/app/data/input/obj \
  -e INPUT_IMAGE_DIR=/app/data/input/image \
  -e INPUT_EX_CALIB=/app/data/input/ex_calib.txt \
  -e INPUT_CAMERA_INFO=/app/data/input/camera_info.txt \
  -e OUTPUT_DIR=/app/data/output \
  bldg-lod2-tool-texture \
  ./process.sh
```

### 主なパラメータ:
- `MODE`: 実行モード (`FULL`, `SKIP_TEXTURE_MAPPING`, `ONLY_TEXTURE_MAPPING`)
- `INPUT_OBJ_DIR`: OBJファイルが格納されているディレクトリ
- `INPUT_IMAGE_DIR`: 地上画像ファイルが格納されているディレクトリ
- `INPUT_EX_CALIB`: 外部評定要素ファイルパス
- `INPUT_CAMERA_INFO`: 内部評定要素ファイルパス
- `INPUT_ORTHO_DIR`: (オプション) オルソ画像が格納されているディレクトリ
- `OUTPUT_DIR`: 出力先ディレクトリ
- `METER_PER_TEXTURE_PIXEL`: テクスチャ解像度 (デフォルト 0.16m/px)

## 利用技術

| ライブラリ名 | ライセンス | 説明 |
| - | - | - |
| fire | Apache 2.0 | CLI作成ライブラリ |
| loguru | MIT License | ロギングライブラリ |
| lxml | BSD 3-Clause License | XML処理ライブラリ |
| NumPy | BSD 3-Clause License | 数値計算ライブラリ |
| OpenCV | MIT License | 画像処理ライブラリ |
| Pillow | HPND License | 画像処理ライブラリ |
| Pytorch / Torch | BSD 3-Clause License | 機械学習フレームワーク |
| rasterio | BSD 3-Clause License | 地理空間画像処理ライブラリ |
| Shapely | BSD 3-Clause License | 図形処理ライブラリ |
| spandrel | MIT License | ニューラルネットワーク構造推論ライブラリ |
| Torchvision | BSD 3-Clause License | 画像処理ライブラリ |
| albumentations | MIT License | 画像拡張ライブラリ |

## 注意事項
- 本レポジトリは参考資料として提供しているものです。動作保証は行っておりません。
- 予告なく変更・削除する可能性があります。
- 本レポジトリの利用により生じた損失及び損害等について、開発元および Realglobe はいかなる責任も負わないものとします。

## ライセンス・著作権

### ライセンス
本プロジェクトは GNU General Public License v3.0 を適用します。詳細は [LICENSEファイル](LICENSE) を参照してください。
本ドキュメントは [Project PLATEAUのサイトポリシー](https://www.mlit.go.jp/plateau/site-policy/) (CCBY4.0および政府標準利用規約2.0) に従い提供されています。

### 著作権
- 本プロジェクトの元のコードは以下の著作権に従います: (C) 2024 国土交通省
- 本プロジェクトは [Auto-Create-bldg-lod2-tool](https://github.com/Project-PLATEAU/Auto-Create-bldg-lod2-tool) をフォークしたものです。
- 新しい変更部分に関する著作権: (C) 2024 Realglobe
