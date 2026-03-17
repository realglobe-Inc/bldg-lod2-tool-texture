#!/bin/sh

set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########
# MODE:
#     実行モードを指定します。
#     - FULL: テクスチャマッピングから高精度化まで全行程を実行します。
#     - SKIP_MAPPING: テクスチャマッピングをスキップし、既存の OBJ を入力として高精度化のみ実行します。
#     - ONLY_MAPPING: テクスチャマッピングのみを実行します。
# INPUT_OBJ_DIR:
#     OBJファイルが格納されているディレクトリパス。
# INPUT_IMAGE_DIR:
#     画像ファイルが格納されているディレクトリパス。
#     - FULL/ONLY_MAPPING の場合に必要
# INPUT_EX_CALIB:
#     外部評定要素のファイルパス
#     - FULL/ONLY_MAPPING の場合に必要
# INPUT_CAMERA_INFO:
#     内部評定要素のファイルパス
#     - FULL/ONLY_MAPPING の場合に必要
# OUTPUT_DIR:
#     出力ファイルや中間ファイルを保存するディレクトリパス。
# METER_PER_PIXEL:
#     テクスチャマッピング時の解像度（1ピクセルが何mに相当するか）。
#     デフォルト0.16。
# METER_PER_TEXTURE_PIXEL:
#     テクスチャ高精度化時の基準解像度。
#     デフォルトは METER_PER_PIXEL と同じ。

mode="${MODE:-FULL}"

project_dir="$(realpath "$(dirname "$0")")"

output_dir="$(realpath -sm "${OUTPUT_DIR:-"${project_dir}/data/output"}")"
input_obj_dir="$(realpath -s "${INPUT_OBJ_DIR:-"${project_dir}/data/input/obj"}")"
input_image_dir="$(realpath -s "${INPUT_IMAGE_DIR:-"${project_dir}/data/input/image"}")"
input_ex_calib="$(realpath -s "${INPUT_EX_CALIB:-"${project_dir}/data/input/ex_calib.txt"}")"
input_camera_info="$(realpath -s "${INPUT_CAMERA_INFO:-"${project_dir}/data/input/camera_info.txt"}")"

meter_per_pixel="${METER_PER_PIXEL:-0.16}"
meter_per_texture_pixel="${METER_PER_TEXTURE_PIXEL:-${meter_per_pixel}}"

wall_super_resolution_model="${WALL_SURFACE_MODEL:-"${project_dir}/model/latest_net_G_A.pth"}"
real_esrgan_model="${REAL_ESRGAN_MODEL:-"${project_dir}/model/RealESRGAN_x4plus.pth"}"
deblur_gan_model="${DEBLUR_GAN_MODEL:-"${project_dir}/model/fpn_inception.h5"}"

echo "mode: ${mode}"
echo "input_obj_dir: ${input_obj_dir}"
if [ "${mode}" = "FULL" ] || [ "${mode}" = "ONLY_MAPPING" ]; then
  echo "input_ex_calib: ${input_ex_calib}"
  echo "input_camera_info: ${input_camera_info}"
  echo "input_image_dir: ${input_image_dir}"
fi
echo "output_dir: ${output_dir}"
echo "meter_per_texture_pixel: ${meter_per_texture_pixel}"

mkdir -p "${output_dir}"


if [ "${mode}" = "FULL" ] || [ "${mode}" = "ONLY_MAPPING" ]; then
  echo '########## テクスチャマッピング ##########'
  
  output_mapping_dir="${output_dir}/intermediate/texture_mapping"
  rm -rf "${output_mapping_dir}"

  python src/texture_mapping/main.py \
    --input_obj_dir "${input_obj_dir}" \
    --texture_dir "${input_image_dir}" \
    --ex_calib "${input_ex_calib}" \
    --camera_info "${input_camera_info}" \
    --output_dir "${output_mapping_dir}" \
    --image_format png

  current_obj_dir="${output_mapping_dir}"
