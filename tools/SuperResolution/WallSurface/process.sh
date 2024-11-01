#!/bin/sh

########### Docker コンテナ内部で実行されるスクリプトです ###########

# param.json の作成
if [ -z "${PARAM_JSON}" ]; then
  # PARAM_JSON が設定されていない場合、デフォルトのデータを使用
  echo '{
    "InputDir": "/app/input",
    "OutputDir": "/app/output/output_latest_wall_surface",
    "Device": "cuda",
    "OutputLogDir": "/app/output/log_output_latest_wall_surface",
    "DebugLogOutput": "false"
  }' > param.json
else
  # PARAM_JSON が設定されている場合、その内容を param.json に保存
  echo "${PARAM_JSON}" > param.json
fi

# 入力ファイルのダウンロード
# aws s3 cp --recursive s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/input /app/input

rm -rf /app/output/log_output_latest_wall_surface/*
python3 main.py param.json

# # 出力ファイルのアップロード
# aws s3 cp output.zip s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/output.zip