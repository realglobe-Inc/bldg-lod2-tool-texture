import os
import cv2
import argparse


def process_images(input_dir, output_dir):
    # 入力ディレクトリ以下のJPEGファイルを再帰的に探す
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(".jpg") or file.lower().endswith(".jpeg"):
                input_path = os.path.join(root, file)
                # 入力ディレクトリ以下の相対パスを保持した出力パス
                relative_path = os.path.relpath(root, input_dir)
                output_path = os.path.join(output_dir, relative_path)
                # 出力ディレクトリ構造を作成
                os.makedirs(output_path, exist_ok=True)
                # ファイルの出力パス
                output_file_path = os.path.join(output_path, file)

                # 画像の読み込みと保存
                image = cv2.imread(input_path)
                if image is None:
                    print(f"警告: 画像を読み込めませんでした {input_path}")
                    continue
                cv2.imwrite(output_file_path, image)
                print(f"保存しました: {output_file_path}")


def main():
    parser = argparse.ArgumentParser(description="JPEG画像を再保存するスクリプト")
    parser.add_argument("-i", "--input", required=True, help="入力ディレクトリのパス")
    parser.add_argument("-o", "--output", required=True, help="出力ディレクトリのパス")
    args = parser.parse_args()

    input_dir = args.input
    output_dir = args.output

    # 入力ディレクトリと出力ディレクトリの存在確認
    if not os.path.isdir(input_dir):
        print(f"エラー: 入力ディレクトリが存在しません: {input_dir}")
        return

    process_images(input_dir, output_dir)


if __name__ == "__main__":
    main()
