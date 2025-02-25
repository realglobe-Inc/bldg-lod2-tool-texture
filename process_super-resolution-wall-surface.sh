#!/bin/sh

set -e

########## 壁面視認性向上ツール ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")
output_log_dir=$(realpath -m "${OUTPUT_LOG_DIR:-${output_dir}/log}")
debug_log_output=${DEBUG_LOG_OUTPUT:-true}

output_format="${OUTPUT_FORMAT:-"png"}"

cd "$(dirname "$0")/tools/SuperResolution/WallSurface"
. "./$(basename $PWD)/bin/activate"

param_file=$(mktemp --suffix .json)
echo "{
  \"InputDir\": \"${input_dir}\",
  \"OutputDir\": \"${output_dir}\",
  \"Device\": \"cuda\",
  \"OutputLogDir\": \"${output_log_dir}\",
  \"DebugLogOutput\": \"${debug_log_output}\"
}" > "${param_file}"
rm -rf "${output_dir}/"*
python main.py param.json --output-format "${output_format}"

deactivate
