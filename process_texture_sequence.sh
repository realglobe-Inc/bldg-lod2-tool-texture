#!/bin/sh

set -e

input_dir=${INPUT_DIR:?}
output_dir=${OUTPUT_DIR:?}

processes=${@:?}

short_name() {
  res=""
  for i in $@; do
    case ${i} in
      super-resolution-wall-surface)
        res="${res} wall"
        ;;
      real-esrgan)
        res="${res} esrgan"
        ;;
      unsharp-mask)
        res="${res} unsharp"
        ;;
      *)
        res="${res} ${i}"
        ;;
    esac
  done
  echo ${res}
}

long_name() {
  res=""
  for i in $@; do
    case ${i} in
      wall)
        res="${res} super-resolution-wall-surface"
        ;;
      esrgan)
        res="${res} real-esrgan"
        ;;
      unsharp)
        res="${res} unsharp-mask"
        ;;
      *)
        res="${res} ${i}"
        ;;
    esac
  done
  echo ${res}
}

# 処理する
stack=""
for proc in ${processes}; do
  process=$(long_name "${proc}")
  if [ -z "${stack}" ]; then
    current_input_dir="${input_dir}"
    current_output_dir="${output_dir}/output_$(short_name ${process} | xargs)"
  else
    current_input_dir="${output_dir}/output_$(short_name ${stack} | tr ' ' '_')"
    current_output_dir="${output_dir}/output_$(short_name ${stack} ${process}| tr ' ' '_')"
  fi

  if [ -d "${current_output_dir}" ]; then
    echo "SKIP: [${stack}] ${process}"
  else
    echo "RUN: [${stack}] ${process}"
    INPUT_DIR="${current_input_dir}" OUTPUT_DIR="${current_output_dir}" "./process_${process}.sh"
  fi

  if [ -z "${stack}" ]; then
    stack="${process}"
  else
    stack="${stack} ${process}"
  fi
done
