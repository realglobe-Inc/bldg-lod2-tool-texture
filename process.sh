#!/bin/sh

set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########
# MODE:
#     実行モードを指定します。
#     - FULL: テクスチャマッピングから高精度化まで全行程を実行します。
#     - SKIP_TEXTURE_MAPPING: テクスチャマッピングをスキップし、既存の OBJ を入力として高精度化のみ実行します。
#     - ONLY_TEXTURE_MAPPING: テクスチャマッピングのみを実行します。
# INPUT_OBJ_DIR:
#     OBJファイルが格納されているディレクトリパス。
# INPUT_IMAGE_DIR:
#     画像ファイルが格納されているディレクトリパス。
#     - FULL/ONLY_TEXTURE_MAPPING の場合に必要
# INPUT_EX_CALIB:
#     外部評定要素のファイルパス
#     - FULL/ONLY_TEXTURE_MAPPING の場合に必要
# INPUT_CAMERA_INFO:
#     内部評定要素のファイルパス
#     - FULL/ONLY_TEXTURE_MAPPING の場合に必要
# INPUT_ORTHO_DIR:
#     オルソ画像が格納されているディレクトリパス。
#     - FULL/ONLY_TEXTURE_MAPPING の場合のオプション
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
if [ -n "${INPUT_ORTHO_DIR}" ]; then
  input_ortho_dir="$(realpath -sm "${INPUT_ORTHO_DIR}")"
fi

meter_per_pixel="${METER_PER_PIXEL:-0.16}"
meter_per_texture_pixel="${METER_PER_TEXTURE_PIXEL:-${meter_per_pixel}}"

wall_super_resolution_model="${WALL_SURFACE_MODEL:-"${project_dir}/model/latest_net_G_A.pth"}"
real_esrgan_model="${REAL_ESRGAN_MODEL:-"${project_dir}/model/RealESRGAN_x4plus.pth"}"
deblur_gan_model="${DEBLUR_GAN_MODEL:-"${project_dir}/model/fpn_inception.h5"}"

grid_pixel=${GRID_PIXEL:-1000}

echo "パラメータ"
echo "  mode: ${mode}"
echo "  input_obj_dir: ${input_obj_dir}"
if [ "${mode}" = "FULL" ] || [ "${mode}" = "ONLY_TEXTURE_MAPPING" ]; then
  echo "  input_ex_calib: ${input_ex_calib}"
  echo "  input_camera_info: ${input_camera_info}"
  echo "  input_image_dir: ${input_image_dir}"
  echo "  input_ortho_dir: ${input_ortho_dir}"
fi
echo "  output_dir: ${output_dir}"
echo "  meter_per_texture_pixel: ${meter_per_texture_pixel}"

