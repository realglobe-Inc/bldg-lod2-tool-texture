#!/bin/sh

set -e

########## テクスチャ鮮明化ツール ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

(
cd "$(dirname "$0")/src/deblur_gan_v2"

rm -rf "${output_dir}/"*
python predict.py -c checkpoints/fpn_inception.h5 -i "${input_dir}" -o "${output_dir}" --input-format "${input_format}" --output-format "${output_format}"

)

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" "$(dirname "$0")/process_copy-obj.sh"
