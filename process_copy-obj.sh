#!/bin/sh

set -e

########## objファイル等をコピーする ##########

input_dir=$(realpath -m "${INPUT_DIR:?}")
output_dir=$(realpath -m "${OUTPUT_DIR:?}")

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

for appearance_dir in "${output_dir}/"*_appearance; do
  grp=$(basename -s '_appearance' "${appearance_dir}")

  # gmlファイルをコピー
  cp -n "${input_dir}/${grp}_op.gml" "${output_dir}/"

  # objファイルをコピー
  obj_dir_path="${output_dir}/obj/${grp}_op"
  mkdir -p "${obj_dir_path}"
  for texture_file in "${appearance_dir}/"*".${output_format}"; do
    bldg_id=$(basename -s ".${output_format}" "${texture_file}")
    cp -n "${input_dir}/obj/${grp}_op/${bldg_id}.obj" "${obj_dir_path}/"
  done

  # mtlファイル作成
  mtl_file_path="${obj_dir_path}/${grp}_op.mtl"
  rm -f "${mtl_file_path}"
  for texture_file in "${appearance_dir}/"*".${output_format}"; do
    bldg_id=$(basename -s ".${output_format}" "${texture_file}")
    printf '%s\n\n' "newmtl ${bldg_id}" >> "${mtl_file_path}"
    printf '%s\n\n' "map_Kd $(realpath --relative-to "${obj_dir_path}" "${texture_file}")" >> "${mtl_file_path}"
  done
done

if [ "${input_format}" != "${output_format}" ]; then
  (
  cd "$(dirname "$0")/tools/misc"
  . "./$(basename $PWD)/bin/activate"

  for gml_file in $(find "${output_dir}" -name '*.gml'); do
    python change_texture_image_ext_in_gml.py -i "${gml_file}" -o "${gml_file}" --ext "${output_format}"
  done

  deactivate
  )
fi
