# Docker Image のビルドとテスト方法

## 開発環境での docker インストール
- [docker バージョン 23.0.2 以上をインストール](https://docs.docker.com/desktop/install/)
- docker-compose が docker 内部に組み込まれているもの : `docker compose`
- バージョン確認 : `docker --version`

## 実行準 / ビルドイメージ名 / ビルド方法
- まず、ベースイメージを pull
  ```
  docker pull nvidia/cuda:11.3.1-cudnn8-devel-ubuntu20.04
  ```
- その後ビルド
  ```
  docker compose build
  ```

## インプット/アウトプットのデーターのI/Fは [docker-compose.yml](../../../docker-compose.yml) を参照

## docker-compose.yml 設定

### インプットフォルダーのパス変更
- [docker-compose.yml](../../../docker-compose.yml) の `~/lod2_data/kawazaki` を入力データーのあるフォルダーのパスに変更

### 入力データーのフォルダーの中のフォルダー名変更
- `~/lod2_data/kawazaki` の中には以下のデーターが必要
  |フォルダー名|[パラメター名](../setup-linux/README.md#必須パラメーター)|
  |-|-|
  |01_原画像|TextureFolderPath|
  |02_外部標定要素|ExternalCalibElementPath|
  |03_内部標定要素|CameraInfoPath|
  |04_DSM_RGB|DsmFolderPath|
  |08_CityGML|CityGMLFolderPath|

## docker compose exec で順番に docker で実行
```
docker compose up -d # バックグラウンドで実行
docker compose exec 3d-model bash -c "/app/process.sh"
```

## その他 docker compose で使えるコマンド
```
docker compose down # バックグラウンド終了
docker compose ps # 稼働中のコンテナ確認
docker compose exec 3d-model bash # コンテナ内部へアクセス
```
