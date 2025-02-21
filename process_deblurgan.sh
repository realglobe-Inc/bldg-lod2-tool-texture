#!/bin/sh

set -e

########## テクスチャ鮮明化ツール ##########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"


cd "$(dirname "$0")/tools/DeblurGANv2"
. "./$(basename $PWD)/bin/activate"

rm -rf "${output_dir}/*"
python predict.py -c checkpoints/fpn_inception.h5 -i "${input_dir}" -o "${output_dir}"

deactivate

INPUT_DIR="${input_dir}" OUTPUT_DIR="${output_dir}" INPUT_FORMAT="${input_format}" OUTPUT_FORMAT="${output_format}" ./process_copy-obj.sh
