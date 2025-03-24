#!/bin/sh

set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########

output_dir="$(realpath -sm "${OUTPUT_DIR:?}")"

bldg_lod2_tool_param="${BLDG_LOD2_TOOL_PARAM}"
if [ -n "${INPUT_DIR}" ]; then
  input_dir="$(realpath "${INPUT_DIR}")"
fi
las_coordinate_system="${LAS_COORDINATE_SYSTEM:-9}"
output_texture_enabled="${OUTPUT_TEXTURE_ENABLED:-false}"

meter_per_texture_pixel="${METER_PER_TEXTURE_PIXEL:-0.24}"

echo "output_dir: ${output_dir}"
printf 'bldg_lod2_tool_param: %s\n' "${bldg_lod2_tool_param}" | head -n 5
echo "input_dir: ${input_dir}"
echo "las_coordinate_system: ${las_coordinate_system}"
echo "output_texture_enabled ${output_texture_enabled}"
echo "meter_per_texture_pixel: ${meter_per_texture_pixel}"

project_dir="$(realpath "$(dirname "$0")")"



########## LOD2建築物自動作成ツール ##########

echo '########## LOD2建築物自動作成ツール ##########'

# LOD2建築物自動作成ツールのフォルダーに移動
cd "${project_dir}"

bldg_lod2_tool_param_file="$(mktemp --suffix .json)"
if [ -n "${bldg_lod2_tool_param}" ]; then
  printf '%s' "${bldg_lod2_tool_param}" > "${bldg_lod2_tool_param_file}"
  output_texture_enabled="$(jq -r '.OutputTexture' "${bldg_lod2_tool_param_file}")"
elif [ -n "${input_dir}" ]; then
  cat <<EOF > "${bldg_lod2_tool_param_file}"
{
  "TextureFolderPath": "${input_dir}/RawImage",
  "ExternalCalibElementPath": "${input_dir}/ExCalib/ExCalib.txt",
  "CameraInfoPath": "${input_dir}/CamInfo/CamInfo.txt",
  "DsmFolderPath": "${input_dir}/DSM",
  "CityGMLFolderPath": "${input_dir}/CityGML",
  "LasCoordinateSystem": ${las_coordinate_system},
  "LasSwapXY": false,
  "RotateMatrixMode": 0,
  "OutputFolderPath": "${output_dir}",
  "OutputOBJ": true,
  "OutputTexture": ${output_texture_enabled},
  "OutputCityGML": true,
  "OutputLogFolderPath": "${output_dir}",
  "DebugLogOutput": true,
  "PhaseConsistency": {
    "DeleteErrorObject": true,
    "NonPlaneThickness": 0.05,
    "NonPlaneAngle": 15
  },
  "DebugMode": false,
  "TargetCoordAreas": null,
  "TargetBuildingIds": null,
  "TextureOutputWidthMax": 4096,
  "TextureOutputHeightMax": 4096,
  "TextureImageFormat": "png"
}
EOF
else
  echo 'BLDG_LOD2_TOOL_PARAM or INPUT_DIR required'
  exit 1
fi
city_gml_dir_name="$(basename "$(jq -r '.CityGMLFolderPath' "${bldg_lod2_tool_param_file}")")"
output_bldg_lod2_tool_dir_path="$(realpath -sm "$(jq -r '.OutputFolderPath' "${bldg_lod2_tool_param_file}")")"

. "./$(basename $PWD)/bin/activate"
python AutoCreateLod2.py "${bldg_lod2_tool_param_file}"
deactivate

# 最新のフォルダを取得
output_bldg_lod2_tool_path="${output_dir}/output_bldg_lod2_tool"
latest_folder="$(ls -t "${output_bldg_lod2_tool_dir_path}" | grep -E "^${city_gml_dir_name}_[0-9]{8}_[0-9]{4}$" | head -n 1)"
if [ -n "${latest_folder}" ]; then
  cd "${output_dir}"
  rm -f ./output_bldg_lod2_tool
  ln -s "${output_bldg_lod2_tool_dir_path}/${latest_folder}" ./output_bldg_lod2_tool
else
  echo '最新のフォルダが見つかりませんでした。'
  exit 1
fi



if ! "${output_texture_enabled}"; then
  # テクスチャつくらないなら終わり
  output_result_path="${output_dir}/output_result"
  rm -rf "${output_result_path}/"
  cp -r "${output_bldg_lod2_tool_path}" "${output_result_path}"

  echo "最終結果 : ${output_result_path}"
  exit 0
fi



########## 正対化ツール ##########

echo '########## 正対化ツール ##########'

# 正対化ツールのフォルダーに移動
cd "${project_dir}/tools/misc"

output_rectify_path="${output_dir}/output_rectify"
rm -rf "${output_rectify_path}/"*

. "./$(basename $PWD)/bin/activate"
python rectify_texture_image.py -i "${output_bldg_lod2_tool_path}" -o "${output_rectify_path}" \
 --format png --meter-per-pixel "${meter_per_texture_pixel}"
deactivate



########## 壁面視認性向上ツール ##########

echo '########## 壁面視認性向上ツール ##########'

# 壁面視認性向上ツールのフォルダーに移動
cd "${project_dir}/tools/SuperResolution/WallSurface"

output_wall_path="${output_dir}/output_wall"
rm -rf "${output_wall_path}/"*