(cd "${project_dir}"
  if [ "${mode}" = "FULL" ] || [ "${mode}" = "ONLY_TEXTURE_MAPPING" ]; then
    if [ -d "${input_ortho_dir}" ]; then
      echo '########## オルソ分割 ##########'

      split_ortho_dir="${output_dir}/intermediate/split_ortho"
      mkdir -p "${split_ortho_dir}"
      for ortho_path in "${input_ortho_dir}/"*.tif; do
        ortho_basename=$(basename "${ortho_path}")
        ortho_name="${ortho_basename%.*}"
        ortho_ext="${ortho_basename##*.}"
        if find "${split_ortho_dir}" -name "${ortho_name}*.${ortho_ext}" 2> /dev/null | grep -q .; then
          echo "${ortho_path}の分割をスキップします"
          continue
        fi
        echo "${ortho_path}を分割します"
        gdal_retile.py -ps "${grid_pixel}" "${grid_pixel}" -targetDir "${split_ortho_dir}" -co "COMPRESS=DEFLATE" -co "PREDICTOR=2" "${ortho_path}"
      done

      ortho_option="--ortho_dir ${split_ortho_dir}"
    fi


    echo '########## 画像分割 ##########'

    split_image_dir="${output_dir}/intermediate/split_image"
    mkdir -p "${split_image_dir}"
    for image_path in "${input_image_dir}/"*.tif; do
      image_basename=$(basename "${image_path}")
      image_name="${image_basename%.*}"
      image_ext="${image_basename##*.}"
      if find "${split_image_dir}" -name "${image_name}*.${image_ext}" 2> /dev/null | grep -q .; then
        echo "${image_path}の分割をスキップします"
        continue
      fi
      echo "${image_path}を分割します"
      magick "${image_path}[0]" -crop "${grid_pixel}x${grid_pixel}" -set filename:tile "${image_name}_%[fx:page.x/${grid_pixel}]_%[fx:page.y/${grid_pixel}]" +repage "${split_image_dir}/%[filename:tile].${image_ext}"
    done


    echo '########## テクスチャマッピング ##########'

    tool_output_dir="${output_dir}/intermediate/texture_mapping"
    rm -rf "${tool_output_dir}"

    python -m src.texture_mapping.main \
      --input_obj_dir "${input_obj_dir}" \
      --texture_dir "${split_image_dir}" \
      --ex_calib "${input_ex_calib}" \
      --camera_info "${input_camera_info}" \
      --output_dir "${tool_output_dir}" \
      --image_format png \
      --log-path "${tool_output_dir}/output.log" ${ortho_option}
  else
    echo '########## テクスチャマッピングをスキップします ##########'
    tool_output_dir="${input_obj_dir}"
  fi


  if [ "${mode}" = "ONLY_TEXTURE_MAPPING" ]; then
    echo "テクスチャマッピングが完了しました。"
    rm -rf "${output_dir}/obj" "${output_dir}/appearance"
    cp -r "${tool_output_dir}/obj" "${tool_output_dir}/appearance" "${output_dir}/"
    echo "最終結果 : ${output_dir}/obj ${output_dir}/appearance"
    exit 0
  fi



  echo '########## 正対化ツール ##########'

  tool_input_dir="${tool_output_dir}/obj"
  tool_output_dir="${output_dir}/intermediate/rectify"
  rm -rf "${tool_output_dir}"

  python -m src.rectify.main \
    -i "${tool_input_dir}" \
    -o "${tool_output_dir}" \
    --format png \
    --meter-per-pixel "${meter_per_texture_pixel}" \
    --log-path "${tool_output_dir}/output.log"



#  echo '########## 壁面視認性向上ツール ##########'
#
#  tool_input_dir="${tool_output_dir}/obj"
#  tool_output_dir="${output_dir}/intermediate/wall_super_resolution"
#  rm -rf "${tool_output_dir}"
#
#  python -m src.wall_super_resolution.main \
#    --input_dir "${tool_input_dir}" \
#    --output_dir "${tool_output_dir}" \
#    --device cuda \
#    --checkpoint "${wall_super_resolution_model}" \
#    --debug_log_output false \
#    --meter_per_pixel "${meter_per_texture_pixel}" \
#    --output_format png \
#    --log-path "${tool_output_dir}/output.log"



  echo '########## テクスチャ鮮明化ツール ##########'

  tool_input_dir="${tool_output_dir}/obj"
  tool_output_dir="${output_dir}/intermediate/deblur_gan"
  rm -rf "${tool_output_dir}"

  python -m src.deblur_gan_v2.predict \
    -c "${deblur_gan_model}" \
    -i "${tool_input_dir}" \
    -o "${tool_output_dir}" \
    --input-format png \
    --output-format png \
    --log-path "${tool_output_dir}/output.log"



  echo '########## テクスチャ解像度向上ツール ##########'

  tool_input_dir="${tool_output_dir}/obj"
  tool_output_dir="${output_dir}/intermediate/real_esrgan"
  rm -rf "${tool_output_dir}"

  python -m src.real_esrgan.inference_realesrgan \
    -n RealESRGAN_x4plus \
    -g 0 \
    -s 4 \
    --tile 1024 \
    --model_path "${real_esrgan_model}" \
    -i "${tool_input_dir}/obj" \
    -o "${tool_output_dir}" \
    --input-ext png \
    --ext png \
    --log-path "${tool_output_dir}/output.log"



#  echo '########## 壁面視認性向上ツール（2度掛け） ##########'
#
#  tool_input_dir="${tool_output_dir}/obj"
#  tool_output_dir="${output_dir}/intermediate/wall_super_resolution2"
#  rm -rf "${tool_output_dir}"
#
#  meter_per_texture_pixel2=$(echo "scale=8; ${meter_per_texture_pixel} / 4" | bc | sed 's/^\./0./; s/\(\.[0-9]*[1-9]\)0*$/\1/; s/\.0*$//')
#
#  python -m src.wall_super_resolution.main \
#    --input_dir "${tool_input_dir}" \
#    --output_dir "${tool_output_dir}" \
#    --device cuda \
#    --checkpoint "${wall_super_resolution_model}" \
#    --debug_log_output false \
#    --meter_per_pixel "${meter_per_texture_pixel2}" \
#    --output_format png \
#    --log-path "${tool_output_dir}/output.log"



  rm -rf "${output_dir}/obj" "${output_dir}/appearance"
  cp -r "${tool_output_dir}/obj" "${tool_output_dir}/appearance" "${output_dir}/"
  echo "最終結果 : ${output_dir}/obj ${output_dir}/appearance"
)
