#!/bin/sh

set -e

########## テクスチャ正対化ツール ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")

output_format="${OUTPUT_FORMAT:-"png"}"
meter_per_pixel="${METER_PER_PIXEL:-0.16}"

(
cd "$(dirname "$0")/src/misc/"

rm -rf "${output_dir}/"*
python rectify_texture_image.py -i "${input_dir}" -o "${output_dir}" --format "${output_format}" --meter-per-pixel "${meter_per_pixel}"

)
