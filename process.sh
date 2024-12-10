#!/bin/bash

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
    \"LasCoordinateSystem\": 9,
    \"LasSwapXY\": false,
    \"RotateMatrixMode\": 0,
    \"OutputFolderPath\": \"${base_output_dir}\",
    \"OutputOBJ\": true,
    \"OutputTexture\": true,
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
    \"TextureOutputWidthMax\": 2048,
    \"TextureOutputHeightMax\": 2048
  }" > param.json
else
  # PARAM_JSON が設定されている場合、その内容を param.json に保存
  echo "${PARAM_JSON}" > param.json
fi
city_gml_dir_name=$(basename $(jq -r '.CityGMLFolderPath' param.json))

# 入力ファイルのダウンロード
# aws s3 cp --recursive s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/input ${base_input_dir}

python3 AutoCreateLod2.py param.json
deactivate

# 最新のフォルダを取得
output_latest_bldb_lod2_tool_path="${base_output_dir}/output_latest_bldb_lod2_tool"
latest_folder=$(ls -t "${base_output_dir}" | grep -E "^${city_gml_dir_name}_[0-9]{8}_[0-9]{4}$" | head -n 1)
if [ -n "$latest_folder" ]; then
  cd $base_output_dir
  rm -f ./output_latest_bldb_lod2_tool
  ln -s "./${latest_folder}" "./output_latest_bldb_lod2_tool"
else
  echo "最新のフォルダが見つかりませんでした。"
fi



########## 壁面視認性向上ツール ##########

echo '########## 壁面視認性向上ツール ##########'

# 壁面視認性向上ツールのフォルダーに移動
cd "${workspace_dir}/tools/SuperResolution/WallSurface"
source ./$(basename $PWD)/bin/activate

output_latest_wall_surface_path="${base_output_dir}/output_latest_wall_surface"
echo "{
  \"InputDir\": \"${output_latest_bldb_lod2_tool_path}\",
  \"OutputDir\": \"${output_latest_wall_surface_path}\",
  \"Device\": \"cuda\",
  \"OutputLogDir\": \"${base_output_dir}/log_output_latest_wall_surface\",
  \"DebugLogOutput\": \"false\"
}" > param.json

rm -rf $output_latest_wall_surface_path/*
python3 main.py param.json
deactivate



########## テクスチャ解像度向上ツール ##########

echo '########## テクスチャ解像度向上ツール ##########'

# テクスチャ解像度向上ツールのフォルダーに移動
cd "${workspace_dir}/tools/Real-ESRGAN"
source ./$(basename $PWD)/bin/activate

output_latest_esrgan_path="${base_output_dir}/output_latest_esrgan"
rm -rf "${output_latest_esrgan_path}/*"
python3 inference_realesrgan.py \
  -n RealESRGAN_x2plus -g 0 -s 2 \
  -i "${output_latest_wall_surface_path}" -o "${output_latest_esrgan_path}"
deactivate



# ########## テクスチャ鮮明化ツール ##########

echo '########## テクスチャ鮮明化ツール ##########'

# テクスチャ鮮明化ツールのフォルダーに移動
cd "${workspace_dir}/tools/DeblurGANv2"
source ./$(basename $PWD)/bin/activate

output_latest_deblurgan_path="${base_output_dir}/output_latest_deblurgan"
rm -rf "${output_latest_deblurgan_path}/*"
python3 predict.py \
  -c checkpoints/fpn_inception.h5 \
  -i "${output_latest_esrgan_path}" -o "${output_latest_deblurgan_path}"
deactivate



########## テクスチャシャープ化ツール ##########

echo '########## テクスチャシャープ化ツール ##########'

# テクスチャシャープ化ツールのフォルダーに移動
cd "${workspace_dir}/tools/UnsharpMask"
source ./$(basename $PWD)/bin/activate

output_latest_unsharp_mask_path="${base_output_dir}/output_latest_unsharp_mask"
rm -rf "${output_latest_unsharp_mask_path}/*"
python3 UnsharpMask.py \
  -i "${output_latest_deblurgan_path}" -o "${output_latest_unsharp_mask_path}"
deactivate

# .gml ファイルを再帰的にコピー
find "${output_latest_wall_surface_path}" -type f -name "*.gml" | while read file; do
  # コピー先のディレクトリ構造を作成
  target_dir="${output_latest_unsharp_mask_path}/$(dirname "${file#${output_latest_wall_surface_path}/}")"
  mkdir -p "${target_dir}"

  # ファイルをコピー
  cp "${file}" "${target_dir}"
done



# バグがあるため、一旦保留
# ########## テクスチャアトラス化ツール ##########

# echo '########## テクスチャアトラス化ツール ##########'

# # テクスチャアトラス化ツールのフォルダーに移動
# cd "${workspace_dir}/tools/Atlas_Prot"
# source ./$(basename $PWD)/bin/activate

# output_latest_atlas_prot_path="${base_output_dir}/output_latest_atlas_prot"
# echo "{
#   \"FilePath\": {
#     \"InputGMLFolderPath\": \"${output_latest_unsharp_mask_path}\",
#     \"OutputGMLFolderPath\": \"${output_latest_atlas_prot_path}\"
#   },
#   \"OutputWidth\": 2048,
#   \"OutputHeight\": 2048,
#   \"BackGroundColor\": 255,
#   \"Extentpixel\": 1
# }" > param.json

# rm -rf "${output_latest_atlas_prot_path}/*"
# python3 Atlas_Prot.py param.json
# deactivate



# ########## 最終結果フォルダー ##########

output_latest_result_path="${base_output_dir}/output_latest_result"
rm -rf "${output_latest_result_path}/"
mv "${output_latest_unsharp_mask_path}" "${output_latest_result_path}"
echo "最終結果 : ${output_latest_result_path}"
