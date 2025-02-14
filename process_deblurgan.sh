#!/bin/sh

set -e

########## テクスチャ鮮明化ツール ##########

project_dir=${PROJECT_DIR:-${PWD}}
base_output_dir=${BASE_OUTPUT_DIR:-${project_dir}/output}

input_dir=$(realpath -m "${INPUT_DIR:-${base_output_dir}/output_esrgan}")
output_dir=$(realpath -m "${OUTPUT_DIR:-${base_output_dir}/output_deblurgan}")

# テクスチャ鮮明化ツールのフォルダーに移動
cd "${project_dir}/tools/DeblurGANv2"

rm -rf "${output_dir}/*"

. "./$(basename $PWD)/bin/activate"
python predict.py -c checkpoints/fpn_inception.h5 -i "${input_dir}" -o "${output_dir}"
deactivate

for appearance_dir in "${output_dir}/"*_appearance; do
  grp=$(basename -s '_appearance' "${appearance_dir}")
  mkdir -p "${output_dir}/obj/${grp}_op"

  # gmlファイルをコピー
  cp -n "${input_dir}/${grp}_op.gml" "${output_dir}/"

  # objファイルをコピー
  for texture_file in "${appearance_dir}/"*.jpg; do
    bldg_id=$(basename -s '.jpg' "${texture_file}")
    cp -n "${input_dir}/obj/${grp}_op/${bldg_id}.obj" "${output_dir}/obj/${grp}_op/"
  done

  # mtlファイル作成
  rm -f "${output_dir}/obj/${grp}_op/${grp}_op.mtl"
  for texture_file in "${appearance_dir}/"*.jpg; do
    bldg_id=$(basename -s '.jpg' "${texture_file}")
    printf '%s\n\n%s\n\n' "newmtl ${bldg_id}" "map_Kd ../../${grp}_appearance/${bldg_id}.jpg" >> "${output_dir}/obj/${grp}_op/${grp}_op.mtl"
  done
done
