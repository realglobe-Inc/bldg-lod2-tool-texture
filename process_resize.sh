#!/bin/sh

set -e

########## 画像を半分にする ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"
scale="${SCALE:?}"

mkdir -p "${output_dir}"
rm -rf "${output_dir}/"*
cp -r "${input_dir}/"* "${output_dir}/"
mogrify -resize "${scale}" -format "${output_format}" "${output_dir}/"**/*".${input_format}"
if [ "${output_format}" != "${input_format}" ]; then
  rm "${output_dir}/"**/*".${input_format}"
fi

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" "$(dirname "$0")/process_copy-obj.sh"
