#!/bin/sh

set -e

########## objファイル等をコピーする ##########

input_dir="${INPUT_DIR:?}"
output_dir="${OUTPUT_DIR:?}"

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

for appearance_dir in "${output_dir}/"*_appearance; do
  grp=$(basename -s '_appearance' "${appearance_dir}")
  mkdir -p "${output_dir}/obj/${grp}_op"

  # gmlファイルをコピー
  cp -n "${input_dir}/${grp}_op.gml" "${output_dir}/"

  # objファイルをコピー
  for texture_file in "${appearance_dir}/*.${output_format}"; do
    bldg_id=$(basename -s ".${output_format}" "${texture_file}")
    cp -n "${input_dir}/obj/${grp}_op/${bldg_id}.obj" "${output_dir}/obj/${grp}_op/"
  done

  # mtlファイル作成
  rm -f "${output_dir}/obj/${grp}_op/${grp}_op.mtl"
  for texture_file in "${appearance_dir}/*.${output_format}"; do
    bldg_id=$(basename -s ".${output_format}" "${texture_file}")
    printf '%s\n\n%s\n\n' "newmtl ${bldg_id}" "map_Kd ../../${grp}_appearance/${texture_file}" >> "${output_dir}/obj/${grp}_op/${grp}_op.mtl"
  done
done
