#!/usr/bin/env bash

set -e

if [[ $COMMON == "" ]]
then
    echo "INTERNAL ERROR: \$COMMON is undefined" 1>&2
    exit 1
fi
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"

# Function defined in `common.sh`.
generate_dictionary "pdf.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC=$CC
    export CXX=$CXX
    export CFLAGS="${COVERAGE_FLAGS[*]}"
    export CXXFLAGS="$CFLAGS"
    export LDFLAGS="$CFLAGS"
    export AFL_LLVM_CMPLOG=1

    mkdir build/
    cd build/

    cmake .. \
      -DCMAKE_BUILD_TYPE=debug \
      -DBUILD_SHARED_LIBS=OFF \
      -DENABLE_FUZZER=OFF \
      -DENABLE_GOBJECT_INTROSPECTION=OFF \
      -DENABLE_LIBPNG=OFF \
      -DENABLE_ZLIB=OFF \
      -DENABLE_LIBTIFF=OFF \
      -DENABLE_LIBJPEG=OFF \
      -DENABLE_LIBCURL=OFF \
      -DENABLE_GPGME=OFF \
      -DENABLE_QT6=OFF \
      -DENABLE_QT5=OFF \
      -DENABLE_UTILS=OFF \
      -DENABLE_LIBOPENJPEG=none \
      -DENABLE_LCMS=OFF

    make -j"$(nproc)" poppler poppler-cpp

    IFS=" " read -r -a pkg_config_libs <<< \
        "$(pkg-config --libs freetype2 lcms2 libopenjp2 fontconfig libpng nss libjpeg)"
    LIBS=(
        "./cpp/libpoppler-cpp.a"
        "./libpoppler.a"
        "-ldl"
        "-lm"
        "-lc"
        "-lz"
        "-pthread"
        "-lrt"
        "-lpthread"
        "-ltiff"
        "${pkg_config_libs[@]}"
    )

    $CXX "${COVERAGE_FLAGS[@]}" -std=c++11 -I../cpp -I./cpp -fsanitize=fuzzer \
        ../cpp/tests/fuzzing/pdf_fuzzer.cc -o ../pdf-fuzzer.cmplog \
        "${LIBS[@]}"
popd
