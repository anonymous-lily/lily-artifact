FROM rosa:0.6.0-alpha22
# TODO: remove this to enable ROSA's documentation server.
CMD ["bash"]

LABEL maintainer="anonymous@example.com"

RUN apt-get update && apt-get install -y autoconf automake libtool libsqlite3-dev make re2c tcl \
    zlib1g-dev autogen build-essential libasound2-dev libflac-dev libogg-dev libvorbis-dev \
    libopus-dev libmp3lame-dev libmpg123-dev pkg-config python3 libreadline-dev rcs tcl-dev tk-dev \
    libnss3-dev libboost-dev liblcms2-dev libopenjp2-7-dev parallel zip libcap-dev

# For running Python scripts with dependencies.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin/:$PATH"

# For debugging purposes.
RUN apt-get update && apt-get install -y htop tmux neovim

WORKDIR /root
COPY . ./artifact

RUN /root/artifact/tools/startup/startup.sh
ENV COLORTERM=truecolor
ENV PACKAGE_EXPERIMENT=1

WORKDIR /root/artifact
