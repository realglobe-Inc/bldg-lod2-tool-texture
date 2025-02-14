#!/bin/sh

set -e

########## 壁面視認性向上ツール ##########

project_dir=${PROJECT_DIR:-${PWD}}
base_output_dir=${BASE_OUTPUT_DIR:-${project_dir}/output}

input_dir=$(realpath -m "${INPUT_DIR:-${base_output_dir}/output_bldg_lod2_tool}")
output_dir=$(realpath -m "${OUTPUT_DIR:-${base_output_dir}/output_wall_surface}")
output_log_dir=$(realpath -m "${OUTPUT_LOG_DIR:-${output_dir}/log_output_wall_surface}")
debug_log_output=${DEBUG_LOG_OUTPUT:-false}

# 壁面視認性向上ツールのフォルダーに移動
cd "${project_dir}/tools/SuperResolution/WallSurface"

echo "{
  \"InputDir\": \"${input_dir}\",
  \"OutputDir\": \"${output_dir}\",
  \"Device\": \"cuda\",
  \"OutputLogDir\": \"${output_log_dir}\",
  \"DebugLogOutput\": \"${debug_log_output}\"
}" > param.json

rm -rf "${output_dir}/"*

. "./$(basename $PWD)/bin/activate"
python main.py param.json
deactivate
