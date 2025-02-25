#!/bin/sh

set -e

########## テクスチャ正対化ツール ##########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"


cd "$(dirname "$0")/tools/misc/"
. "./$(basename $PWD)/bin/activate"

rm -rf "${output_dir}/*"
python rectify_texture_image.py -i "${input_dir}" -o "${output_dir}" --input-format "${input_format}" --output-format "${output_format}"

deactivate

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" ./process_copy-obj.sh
