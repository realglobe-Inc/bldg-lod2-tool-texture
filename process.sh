#!/bin/bash
set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########
# 建物LOD2テクスチャマッピング処理（全部入り版）
#
# 処理ステップ:
#   1. OBJ展開・整形
#   2. 画像分割（オルソ + 地上画像）
#   3. テクスチャマッピング
#   4. 正対化
#   5. 壁面視認性向上（CycleGAN）
#   6. テクスチャ解像度向上（Real-ESRGAN 4x）
#   7. 壁面視認性向上（2回目）
#   8. テクスチャ鮮明化（DeblurGAN）
#
# 入力:
#   /opt/ml/processing/input/raw_image/       - 地上画像（.tif）
#   /opt/ml/processing/input/ortho/           - オルソ画像（.tif + .tfw、オプション）
#   /opt/ml/processing/input/external_params/param.txt - 外部評定要素
#   /opt/ml/processing/input/internal_params/param.txt - 内部評定要素
#   /opt/ml/processing/input/param.yml        - パラメータファイル（対象建物リスト）
#   /opt/ml/processing/source/result.zip      - 元ジョブの出力（OBJファイル）
#
# 環境変数:
#   SAGEMAKER_OUTPUT_DIR - 出力ディレクトリ

INPUT_DIR="/opt/ml/processing/input"
SOURCE_DIR="/opt/ml/processing/source"
OUTPUT_DIR="${SAGEMAKER_OUTPUT_DIR:-/opt/ml/processing/output}"
WORK_DIR="/app/work"
PARAM_FILE="${INPUT_DIR}/param.yml"
METER_PER_PIXEL=0.16

# モデルパス
WALL_SR_MODEL="/app/model/latest_net_G_A.pth"
REAL_ESRGAN_MODEL="/app/model/RealESRGAN_x4plus.pth"
DEBLUR_GAN_MODEL="/app/model/fpn_inception.h5"

echo "========== 建物LOD2テクスチャマッピング（全部入り）開始 =========="

# === 1. 元ジョブのOBJファイルを展開 ===
echo ""
echo "########## OBJファイル展開 ##########"
mkdir -p "${WORK_DIR}/source_obj"
unzip -o "${SOURCE_DIR}/result.zip" -d "${WORK_DIR}/source_obj/"

# === 2. 対象建物のOBJを整形 ===
echo ""
echo "########## OBJ整形 ##########"
OBJ_DIR="${WORK_DIR}/obj"
mkdir -p "${OBJ_DIR}"

python3 -c "
import yaml, shutil, glob, os

with open('${PARAM_FILE}') as f:
    params = yaml.safe_load(f)

source_dir = '${WORK_DIR}/source_obj'
obj_dir = '${OBJ_DIR}'
count = 0

for b in params.get('buildings', []):
    bldg_id = b['id']
    roof_class = b['roof_class']
    obj_name = f'{roof_class}_roof_building.obj'

    matches = glob.glob(f'{source_dir}/**/{bldg_id}/{obj_name}', recursive=True)
    if matches:
        shutil.copy2(matches[0], f'{obj_dir}/{bldg_id}.obj')
        print(f'  {bldg_id}: {obj_name} -> {bldg_id}.obj')
        count += 1
    else:
        print(f'  {bldg_id}: WARNING - {obj_name} not found')

print(f'整形完了: {count} 建物')
"

# === 3. 画像分割 ===
SPLIT_DIR="${WORK_DIR}/split"
GRID_PIXEL=1000

# オルソ分割（オプション）
ORTHO_OPTION=""
if [ -d "${INPUT_DIR}/ortho" ] && [ "$(ls -A "${INPUT_DIR}/ortho/"*.tif 2>/dev/null)" ]; then
  echo ""
  echo "########## オルソ画像分割 ##########"
  SPLIT_ORTHO="${SPLIT_DIR}/ortho"
  mkdir -p "${SPLIT_ORTHO}"
  for tif in "${INPUT_DIR}/ortho/"*.tif; do
    [ -f "$tif" ] || continue
    echo "  分割: $(basename "$tif")"
    gdal_retile.py -ps ${GRID_PIXEL} ${GRID_PIXEL} -targetDir "${SPLIT_ORTHO}" \
      -co "COMPRESS=DEFLATE" -co "PREDICTOR=2" "$tif"
  done
  ORTHO_OPTION="--ortho_dir ${SPLIT_ORTHO}"
fi

# 地上画像分割
echo ""
echo "########## 地上画像分割 ##########"
SPLIT_IMAGE="${SPLIT_DIR}/image"
mkdir -p "${SPLIT_IMAGE}"
for tif in "${INPUT_DIR}/raw_image/"*.tif; do
  [ -f "$tif" ] || continue
  name=$(basename "${tif%.*}")
  ext="${tif##*.}"
  echo "  分割: $(basename "$tif")"
  magick "${tif}[0]" -crop "${GRID_PIXEL}x${GRID_PIXEL}" \
    -set filename:tile "${name}_%[fx:page.x/${GRID_PIXEL}]_%[fx:page.y/${GRID_PIXEL}]" \
    +repage "${SPLIT_IMAGE}/%[filename:tile].${ext}"
