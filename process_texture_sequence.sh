#!/bin/sh

set -e

input_dir=${INPUT_DIR:?}
output_dir=${OUTPUT_DIR:?}

input_format="${INPUT_FORMAT:-"png"}"
output_format="${OUTPUT_FORMAT:-"png"}"

# 処理する
stack=""
while [ "$#" -gt 0 ]; do
  process="${1}"
  shift

  if [ "${process}" = "resize" ]; then
    scale="${1}"
    shift
  else
    unset scale
  fi
  if [ "${process}" = "rectify" ] || [ "${process}" = "wall" ] ; then
    meter_per_pixel="${1}"
    shift
  else
    unset meter_per_pixel
  fi
  label="${process}${scale}${meter_per_pixel}"

  if [ -z "${stack}" ]; then
    current_input_dir="${input_dir}"
    current_output_dir="${output_dir}/output_${label}"
  else
    current_input_dir="${output_dir}/output_$(echo ${stack} | tr ' ' '_')"
    current_output_dir="${output_dir}/output_$(echo ${stack} ${label} | tr ' ' '_')"
  fi

  if [ -d "${current_output_dir}" ]; then
    echo "SKIP: [${stack}] ${label}"
  else
    echo "RUN: [${stack}] ${label}"
    if [ -z "${stack}" ]; then
      _input_format="${input_format}"
    else
      _input_format="${output_format}"
    fi
    INPUT_DIR="${current_input_dir}" OUTPUT_DIR="${current_output_dir}" INPUT_FORMAT="${_input_format}" OUTPUT_FORMAT="${output_format}" SCALE="${scale}" METER_PER_PIXEL="${meter_per_pixel}" "./process_${process}.sh"
  fi

  if [ -z "${stack}" ]; then
    stack="${label}"
  else
    stack="${stack} ${label}"
  fi
done
