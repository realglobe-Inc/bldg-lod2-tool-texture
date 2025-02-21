#!/bin/sh

set -e

########## テクスチャ解像度向上ツール ##########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

cd "$(dirname "$0")/tools/Real-ESRGAN"
. "./$(basename $PWD)/bin/activate"

rm -rf "${output_dir}/*"
python inference_realesrgan.py -n RealESRGAN_x4plus -g 0 -s 4 --tile 1024 -i "${input_dir}" -o "${output_dir}" --input-ext "${input_format}" --ext "${output_format}"

deactivate

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" ./process_copy-obj.sh
