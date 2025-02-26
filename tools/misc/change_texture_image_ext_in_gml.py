import argparse
from pathlib import Path

from lxml import etree


def change(input: str, output: str, ext: str) -> None:
    """
    GMLファイルを解析し、`app:ParameterizedTexture` 要素内の `imageURI` の
    ファイル拡張子を指定されたものに更新し、修正後のXMLを新しいファイルに書き出します。
    この関数は、対象の`app:Appearance`要素内にある`app:surfaceDataMember`要素も更新します。

    :param input: 元のGMLファイルの入力パス。有効なファイルパスである必要があります。
    :type input: str
    :param output: 修正されたGMLファイルを書き出す出力パス。有効なファイルパスである必要があります。
    :type output: str
    :param ext: `imageURI`の古い拡張子を置き換えるための新しいファイル拡張子。
    :type ext: str
    :return: この関数は値を返しません。修正された内容は指定されたファイルに保存されます。
    :rtype: None
    """
    # GMLファイルを解析
    tree = etree.parse(input)
    root = tree.getroot()

    # app:surfaceDataMemberのnamespaceを取得
    namespaces = {'app': 'http://www.opengis.net/citygml/appearance/2.0'}

    # app:Appearance要素を取得
    for appearance in root.findall(".//app:Appearance", namespaces):
        for surface_data_member in appearance.findall("app:surfaceDataMember", namespaces):
            parameterized_texture = surface_data_member.find('app:ParameterizedTexture', namespaces)
            if parameterized_texture is not None:
                image_uri = parameterized_texture.find('app:imageURI', namespaces)
                if image_uri is not None and image_uri.text:
                    image_uri.text = str(Path(image_uri.text).with_suffix(f'.{ext}'))
                mime_type = parameterized_texture.find('app:mimeType', namespaces)
                if mime_type is not None and mime_type.text:
                    mime_type.text = f'image/{ext}'

    # 結果を新しいファイルに保存 (XML宣言を含む)
    tree.write(output, encoding='utf-8', xml_declaration=True, pretty_print=True)


def main():
    # コマンドライン引数の設定
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="Input GML file")
    parser.add_argument("-o", "--output", help="Output GML file")
    parser.add_argument(
        '--ext', type=str, default='png', help='Converted image extension'
    )

    args = parser.parse_args()

    # 実行
    change(args.input, args.output, args.ext)


if __name__ == "__main__":
    main()
