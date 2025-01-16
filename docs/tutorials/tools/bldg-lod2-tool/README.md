# LOD2建築物自動作成ツールの実行フロー
- [CityGMLの建築物モデル生成](#CityGMLの建築物モデル生成)
- [生成したモデルの位相一貫性検査と補正](#生成したモデルの位相一貫性検査と補正)
- [生成したモデルにテクスチャー貼り付け](#生成したモデルにテクスチャー貼り付け)

```mermaid
flowchart TB
  node_1["全てのCityGML読み込み"]
  node_2[/"loop start : CityGMLファイル毎処理開始"\]
  node_3["CityGMLの全ての建築物読み込み"]
  node_4[["CityGMLの建築物モデル生成"]]
  node_5[["生成したモデルの位相一貫性検査と補正"]]
  node_6[["生成したモデルにテクスチャー貼り付け"]]
  node_7[\"loop end : CityGMLファイルの処理終了"/]

  node_1 --> node_2
  node_2 --> node_3
  node_3 --> node_4
  node_4 --> node_5
  node_5 --> node_6
  node_6 --> node_7
```

### CityGMLの建築物モデル生成
- [BuildingModelBuilder-陸屋根のモデルを生成](./flat-model/README.md)
- [HouseModelBuilder-非陸屋根のモデルを生成](./non-flat-model/README.md)

```mermaid
flowchart TB
  node_2[/"loop start : CityGMLの建築物毎にモデル作成開始"\]
  node_3["CityGMLの建築物LOD0から建物の外周ポリゴン情報を取得"]
  node_4{"DSMキャッシュファイルが存在？"}
  node_5{"デバッグモード？"}
  node_6["キャッシュファイルから点群の情報を読み込む"]
  node_7["DSMフィルから点群の情報を読み込む"]
  node_8{"デバッグモード？"}
  node_9["読み込んだ点群情報をDSMキャッシュファイルに保存"]
  node_10["建物分類結果をキャッシュファイルから読み込む"]
  node_11{"建物分類結果の<br />キャッシュ情報がない？"}
  node_12["建物分類を開始"]
  node_13{"デバッグモード？"}
  node_14["建物分類結果をキャッシュファイルに保存"]
  node_15{"建物分類が陸屋根？"}
  node_16[["BuildingModelBuilder-陸屋根のモデルを生成"]]
  node_17[["HouseModelBuilder-非陸屋根のモデルを生成"]]
  node_18[\"loop end : CityGMLの建築物のモデル作成終了"/]

  node_2 --> node_3
  node_3 --> node_4
  node_4 --"True"--> node_5
  node_4 --"False"--> node_7
  node_5 --"True"--> node_6
  node_5 --"False"--> node_7
  node_7 --> node_8
  node_8 --"True"--> node_9
  node_9 --> node_10
  node_6 --> node_10
  node_10 --> node_11
  node_11 --"True"--> node_12
  node_12 --> node_13
  node_13 --"True"--> node_14
  node_11 --"True"--> node_15
  node_14 --> node_15
  node_13 --"False"--> node_15
  node_15 --"True"--> node_16
  node_15 --"False"--> node_17
  node_16 --> node_18
  node_17 --> node_18
```

### 生成したモデルの位相一貫性検査と補正

```mermaid
```


### 生成したモデルにテクスチャー貼り付け

```mermaid
```