wall_param_file="$(mktemp --suffix .json)"
cat <<EOF > "${wall_param_file}"
{
  "InputDir": "${output_rectify_path}",
  "OutputDir": "${output_wall_path}",
  "Device": "cuda",
  "OutputLogDir": "${output_dir}/log_output_wall",
  "DebugLogOutput": "false",
  "MeterPerPixel": "${meter_per_texture_pixel}",
  "OutputFormat": "png"
}
EOF

. "./$(basename $PWD)/bin/activate"
python main.py "${wall_param_file}"
deactivate



########## テクスチャ解像度向上ツール ##########

echo '########## テクスチャ解像度向上ツール ##########'

# テクスチャ解像度向上ツールのフォルダーに移動
cd "${project_dir}/tools/Real-ESRGAN"

output_esrgan_path="${output_dir}/output_esrgan"
rm -rf "${output_esrgan_path}/*"

. "./$(basename $PWD)/bin/activate"
python inference_realesrgan.py \
  -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 \
  -i "${output_wall_path}" -o "${output_esrgan_path}" \
  --input-ext png --ext png
deactivate


copy_misc() {
  input_image_path="${1}"
  input_misc_path="${2}"
  output_result_path="${3}"
  output_format="${4}"
  if [ "${input_image_path}" != "${output_result_path}" ]; then
    rm -rf "${output_result_path}"
    cp -r "${input_image_path}" "${output_result_path}"
  fi

  # テクスチャ画像以外のファイルをコピー
  for appearance_dir in "${output_result_path}/"*_appearance; do
    grp="$(basename -s '_appearance' "${appearance_dir}")"

    # gmlファイルをコピー
    cp -n "${input_misc_path}/${grp}_op.gml" "${output_result_path}/"

    # objファイルをコピー
    obj_dir_path="${output_result_path}/obj/${grp}_op"
    mkdir -p "${obj_dir_path}"
    for texture_file in "${appearance_dir}/"*."${output_format}"; do
      bldg_id="$(basename -s ."${output_format}" "${texture_file}")"
      cp -n "${input_misc_path}/obj/${grp}_op/${bldg_id}.obj" "${obj_dir_path}/"
    done

    # mtlファイル作成
    mtl_file_path="${obj_dir_path}/${grp}_op.mtl"
    rm -f "${mtl_file_path}"
    for texture_file in "${appearance_dir}/"*."${output_format}"; do
      bldg_id="$(basename -s ."${output_format}" "${texture_file}")"
      printf '%s\n\n' "newmtl ${bldg_id}" >> "${mtl_file_path}"
      printf '%s\n\n' "map_Kd $(realpath --relative-to "${obj_dir_path}" "${texture_file}")" >> "${mtl_file_path}"
    done
  done

  # gmlファイルの中で変更
  cd "${project_dir}/tools/misc"
  . "./$(basename $PWD)/bin/activate"
  for gml_file in $(find "${output_result_path}" -name '*.gml'); do
    python change_texture_image_ext_in_gml.py -i "${gml_file}" -o "${gml_file}" --ext "${output_format}"
  done
  deactivate
}

copy_misc "${output_esrgan_path}" "${output_wall_path}" "${output_esrgan_path}" png



########## 壁面視認性向上ツール（2度掛け） ##########

echo '########## 壁面視認性向上ツール（2度掛け） ##########'

# 壁面視認性向上ツールのフォルダーに移動
cd "${project_dir}/tools/SuperResolution/WallSurface"

output_wall_path2="${output_dir}/output_wall2"
rm -rf "${output_wall_path2}/"*

wall_param_file2="$(mktemp --suffix .json)"
meter_per_texture_pixel2=$(echo "scale=8; ${meter_per_texture_pixel} / 4" | bc | sed 's/^\./0./; s/\(\.[0-9]*[1-9]\)0*$/\1/; s/\.0*$//')
cat <<EOF > "${wall_param_file2}"
{
  "InputDir": "${output_esrgan_path}",
  "OutputDir": "${output_wall_path2}",
  "Device": "cuda",
  "OutputLogDir": "${output_dir}/log_output_wall2",
  "DebugLogOutput": "false",
  "MeterPerPixel": "${meter_per_texture_pixel2}",
  "OutputFormat": "png"
}
EOF

. "./$(basename $PWD)/bin/activate"
python main.py "${wall_param_file2}"
deactivate



########## テクスチャ鮮明化ツール ##########

echo '########## テクスチャ鮮明化ツール ##########'

# テクスチャ鮮明化ツールのフォルダーに移動
cd "${project_dir}/tools/DeblurGANv2"

output_deblurgan_path="${output_dir}/output_deblurgan"
rm -rf "${output_deblurgan_path}/"*

. "./$(basename $PWD)/bin/activate"
python predict.py \
  -c checkpoints/fpn_inception.h5 \
  -i "${output_wall_path2}" -o "${output_deblurgan_path}" \
  --input-format png --output-format jpg
deactivate



########## テクスチャシャープ化ツール ##########
# テクスチャシャープ化ツールはきれいにならないため使わない

########## テクスチャアトラス化ツール ##########
# テクスチャアトラス化ツールはうまく動かないため使わない



########## 最終結果フォルダー ##########

output_path="${output_dir}/output_result"
copy_misc "${output_deblurgan_path}" "${output_wall_path2}" "${output_path}" jpg

echo "最終結果 : ${output_path}"
