#!/bin/bash

set -e

########### Docker コンテナ内部で実行されるスクリプトです ###########

source ~/.bashrc

workspace_dir=$PWD
base_output_dir="${workspace_dir}/output"
base_input_dir="${workspace_dir}/input"

########## LOD2建築物自動作成ツール ##########

echo '########## LOD2建築物自動作成ツール ##########'

# LOD2建築物自動作成ツールのフォルダーに移動
cd "${workspace_dir}"
source ./$(basename $PWD)/bin/activate

# param.json の作成
if [ -z "${PARAM_JSON}" ]; then
  # PARAM_JSON が設定されていない場合、デフォルトのデータを使用
  echo "{
    \"TextureFolderPath\": \"${base_input_dir}/01_原画像\",
    \"ExternalCalibElementPath\": \"${base_input_dir}/02_外部標定要素/ExCalib.txt\",
    \"CameraInfoPath\": \"${base_input_dir}/03_内部標定要素/CamInfo.txt\",
    \"DsmFolderPath\": \"${base_input_dir}/04_DSM_RGB\",
    \"CityGMLFolderPath\": \"${base_input_dir}/08_CityGML\",
    \"LasCoordinateSystem\": 7,
    \"LasSwapXY\": false,
    \"RotateMatrixMode\": 0,
    \"OutputFolderPath\": \"${base_output_dir}\",
    \"OutputOBJ\": true,
    \"OutputTexture\": true,
    \"OutputCityGML\": true,
    \"OutputLogFolderPath\": \"${base_output_dir}\",
    \"DebugLogOutput\": true,
    \"PhaseConsistency\": {
      \"DeleteErrorObject\": true,
      \"NonPlaneThickness\": 0.05,
      \"NonPlaneAngle\": 15
    },
    \"DebugMode\": false,
    \"TargetCoordAreas\": null,
    \"TargetBuildingIds\": null,
    \"TextureOutputWidthMax\": 1024,
    \"TextureOutputHeightMax\": 1024,
    \"TextureImageFormat\": \"png\"
  }" > param.json
else
  # PARAM_JSON が設定されている場合、その内容を param.json に保存
  echo "${PARAM_JSON}" > param.json
fi
city_gml_dir_name=$(basename $(jq -r '.CityGMLFolderPath' param.json))

# 入力ファイルのダウンロード
# aws s3 cp --recursive s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/input ${base_input_dir}

python AutoCreateLod2.py param.json
deactivate

# 最新のフォルダを取得
output_latest_bldg_lod2_tool_path="${base_output_dir}/output_latest_bldg_lod2_tool"
latest_folder=$(ls -t "${base_output_dir}" | grep -E "^${city_gml_dir_name}_[0-9]{8}_[0-9]{4}$" | head -n 1)
if [ -n "${latest_folder}" ]; then
  cd "${base_output_dir}"
  rm -f ./output_latest_bldg_lod2_tool
  ln -s "./${latest_folder}" "./output_latest_bldg_lod2_tool"
else
  echo "最新のフォルダが見つかりませんでした。"
fi



########## 正対化ツール ##########

echo '########## 正対化ツール ##########'

# 正対化ツールのフォルダーに移動
cd "${workspace_dir}/tools/misc"
source ./$(basename $PWD)/bin/activate

output_latest_rectify_path="${base_output_dir}/output_latest_rectify"

rm -rf "${output_latest_rectify_path}/"*
python rectify_texture_image.py -i "${output_latest_bldg_lod2_tool_path}" -o "${output_latest_rectify_path}" \
 --format "png" --meter-per-pixel "0.16"
deactivate



########## 壁面視認性向上ツール ##########

echo '########## 壁面視認性向上ツール ##########'

# 壁面視認性向上ツールのフォルダーに移動
cd "${workspace_dir}/tools/SuperResolution/WallSurface"
source ./$(basename $PWD)/bin/activate

