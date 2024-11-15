FROM nvidia/cuda:11.3.1-cudnn8-devel-ubuntu20.04

# タイムゾーンの設定
RUN ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime

# 必要なパッケージのインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nano curl wget zip unzip libopencv-dev jq build-essential \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libffi-dev liblzma-dev git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# pyenv のインストール
ENV PYENV_ROOT="/root/.pyenv"
ENV PATH="${PYENV_ROOT}/bin:${PATH}"
RUN git clone https://github.com/pyenv/pyenv.git "${PYENV_ROOT}" && \
    git clone https://github.com/pyenv/pyenv-virtualenv.git "${PYENV_ROOT}/plugins/pyenv-virtualenv" && \
    echo 'eval "$(pyenv init --path)"' >> ~/.bashrc && \
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# Python 3.9.19 のインストールと設定
RUN eval "$(pyenv init --path)" && \
    pyenv install 3.9.19 && \
    pyenv global 3.9.19 && \
    pyenv rehash

# Python のパス設定
ENV PATH="${PYENV_ROOT}/shims:${PATH}"

# AWS CLIのインストール
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws

# ワーキングディレクトリを設定
WORKDIR /app

# 出力用ディレクトリを作成
RUN mkdir -p ./output

# pip 仮装環境コマンド追加
RUN echo "alias create_env='python -m venv \$(basename \$PWD)'" >> ~/.bashrc && \
    echo "alias activate='source \"\$PWD/\$(basename \$PWD)/bin/activate\"'" >> ~/.bashrc

########## 01-LOD2建築物自動作成ツールのインストール ##########

# LOD2建築物自動作成ツールのフォルダーに移動
RUN mkdir -p /app
WORKDIR /app

# 必要なファイルをコピー
COPY requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    deactivate

# 学習済みモデルのダウンロード（ファイルがない場合のみ）
RUN mkdir -p src/createmodel/data && \
    test -f src/createmodel/data/classifier_parameter.pkl || \
    wget --no-check-certificate 'https://drive.google.com/uc?export=download&id=1hs-DT4Y0ZtjdV9kJ438lvAPpJcfz_dE_' \
      -O src/createmodel/data/classifier_parameter.pkl && \
    test -f src/createmodel/data/roof_edge_detection_parameter.pth || \
    wget --no-check-certificate 'https://drive.google.com/uc?export=download&id=1QqxfS05a4T1_IdrzYle3iuBXjuyqFz-u' \
      -O src/createmodel/data/roof_edge_detection_parameter.pth && \
    test -f src/createmodel/data/balcony_segmentation_parameter.pkl || \
    wget --no-check-certificate 'https://drive.google.com/uc?export=download&id=1MINHffIvcooDOrQq3E4mBvdsgWUfzIi5' \
      -O src/createmodel/data/balcony_segmentation_parameter.pkl



########## 02-壁面視認性向上ツールのインストール ##########

# 壁面視認性向上ツールのフォルダーに移動
RUN mkdir -p /app/tools/SuperResolution/WallSurface
WORKDIR /app/tools/SuperResolution/WallSurface

# 必要なファイルをコピー
COPY tools/SuperResolution/WallSurface/checkpoint checkpoint
COPY tools/SuperResolution/WallSurface/requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    deactivate

# 学習済みモデルのダウンロード（ファイルがない場合のみ）
RUN test -f checkpoint/latest_net_G_A.pth || \
    wget 'https://github.com/realglobe-Inc/pytorch-CycleGAN-and-pix2pix/releases/download/bldg-lod2-tool-v2.0.0/latest_net_G_A.pth' \
      -O checkpoint/latest_net_G_A.pth



########## 03-テクスチャ鮮明化ツールのインストール ##########

# テクスチャ鮮明化ツールのフォルダーに移動
RUN mkdir -p /app/tools/DeblurGANv2
WORKDIR /app/tools/DeblurGANv2

# 必要なファイルをコピー
COPY tools/DeblurGANv2/checkpoints checkpoints
COPY tools/DeblurGANv2/requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    deactivate

