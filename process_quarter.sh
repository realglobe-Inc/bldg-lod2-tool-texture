#!/bin/sh

set -e

########## 画像を4分の1にする ##########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

mkdir -p "${output_dir}"
rm -rf "${output_dir}/*"
cp -r "${input_dir}/*" "${output_dir}/"
mogrify -resize 25% -format "${output_format}" "${output_dir}/**/*.${input_format}"
if [ "${output_format}" != "${input_format}" ]; then
  rm "${output_dir}/**/*.${input_format}"
fi
