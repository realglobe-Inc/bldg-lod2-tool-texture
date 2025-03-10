#!/bin/sh

set -e
trap 'if [ "$?" -ne 0 ]; then echo "Error on line ${LINENO}"; fi' EXIT

########### Docker コンテナ内部で実行されるスクリプトです ###########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

bldg_lod2_tool_param="${BLDG_LOD2_TOOL_PARAM}"
las_coordinate_system="${LAS_COORDINATE_SYSTEM:-9}"
output_texture_enabled="${OUTPUT_TEXTURE_ENABLED:-false}"
meter_per_texture_pixel="${METER_PER_TEXTURE_PIXEL:-0.16}"

echo "input_dir: ${input_dir}"
echo "output_dir: ${output_dir}"
echo "bldg_lod2_tool_param: ${bldg_lod2_tool_param}" | head -n 3
echo "las_coordinate_system: ${las_coordinate_system}"
echo "output_texture_enabled ${output_texture_enabled}"
echo "meter_per_texture_pixel: ${meter_per_texture_pixel}"

project_dir="$(dirname "$0")"



########## LOD2建築物自動作成ツール ##########

echo '########## LOD2建築物自動作成ツール ##########'

# LOD2建築物自動作成ツールのフォルダーに移動
cd "${project_dir}"

bldg_lod2_tool_param_file=$(mktemp --suffix .json)
if [ -z "${bldg_lod2_tool_param}" ]; then
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
  echo "${bldg_lod2_tool_param}" > "${bldg_lod2_tool_param_file}"
  output_texture_enabled=$(jq -r '.OutputTexture' "${bldg_lod2_tool_param_file}")
fi
city_gml_dir_name=$(basename $(jq -r '.CityGMLFolderPath' "${bldg_lod2_tool_param_file}"))

. ./$(basename $PWD)/bin/activate
python AutoCreateLod2.py "${bldg_lod2_tool_param_file}"
deactivate

# 最新のフォルダを取得
output_latest_bldg_lod2_tool_path="${output_dir}/output_latest_bldg_lod2_tool"
latest_folder=$(ls -t "${output_dir}" | grep -E "^${city_gml_dir_name}_[0-9]{8}_[0-9]{4}$" | head -n 1)
if [ -n "${latest_folder}" ]; then
  cd "${output_dir}"
  rm -f ./output_latest_bldg_lod2_tool
  ln -s "./${latest_folder}" ./output_latest_bldg_lod2_tool
else
  echo '最新のフォルダが見つかりませんでした。'
  echo "${output_dir}/${city_gml_dir_name}"
  exit 1
fi



if ! "${output_texture_enabled}"; then
  # テクスチャつくらないなら終わり
  output_latest_result_path="${output_dir}/output_latest_result"
  rm -rf "${output_latest_result_path}/"
  cp -r "${output_latest_bldg_lod2_tool_path}" "${output_latest_result_path}"

  echo "最終結果 : ${output_latest_result_path}"
  exit 0
fi



########## 正対化ツール ##########

echo '########## 正対化ツール ##########'

# 正対化ツールのフォルダーに移動
cd "${project_dir}/tools/misc"

output_latest_rectify_path="${output_dir}/output_latest_rectify"
rm -rf "${output_latest_rectify_path}/"*

. ./$(basename $PWD)/bin/activate
python rectify_texture_image.py -i "${output_latest_bldg_lod2_tool_path}" -o "${output_latest_rectify_path}" \
 --format png --meter-per-pixel "${meter_per_texture_pixel}"
deactivate



########## 壁面視認性向上ツール ##########

echo '########## 壁面視認性向上ツール ##########'

# 壁面視認性向上ツールのフォルダーに移動
cd "${project_dir}/tools/SuperResolution/WallSurface"

output_latest_wall_surface_path="${output_dir}/output_latest_wall_surface"
rm -rf "${output_latest_wall_surface_path}/"*