# 学習済みモデルのダウンロード（ファイルがない場合のみ）
RUN mkdir -p ~/.cache/torch/hub/checkpoints && \
    test -f ~/.cache/torch/hub/checkpoints/inceptionresnetv2-520b38e4.pth || \
    wget --no-check-certificate 'https://github.com/realglobe-Inc/DeblurGANv2/releases/download/v1.0.0/inceptionresnetv2-520b38e4.pth' \
      -O ~/.cache/torch/hub/checkpoints/inceptionresnetv2-520b38e4.pth && \
    test -f checkpoints/fpn_inception.h5 || \
    wget --no-check-certificate 'https://drive.google.com/uc?export=view&id=1UXcsRVW-6KF23_TNzxw-xC0SzaMfXOaR' \
      -O checkpoints/fpn_inception.h5



########## 04-テクスチャシャープ化ツールのインストール ##########

# テクスチャシャープ化ツールのフォルダーに移動
RUN mkdir -p /app/tools/UnsharpMask
WORKDIR /app/tools/UnsharpMask

# 必要なファイルをコピー
COPY tools/UnsharpMask/UnsharpMask.py .
COPY tools/UnsharpMask/requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    deactivate



########## 05-テクスチャ解像度向上ツールのインストール ##########

# テクスチャ解像度向上ツールのフォルダーに移動
RUN mkdir -p /app/tools/Real-ESRGAN
WORKDIR /app/tools/Real-ESRGAN

# 必要なファイルをコピー
COPY tools/Real-ESRGAN/weights weights
COPY tools/Real-ESRGAN/realesrgan realesrgan
COPY tools/Real-ESRGAN/setup.py .
COPY tools/Real-ESRGAN/VERSION .
COPY tools/Real-ESRGAN/README.md .
COPY tools/Real-ESRGAN/requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    python3 setup.py develop && \
    deactivate

# 学習済みモデルのダウンロード（ファイルがない場合のみ）
RUN test weights/RealESRGAN_x2plus.pth || \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x2plus.pth \
      -O weights/RealESRGAN_x2plus.pth



########## 06-アトラス化ツールのインストール ##########

# アトラス化ツールのフォルダーに移動
RUN mkdir -p /app/tools/Atlas_Prot
WORKDIR /app/tools/Atlas_Prot

# 必要なファイルをコピー
COPY tools/Atlas_Prot/Atlas_Prot.py .
COPY tools/Atlas_Prot/requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m venv $(basename $PWD) && \
    . $(basename $PWD)/bin/activate && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    deactivate



########################################################################
########## ビルド速度向上のため、この下は頻繁に変更されるファイルの処理 ##########
########################################################################



########## 01-LOD2建築物自動作成ツールの頻繁に変更されるファイル ##########

# LOD2建築物自動作成ツールのフォルダーに移動
WORKDIR /app

# 必要なファイルをコピー
COPY requirements.txt .

# 必要なファイルをコピー
COPY src src
COPY AutoCreateLod2.py .



########## 02-壁面視認性向上ツールの頻繁に変更されるファイル ##########

# 壁面視認性向上ツールのフォルダーに移動
WORKDIR /app/tools/SuperResolution/WallSurface

# 必要なファイルをコピー
COPY tools/SuperResolution/WallSurface/src src
COPY tools/SuperResolution/WallSurface/cyclegan cyclegan
COPY tools/SuperResolution/WallSurface/main.py .



########## 03-テクスチャ鮮明化ツールの頻繁に変更されるファイル ##########

# テクスチャ鮮明化ツールのフォルダーに移動
WORKDIR /app/tools/DeblurGANv2

# 必要なファイルをコピー
COPY tools/DeblurGANv2/models models
COPY tools/DeblurGANv2/config config
COPY tools/DeblurGANv2/predict.py .
COPY tools/DeblurGANv2/aug.py .



########## 04-テクスチャシャープ化ツールの頻繁に変更されるファイル ##########

# テクスチャシャープ化ツールのフォルダーに移動
WORKDIR /app/tools/UnsharpMask



########## 05-テクスチャ解像度向上ツールの頻繁に変更されるファイル ##########

# テクスチャ解像度向上ツールのフォルダーに移動
WORKDIR /app/tools/Real-ESRGAN

# 必要なファイルをコピー
COPY tools/Real-ESRGAN/inference_realesrgan.py .



########## 06-アトラス化ツールの頻繁に変更されるファイル ##########

# アトラス化ツールのフォルダーに移動
WORKDIR /app/tools/Atlas_Prot

# 必要なファイルをコピー
COPY tools/Atlas_Prot/src src



########## 実行関連設定 ##########

# デフォルト実行パス
WORKDIR /app

# 実行ファイルをコピー
COPY process.sh .
