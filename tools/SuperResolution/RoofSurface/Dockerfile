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
RUN mkdir -p /app/output

# 必要なファイルをコピー
COPY checkpoint checkpoint
COPY CreateSuperResolution.py requirements.txt .

# 必要なPythonライブラリをインストール
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# 学習済みモデルのダウンロード（ファイルがない場合のみ）
RUN test -f /app/checkpoint/iter_280000_conv.pth || \
    wget 'https://drive.google.com/file/d/1xBFAVgGeIGFsvMN6bG_Y9renLyNm46is/view?usp=drivesdk' \
      -O /app/checkpoint/iter_280000_conv.pth

# 必要なファイルをコピー
COPY tools tools

# 実行ファイルをコピー
COPY process.sh .
