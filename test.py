import xml.etree.ElementTree as ET


def extract_texture_paths(citygml_file):
  # CityGMLファイルを解析
  tree = ET.parse(citygml_file)
  root = tree.getroot()

  # GMLのnamespace (適宜確認して更新する)
  namespaces = {'app': "http://www.opengis.net/citygml/appearance/2.0"}
  texture_paths = set()

  breakpoint()
  # テクスチャファイルのパスを検索
  for image_uri in root.findall(".//app:imageURI", namespaces):
    texture_paths.add(image_uri.text)

  return list(texture_paths)


# CityGMLファイルのパス
citygml_file_path = "/home/ubuntu/gifu/53360690_bldg_6697_op.gml"

# テクスチャファイルのパスを取得
texture_paths = extract_texture_paths(citygml_file_path)

# 結果を表示
print("Found Texture Paths:")
for path in texture_paths:
  print(path)
