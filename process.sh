#!/bin/sh

set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########
# MODE:
#     実行モードを指定します。
#     - FULL: テクスチャマッピングから高精度化まで全行程を実行します。
#     - SKIP_MAPPING: テクスチャマッピングをスキップし、既存の OBJ を入力として高精度化のみ実行します。
#     - ONLY_MAPPING: テクスチャマッピングのみを実行します。
# INPUT_DIR:
#     入力データが格納されているディレクトリパス。
#     - FULL/ONLY_MAPPING の場合:
#         RawImage, ExCalib, CamInfo, CityGML を含むディレクトリ。
#     - SKIP_MAPPING の場合:
#         既存の obj ディレクトリと appearance ディレクトリを含むディレクトリ。
# OUTPUT_DIR:
#     出力ファイルや中間ファイルを保存するディレクトリパス。
# METER_PER_PIXEL:
#     テクスチャマッピング時の解像度（1ピクセルが何mに相当するか）。
#     デフォルト0.25。
# METER_PER_TEXTURE_PIXEL:
#     テクスチャ高精度化時の基準解像度。
#     デフォルトは METER_PER_PIXEL と同じ。

mode="${MODE:-FULL}"
output_dir="$(realpath -sm "${OUTPUT_DIR:?OUTPUT_DIR is required}")"
input_dir="$(realpath "${INPUT_DIR:?INPUT_DIR is required}")"

meter_per_pixel="${METER_PER_PIXEL:-0.25}"
meter_per_texture_pixel="${METER_PER_TEXTURE_PIXEL:-${meter_per_pixel}}"

project_dir="$(realpath "$(dirname "$0")")"
wall_surface_model="${WALL_SURFACE_MODEL:-"${project_dir}/model/latest_net_G_A.pth"}"
real_esrgan_model="${REAL_ESRGAN_MODEL:-"${project_dir}/model/RealESRGAN_x4plus.pth"}"
deblur_gan_model="${DEBLUR_GAN_MODEL:-"${project_dir}/model/fpn_inception.h5"}"

echo "mode: ${mode}"
echo "input_dir: ${input_dir}"
echo "output_dir: ${output_dir}"
echo "meter_per_texture_pixel: ${meter_per_texture_pixel}"

mkdir -p "${output_dir}"

########## テクスチャマッピング (src/texture_mapping/main.py) ##########

if [ "${mode}" = "FULL" ] || [ "${mode}" = "ONLY_MAPPING" ]; then
  echo '########## テクスチャマッピング ##########'
  
  output_mapping_path="${output_dir}/10_texture_mapping"
  rm -rf "${output_mapping_path}"
  mkdir -p "${output_mapping_path}"

  # 入力パスの構築
  texture_dir="${input_dir}/RawImage"
  ex_calib="${input_dir}/ExCalib/ExCalib.txt"
  [ ! -f "${ex_calib}" ] && ex_calib="${input_dir}/ExCalib/ExCalib.csv"
  camera_info="${input_dir}/CamInfo/CamInfo.txt"
  input_obj_dir="${input_dir}/CityGML"

  python src/texture_mapping/main.py \
    --texture_dir "${texture_dir}" \
    --ex_calib "${ex_calib}" \
    --camera_info "${camera_info}" \
    --output_dir "${output_mapping_path}" \
    --input_obj_dir "${input_obj_dir}" \
    --image_format png

  current_obj_path="${output_mapping_path}"
else
  echo '########## テクスチャマッピングをスキップします ##########'
  current_obj_path="${input_dir}"
fi

if [ "${mode}" = "ONLY_MAPPING" ]; then
  echo "テクスチャマッピングが完了しました。"
  output_result_path="${output_dir}/output_result"
  rm -rf "${output_result_path}"
  cp -r "${current_obj_path}" "${output_result_path}"
  echo "最終結果 : ${output_result_path}"
  exit 0
fi


########## 正対化ツール ##########

echo '########## 正対化ツール ##########'

output_rectify_path="${output_dir}/20_rectify"
rm -rf "${output_rectify_path}"

# PYTHONPATH を調整して実行
export PYTHONPATH="${project_dir}:${PYTHONPATH}"
python src/misc/rectify_texture_image.py \
  -i "${current_obj_path}" \
  -o "${output_rectify_path}" \
  --format png \
  --meter-per-pixel "${meter_per_texture_pixel}"



########## 壁面視認性向上ツール ##########

echo '########## 壁面視認性向上ツール ##########'

output_wall_path="${output_dir}/30_wall_sr"
rm -rf "${output_wall_path}"

(
  cd "${project_dir}/src/wall_super_resolution"
  python main.py \
    --input_dir "${output_rectify_path}" \
    --output_dir "${output_wall_path}" \
    --device cuda \
    --checkpoint "${wall_surface_model}" \
    --output_log_dir "${output_dir}/log_wall_sr" \
    --debug_log_output false \
    --meter_per_pixel "${meter_per_texture_pixel}" \
    --output_format png
)



########## テクスチャ解像度向上ツール ##########

echo '########## テクスチャ解像度向上ツール ##########'

output_esrgan_path="${output_dir}/40_esrgan"
rm -rf "${output_esrgan_path}"

(
  cd "${project_dir}/src/real_esrgan"
  python inference_realesrgan.py \
    -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 \
    --model_path "${real_esrgan_model}" \
    -i "${output_wall_path}" -o "${output_esrgan_path}" \
    --input-ext png --ext png
)



########## 壁面視認性向上ツール（2度掛け） ##########

echo '########## 壁面視認性向上ツール（2度掛け） ##########'

output_wall_path2="${output_dir}/50_wall_sr_2"
rm -rf "${output_wall_path2}"

meter_per_texture_pixel2=$(echo "scale=8; ${meter_per_texture_pixel} / 4" | bc | sed 's/^\./0./; s/\(\.[0-9]*[1-9]\)0*$/\1/; s/\.0*$//')

(
  cd "${project_dir}/src/wall_super_resolution"
  python main.py \
    --input_dir "${output_esrgan_path}" \
    --output_dir "${output_wall_path2}" \
    --device cuda \
    --checkpoint "${wall_surface_model}" \
    --output_log_dir "${output_dir}/log_wall_sr_2" \
    --debug_log_output false \
    --meter_per_pixel "${meter_per_texture_pixel2}" \
    --output_format png
)



########## テクスチャ鮮明化ツール ##########

echo '########## テクスチャ鮮明化ツール ##########'

output_deblurgan_path="${output_dir}/60_deblurgan"
rm -rf "${output_deblurgan_path}"

(
  cd "${project_dir}/src/deblur_gan_v2"
  python predict.py \
    -c "${deblur_gan_model}" \
    -i "${output_wall_path2}" -o "${output_deblurgan_path}" \
    --input-format png --output-format jpg
)



########## 最終結果フォルダー ##########

output_result_path="${output_dir}/output_result"
rm -rf "${output_result_path}"
cp -r "${output_deblurgan_path}" "${output_result_path}"

echo "最終結果 : ${output_result_path}"
