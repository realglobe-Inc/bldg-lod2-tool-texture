# Docker Image のビルドとテスト方法

## 開発環境での docker インストール
- [docker バージョン 23.0.2 以上をインストール](https://docs.docker.com/desktop/install/)
- docker-compose が docker 内部に組み込まれているもの : `docker compose`
- バージョン確認 : `docker --version`

## ビルド方法

```shell
docker compose build
```

## 実行方法

以下では、[テスト用データ](https://drive.google.com/file/d/1UnxBL2MrDZaQ5EF44TXCFc-ZnVbp9Gf6/view)を使うとする。
別のデータを使う場合は適宜置き換えること。

設定ファイルを用意する。

```shell
cat <<EOF > AutoCreateLod2_tutorial/LOD2Creator_tutorial/param.docker.json
{
  "LasCoordinateSystem": 9,
  "DsmFolderPath": "/workspace/dataset/DSM",
  "LasSwapXY": false,
  "CityGMLFolderPath": "/workspace/dataset/CityGML",
  "TextureFolderPath": "/workspace/dataset/RawImage",
  "RotateMatrixMode": 0,
  "ExternalCalibElementPath": "/workspace/dataset/ExCalib/ExCalib.txt",
  "CameraInfoPath": "/workspace/dataset/CamInfo/CamInfo.txt",
  "OutputFolderPath": "/workspace/output",
  "OutputOBJ": true,
  "OutputTexture": true,
  "OutputCityGML": true,
  "OutputLogFolderPath": "/workspace/output",
  "DebugLogOutput": false,
  "PhaseConsistency": {
    "DeleteErrorObject": true,
    "NonPlaneThickness": 0.05,
    "NonPlaneAngle": 15
  }
}
EOF
```

設定内容については[LOD2建築物モデル自動作成ツールの旧操作マニュアル](https://project-plateau.github.io/Auto-Create-bldg-lod2-tool/manual/userManLod2Bldg.html#3-2-%E8%A8%AD%E5%AE%9A%E3%83%91%E3%83%A9%E3%83%A1%E3%83%BC%E3%82%BF%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB)を参照。

環境変数でデータと設定ファイルを指定して実行する。

```
WORKSPACE_DIR=./AutoCreateLod2_tutorial/LOD2Creator_tutorial \
  OUTPUT_DIR=/workspace/output \
  BLDG_LOD2_TOOL_PARAM_FILE=/workspace/param.docker.json \
  docker compose up
```

`WORKSPACE_DIR`にはコンテナ内の /workspace にマウントするディレクトリを指定する。
`WORKSPACE_DIR`以外の環境変数については[process.sh](../../../process.sh)を参照。

最終的な出力は AutoCreateLod2_tutorial/LOD2Creator_tutorial/output/output_result/ に保存される。
