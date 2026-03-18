FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04

# タイムゾーンの設定
RUN ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime

# 必要なパッケージのインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nano curl wget zip unzip libopencv-dev libgdal-dev jq build-essential \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libffi-dev liblzma-dev git locales bc \
    gdal-bin imagemagick \
    python3 python3-pip python3-venv python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8 ja_JP.UTF-8
RUN update-locale LANG=en_US.UTF-8

ENV HOME="/root"

# venv を作成してパスを通す
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# 統合 requirements.txt のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 学習済みモデルのダウンロード
RUN mkdir -p model && \
    wget 'https://github.com/realglobe-Inc/pytorch-CycleGAN-and-pix2pix/releases/download/bldg-lod2-tool-v2.0.0/latest_net_G_A.pth' \
      -O model/latest_net_G_A.pth && \
    wget 'https://github.com/realglobe-Inc/DeblurGANv2/releases/download/v1.0.0/fpn_inception.h5' \
      -O model/fpn_inception.h5 && \
    wget 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth' \
      -O model/RealESRGAN_x4plus.pth

########################################################################
########## ビルド速度向上のため、この下は頻繁に変更されるファイルの処理 ##########
########################################################################

WORKDIR /app
COPY src src

WORKDIR /app
COPY process.sh .
COPY process_*.sh .
