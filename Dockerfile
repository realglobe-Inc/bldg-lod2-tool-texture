FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu24.04

# タイムゾーンの設定
RUN ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime

# 必要なパッケージのインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    nano curl wget zip unzip libopencv-dev jq build-essential \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libffi-dev liblzma-dev git locales bc \
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

# basicsr のパッチ適用 (Python 3.12 / PyTorch 2.x 用)
RUN BASICKSR_DIR=$(python3 -c "import basicsr; import os; print(os.path.dirname(basicsr.__file__))") && \
    sed -i 's/collections.Mapping/collections.abc.Mapping/g' ${BASICKSR_DIR}/data/degradations.py && \
    sed -i 's/collections.Mapping/collections.abc.Mapping/g' ${BASICKSR_DIR}/utils/img_util.py

# 学習済みモデルのダウンロード（LOD2建築物自動作成ツール）
RUN mkdir -p src/create_model/data && \
    wget 'https://github.com/realglobe-Inc/bldg-lod2-tool/releases/download/PretrainedModels-1.0/classifier_parameter.pkl' \
      -O src/create_model/data/classifier_parameter.pkl && \
    wget 'https://github.com/realglobe-Inc/bldg-lod2-tool/releases/download/PretrainedModels-1.0/roof_edge_detection_parameter.pth' \
      -O src/create_model/data/roof_edge_detection_parameter.pth && \
    wget 'https://github.com/realglobe-Inc/bldg-lod2-tool/releases/download/PretrainedModels-1.0/balcony_segmentation_parameter.pkl' \
      -O src/create_model/data/balcony_segmentation_parameter.pkl

# 壁面視認性向上ツール
WORKDIR /app/tools/SuperResolution/WallSurface
COPY tools/SuperResolution/WallSurface/checkpoint checkpoint
RUN test -f checkpoint/latest_net_G_A.pth || \
    wget 'https://github.com/realglobe-Inc/pytorch-CycleGAN-and-pix2pix/releases/download/bldg-lod2-tool-v2.0.0/latest_net_G_A.pth' \
      -O checkpoint/latest_net_G_A.pth

# テクスチャ鮮明化ツール
WORKDIR /app/tools/DeblurGANv2
COPY tools/DeblurGANv2/checkpoints checkpoints
RUN mkdir -p "${HOME}/.cache/torch/hub/checkpoints" && \
    wget 'https://github.com/realglobe-Inc/DeblurGANv2/releases/download/v1.0.0/inceptionresnetv2-520b38e4.pth' \
      -O "${HOME}/.cache/torch/hub/checkpoints/inceptionresnetv2-520b38e4.pth" && \
    wget 'https://github.com/realglobe-Inc/DeblurGANv2/releases/download/v1.0.0/fpn_inception.h5' \
      -O checkpoints/fpn_inception.h5

# テクスチャ解像度向上ツール
WORKDIR /app/tools/Real-ESRGAN
COPY tools/Real-ESRGAN/weights weights
COPY tools/Real-ESRGAN/realesrgan realesrgan
COPY tools/Real-ESRGAN/setup.py .
COPY tools/Real-ESRGAN/VERSION .
COPY tools/Real-ESRGAN/README.md .
COPY tools/Real-ESRGAN/requirements.txt .
RUN python setup.py develop --no-deps && \
    (test -f weights/RealESRGAN_x4plus.pth || \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth \
      -O weights/RealESRGAN_x4plus.pth)

# その他のツール (misc)
WORKDIR /app/tools/misc

########################################################################
########## ビルド速度向上のため、この下は頻繁に変更されるファイルの処理 ##########
########################################################################

WORKDIR /app
COPY src src
COPY run_texture_mapping.py .

WORKDIR /app/tools/SuperResolution/WallSurface
COPY tools/SuperResolution/WallSurface/src src
COPY tools/SuperResolution/WallSurface/cyclegan cyclegan
COPY tools/SuperResolution/WallSurface/main.py .

WORKDIR /app/tools/DeblurGANv2
COPY tools/DeblurGANv2/models models
COPY tools/DeblurGANv2/config config
COPY tools/DeblurGANv2/predict.py .
COPY tools/DeblurGANv2/aug.py .

WORKDIR /app/tools/Real-ESRGAN
COPY tools/Real-ESRGAN/inference_realesrgan.py .

WORKDIR /app/tools/misc
COPY tools/misc/change_texture_image_ext_in_gml.py .
COPY tools/misc/rectify_texture_image.py .

WORKDIR /app
COPY process.sh .
COPY process_*.sh .
