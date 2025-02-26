#!/bin/sh

set -e

########## テクスチャシャープ化ツール ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

cd "$(dirname "$0")/tools/UnsharpMask"
. "./$(basename $PWD)/bin/activate"

rm -rf "${output_dir}/"*
python UnsharpMask.py -i "${input_dir}" -o "${output_dir}" --input-format "${input_format}" --output-format "${output_format}"

deactivate

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" ./process_copy-obj.sh