else
  echo '########## テクスチャマッピングをスキップします ##########'
  current_obj_dir="${input_obj_dir}"
fi


if [ "${mode}" = "ONLY_MAPPING" ]; then
  echo "テクスチャマッピングが完了しました。"
  rm -rf "${output_dir}/obj" "${output_dir}/appearance"
  cp -r "${current_obj_dir}/obj" "${current_obj_dir}/appearance" "${output_dir}/"
  echo "最終結果 : ${output_dir}/obj ${output_dir}/appearance"
  exit 0
fi



echo '########## 正対化ツール ##########'

output_rectify_dir="${output_dir}/intermediate/rectify"
rm -rf "${output_rectify_dir}"

# PYTHONPATH を調整して実行
export PYTHONPATH="${project_dir}:${PYTHONPATH}"
python src/misc/rectify_texture_image.py \
  -i "${current_obj_dir}" \
  -o "${output_rectify_dir}" \
  --format png \
  --meter-per-pixel "${meter_per_texture_pixel}"



echo '########## 壁面視認性向上ツール ##########'

output_wall_super_resolution_dir="${output_dir}/intermediate/wall_super_resolution"
rm -rf "${output_wall_super_resolution_dir}"

(
  cd "${project_dir}/src/wall_super_resolution"
  python main.py \
    --input_dir "${output_rectify_dir}" \
    --output_dir "${output_wall_super_resolution_dir}" \
    --device cuda \
    --checkpoint "${wall_super_resolution_model}" \
    --output_log_dir "${output_wall_super_resolution_dir}/log" \
    --debug_log_output false \
    --meter_per_pixel "${meter_per_texture_pixel}" \
    --output_format png
)



echo '########## テクスチャ解像度向上ツール ##########'

output_real_esrgan_dir="${output_dir}/intermediate/real_esrgan"
rm -rf "${output_real_esrgan_dir}"

(
  cd "${project_dir}/src/real_esrgan"
  python inference_realesrgan.py \
    -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 \
    --model_dir "${real_esrgan_model}" \
    -i "${output_wall_super_resolution_dir}" \
    -o "${output_real_esrgan_dir}" \
    --input-ext png --ext png
)



echo '########## 壁面視認性向上ツール（2度掛け） ##########'

output_wall_super_resolution2_dir="${output_dir}/intermediate/wall_super_resolution2"
rm -rf "${output_wall_super_resolution2_dir}"

meter_per_texture_pixel2=$(echo "scale=8; ${meter_per_texture_pixel} / 4" | bc | sed 's/^\./0./; s/\(\.[0-9]*[1-9]\)0*$/\1/; s/\.0*$//')

(
  cd "${project_dir}/src/wall_super_resolution"
  python main.py \
    --input_dir "${output_real_esrgan_dir}" \
    --output_dir "${output_wall_super_resolution2_dir}" \
    --device cuda \
    --checkpoint "${wall_super_resolution_model}" \
    --output_log_dir "${output_wall_super_resolution2_dir}/log" \
    --debug_log_output false \
    --meter_per_pixel "${meter_per_texture_pixel2}" \
    --output_format png
)



echo '########## テクスチャ鮮明化ツール ##########'

output_deblurgan_dir="${output_dir}/intermediate/deblurgan"
rm -rf "${output_deblurgan_dir}"

(
  cd "${project_dir}/src/deblur_gan_v2"
  python predict.py \
    -c "${deblur_gan_model}" \
    -i "${output_wall_super_resolution2_dir}" \
    -o "${output_deblurgan_dir}" \
    --input-format png \
    --output-format png
)



rm -rf "${output_dir}/obj" "${output_dir}/appearance"
cp -r "${output_deblurgan_dir}/obj" "${output_deblurgan_dir}/appearance" "${output_dir}/"
echo "最終結果 : ${output_dir}/obj ${output_dir}/appearance"