done

# === 4. テクスチャマッピング ===
echo ""
echo "########## テクスチャマッピング ##########"
TOOL_OUTPUT="${WORK_DIR}/intermediate/texture_mapping"
rm -rf "${TOOL_OUTPUT}"

python -m src.texture_mapping.main \
  --input_obj_dir "${OBJ_DIR}" \
  --texture_dir "${SPLIT_IMAGE}" \
  --ex_calib "${INPUT_DIR}/external_params/param.txt" \
  --camera_info "${INPUT_DIR}/internal_params/param.txt" \
  --output_dir "${TOOL_OUTPUT}" \
  --image_format png \
  --log-path "${TOOL_OUTPUT}/output.log" ${ORTHO_OPTION}

# === 5. 正対化 ===
echo ""
echo "########## 正対化 ##########"
TOOL_INPUT="${TOOL_OUTPUT}/obj"
TOOL_OUTPUT="${WORK_DIR}/intermediate/rectify"
rm -rf "${TOOL_OUTPUT}"

python -m src.rectify.main \
  -i "${TOOL_INPUT}" \
  -o "${TOOL_OUTPUT}" \
  --format png \
  --meter-per-pixel "${METER_PER_PIXEL}" \
  --log-path "${TOOL_OUTPUT}/output.log"

# === 6. 壁面視認性向上 ===
echo ""
echo "########## 壁面視認性向上 ##########"
TOOL_INPUT="${TOOL_OUTPUT}/obj"
TOOL_OUTPUT="${WORK_DIR}/intermediate/wall_super_resolution"
rm -rf "${TOOL_OUTPUT}"

python -m src.wall_super_resolution.main \
  --input_dir "${TOOL_INPUT}" \
  --output_dir "${TOOL_OUTPUT}" \
  --device cuda \
  --checkpoint "${WALL_SR_MODEL}" \
  --debug_log_output false \
  --meter_per_pixel "${METER_PER_PIXEL}" \
  --output_format png \
  --log-path "${TOOL_OUTPUT}/output.log"

# === 7. テクスチャ解像度向上（4倍） ===
echo ""
echo "########## テクスチャ解像度向上 ##########"
TOOL_INPUT="${TOOL_OUTPUT}/obj"
TOOL_OUTPUT="${WORK_DIR}/intermediate/real_esrgan"
rm -rf "${TOOL_OUTPUT}"

python -m src.real_esrgan.inference_realesrgan \
  -n RealESRGAN_x4plus \
  -g 0 \
  -s 4 \
  --tile 1024 \
  --model_path "${REAL_ESRGAN_MODEL}" \
  -i "${TOOL_INPUT}" \
  -o "${TOOL_OUTPUT}" \
  --input-ext png \
  --ext png \
  --log-path "${TOOL_OUTPUT}/output.log"

# === 8. 壁面視認性向上（2回目） ===
echo ""
echo "########## 壁面視認性向上（2回目） ##########"
TOOL_INPUT="${TOOL_OUTPUT}/obj"
TOOL_OUTPUT="${WORK_DIR}/intermediate/wall_super_resolution2"
rm -rf "${TOOL_OUTPUT}"

METER_PER_PIXEL2=$(echo "scale=8; ${METER_PER_PIXEL} / 4" | bc | sed 's/^\./0./; s/\(\.[0-9]*[1-9]\)0*$/\1/; s/\.0*$//')

python -m src.wall_super_resolution.main \
  --input_dir "${TOOL_INPUT}" \
  --output_dir "${TOOL_OUTPUT}" \
  --device cuda \
  --checkpoint "${WALL_SR_MODEL}" \
  --debug_log_output false \
  --meter_per_pixel "${METER_PER_PIXEL2}" \
  --output_format png \
  --log-path "${TOOL_OUTPUT}/output.log"

# === 9. テクスチャ鮮明化 ===
echo ""
echo "########## テクスチャ鮮明化 ##########"
TOOL_INPUT="${TOOL_OUTPUT}/obj"
TOOL_OUTPUT="${WORK_DIR}/intermediate/deblur_gan"
rm -rf "${TOOL_OUTPUT}"

python -m src.deblur_gan_v2.predict \
  -c "${DEBLUR_GAN_MODEL}" \
  -i "${TOOL_INPUT}" \
  -o "${TOOL_OUTPUT}" \
  --input-format png \
  --output-format png \
  --log-path "${TOOL_OUTPUT}/output.log"

# === 10. 結果パッケージング ===
echo ""
echo "########## 結果パッケージング ##########"
cd "${TOOL_OUTPUT}"
zip -r "${OUTPUT_DIR}/result.zip" obj/ appearance/
touch "${OUTPUT_DIR}/job_completed.txt"

echo ""
echo "========== テクスチャマッピング（全部入り）完了 =========="