output_latest_wall_surface_path="${base_output_dir}/output_latest_wall_surface"
echo "{
  \"InputDir\": \"${output_latest_rectify_path}\",
  \"OutputDir\": \"${output_latest_wall_surface_path}\",
  \"Device\": \"cuda\",
  \"OutputLogDir\": \"${base_output_dir}/log_output_latest_wall_surface\",
  \"DebugLogOutput\": \"false\",
  \"MeterPerPixel\": \"0.16\",
  \"OutputFormat\": \"png\"
}" > param.json

rm -rf "${output_latest_wall_surface_path}/"*
python main.py param.json
deactivate



########## テクスチャ解像度向上ツール ##########

echo '########## テクスチャ解像度向上ツール ##########'

# テクスチャ解像度向上ツールのフォルダーに移動
cd "${workspace_dir}/tools/Real-ESRGAN"
source ./$(basename $PWD)/bin/activate

output_latest_esrgan_path="${base_output_dir}/output_latest_esrgan"
rm -rf "${output_latest_esrgan_path}/*"
python inference_realesrgan.py \
  -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 \
  -i "${output_latest_wall_surface_path}" -o "${output_latest_esrgan_path}" \
  --input-ext "png" --ext "png"
deactivate



########## テクスチャ鮮明化ツール ##########

echo '########## テクスチャ鮮明化ツール ##########'

# テクスチャ鮮明化ツールのフォルダーに移動
cd "${workspace_dir}/tools/DeblurGANv2"
source ./$(basename $PWD)/bin/activate

output_latest_deblurgan_path="${base_output_dir}/output_latest_deblurgan"
rm -rf "${output_latest_deblurgan_path}/*"
python predict.py \
  -c checkpoints/fpn_inception.h5 \
  -i "${output_latest_esrgan_path}" -o "${output_latest_deblurgan_path}" \
  --input-format "png" --output-format "jpg"
deactivate



# tools/UnsharpMask はきれいにならないため使わない
# tools/Atlas_Prot はうまく動かないため使わない



########## 最終結果フォルダー ##########
output_latest_result_path="${base_output_dir}/output_latest_result"
rm -rf "${output_latest_result_path}/"
cp -r "${output_latest_deblurgan_path}" "${output_latest_result_path}"

for appearance_dir in "${output_latest_result_path}/"*_appearance; do
  grp=$(basename -s '_appearance' "${appearance_dir}")
  mkdir -p "${output_latest_result_path}/obj/${grp}_op"

  # gmlファイルをコピー
  cp -n "${output_latest_wall_surface_path}/${grp}_op.gml" "${output_latest_result_path}/"

  # objファイルをコピー
  for texture_file in "${appearance_dir}/"*".jpg"; do
    bldg_id=$(basename -s ".jpg" "${texture_file}")
    cp -n "${output_latest_wall_surface_path}/obj/${grp}_op/${bldg_id}.obj" "${output_latest_result_path}/obj/${grp}_op/"
  done

  # mtlファイル作成
  rm -f "${output_latest_result_path}/obj/${grp}_op/${grp}_op.mtl"
  for texture_file in "${appearance_dir}/"*".jpg"; do
    bldg_id=$(basename -s ".jpg" "${texture_file}")
    printf '%s\n\n%s\n\n' "newmtl ${bldg_id}" "map_Kd $(realpath --relative-to "${output_latest_result_path}/obj/${grp}_op" "${texture_file}")" >> "${output_latest_result_path}/obj/${grp}_op/${grp}_op.mtl"
  done
done

cd "${workspace_dir}/tools/misc"
. "./$(basename $PWD)/bin/activate"

for gml_file in $(find "${output_latest_result_path}" -name '*.gml'); do
  python change_texture_image_ext_in_gml.py -i "${gml_file}" -o "${gml_file}" --ext "jpg"
done

deactivate



echo "最終結果 : ${output_latest_result_path}"
