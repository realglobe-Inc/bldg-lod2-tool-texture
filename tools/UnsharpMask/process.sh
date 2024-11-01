#!/bin/sh

########### Docker コンテナ内部で実行されるスクリプトです ###########

# 入力ファイルのダウンロード
# aws s3 cp --recursive s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/input /app/input

# 画像ファイルだけ処理される。
python3 UnsharpMask.py -i "${InputGMLFolderPath}" -o "${OutputGMLFolderPath}"
rm -rf "${OutputGMLFolderPath}/*"

# .gml ファイルを再帰的にコピー
find "${InputGMLFolderPath}" -type f -name "*.gml" | while read file; do
  # コピー先のディレクトリ構造を作成
  target_dir="${OutputGMLFolderPath}/$(dirname "${file#${InputGMLFolderPath}/}")"
  mkdir -p "$target_dir"

  # ファイルをコピー
  cp "$file" "$target_dir"
done

# # 出力ファイルのアップロード
# aws s3 cp output.zip s3://${BUCKET_NAME}/files/${JOB_INPUT_ID}/output.zip