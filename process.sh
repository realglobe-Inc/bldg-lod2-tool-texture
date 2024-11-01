#!/bin/sh

########### Docker コンテナ内部で実行されるスクリプトです ###########

# param.json の作成
if [ -z "${PARAM_JSON}" ]; then
  # PARAM_JSON が設定されていない場合、デフォルトのデータを使用
  echo '{
    "TextureFolderPath": "/app/input/01_原画像",
    "ExternalCalibElementPath": "/app/input/02_外部標定要素/ExCalib.txt",
    "CameraInfoPath": "/app/input/03_内部標定要素/CamInfo.txt",
    "DsmFolderPath": "/app/input/04_DSM_RGB",
    "CityGMLFolderPath": "/app/input/08_CityGML",
    "LasCoordinateSystem": 9,
    "LasSwapXY": false,
    "RotateMatrixMode": 0,
    "OutputFolderPath": "/app/output",
    "OutputOBJ": true,
    "OutputTexture": true,
    "OutputLogFolderPath": "/app/output",
    "DebugLogOutput": true,
    "PhaseConsistency": {
      "DeleteErrorObject": true,
      "NonPlaneThickness": 0.05,
      "NonPlaneAngle": 15
    },
    "DebugMode": false,
    "TargetCoordAreas": null,
    "TargetBuildingIds": null,
    "TextureOutputWidthMax": 2048,
    "TextureOutputHeightMax": 2048
  }' > param.json
else
  # PARAM_JSON が設定されている場合、その内容を param.json に保存
  echo "${PARAM_JSON}" > param.json
fi

# 入力ファイルのダウンロード
# aws s3 cp --recursive s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/input /app/input

python3 AutoCreateLod2.py param.json

# ベースディレクトリを指定
base_dir=./output

# 最新のフォルダを取得
latest_folder=$(ls -t "$base_dir" | grep -E '^08_CityGML_[0-9]{8}_[0-9]{4}$' | head -n 1)
echo $latest_folder
if [ -n "$latest_folder" ]; then
  ln -s $base_dir/$latest_folder $base_dir/output_latest_bldb-lod2-tool
else
  echo "最新のフォルダが見つかりませんでした。"
fi

# # 出力ファイルのアップロード
# aws s3 cp output.zip s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/output.zip
