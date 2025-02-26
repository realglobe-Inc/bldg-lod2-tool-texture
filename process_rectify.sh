#!/bin/sh

set -e

########## テクスチャ正対化ツール ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")
temp_dir=$(realpath -m "${TEMP_DIR:-$(mktemp)}")
output_format="${OUTPUT_FORMAT:-"png"}"

cd "$(dirname "$0")/tools/misc/"
. "./$(basename $PWD)/bin/activate"

rm -rf "${output_dir}/"*
python rectify_texture_image.py -i "${input_dir}" -o "${output_dir}" --temp-dir "${TEMP_DIR}" --format "${output_format}"

deactivate