wall_surface_param_file=$(mktemp --suffix .json)
cat <<EOF > "${wall_surface_param_file}"
{
  "InputDir": "${output_latest_rectify_path}",
  "OutputDir": "${output_latest_wall_surface_path}",
  "Device": "cuda",
  "OutputLogDir": "${output_dir}/log_output_latest_wall_surface",
  "DebugLogOutput": "false",
  "MeterPerPixel": "${meter_per_texture_pixel}",
  "OutputFormat": "png"
}
EOF

. ./$(basename $PWD)/bin/activate
python main.py "${wall_surface_param_file}"
deactivate



########## テクスチャ解像度向上ツール ##########

echo '########## テクスチャ解像度向上ツール ##########'

# テクスチャ解像度向上ツールのフォルダーに移動
cd "${project_dir}/tools/Real-ESRGAN"

output_latest_esrgan_path="${output_dir}/output_latest_esrgan"
rm -rf "${output_latest_esrgan_path}/*"

. ./$(basename $PWD)/bin/activate
python inference_realesrgan.py \
  -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 \
  -i "${output_latest_wall_surface_path}" -o "${output_latest_esrgan_path}" \
  --input-ext png --ext png
deactivate



########## テクスチャ鮮明化ツール ##########

echo '########## テクスチャ鮮明化ツール ##########'

# テクスチャ鮮明化ツールのフォルダーに移動
cd "${project_dir}/tools/DeblurGANv2"

output_latest_deblurgan_path="${output_dir}/output_latest_deblurgan"
rm -rf "${output_latest_deblurgan_path}/"*

. ./$(basename $PWD)/bin/activate
python predict.py \
  -c checkpoints/fpn_inception.h5 \
  -i "${output_latest_esrgan_path}" -o "${output_latest_deblurgan_path}" \
  --input-format png --output-format jpg
deactivate



########## テクスチャシャープ化ツール ##########
# テクスチャシャープ化ツールはきれいにならないため使わない

########## テクスチャアトラス化ツール ##########
# テクスチャアトラス化ツールはうまく動かないため使わない



########## 最終結果フォルダー ##########

output_latest_result_path="${output_dir}/output_latest_result"
rm -rf "${output_latest_result_path}/"
cp -r "${output_latest_deblurgan_path}" "${output_latest_result_path}"

# テクスチャ画像以外のファイルをコピー
for appearance_dir in "${output_latest_wall_surface_path}/"*_appearance; do
  grp=$(basename -s '_appearance' "${appearance_dir}")
  mkdir -p "${output_latest_result_path}/obj/${grp}_op"

  # gmlファイルをコピー
  cp -n "${output_latest_wall_surface_path}/${grp}_op.gml" "${output_latest_result_path}/"

  # objファイルをコピー
  for texture_file in "${appearance_dir}/"*.jpg; do
    bldg_id=$(basename -s .jpg "${texture_file}")
    cp -n "${output_latest_wall_surface_path}/obj/${grp}_op/${bldg_id}.obj" "${output_latest_result_path}/obj/${grp}_op/"
  done

  # mtlファイル作成
  rm -f "${output_latest_result_path}/obj/${grp}_op/${grp}_op.mtl"
  for texture_file in "${appearance_dir}/"*.jpg; do
    bldg_id=$(basename -s .jpg "${texture_file}")
    printf '%s\n\n%s\n\n' "newmtl ${bldg_id}" "map_Kd $(realpath --relative-to "${output_latest_result_path}/obj/${grp}_op" "${texture_file}")" >> "${output_latest_result_path}/obj/${grp}_op/${grp}_op.mtl"
  done
done

# gmlファイルの中でpngの箇所をjpgに変更
cd "${project_dir}/tools/misc"
. "./$(basename $PWD)/bin/activate"
for gml_file in $(find "${output_latest_result_path}" -name '*.gml'); do
  python change_texture_image_ext_in_gml.py -i "${gml_file}" -o "${gml_file}" --ext jpg
done
deactivate

echo "最終結果 : ${output_latest_result_path}"
